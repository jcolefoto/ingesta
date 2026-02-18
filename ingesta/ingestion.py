"""
Media ingestion module for copying files with verification.

Provides Shotput Pro-style offloading with checksum verification.
"""

import shutil
import logging
from pathlib import Path
from typing import Union, List, Optional, Callable, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json
import sys

from .checksum import calculate_checksum, verify_checksum


class IngestionStage(Enum):
    """Stages of the ingestion process."""
    SCANNING = "scanning"
    COPYING = "copying"
    VERIFYING = "verifying"
    COMPLETE = "complete"


@dataclass
class ProgressEvent:
    """Structured progress event for ingestion operations.
    
    Fields:
        stage: Current stage (scanning, copying, verifying, complete)
        source_file: Current source file being processed (or None if between files)
        current_file_index: Index of current file (0-based)
        total_source_files: Total number of source files
        current_destination_index: Index of current destination (0-based)
        total_destinations: Total number of destinations
        bytes_copied: Bytes copied for current file
        total_bytes: Total bytes for current file
        current_speed_mb_s: Current copy speed in MB/s (or None)
        eta_seconds: Estimated seconds remaining (or None)
    """
    stage: IngestionStage
    source_file: Optional[Path] = None
    current_file_index: int = 0
    total_source_files: int = 0
    current_destination_index: int = 0
    total_destinations: int = 0
    bytes_copied: int = 0
    total_bytes: int = 0
    current_speed_mb_s: Optional[float] = None
    eta_seconds: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stage": self.stage.value,
            "source_file": str(self.source_file) if self.source_file else None,
            "current_file_index": self.current_file_index,
            "total_source_files": self.total_source_files,
            "current_destination_index": self.current_destination_index,
            "total_destinations": self.total_destinations,
            "bytes_copied": self.bytes_copied,
            "total_bytes": self.total_bytes,
            "current_speed_mb_s": self.current_speed_mb_s,
            "eta_seconds": self.eta_seconds,
        }


@dataclass
class IngestionCompletion:
    """Structured completion result for ingestion operations.
    
    Fields:
        source_file_count: Number of source files
        destination_count: Number of destinations
        total_operations: Total copy operations (files × destinations)
        successful_operations: Number of successful copy operations
        failed_operations: Number of failed copy operations
        safe_to_format: Whether source is safe to format
        duration_seconds: Total duration in seconds
        total_bytes: Total bytes copied successfully
        checksum_algorithm: Algorithm used for verification
        files: List of file results
    """
    source_file_count: int
    destination_count: int
    total_operations: int
    successful_operations: int
    failed_operations: int
    safe_to_format: bool
    duration_seconds: float
    total_bytes: int
    checksum_algorithm: str
    files: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class FileResult:
    """Result of a single file copy operation."""
    source_path: Path
    dest_path: Path
    success: bool
    checksum: Optional[str] = None
    verified: bool = False
    error_message: Optional[str] = None
    file_size: int = 0
    copy_time: float = 0.0
    copy_speed_mbps: Optional[float] = None  # Copy speed in MB/s


