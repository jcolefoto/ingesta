"""
Card/device tracking module for ingesta.

Tracks physical storage media (SD cards, CFexpress, SSDs) with:
- Physical labels (user-applied, like "VM_03" or "RentalHouse_001")
- Electronic volume names (what the computer sees, like "Untitled")
- Performance metrics and write speeds
- Issue tracking for problematic cards
- Historical database to identify cards to avoid

Helps DITs track which cards have issues and should be retired.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import platform


logger = logging.getLogger(__name__)


class CardStatus(Enum):
    """Status of a tracked card."""
    ACTIVE = "active"
    SUSPECT = "suspect"  # Showing issues but not confirmed bad
    RETIRED = "retired"  # Confirmed bad, don't use
    LOST = "lost"  # Physically lost/missing


class CardType(Enum):
    """Types of storage media."""
    SD_CARD = "sd_card"
    MICRO_SD = "micro_sd"
    CFEXPRESS_TYPE_A = "cfexpress_a"
    CFEXPRESS_TYPE_B = "cfexpress_b"
    COMPACT_FLASH = "compact_flash"
    SSD_SATA = "ssd_sata"
    SSD_NVME = "ssd_nvme"
    USB_DRIVE = "usb_drive"
    UNKNOWN = "unknown"


@dataclass
class CardPerformance:
    """Performance metrics for a card."""
    timestamp: str
    avg_write_speed_mbps: Optional[float] = None
    min_write_speed_mbps: Optional[float] = None
    max_write_speed_mbps: Optional[float] = None
    files_copied: int = 0
    total_bytes: int = 0
    duration_seconds: float = 0.0
    
    @property
    def overall_speed_mbps(self) -> Optional[float]:
        """Calculate overall write speed."""
        if self.duration_seconds > 0 and self.total_bytes > 0:
            return (self.total_bytes / self.duration_seconds) / (1024 * 1024)
        return None


@dataclass
class CardIssue:
    """Issue recorded for a card."""
    timestamp: str
    issue_type: str  # 'slow', 'corruption', 'read_error', 'write_error', etc.
    description: str
    severity: str  # 'minor', 'major', 'critical'
    
    
@dataclass
class TrackedCard:
    """A tracked storage device/card."""
    card_id: str  # Unique identifier
    
    # Three different identifiers
    physical_label: Optional[str] = None  # User-applied label (e.g., "VM_03")
    volume_name: Optional[str] = None  # What computer sees (e.g., "Untitled")
    reel_id: Optional[str] = None  # Camera assignment (e.g., "A001")
    
    # Card info
    card_type: CardType = CardType.UNKNOWN
    capacity_gb: Optional[float] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    
    # Status
    status: CardStatus = CardStatus.ACTIVE
    
    # History
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None
    use_count: int = 0
    
    # Performance tracking
    performance_history: List[CardPerformance] = field(default_factory=list)
    issues: List[CardIssue] = field(default_factory=list)
    notes: str = ""
    
    def record_performance(self, performance: CardPerformance):
        """Record a performance measurement."""
        self.performance_history.append(performance)
        self.last_used = performance.timestamp
        self.use_count += 1
    
    def record_issue(self, issue: CardIssue):
        """Record an issue with the card."""
        self.issues.append(issue)
        
        # Auto-update status based on issues
        critical_count = sum(1 for i in self.issues if i.severity == 'critical')
        major_count = sum(1 for i in self.issues if i.severity == 'major')
        
        if critical_count >= 2 or major_count >= 3:
            self.status = CardStatus.RETIRED
        elif critical_count == 1 or major_count >= 1:
            self.status = CardStatus.SUSPECT
    
    def get_avg_speed(self) -> Optional[float]:
        """Get average write speed across all uses."""
        speeds = [p.overall_speed_mbps for p in self.performance_history 
                  if p.overall_speed_mbps]
        if speeds:
            return sum(speeds) / len(speeds)
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'card_id': self.card_id,
            'physical_label': self.physical_label,
            'volume_name': self.volume_name,
            'reel_id': self.reel_id,
            'card_type': self.card_type.value,
            'capacity_gb': self.capacity_gb,
            'manufacturer': self.manufacturer,
            'model': self.model,
            'serial_number': self.serial_number,
            'status': self.status.value,
            'first_seen': self.first_seen,
            'last_used': self.last_used,
            'use_count': self.use_count,
            'avg_speed_mbps': self.get_avg_speed(),
            'performance_history': [asdict(p) for p in self.performance_history],
            'issues': [asdict(i) for i in self.issues],
            'notes': self.notes,
        }


class CardTracker:
    """Track and manage storage cards/devices."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize card tracker.
        
        Args:
            db_path: Path to SQLite database file
        """
        if db_path is None:
            # Store in user's home directory
            home = Path.home()
            db_path = home / '.ingesta' / 'card_tracker.db'
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
        self.logger = logging.getLogger(__name__)
    
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cards (
                card_id TEXT PRIMARY KEY,
                physical_label TEXT,
                volume_name TEXT,
                reel_id TEXT,
                card_type TEXT,
                capacity_gb REAL,
                manufacturer TEXT,
                model TEXT,
                serial_number TEXT,
                status TEXT DEFAULT 'active',
                first_seen TEXT,
                last_used TEXT,
                use_count INTEGER DEFAULT 0,
                notes TEXT,
                UNIQUE(physical_label, serial_number)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT,
                timestamp TEXT,
                avg_write_speed_mbps REAL,
                min_write_speed_mbps REAL,
                max_write_speed_mbps REAL,
                files_copied INTEGER,
                total_bytes INTEGER,
                duration_seconds REAL,
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS card_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id TEXT,
                timestamp TEXT,
                issue_type TEXT,
                description TEXT,
                severity TEXT,
                FOREIGN KEY (card_id) REFERENCES cards(card_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_or_create_card(self, 
                          physical_label: Optional[str] = None,
                          volume_name: Optional[str] = None,
                          reel_id: Optional[str] = None,
                          card_type: CardType = CardType.UNKNOWN) -> TrackedCard:
        """
        Get existing card or create new one.
        
        Tries to match by physical_label first, then by volume_name + serial.
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        card = None
        
        # Try to find by physical label
        if physical_label:
            cursor.execute(
                'SELECT * FROM cards WHERE physical_label = ?',
                (physical_label,)
            )
            row = cursor.fetchone()
            if row:
                card = self._row_to_card(cursor, row)
        
        # Try to find by volume name if no match
        if card is None and volume_name:
            cursor.execute(
                'SELECT * FROM cards WHERE volume_name = ? ORDER BY last_used DESC LIMIT 1',
                (volume_name,)
            )
            row = cursor.fetchone()
            if row:
                card = self._row_to_card(cursor, row)
        
        conn.close()
        
        if card:
            return card
        
        # Create new card
        card_id = f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self)}"
        card = TrackedCard(
            card_id=card_id,
            physical_label=physical_label,
            volume_name=volume_name,
            reel_id=reel_id,
            card_type=card_type
        )
        
        self._save_card(card)
        self.logger.info(f"Created new card tracking entry: {card_id}")
        
        return card
    
    def _row_to_card(self, cursor, row) -> TrackedCard:
        """Convert database row to TrackedCard."""
        columns = [description[0] for description in cursor.description]
        data = dict(zip(columns, row))
        
        card = TrackedCard(
            card_id=data['card_id'],
            physical_label=data['physical_label'],
            volume_name=data['volume_name'],
            reel_id=data['reel_id'],
            card_type=CardType(data.get('card_type', 'unknown')),
            capacity_gb=data.get('capacity_gb'),
            manufacturer=data.get('manufacturer'),
            model=data.get('model'),
            serial_number=data.get('serial_number'),
            status=CardStatus(data.get('status', 'active')),
            first_seen=data['first_seen'],
            last_used=data.get('last_used'),
            use_count=data.get('use_count', 0),
            notes=data.get('notes', '')
        )
        
        # Load performance history
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT * FROM card_performance WHERE card_id = ? ORDER BY timestamp DESC',
            (card.card_id,)
        )
        for perf_row in cursor.fetchall():
            perf_columns = [description[0] for description in cursor.description]
            perf_data = dict(zip(perf_columns, perf_row))
            card.performance_history.append(CardPerformance(
                timestamp=perf_data['timestamp'],
                avg_write_speed_mbps=perf_data.get('avg_write_speed_mbps'),
                min_write_speed_mbps=perf_data.get('min_write_speed_mbps'),
                max_write_speed_mbps=perf_data.get('max_write_speed_mbps'),
                files_copied=perf_data.get('files_copied', 0),
                total_bytes=perf_data.get('total_bytes', 0),
                duration_seconds=perf_data.get('duration_seconds', 0.0)
            ))
        
        # Load issues
        cursor.execute(
            'SELECT * FROM card_issues WHERE card_id = ? ORDER BY timestamp DESC',
            (card.card_id,)
        )
        for issue_row in cursor.fetchall():
            issue_columns = [description[0] for description in cursor.description]
            issue_data = dict(zip(issue_columns, issue_row))
            card.issues.append(CardIssue(
                timestamp=issue_data['timestamp'],
                issue_type=issue_data['issue_type'],
                description=issue_data['description'],
                severity=issue_data['severity']
            ))
        
        conn.close()
        return card
    
    def _save_card(self, card: TrackedCard):
        """Save card to database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO cards 
            (card_id, physical_label, volume_name, reel_id, card_type, capacity_gb,
             manufacturer, model, serial_number, status, first_seen, last_used, use_count, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            card.card_id, card.physical_label, card.volume_name, card.reel_id,
            card.card_type.value, card.capacity_gb, card.manufacturer, card.model,
            card.serial_number, card.status.value, card.first_seen, card.last_used,
            card.use_count, card.notes
        ))
        
        conn.commit()
        conn.close()
    
    def record_ingestion(self, 
                        card: TrackedCard,
                        files_copied: int,
                        total_bytes: int,
                        duration_seconds: float,
                        avg_speed: Optional[float] = None):
        """Record ingestion performance for a card."""
        performance = CardPerformance(
            timestamp=datetime.now().isoformat(),
            files_copied=files_copied,
            total_bytes=total_bytes,
            duration_seconds=duration_seconds,
            avg_write_speed_mbps=avg_speed
        )
        
        card.record_performance(performance)
        
        # Save to database
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO card_performance 
            (card_id, timestamp, avg_write_speed_mbps, files_copied, total_bytes, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            card.card_id, performance.timestamp, performance.avg_write_speed_mbps,
            performance.files_copied, performance.total_bytes, performance.duration_seconds
        ))
        
        # Update card stats
        cursor.execute('''
            UPDATE cards SET last_used = ?, use_count = ? WHERE card_id = ?
        ''', (card.last_used, card.use_count, card.card_id))
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Recorded ingestion for card {card.card_id}: "
                        f"{files_copied} files, {avg_speed:.1f} MB/s avg")
    
    def record_card_issue(self, 
                         card: TrackedCard,
                         issue_type: str,
                         description: str,
                         severity: str = 'minor'):
        """Record an issue with a card."""
        issue = CardIssue(
            timestamp=datetime.now().isoformat(),
            issue_type=issue_type,
            description=description,
            severity=severity
        )
        
        card.record_issue(issue)
        
        # Save to database
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO card_issues (card_id, timestamp, issue_type, description, severity)
            VALUES (?, ?, ?, ?, ?)
        ''', (card.card_id, issue.timestamp, issue.issue_type, issue.description, issue.severity))
        
        # Update status
        cursor.execute('''
            UPDATE cards SET status = ? WHERE card_id = ?
        ''', (card.status.value, card.card_id))
        
        conn.commit()
        conn.close()
        
        self.logger.warning(f"Recorded issue for card {card.card_id}: {issue_type} - {description}")
    
    def get_card_warnings(self, card: TrackedCard) -> List[str]:
        """Get warnings for a card based on its history."""
        warnings = []
        
        # Check status
        if card.status == CardStatus.RETIRED:
            warnings.append(f"⚠️  CARD RETIRED - Do not use: {card.physical_label or card.volume_name}")
            if card.issues:
                warnings.append(f"   Reason: {card.issues[-1].description}")
        elif card.status == CardStatus.SUSPECT:
            warnings.append(f"⚠️  CARD SUSPECT - Monitor closely: {card.physical_label or card.volume_name}")
        
        # Check performance degradation
        if len(card.performance_history) >= 3:
            recent = card.performance_history[-3:]
            speeds = [p.overall_speed_mbps for p in recent if p.overall_speed_mbps]
            if speeds and len(speeds) >= 2:
                if speeds[-1] < speeds[0] * 0.7:  # 30% slower
                    warnings.append(f"⚠️  Performance degradation detected: {speeds[0]:.1f} → {speeds[-1]:.1f} MB/s")
        
        # Check for past issues
        critical_issues = [i for i in card.issues if i.severity == 'critical']
        if critical_issues:
            warnings.append(f"⚠️  {len(critical_issues)} critical issue(s) in history")
        
        return warnings
    
    def list_all_cards(self, status: Optional[CardStatus] = None) -> List[TrackedCard]:
        """List all tracked cards, optionally filtered by status."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        if status:
            cursor.execute('SELECT * FROM cards WHERE status = ? ORDER BY last_used DESC', 
                          (status.value,))
        else:
            cursor.execute('SELECT * FROM cards ORDER BY last_used DESC')
        
        cards = []
        for row in cursor.fetchall():
            cards.append(self._row_to_card(cursor, row))
        
        conn.close()
        return cards
    
    def get_problematic_cards(self) -> List[TrackedCard]:
        """Get cards with issues or retired status."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT c.* FROM cards c
            LEFT JOIN card_issues i ON c.card_id = i.card_id
            WHERE c.status IN ('suspect', 'retired') OR i.id IS NOT NULL
            ORDER BY c.last_used DESC
        ''')
        
        cards = []
        for row in cursor.fetchall():
            cards.append(self._row_to_card(cursor, row))
        
        conn.close()
        return cards
    
    def export_card_report(self, output_path: Path):
        """Export comprehensive card report."""
        cards = self.list_all_cards()
        
        lines = []
        lines.append("=" * 80)
        lines.append("CARD TRACKING REPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append(f"Total Cards Tracked: {len(cards)}")
        lines.append("")
        
        # Summary by status
        status_counts = {}
        for card in cards:
            status_counts[card.status.value] = status_counts.get(card.status.value, 0) + 1
        
        lines.append("Status Summary:")
        for status, count in status_counts.items():
            lines.append(f"  {status}: {count}")
        lines.append("")
        
        # Problematic cards
        problematic = [c for c in cards if c.status != CardStatus.ACTIVE or c.issues]
        if problematic:
            lines.append("⚠️  CARDS REQUIRING ATTENTION")
            lines.append("-" * 80)
            for card in problematic:
                lines.append(f"\n{card.physical_label or card.volume_name or 'Unknown Card'}")
                lines.append(f"  Status: {card.status.value.upper()}")
                lines.append(f"  Type: {card.card_type.value}")
                lines.append(f"  Uses: {card.use_count}")
                if card.get_avg_speed():
                    lines.append(f"  Avg Speed: {card.get_avg_speed():.1f} MB/s")
                if card.issues:
                    lines.append(f"  Recent Issues:")
                    for issue in card.issues[-3:]:
                        lines.append(f"    [{issue.severity.upper()}] {issue.issue_type}: {issue.description}")
            lines.append("")
        
        # All cards
        lines.append("ALL TRACKED CARDS")
        lines.append("-" * 80)
        for card in cards:
            lines.append(f"\n{card.physical_label or 'No Label'} | {card.volume_name or 'No Vol Name'}")
            lines.append(f"  Reel: {card.reel_id or 'N/A'}")
            lines.append(f"  Type: {card.card_type.value}")
            lines.append(f"  Status: {card.status.value}")
            lines.append(f"  Uses: {card.use_count}")
            if card.last_used:
                lines.append(f"  Last Used: {card.last_used[:10]}")
            if card.get_avg_speed():
                lines.append(f"  Avg Speed: {card.get_avg_speed():.1f} MB/s")
        
        lines.append("\n" + "=" * 80)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path


def get_card_tracker(db_path: Optional[Path] = None) -> CardTracker:
    """Get card tracker instance."""
    return CardTracker(db_path)