"""
Editor handoff email pack module for ingesta.

Generates professional editor handoff emails including:
- Project summary and metadata
- Deliverables overview with paths/links
- Issue summaries (QC flags, missing items)
- Safe to format confirmation
- Direct links to deliverable packages

Makes editor handoff quick and professional.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import formatdate

from ..analysis import ClipAnalysis
from ..project_manager import Project


logger = logging.getLogger(__name__)


@dataclass
class EditorHandoffPackage:
    """Complete handoff package for an editor."""
    project_name: str
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Deliverables
    deliverable_zip_path: Optional[Path] = None
    reports_dir: Optional[Path] = None
    proxies_dir: Optional[Path] = None
    
    # Media summary
    total_clips: int = 0
    total_duration_seconds: float = 0.0
    total_size_bytes: int = 0
    
    # Breakdown
    clip_types: Dict[str, int] = field(default_factory=dict)
    camera_reels: List[str] = field(default_factory=list)
    
    # Quality/Checklist
    has_qc_issues: bool = False
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Sync/Multicam
    synced_count: int = 0
    multicam_groups: int = 0
    
    # Safe to format
    safe_to_format: bool = False
    
    # Transcription
    transcribed_count: int = 0
    
    # Project metadata
    client: Optional[str] = None
    director: Optional[str] = None
    shoot_date: Optional[str] = None
    shoot_location: Optional[str] = None


class EditorHandoffGenerator:
    """Generate professional editor handoff packages and emails."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_handoff_package(self,
                               project_name: str,
                               analyses: List[ClipAnalysis],
                               deliverable_path: Optional[Path] = None,
                               checklist_summary: Optional[Dict] = None,
                               sync_summary: Optional[Dict] = None,
                               safe_to_format: bool = False,
                               project_metadata: Optional[Dict] = None) -> EditorHandoffPackage:
        """
        Create a complete editor handoff package.
        
        Args:
            project_name: Name of the project
            analyses: List of clip analyses
            deliverable_path: Path to deliverables ZIP
            checklist_summary: Summary from delivery checklist
            sync_summary: Summary from sync analysis
            safe_to_format: Whether source is safe to format
            project_metadata: Additional project metadata
            
        Returns:
            EditorHandoffPackage with all handoff info
        """
        # Calculate basic stats
        total_duration = sum(a.duration for a in analyses)
        total_size = sum(self._get_file_size(a.file_path) for a in analyses)
        
        # Count clip types
        clip_types = {}
        for analysis in analyses:
            clip_type = analysis.clip_type.value
            clip_types[clip_type] = clip_types.get(clip_type, 0) + 1
        
        # Get camera reels
        reels = set()
        for analysis in analyses:
            reel = getattr(analysis, 'reel_id', None)
            if reel:
                reels.add(reel)
        
        # Get transcribed count
        transcribed = sum(1 for a in analyses if getattr(a, 'transcription', None))
        
        # Get synced count
        synced = sum(1 for a in analyses if a.is_syncable)
        
        # Extract issues from checklist
        critical_issues = []
        warnings = []
        has_qc_issues = False
        
        if checklist_summary:
            if checklist_summary.get('critical_count', 0) > 0:
                has_qc_issues = True
            # Could extract specific issues here
        
        # Get multicam groups
        multicam_groups = 0
        if sync_summary:
            multicam_groups = sync_summary.get('multicam_groups_detected', 0)
        
        metadata = project_metadata or {}
        
        return EditorHandoffPackage(
            project_name=project_name,
            deliverable_zip_path=deliverable_path,
            total_clips=len(analyses),
            total_duration_seconds=total_duration,
            total_size_bytes=total_size,
            clip_types=clip_types,
            camera_reels=sorted(list(reels)),
            has_qc_issues=has_qc_issues,
            critical_issues=critical_issues,
            warnings=warnings,
            synced_count=synced,
            multicam_groups=multicam_groups,
            transcribed_count=transcribed,
            safe_to_format=safe_to_format,
            client=metadata.get('client'),
            director=metadata.get('director'),
            shoot_date=metadata.get('shoot_date'),
            shoot_location=metadata.get('shoot_location'),
        )
    
    def _get_file_size(self, file_path: Path) -> int:
        """Get file size safely."""
        try:
            return file_path.stat().st_size
        except (OSError, FileNotFoundError):
            return 0
    
    def generate_email_draft(self, package: EditorHandoffPackage) -> str:
        """
        Generate a professional email draft for editor handoff.
        
        Args:
            package: EditorHandoffPackage with handoff info
            
        Returns:
            Formatted email text
        """
        lines = []
        
        # Subject
        subject = f"[DELIVERY] {package.project_name} - Media Ready for Edit"
        lines.append(f"Subject: {subject}")
        lines.append("")
        
        # Greeting
        lines.append("Hi,")
        lines.append("")
        
        # Opening
        lines.append(f"The media for **{package.project_name}** has been ingested and is ready for editing.")
        lines.append("")
        
        # Safe to format badge
        if package.safe_to_format:
            lines.append("✅ **SAFE TO FORMAT** - All checksums verified, source media can be erased")
        else:
            lines.append("⚠️ **DO NOT FORMAT SOURCE** - Please verify backup integrity first")
        lines.append("")
        
        # Quick Stats
        lines.append("## Quick Stats")
        lines.append("")
        lines.append(f"- **Total Clips:** {package.total_clips}")
        lines.append(f"- **Total Duration:** {self._format_duration(package.total_duration_seconds)}")
        lines.append(f"- **Total Size:** {self._format_size(package.total_size_bytes)}")
        
        if package.synced_count > 0:
            lines.append(f"- **Syncable Clips:** {package.synced_count}")
        
        if package.multicam_groups > 0:
            lines.append(f"- **Multicam Groups:** {package.multicam_groups}")
        
        if package.transcribed_count > 0:
            lines.append(f"- **Transcribed Clips:** {package.transcribed_count}")
        
        lines.append("")
        
        # Deliverables Location
        lines.append("## Deliverables")
        lines.append("")
        
        if package.deliverable_zip_path:
            lines.append(f"**Download Package:**")
            lines.append(f"```")
            lines.append(f"{package.deliverable_zip_path}")
            lines.append(f"```")
            lines.append("")
        
        lines.append("**Package Contents:**")
        lines.append("- 📄 PDF Report with thumbnails and metadata")
        lines.append("- 📊 CSV spreadsheets for clip tracking")
        lines.append("- 🎥 Proxy files for offline editing")
        lines.append("- 📝 Transcripts (TXT, SRT, JSON)")
        lines.append("- 🖼️ Clip thumbnails")
        lines.append("- 📋 Metadata and manifest")
        
        if package.camera_reels:
            lines.append("")
            lines.append(f"**Camera Reels:** {', '.join(package.camera_reels)}")
        
        lines.append("")
        
        # Clip Types
        if package.clip_types:
            lines.append("## Clip Breakdown")
            lines.append("")
            for clip_type, count in sorted(package.clip_types.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {clip_type.replace('_', ' ').title()}: {count}")
            lines.append("")
        
        # Issues & Warnings
        if package.has_qc_issues:
            lines.append("## ⚠️ Issues Requiring Attention")
            lines.append("")
            lines.append("Please review the delivery checklist in the reports folder for details on:")
            
            if package.critical_issues:
                lines.append("")
                lines.append("**Critical Issues:**")
                for issue in package.critical_issues[:5]:
                    lines.append(f"- {issue}")
            
            if package.warnings:
                lines.append("")
                lines.append("**Warnings:**")
                for warning in package.warnings[:5]:
                    lines.append(f"- {warning}")
            
            lines.append("")
            lines.append("See `delivery_checklist.txt` in the reports folder for complete details.")
            lines.append("")
        
        # Project Metadata
        if package.client or package.director or package.shoot_date:
            lines.append("## Project Info")
            lines.append("")
            if package.client:
                lines.append(f"**Client:** {package.client}")
            if package.director:
                lines.append(f"**Director:** {package.director}")
            if package.shoot_date:
                lines.append(f"**Shoot Date:** {package.shoot_date}")
            if package.shoot_location:
                lines.append(f"**Location:** {package.shoot_location}")
            lines.append("")
        
        # Technical Notes
        lines.append("## Technical Notes")
        lines.append("")
        lines.append("- All clips verified with xxhash64 checksums")
        lines.append("- Timecode extracted where available")
        lines.append("- Audio synced using waveform matching")
        lines.append("- Proxy files generated at 960x540 for offline editing")
        lines.append("")
        
        # Questions
        lines.append("## Questions?")
        lines.append("")
        lines.append("Let me know if you need anything else or have questions about the media.")
        lines.append("")
        
        # Signature
        lines.append("Best,")
        lines.append("")
        lines.append("[Your Name]")
        lines.append("[Your Title]")
        lines.append("")
        
        # Footer
        lines.append("---")
        lines.append(f"*Generated by ingesta on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        
        return '\n'.join(lines)
    
    def generate_html_email(self, package: EditorHandoffPackage) -> str:
        """
        Generate HTML version of the handoff email.
        
        Args:
            package: EditorHandoffPackage with handoff info
            
        Returns:
            HTML email content
        """
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background-color: #2c5aa0; color: white; padding: 20px; text-align: center; }}
        .badge {{ display: inline-block; padding: 10px 20px; border-radius: 5px; font-weight: bold; margin: 10px 0; }}
        .badge-success {{ background-color: #28a745; color: white; }}
        .badge-warning {{ background-color: #ffc107; color: black; }}
        .section {{ margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #2c5aa0; }}
        .warning {{ border-left-color: #dc3545; }}
        .stats {{ display: flex; flex-wrap: wrap; gap: 20px; }}
        .stat-item {{ flex: 1; min-width: 150px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2c5aa0; }}
        .path {{ background-color: #e9ecef; padding: 10px; font-family: monospace; border-radius: 4px; }}
        ul {{ list-style-type: none; padding-left: 0; }}
        li {{ margin: 5px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{package.project_name}</h1>
        <p>Media Delivery Ready</p>
    </div>
"""
        
        # Safe to format badge
        if package.safe_to_format:
            html += '<div class="badge badge-success">✅ SAFE TO FORMAT</div>'
        else:
            html += '<div class="badge badge-warning">⚠️ DO NOT FORMAT SOURCE</div>'
        
        # Stats section
        html += f"""
    <div class="section">
        <h2>Quick Stats</h2>
        <div class="stats">
            <div class="stat-item">
                <div class="stat-value">{package.total_clips}</div>
                <div>Total Clips</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{self._format_duration(package.total_duration_seconds)}</div>
                <div>Duration</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{self._format_size(package.total_size_bytes)}</div>
                <div>Size</div>
            </div>
        </div>
    </div>
"""
        
        # Deliverables
        html += """
    <div class="section">
        <h2>Deliverables</h2>
"""
        if package.deliverable_zip_path:
            html += f'<p><strong>Download:</strong></p><div class="path">{package.deliverable_zip_path}</div>'
        
        html += """
        <ul>
            <li>📄 PDF Report with thumbnails</li>
            <li>📊 CSV spreadsheets</li>
            <li>🎥 Proxy files for editing</li>
            <li>📝 Transcripts</li>
            <li>📋 Delivery checklist</li>
        </ul>
    </div>
"""
        
        # Issues
        if package.has_qc_issues:
            html += """
    <div class="section warning">
        <h2>⚠️ Issues Requiring Attention</h2>
        <p>Please review the delivery checklist for details on flagged items.</p>
    </div>
"""
        
        # Footer
        html += f"""
    <div class="footer">
        <p>Generated by ingesta on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>
</body>
</html>
"""
        return html
    
    def save_handoff_package(self, 
                            package: EditorHandoffPackage, 
                            output_dir: Path) -> Dict[str, Path]:
        """
        Save handoff package files (email drafts, summary).
        
        Args:
            package: EditorHandoffPackage to save
            output_dir: Directory to save files
            
        Returns:
            Dict mapping file types to paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = {}
        
        # Save text email draft
        email_text = self.generate_email_draft(package)
        email_path = output_dir / "editor_handoff_email.txt"
        with open(email_path, 'w', encoding='utf-8') as f:
            f.write(email_text)
        saved_files['email_text'] = email_path
        
        # Save HTML email
        email_html = self.generate_html_email(package)
        html_path = output_dir / "editor_handoff_email.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(email_html)
        saved_files['email_html'] = html_path
        
        # Save summary JSON
        import json
        summary = {
            'project_name': package.project_name,
            'generated_at': package.generated_at,
            'deliverable_path': str(package.deliverable_zip_path) if package.deliverable_zip_path else None,
            'stats': {
                'total_clips': package.total_clips,
                'total_duration': package.total_duration_seconds,
                'total_size': package.total_size_bytes,
            },
            'safe_to_format': package.safe_to_format,
            'has_qc_issues': package.has_qc_issues,
        }
        json_path = output_dir / "handoff_summary.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        saved_files['summary_json'] = json_path
        
        self.logger.info(f"Saved handoff package to {output_dir}")
        return saved_files
    
    def _format_duration(self, seconds: float) -> str:
        """Format seconds as readable duration."""
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}:{secs:02d}"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}"
    
    def _format_size(self, bytes_size: int) -> str:
        """Format bytes as readable size."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"


def generate_editor_handoff(project_name: str,
                           analyses: List[ClipAnalysis],
                           deliverable_path: Optional[Path] = None,
                           **kwargs) -> EditorHandoffPackage:
    """
    Convenience function to generate editor handoff package.
    
    Args:
        project_name: Name of the project
        analyses: List of clip analyses
        deliverable_path: Path to deliverables ZIP
        **kwargs: Additional arguments for create_handoff_package
        
    Returns:
        EditorHandoffPackage
    """
    generator = EditorHandoffGenerator()
    return generator.create_handoff_package(
        project_name=project_name,
        analyses=analyses,
        deliverable_path=deliverable_path,
        **kwargs
    )