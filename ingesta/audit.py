"""
Audit logging module for ingesta.

Provides chain-of-custody tracking for all media operations:
- File checksums (xxhash64, MD5, SHA256) at each step
- Immutable timestamps for all operations
- User and system information
- Complete chain-of-custody report

Features:
- Tamper-evident logging with hash chains
- JSON and human-readable text output
- Verification of chain integrity
- Export for legal/professional compliance

All logging is done locally - no external services.
"""

import json
import hashlib
import logging
import getpass
import platform
from pathlib import Path
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from .checksum import calculate_checksum


logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of auditable events."""
    INGEST_START = "ingest_start"
    INGEST_COMPLETE = "ingest_complete"
    FILE_COPY = "file_copy"
    FILE_VERIFY = "file_verify"
    CHECKSUM_CALCULATE = "checksum_calculate"
    CHECKSUM_VERIFY = "checksum_verify"
    PROJECT_CREATE = "project_create"
    SHOOT_DAY_CREATE = "shoot_day_create"
    SESSION_CREATE = "session_create"
    REPORT_GENERATE = "report_generate"
    PROXY_GENERATE = "proxy_generate"
    TRANSCRIPT_GENERATE = "transcript_generate"
    EXPORT_CREATE = "export_create"
    DELIVERABLE_CREATE = "deliverable_create"
    USER_ACTION = "user_action"


class AuditLogLevel(Enum):
    """Audit log importance levels."""
    CRITICAL = "critical"  # Chain-of-custody events
    HIGH = "high"          # Important operations
    NORMAL = "normal"      # Standard operations
    LOW = "low"            # Verbose logging


@dataclass
class FileAuditRecord:
    """Record of a file operation with checksums."""
    file_path: str
    file_size_bytes: int
    checksum_algorithm: str
    checksum_value: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AuditEntry:
    """
    Single audit log entry.
    
    Immutable record of an operation with full chain-of-custody data.
    """
    entry_id: str
    timestamp: str
    event_type: str
    event_description: str
    
    # File records (source and destination)
    source_file: Optional[FileAuditRecord] = None
    destination_file: Optional[FileAuditRecord] = None
    
    # Context
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    user: str = field(default_factory=getpass.getuser)
    hostname: str = field(default_factory=platform.node)
    working_directory: str = field(default_factory=lambda: str(Path.cwd()))
    
    # Verification
    verification_status: Optional[str] = None  # 'passed', 'failed', 'pending'
    verification_notes: Optional[str] = None
    
    # Chain integrity (for tamper detection)
    previous_entry_hash: Optional[str] = None
    entry_hash: Optional[str] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def calculate_hash(self) -> str:
        """Calculate hash of this entry for chain integrity."""
        # Create deterministic string representation
        data = {
            'entry_id': self.entry_id,
            'timestamp': self.timestamp,
            'event_type': self.event_type,
            'event_description': self.event_description,
            'source_file': self.source_file.to_dict() if self.source_file else None,
            'destination_file': self.destination_file.to_dict() if self.destination_file else None,
            'previous_entry_hash': self.previous_entry_hash,
        }
        
        # Calculate hash
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        result = asdict(self)
        # Convert nested dataclasses
        if self.source_file:
            result['source_file'] = self.source_file.to_dict()
        if self.destination_file:
            result['destination_file'] = self.destination_file.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AuditEntry':
        """Create from dictionary."""
        # Reconstruct file records
        source_file = None
        if data.get('source_file'):
            source_file = FileAuditRecord(**data['source_file'])
        
        dest_file = None
        if data.get('destination_file'):
            dest_file = FileAuditRecord(**data['destination_file'])
        
        return cls(
            entry_id=data['entry_id'],
            timestamp=data['timestamp'],
            event_type=data['event_type'],
            event_description=data['event_description'],
            source_file=source_file,
            destination_file=dest_file,
            project_id=data.get('project_id'),
            session_id=data.get('session_id'),
            user=data.get('user', 'unknown'),
            hostname=data.get('hostname', 'unknown'),
            working_directory=data.get('working_directory', ''),
            verification_status=data.get('verification_status'),
            verification_notes=data.get('verification_notes'),
            previous_entry_hash=data.get('previous_entry_hash'),
            entry_hash=data.get('entry_hash'),
            metadata=data.get('metadata', {}),
        )


class AuditLogger:
    """
    Chain-of-custody audit logger.
    
    Provides tamper-evident logging with hash chains for legal/professional
    compliance. Every entry links to the previous entry's hash.
    """
    
    DEFAULT_LOG_DIR = Path.home() / ".ingesta" / "audit"
    
    def __init__(self, log_dir: Optional[Path] = None, project_id: Optional[str] = None):
        self.log_dir = log_dir or self.DEFAULT_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.project_id = project_id
        self.entries: List[AuditEntry] = []
        self._entry_counter = 0
        
        # Load existing log if available
        if project_id:
            self._load_existing_log()
    
    def _get_log_path(self) -> Path:
        """Get the log file path for this project."""
        if self.project_id:
            return self.log_dir / f"audit_{self.project_id}.json"
        else:
            # Global log
            return self.log_dir / "audit_global.json"
    
    def _load_existing_log(self):
        """Load existing audit log if present."""
        log_path = self._get_log_path()
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    data = json.load(f)
                
                self.entries = [AuditEntry.from_dict(e) for e in data.get('entries', [])]
                self._entry_counter = len(self.entries)
                
                logger.info(f"Loaded {len(self.entries)} existing audit entries")
            except Exception as e:
                logger.error(f"Failed to load existing audit log: {e}")
                self.entries = []
    
    def _get_next_entry_id(self) -> str:
        """Generate next entry ID."""
        self._entry_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{timestamp}_{self._entry_counter:06d}"
    
    def _get_previous_hash(self) -> Optional[str]:
        """Get hash of previous entry."""
        if self.entries:
            return self.entries[-1].entry_hash
        return None
    
    def log_event(
        self,
        event_type: AuditEventType,
        description: str,
        source_path: Optional[Path] = None,
        dest_path: Optional[Path] = None,
        checksum_algorithm: str = "xxhash64",
        verification_status: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> AuditEntry:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event
            description: Human-readable description
            source_path: Source file path (optional)
            dest_path: Destination file path (optional)
            checksum_algorithm: Algorithm for checksums
            verification_status: Verification result
            metadata: Additional metadata
            
        Returns:
            Created AuditEntry
        """
        # Create file records if paths provided
        source_record = None
        if source_path and source_path.exists():
            try:
                checksum = calculate_checksum(source_path, checksum_algorithm)
                source_record = FileAuditRecord(
                    file_path=str(source_path),
                    file_size_bytes=source_path.stat().st_size,
                    checksum_algorithm=checksum_algorithm,
                    checksum_value=checksum,
                )
            except Exception as e:
                logger.warning(f"Failed to checksum source file: {e}")
        
        dest_record = None
        if dest_path and dest_path.exists():
            try:
                checksum = calculate_checksum(dest_path, checksum_algorithm)
                dest_record = FileAuditRecord(
                    file_path=str(dest_path),
                    file_size_bytes=dest_path.stat().st_size,
                    checksum_algorithm=checksum_algorithm,
                    checksum_value=checksum,
                )
            except Exception as e:
                logger.warning(f"Failed to checksum destination file: {e}")
        
        # Create entry
        entry = AuditEntry(
            entry_id=self._get_next_entry_id(),
            timestamp=datetime.now().isoformat(),
            event_type=event_type.value,
            event_description=description,
            source_file=source_record,
            destination_file=dest_record,
            project_id=self.project_id,
            verification_status=verification_status,
            previous_entry_hash=self._get_previous_hash(),
            metadata=metadata or {},
        )
        
        # Calculate entry hash
        entry.entry_hash = entry.calculate_hash()
        
        # Add to log
        self.entries.append(entry)
        
        # Save immediately
        self._save_log()
        
        logger.debug(f"Audit logged: {event_type.value} - {description}")
        
        return entry
    
    def log_ingest_start(self, source_path: Path, destinations: List[Path]) -> AuditEntry:
        """Log ingestion start."""
        return self.log_event(
            event_type=AuditEventType.INGEST_START,
            description=f"Started ingestion from {source_path} to {len(destinations)} destination(s)",
            source_path=source_path,
            metadata={'destination_count': len(destinations)},
        )
    
    def log_ingest_complete(
        self,
        source_path: Path,
        dest_path: Path,
        files_count: int,
        total_size_bytes: int,
        success: bool,
    ) -> AuditEntry:
        """Log ingestion completion."""
        return self.log_event(
            event_type=AuditEventType.INGEST_COMPLETE,
            description=f"Completed ingestion: {files_count} files, {total_size_bytes / (1024**3):.2f} GB",
            source_path=source_path,
            dest_path=dest_path,
            verification_status='passed' if success else 'failed',
            metadata={
                'files_count': files_count,
                'total_size_bytes': total_size_bytes,
                'success': success,
            },
        )
    
    def log_file_copy(
        self,
        source_path: Path,
        dest_path: Path,
        verified: bool = True,
    ) -> AuditEntry:
        """Log file copy with verification."""
        return self.log_event(
            event_type=AuditEventType.FILE_COPY,
            description=f"Copied file: {source_path.name}",
            source_path=source_path,
            dest_path=dest_path,
            verification_status='passed' if verified else 'failed',
        )
    
    def log_checksum_verification(
        self,
        file_path: Path,
        expected_checksum: str,
        actual_checksum: str,
        algorithm: str = "xxhash64",
    ) -> AuditEntry:
        """Log checksum verification."""
        verified = expected_checksum.lower() == actual_checksum.lower()
        return self.log_event(
            event_type=AuditEventType.CHECKSUM_VERIFY,
            description=f"Checksum verification: {'PASSED' if verified else 'FAILED'}",
            source_path=file_path,
            verification_status='passed' if verified else 'failed',
            metadata={
                'algorithm': algorithm,
                'expected': expected_checksum,
                'actual': actual_checksum,
            },
        )
    
    def _save_log(self):
        """Save audit log to disk."""
        log_path = self._get_log_path()
        
        data = {
            'log_version': '1.0',
            'created_at': self.entries[0].timestamp if self.entries else datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'project_id': self.project_id,
            'entry_count': len(self.entries),
            'entries': [e.to_dict() for e in self.entries],
        }
        
        # Write atomically
        temp_path = log_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        temp_path.rename(log_path)
    
    def verify_chain_integrity(self) -> tuple[bool, List[str]]:
        """
        Verify the integrity of the audit chain.
        
        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []
        
        for i, entry in enumerate(self.entries):
            # Verify entry hash
            calculated_hash = entry.calculate_hash()
            if entry.entry_hash != calculated_hash:
                errors.append(f"Entry {i} ({entry.entry_id}): Hash mismatch - possible tampering")
            
            # Verify chain link (except for first entry)
            if i > 0:
                expected_previous = self.entries[i-1].entry_hash
                if entry.previous_entry_hash != expected_previous:
                    errors.append(f"Entry {i} ({entry.entry_id}): Chain broken - previous hash mismatch")
        
        return len(errors) == 0, errors
    
    def generate_report(self, output_path: Optional[Path] = None) -> Path:
        """
        Generate human-readable audit report.
        
        Returns:
            Path to generated report
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = self.log_dir / f"audit_report_{timestamp}.txt"
        
        # Verify chain first
        is_valid, errors = self.verify_chain_integrity()
        
        lines = []
        lines.append("=" * 80)
        lines.append("CHAIN-OF-CUSTODY AUDIT REPORT")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append(f"Project ID: {self.project_id or 'Global'}")
        lines.append(f"Total Entries: {len(self.entries)}")
        lines.append(f"Chain Integrity: {'✓ VALID' if is_valid else '✗ COMPROMISED'}")
        
        if errors:
            lines.append("")
            lines.append("INTEGRITY ERRORS:")
            for error in errors:
                lines.append(f"  ! {error}")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("AUDIT ENTRIES")
        lines.append("=" * 80)
        lines.append("")
        
        for entry in self.entries:
            lines.append(f"Entry ID: {entry.entry_id}")
            lines.append(f"Timestamp: {entry.timestamp}")
            lines.append(f"Event: {entry.event_type}")
            lines.append(f"Description: {entry.event_description}")
            lines.append(f"User: {entry.user}@{entry.hostname}")
            
            if entry.source_file:
                lines.append(f"Source: {entry.source_file.file_path}")
                lines.append(f"  Size: {entry.source_file.file_size_bytes:,} bytes")
                lines.append(f"  Checksum ({entry.source_file.checksum_algorithm}): {entry.source_file.checksum_value}")
            
            if entry.destination_file:
                lines.append(f"Destination: {entry.destination_file.file_path}")
                lines.append(f"  Size: {entry.destination_file.file_size_bytes:,} bytes")
                lines.append(f"  Checksum ({entry.destination_file.checksum_algorithm}): {entry.destination_file.checksum_value}")
            
            if entry.verification_status:
                status_icon = "✓" if entry.verification_status == 'passed' else "✗"
                lines.append(f"Verification: {status_icon} {entry.verification_status.upper()}")
            
            lines.append(f"Entry Hash: {entry.entry_hash}")
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))
        
        return output_path
    
    def export_json(self, output_path: Optional[Path] = None) -> Path:
        """Export full audit log as JSON."""
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = self.log_dir / f"audit_export_{timestamp}.json"
        
        data = {
            'log_version': '1.0',
            'exported_at': datetime.now().isoformat(),
            'project_id': self.project_id,
            'entry_count': len(self.entries),
            'entries': [e.to_dict() for e in self.entries],
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        return output_path
    
    def get_entries_by_type(self, event_type: AuditEventType) -> List[AuditEntry]:
        """Get all entries of a specific type."""
        return [e for e in self.entries if e.event_type == event_type.value]
    
    def get_entries_for_file(self, file_path: Union[str, Path]) -> List[AuditEntry]:
        """Get all entries related to a specific file."""
        path_str = str(file_path)
        results = []
        
        for entry in self.entries:
            if entry.source_file and entry.source_file.file_path == path_str:
                results.append(entry)
            elif entry.destination_file and entry.destination_file.file_path == path_str:
                results.append(entry)
        
        return results


# Global audit logger instance
_global_logger: Optional[AuditLogger] = None


def get_audit_logger(project_id: Optional[str] = None) -> AuditLogger:
    """Get or create global audit logger instance."""
    global _global_logger
    
    if _global_logger is None or _global_logger.project_id != project_id:
        _global_logger = AuditLogger(project_id=project_id)
    
    return _global_logger


def audit_log(
    event_type: AuditEventType,
    description: str,
    project_id: Optional[str] = None,
    **kwargs
) -> Optional[AuditEntry]:
    """
    Convenience function for quick audit logging.
    
    Args:
        event_type: Type of event
        description: Description of event
        project_id: Optional project ID
        **kwargs: Additional arguments for log_event
        
    Returns:
        AuditEntry if successful, None otherwise
    """
    try:
        logger = get_audit_logger(project_id)
        return logger.log_event(event_type, description, **kwargs)
    except Exception as e:
        logging.error(f"Failed to write audit log: {e}")
        return None
