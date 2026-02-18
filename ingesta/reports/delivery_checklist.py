"""
Editor delivery checklist module for ingesta.

Auto-generates delivery checklists for editors highlighting:
- Missing slates
- Bad audio (clipping, low levels, silence)
- QC flags (corruption, blur, black frames)
- Missing metadata
- Duplicate clips

Used in reports and deliverable packages to alert editors of issues.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from ..analysis import ClipAnalysis


logger = logging.getLogger(__name__)


class ChecklistItemSeverity(Enum):
    """Severity levels for checklist items."""
    CRITICAL = "critical"    # Must fix before delivery
    WARNING = "warning"      # Should review
    INFO = "info"            # FYI only


class ChecklistCategory(Enum):
    """Categories of checklist items."""
    SLATE = "slate"
    AUDIO = "audio"
    QC = "quality_control"
    METADATA = "metadata"
    DUPLICATES = "duplicates"
    SYNC = "sync"


@dataclass
class ChecklistItem:
    """Single checklist item."""
    category: ChecklistCategory
    severity: ChecklistItemSeverity
    clip_name: str
    message: str
    details: Optional[str] = None
    recommendation: Optional[str] = None


@dataclass
class EditorDeliveryChecklist:
    """Complete delivery checklist for an editor."""
    total_clips: int
    items: List[ChecklistItem] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def critical_count(self) -> int:
        return sum(1 for item in self.items if item.severity == ChecklistItemSeverity.CRITICAL)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.items if item.severity == ChecklistItemSeverity.WARNING)
    
    @property
    def info_count(self) -> int:
        return sum(1 for item in self.items if item.severity == ChecklistItemSeverity.INFO)
    
    @property
    def has_critical_issues(self) -> bool:
        return self.critical_count > 0
    
    def get_items_by_category(self, category: ChecklistCategory) -> List[ChecklistItem]:
        return [item for item in self.items if item.category == category]
    
    def get_items_by_severity(self, severity: ChecklistItemSeverity) -> List[ChecklistItem]:
        return [item for item in self.items if item.severity == severity]


class DeliveryChecklistGenerator:
    """Generate editor delivery checklists from clip analyses."""
    
    # Thresholds for flagging issues
    CLIPPING_THRESHOLD = 3  # Number of clipping instances
    LOW_LEVEL_THRESHOLD = -40.0  # dBFS
    HIGH_SILENCE_THRESHOLD = 0.5  # 50% silence
    BLUR_THRESHOLD = 0.3  # Blur score below this is concerning
    BLACK_FRAME_THRESHOLD = 5  # Number of black frames to flag
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_checklist(self, analyses: List[ClipAnalysis]) -> EditorDeliveryChecklist:
        """
        Generate delivery checklist from clip analyses.
        
        Args:
            analyses: List of ClipAnalysis objects
            
        Returns:
            EditorDeliveryChecklist with all flagged items
        """
        items = []
        
        for analysis in analyses:
            items.extend(self._check_slate(analysis))
            items.extend(self._check_audio(analysis))
            items.extend(self._check_quality(analysis))
            items.extend(self._check_metadata(analysis))
            items.extend(self._check_duplicates(analysis))
        
        # Generate summary
        summary = self._generate_summary(analyses, items)
        
        checklist = EditorDeliveryChecklist(
            total_clips=len(analyses),
            items=items,
            summary=summary
        )
        
        self.logger.info(f"Generated checklist: {len(items)} items "
                        f"({checklist.critical_count} critical, "
                        f"{checklist.warning_count} warning, "
                        f"{checklist.info_count} info)")
        
        return checklist
    
    def _check_slate(self, analysis: ClipAnalysis) -> List[ChecklistItem]:
        """Check for missing or detected slates."""
        items = []
        
        has_slate = getattr(analysis, 'has_slate', False)
        slate_text = getattr(analysis, 'slate_text', None)
        
        if not has_slate:
            # Check if this looks like an interview/syncable clip that should have slate
            if analysis.is_syncable or analysis.clip_type.value in ['interview', 'syncable']:
                items.append(ChecklistItem(
                    category=ChecklistCategory.SLATE,
                    severity=ChecklistItemSeverity.WARNING,
                    clip_name=analysis.file_path.name,
                    message="No slate detected",
                    details="This clip appears to be syncable but no slate was detected",
                    recommendation="Check if slate exists or manually mark scene/take info"
                ))
        elif slate_text:
            items.append(ChecklistItem(
                category=ChecklistCategory.SLATE,
                severity=ChecklistItemSeverity.INFO,
                clip_name=analysis.file_path.name,
                message=f"Slate detected: {slate_text}",
                details="Automatic slate detection found markers in audio"
            ))
        
        return items
    
    def _check_audio(self, analysis: ClipAnalysis) -> List[ChecklistItem]:
        """Check for audio issues."""
        items = []
        
        # Check for clipping
        clipping = getattr(analysis, 'audio_clipping', False)
        clipping_count = getattr(analysis, 'audio_clipping_count', 0)
        
        if clipping and clipping_count >= self.CLIPPING_THRESHOLD:
            items.append(ChecklistItem(
                category=ChecklistCategory.AUDIO,
                severity=ChecklistItemSeverity.CRITICAL,
                clip_name=analysis.file_path.name,
                message=f"Audio clipping detected ({clipping_count} instances)",
                details=f"{clipping_count} instances of audio clipping found",
                recommendation="Re-record if possible, or use audio repair tools"
            ))
        elif clipping:
            items.append(ChecklistItem(
                category=ChecklistCategory.AUDIO,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message=f"Minor audio clipping ({clipping_count} instances)",
                details="Some clipping detected but may be acceptable"
            ))
        
        # Check for low levels
        peak_dbfs = getattr(analysis, 'audio_peak_dbfs', None)
        rms_dbfs = getattr(analysis, 'audio_rms_dbfs', None)
        
        if peak_dbfs is not None and peak_dbfs < self.LOW_LEVEL_THRESHOLD:
            items.append(ChecklistItem(
                category=ChecklistCategory.AUDIO,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message="Audio levels very low",
                details=f"Peak level: {peak_dbfs:.1f} dBFS (threshold: {self.LOW_LEVEL_THRESHOLD} dBFS)",
                recommendation="Boost gain or check microphone/setup"
            ))
        
        # Check for silence
        silence_ratio = getattr(analysis, 'silence_ratio', 0)
        if silence_ratio > self.HIGH_SILENCE_THRESHOLD:
            items.append(ChecklistItem(
                category=ChecklistCategory.AUDIO,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message="High silence ratio",
                details=f"{silence_ratio:.1%} of clip is silent",
                recommendation="Check if intentional or if audio track is missing"
            ))
        
        # Check for no audio stream
        if not analysis.has_audio:
            items.append(ChecklistItem(
                category=ChecklistCategory.AUDIO,
                severity=ChecklistItemSeverity.CRITICAL,
                clip_name=analysis.file_path.name,
                message="No audio stream detected",
                details="This clip has no audio track",
                recommendation="Verify camera audio settings or use external audio"
            ))
        
        return items
    
    def _check_quality(self, analysis: ClipAnalysis) -> List[ChecklistItem]:
        """Check for quality issues."""
        items = []
        
        # Check for corruption
        is_corrupted = getattr(analysis, 'is_corrupted', False)
        if is_corrupted:
            items.append(ChecklistItem(
                category=ChecklistCategory.QC,
                severity=ChecklistItemSeverity.CRITICAL,
                clip_name=analysis.file_path.name,
                message="File corruption detected",
                details="This file may be corrupted or truncated",
                recommendation="Re-copy from source or check source media"
            ))
        
        # Check for black frames
        black_frames = getattr(analysis, 'black_frame_count', 0)
        if black_frames >= self.BLACK_FRAME_THRESHOLD:
            items.append(ChecklistItem(
                category=ChecklistCategory.QC,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message=f"Black frames detected ({black_frames})",
                details=f"{black_frames} black frames found in clip",
                recommendation="Check camera/lens cap or re-shoot if critical"
            ))
        
        # Check for blur
        blur_score = getattr(analysis, 'blur_score', 0)
        if blur_score > 0 and blur_score < self.BLUR_THRESHOLD:
            items.append(ChecklistItem(
                category=ChecklistCategory.QC,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message="Clip appears out of focus",
                details=f"Blur score: {blur_score:.2f} (threshold: {self.BLUR_THRESHOLD:.2f})",
                recommendation="Check focus and consider re-shooting"
            ))
        
        # Check quality warnings from detector
        quality_warnings = getattr(analysis, 'quality_warnings', [])
        for warning in quality_warnings:
            items.append(ChecklistItem(
                category=ChecklistCategory.QC,
                severity=ChecklistItemSeverity.WARNING,
                clip_name=analysis.file_path.name,
                message=warning,
                details="Quality check flagged this issue"
            ))
        
        return items
    
    def _check_metadata(self, analysis: ClipAnalysis) -> List[ChecklistItem]:
        """Check for missing metadata."""
        items = []
        
        # Check for timecode
        timecode_start = getattr(analysis, 'timecode_start', None)
        if not timecode_start:
            items.append(ChecklistItem(
                category=ChecklistCategory.METADATA,
                severity=ChecklistItemSeverity.INFO,
                clip_name=analysis.file_path.name,
                message="No timecode detected",
                details="Timecode information not available"
            ))
        
        # Check for reel/scene/take
        reel_id = getattr(analysis, 'reel_id', None)
        scene = getattr(analysis, 'scene', None)
        take = getattr(analysis, 'take', None)
        
        if not reel_id:
            items.append(ChecklistItem(
                category=ChecklistCategory.METADATA,
                severity=ChecklistItemSeverity.INFO,
                clip_name=analysis.file_path.name,
                message="No reel ID detected",
                details="Reel/camera identifier not found"
            ))
        
        if analysis.is_syncable and not scene:
            items.append(ChecklistItem(
                category=ChecklistCategory.METADATA,
                severity=ChecklistItemSeverity.INFO,
                clip_name=analysis.file_path.name,
                message="No scene number detected",
                details="Syncable clip may need scene identification"
            ))
        
        return items
    
    def _check_duplicates(self, analysis: ClipAnalysis) -> List[ChecklistItem]:
        """Check for duplicate clips."""
        items = []
        
        is_duplicate = getattr(analysis, 'is_duplicate', False)
        duplicate_of = getattr(analysis, 'duplicate_of', [])
        duplicate_type = getattr(analysis, 'duplicate_type', '')
        
        if is_duplicate and duplicate_of:
            items.append(ChecklistItem(
                category=ChecklistCategory.DUPLICATES,
                severity=ChecklistItemSeverity.INFO,
                clip_name=analysis.file_path.name,
                message=f"Possible duplicate ({duplicate_type})",
                details=f"May be duplicate of: {', '.join(duplicate_of[:3])}",
                recommendation="Verify if intentional backup or accidental duplicate"
            ))
        
        return items
    
    def _generate_summary(self, analyses: List[ClipAnalysis], items: List[ChecklistItem]) -> Dict[str, Any]:
        """Generate checklist summary statistics."""
        categories = {}
        for cat in ChecklistCategory:
            cat_items = [i for i in items if i.category == cat]
            categories[cat.value] = {
                'total': len(cat_items),
                'critical': sum(1 for i in cat_items if i.severity == ChecklistItemSeverity.CRITICAL),
                'warning': sum(1 for i in cat_items if i.severity == ChecklistItemSeverity.WARNING),
                'info': sum(1 for i in cat_items if i.severity == ChecklistItemSeverity.INFO),
            }
        
        return {
            'total_clips': len(analyses),
            'total_issues': len(items),
            'critical_count': sum(1 for i in items if i.severity == ChecklistItemSeverity.CRITICAL),
            'warning_count': sum(1 for i in items if i.severity == ChecklistItemSeverity.WARNING),
            'info_count': sum(1 for i in items if i.severity == ChecklistItemSeverity.INFO),
            'clips_with_issues': len(set(i.clip_name for i in items)),
            'by_category': categories,
        }
    
    def export_checklist_text(self, checklist: EditorDeliveryChecklist, output_path: Path) -> Path:
        """
        Export checklist as formatted text file.
        
        Args:
            checklist: EditorDeliveryChecklist to export
            output_path: Path to save text file
            
        Returns:
            Path to exported file
        """
        lines = []
        lines.append("=" * 80)
        lines.append("EDITOR DELIVERY CHECKLIST")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Total Clips: {checklist.total_clips}")
        lines.append(f"Total Issues: {checklist.summary.get('total_issues', 0)}")
        lines.append(f"  - Critical: {checklist.critical_count}")
        lines.append(f"  - Warning: {checklist.warning_count}")
        lines.append(f"  - Info: {checklist.info_count}")
        lines.append("")
        
        if checklist.has_critical_issues:
            lines.append("⚠️  CRITICAL ISSUES FOUND - REVIEW BEFORE DELIVERY")
            lines.append("")
        
        # Group by severity
        for severity in [ChecklistItemSeverity.CRITICAL, ChecklistItemSeverity.WARNING, ChecklistItemSeverity.INFO]:
            items = checklist.get_items_by_severity(severity)
            if items:
                lines.append("-" * 80)
                lines.append(f"{severity.value.upper()} ({len(items)} items)")
                lines.append("-" * 80)
                lines.append("")
                
                for item in items:
                    lines.append(f"[{item.category.value.upper()}] {item.clip_name}")
                    lines.append(f"  → {item.message}")
                    if item.details:
                        lines.append(f"     Details: {item.details}")
                    if item.recommendation:
                        lines.append(f"     Recommendation: {item.recommendation}")
                    lines.append("")
        
        lines.append("=" * 80)
        lines.append("END OF CHECKLIST")
        lines.append("=" * 80)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path
    
    def export_checklist_csv(self, checklist: EditorDeliveryChecklist, output_path: Path) -> Path:
        """
        Export checklist as CSV file.
        
        Args:
            checklist: EditorDeliveryChecklist to export
            output_path: Path to save CSV file
            
        Returns:
            Path to exported file
        """
        import csv
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Severity', 'Category', 'Clip Name', 'Message', 'Details', 'Recommendation'])
            
            for item in checklist.items:
                writer.writerow([
                    item.severity.value,
                    item.category.value,
                    item.clip_name,
                    item.message,
                    item.details or '',
                    item.recommendation or ''
                ])
        
        return output_path


def generate_delivery_checklist(analyses: List[ClipAnalysis]) -> EditorDeliveryChecklist:
    """
    Convenience function to generate a delivery checklist.
    
    Args:
        analyses: List of ClipAnalysis objects
        
    Returns:
        EditorDeliveryChecklist with all flagged items
    """
    generator = DeliveryChecklistGenerator()
    return generator.generate_checklist(analyses)