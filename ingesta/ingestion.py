"""
Media ingestion module for copying files with verification.

Provides Shotput Pro-style offloading with checksum verification.
"""

import shutil
import logging
from pathlib import Path
from typing import Union, List, Optional, Callable, Dict
from dataclasses import dataclass, field
from datetime import datetime
import json

from .checksum import calculate_checksum, verify_checksum


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
    progress_callback: Optional[Callable[[str, int, int], None]] = None
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
        progress_callback: Callback(filename, total_files, current_file)
    
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
    
    # Copy files to each destination
    for dest_idx, destination in enumerate(destinations):
        logging.info(f"Copying to destination {dest_idx + 1}/{len(destinations)}: {destination}")
        
        for file_idx, file_path in enumerate(files_to_copy):
            if progress_callback:
                progress_callback(file_path.name, total_files, file_idx + 1)
            
            # Calculate relative path for destination
            if source.is_file():
                relative_path = file_path.name
            else:
                relative_path = file_path.relative_to(source)
            
            dest_path = destination / relative_path
            
            logging.info(f"Copying {relative_path}...")
            
            # Copy file
            result = copy_file_with_checksum(file_path, dest_path, checksum_algorithm)
            
            # Verify if requested
            if verify and result.success:
                logging.info(f"Verifying {relative_path}...")
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
    
    # Log summary
    duration = (job.end_time - job.start_time).total_seconds()
    logging.info(f"Ingestion complete: {job.success_count}/{len(files_to_copy)} files successful")
    logging.info(f"Duration: {duration:.2f}s")
    logging.info(f"Total bytes: {job.total_bytes:,}")
    
    return job