@dataclass
class IngestionJob:
    """Represents a complete ingestion job."""
    source: Path
    destinations: List[Path]
    checksum_algorithm: str = "xxhash64"
    verify: bool = True
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    log_file: Optional[Path] = None

    # Results
    files_processed: List[FileResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def get_completion(self) -> IngestionCompletion:
        """Get structured completion result."""
        duration = 0.0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        source_files = set()
        for result in self.files_processed:
            source_files.add(result.source_path)

        successful = sum(1 for f in self.files_processed if f.success)
        failed = len(self.files_processed) - successful

        files_list = []
        for f in self.files_processed:
            files_list.append({
                "source": str(f.source_path),
                "destination": str(f.dest_path),
                "success": f.success,
                "verified": f.verified,
                "size_bytes": f.file_size,
                "checksum": f.checksum,
                "error": f.error_message,
            })

        return IngestionCompletion(
            source_file_count=len(source_files),
            destination_count=len(self.destinations),
            total_operations=len(self.files_processed),
            successful_operations=successful,
            failed_operations=failed,
            safe_to_format=self.is_safe_to_format,
            duration_seconds=duration,
            total_bytes=self.total_bytes,
            checksum_algorithm=self.checksum_algorithm,
            files=files_list
        )
    
    def __post_init__(self):
        self.source = Path(self.source)
        self.destinations = [Path(d) for d in self.destinations]
        if self.log_file:
            self.log_file = Path(self.log_file)
    
    @property
    def success_count(self) -> int:
        return sum(1 for f in self.files_processed if f.success)
    
    @property
    def failure_count(self) -> int:
        return sum(1 for f in self.files_processed if not f.success)
    
    @property
    def total_bytes(self) -> int:
        return sum(f.file_size for f in self.files_processed if f.success)
    
    @property
    def avg_copy_speed_mbps(self) -> Optional[float]:
        """Calculate average copy speed across all files."""
        speeds = [f.copy_speed_mbps for f in self.files_processed 
                  if f.success and f.copy_speed_mbps]
        if speeds:
            return sum(speeds) / len(speeds)
        return None
    
    @property
    def min_copy_speed_mbps(self) -> Optional[float]:
        """Get minimum copy speed."""
        speeds = [f.copy_speed_mbps for f in self.files_processed 
                  if f.success and f.copy_speed_mbps]
        if speeds:
            return min(speeds)
        return None
    
    @property
    def max_copy_speed_mbps(self) -> Optional[float]:
        """Get maximum copy speed."""
        speeds = [f.copy_speed_mbps for f in self.files_processed 
                  if f.success and f.copy_speed_mbps]
        if speeds:
            return max(speeds)
        return None
    
    @property
    def is_safe_to_format(self) -> bool:
        """
        Determine if the source media is safe to format.
        
        Returns True only if:
        - All files were copied successfully
        - All files passed checksum verification
        - No failures occurred
        """
        if not self.files_processed:
            return False
        
        # Check if all files succeeded and were verified
        for result in self.files_processed:
            if not result.success:
                return False
            if self.verify and not result.verified:
                return False
        
        return True
    
    @property
    def safe_to_format_status(self) -> dict:
        """
        Get detailed safe to format status with reasons.
        
        Returns dict with:
        - safe: bool - Whether safe to format
        - badge: str - Badge text for display
        - reason: str - Explanation
        - verified_count: int - Number of verified files
        - failed_count: int - Number of failed files
        """
        total = len(self.files_processed)
        verified = sum(1 for f in self.files_processed if f.verified)
        failed = sum(1 for f in self.files_processed if not f.success)
        
        if self.is_safe_to_format:
            return {
                'safe': True,
                'badge': '✓ SAFE TO FORMAT',
                'reason': f'All {total} files successfully copied and verified with {self.checksum_algorithm}',
                'verified_count': verified,
                'failed_count': failed,
            }
        elif failed > 0:
            return {
                'safe': False,
                'badge': '✗ DO NOT FORMAT',
                'reason': f'{failed} file(s) failed to copy or verify',
                'verified_count': verified,
                'failed_count': failed,
            }
        elif self.verify and verified < total:
            return {
                'safe': False,
                'badge': '⚠ DO NOT FORMAT',
                'reason': f'Only {verified}/{total} files verified',
                'verified_count': verified,
                'failed_count': failed,
            }
        else:
            return {
                'safe': False,
                'badge': '✗ DO NOT FORMAT',
                'reason': 'Verification not completed',
                'verified_count': verified,
                'failed_count': failed,
            }
    
    def to_dict(self) -> Dict:
        """Convert job to dictionary for serialization."""
        return {
            "source": str(self.source),
            "destinations": [str(d) for d in self.destinations],
            "checksum_algorithm": self.checksum_algorithm,
            "verify": self.verify,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "files_processed": [
                {
                    "source": str(f.source_path),
                    "destination": str(f.dest_path),
                    "success": f.success,
                    "checksum": f.checksum,
                    "verified": f.verified,
                    "error": f.error_message,
                    "size": f.file_size,
                    "time": f.copy_time,
                }
                for f in self.files_processed
            ],
            "summary": {
                "total_files": len(self.files_processed),
                "successful": self.success_count,
                "failed": self.failure_count,
                "total_bytes": self.total_bytes,
            }
        }
    
    def save_report(self, output_path: Union[str, Path]):
        """Save job report to JSON file."""
        output_path = Path(output_path)
        with open(output_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


def should_copy_file(file_path: Path, include_patterns: List[str], exclude_patterns: List[str]) -> bool:
    """
    Determine if a file should be copied based on include/exclude patterns.
    
    Args:
        file_path: Path to file
        include_patterns: List of glob patterns to include (empty = all)
        exclude_patterns: List of glob patterns to exclude
    
    Returns:
        True if file should be copied
    """
    # Check excludes first
    for pattern in exclude_patterns:
        if file_path.match(pattern):
            return False
    
    # If includes specified, file must match at least one
    if include_patterns:
        for pattern in include_patterns:
            if file_path.match(pattern):
                return True
        return False
    
    return True


def copy_file_with_checksum(
    source: Path,
    destination: Path,
    algorithm: str = "xxhash64",
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> FileResult:
    """
    Copy a file and calculate checksum during copy.
    
    Args:
        source: Source file path
        destination: Destination file path
        algorithm: Checksum algorithm
        progress_callback: Optional callback(total, processed)
    
    Returns:
        FileResult with details of the operation
    """
    import time
    
    result = FileResult(
        source_path=source,
        dest_path=destination,
        success=False,
        file_size=source.stat().st_size
    )
    
    start_time = time.time()
    
    try:
        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file with checksum calculation
        from .checksum import calculate_checksum
        
        # For streaming checksum during copy, we need to calculate it manually
        import hashlib
        try:
            import xxhash
            XXHASH_AVAILABLE = True
        except ImportError:
            XXHASH_AVAILABLE = False
        
        algorithm = algorithm.lower()
        if algorithm == "xxhash64":
            if not XXHASH_AVAILABLE:
                raise ImportError("xxhash library not installed")
            hash_obj = xxhash.xxh64()
        elif algorithm == "xxhash32":
            if not XXHASH_AVAILABLE:
                raise ImportError("xxhash library not installed")
            hash_obj = xxhash.xxh32()
        elif algorithm == "md5":
            hash_obj = hashlib.md5()
        elif algorithm == "sha256":
            hash_obj = hashlib.sha256()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        
        total_size = source.stat().st_size
        copied = 0
        
        with open(source, "rb") as src_file:
            with open(destination, "wb") as dst_file:
                while chunk := src_file.read(65536):
                    hash_obj.update(chunk)
                    dst_file.write(chunk)
                    copied += len(chunk)
                    
                    if progress_callback:
                        progress_callback(total_size, copied)
        
        result.checksum = hash_obj.hexdigest()
        result.success = True
        result.copy_time = time.time() - start_time
        
        # Calculate copy speed
        if result.copy_time > 0:
            result.copy_speed_mbps = (result.file_size / result.copy_time) / (1024 * 1024)
        
    except Exception as e:
        result.error_message = str(e)
        logging.error(f"Error copying {source}: {e}")
    
    return result


def verify_file_copy(
    source: Path,
    destination: Path,
    expected_checksum: Optional[str],
    algorithm: str = "xxhash64",
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> bool:
    """
    Verify a copied file matches the expected checksum.
    
    Args:
        source: Source file path (for reference)
        destination: Destination file path to verify
        expected_checksum: Expected checksum value
        algorithm: Checksum algorithm
        progress_callback: Optional callback
    
    Returns:
        True if verification passes
    """
    if not destination.exists():
        logging.error(f"Destination file not found: {destination}")
        return False
    
    actual_checksum = calculate_checksum(destination, algorithm, chunk_size=65536)
    
    return actual_checksum.lower() == expected_checksum.lower()


def ingest_media(
    source: Union[str, Path],
    destinations: Union[str, Path, List[Union[str, Path]]],
    checksum_algorithm: str = "xxhash64",
    verify: bool = True,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    log_file: Optional[Union[str, Path]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    progress_event_callback: Optional[Callable[[ProgressEvent], None]] = None,
    no_progress: bool = False
) -> IngestionJob:
    """
    Ingest media from source to one or more destinations.

    Args:
        source: Source directory or file
        destinations: One or more destination paths
        checksum_algorithm: 'md5' or 'sha256'
        verify: Whether to verify copies
        include_patterns: File patterns to include (e.g., ['*.mov', '*.mp4'])
        exclude_patterns: File patterns to exclude
        log_file: Path to log file
        progress_callback: Legacy callback(filename, total_files, current_file)
        progress_event_callback: Structured progress event callback
        no_progress: Disable progress output (auto-detected for non-TTY)

    Returns:
        IngestionJob with results
    """
    # Normalize inputs
    source = Path(source)
    if isinstance(destinations, (str, Path)):
        destinations = [destinations]
    destinations = [Path(d) for d in destinations]
    
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []
    
    # Setup logging
    if log_file:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    job = IngestionJob(
        source=source,
        destinations=destinations,
        checksum_algorithm=checksum_algorithm,
        verify=verify,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        log_file=Path(log_file) if log_file else None
    )
    
    job.start_time = datetime.now()

    logging.info(f"Starting ingestion from {source}")
    logging.info(f"Destinations: {destinations}")

    # Emit scanning event
    if progress_event_callback:
        progress_event_callback(ProgressEvent(
            stage=IngestionStage.SCANNING,
            total_destinations=len(destinations)
        ))

    # Collect files to copy
    if source.is_file():
        files_to_copy = [source]
    else:
        files_to_copy = [
            f for f in source.rglob("*")
            if f.is_file() and should_copy_file(f.relative_to(source), include_patterns, exclude_patterns)
        ]

    total_files = len(files_to_copy)
    logging.info(f"Found {total_files} files to copy")

    # Calculate total bytes for ETA
    total_bytes_all = sum(f.stat().st_size for f in files_to_copy)
    bytes_copied_total = 0

    # Copy files to each destination
    for dest_idx, destination in enumerate(destinations):
        logging.info(f"Copying to destination {dest_idx + 1}/{len(destinations)}: {destination}")

        for file_idx, file_path in enumerate(files_to_copy):
            file_size = file_path.stat().st_size

            # Legacy callback
            if progress_callback:
                progress_callback(file_path.name, total_files, file_idx + 1)

            # Calculate relative path for destination
            if source.is_file():
                relative_path = file_path.name
            else:
                relative_path = file_path.relative_to(source)

            dest_path = destination / relative_path

            logging.info(f"Copying {relative_path}...")

            # Emit copying event
            if progress_event_callback:
                progress_event_callback(ProgressEvent(
                    stage=IngestionStage.COPYING,
                    source_file=file_path,
                    current_file_index=file_idx,
                    total_source_files=total_files,
                    current_destination_index=dest_idx,
                    total_destinations=len(destinations),
                    bytes_copied=0,
                    total_bytes=file_size
                ))

            # Copy file with progress tracking
            copy_start_time = None
            def copy_progress_callback(total: int, processed: int):
                if progress_event_callback:
                    nonlocal copy_start_time
                    if copy_start_time is None:
                        copy_start_time = datetime.now()

                    # Calculate speed and ETA
                    speed_mbps = None
                    eta = None
                    elapsed = (datetime.now() - copy_start_time).total_seconds()
                    if elapsed > 0:
                        speed_mbps = (processed / elapsed) / (1024 * 1024)
                    if speed_mbps and speed_mbps > 0:
                        remaining_bytes = total_bytes_all - bytes_copied_total - processed
                        eta = remaining_bytes / (speed_mbps * 1024 * 1024)

                    progress_event_callback(ProgressEvent(
                        stage=IngestionStage.COPYING,
                        source_file=file_path,
                        current_file_index=file_idx,
                        total_source_files=total_files,
                        current_destination_index=dest_idx,
                        total_destinations=len(destinations),
                        bytes_copied=processed,
                        total_bytes=file_size,
                        current_speed_mb_s=speed_mbps,
                        eta_seconds=eta
                    ))

            result = copy_file_with_checksum(
                file_path, dest_path, checksum_algorithm,
                progress_callback=copy_progress_callback if progress_event_callback else None
            )

            bytes_copied_total += file_size if result.success else 0

            # Verify if requested
            if verify and result.success:
                logging.info(f"Verifying {relative_path}...")

                # Emit verifying event
                if progress_event_callback:
                    progress_event_callback(ProgressEvent(
                        stage=IngestionStage.VERIFYING,
                        source_file=file_path,
                        current_file_index=file_idx,
                        total_source_files=total_files,
                        current_destination_index=dest_idx,
                        total_destinations=len(destinations),
                        bytes_copied=file_size,
                        total_bytes=file_size
                    ))

                result.verified = verify_file_copy(
                    file_path, dest_path, result.checksum, checksum_algorithm
                )

                if result.verified:
                    logging.info(f"Verification passed for {relative_path}")
                else:
                    logging.error(f"Verification FAILED for {relative_path}")
                    result.success = False
                    result.error_message = "Checksum verification failed"

            job.files_processed.append(result)

    job.end_time = datetime.now()

    # Emit completion event
    if progress_event_callback:
        progress_event_callback(ProgressEvent(
            stage=IngestionStage.COMPLETE,
            total_source_files=total_files,
            total_destinations=len(destinations)
        ))

    # Log summary
    duration = (job.end_time - job.start_time).total_seconds()
    logging.info(f"Ingestion complete: {job.success_count}/{len(files_to_copy)} files successful")
    logging.info(f"Duration: {duration:.2f}s")
    logging.info(f"Total bytes: {job.total_bytes:,}")

    return job
