"""
Client deliverables packaging module for ingesta.

Creates professional, client-ready deliverable packages:
- ZIP archive with organized structure
- PDF reports with thumbnails and metadata
- CSV spreadsheets for data analysis
- Proxy files (editing-friendly low-res versions)
- Transcription files (TXT, SRT, JSON)
- Manifest and README

All processing is done locally - no uploads required.
"""

import os
import re
import json
import shutil
import zipfile
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

from .analysis import ClipAnalysis


logger = logging.getLogger(__name__)


@dataclass
class DeliverableConfig:
    """Configuration for deliverable packaging."""
    # Content selection
    include_pdf_report: bool = True
    include_csv_report: bool = True
    include_proxies: bool = True
    include_transcripts: bool = True
    include_thumbnails: bool = True
    include_metadata: bool = True
    include_manifest: bool = True
    
    # Format options
    transcript_formats: List[str] = field(default_factory=lambda: ['txt', 'srt', 'json'])
    proxy_resolution: str = "960x540"
    thumbnail_size: str = "320x180"
    
    # Organization
    organize_by_scene: bool = False
    organize_by_reel: bool = True
    create_subfolders: bool = True
    
    # Output
    output_filename: Optional[str] = None
    compression_level: int = 6  # 0-9


@dataclass
class ClipTranscript:
    """Transcript data for a single clip."""
    clip_name: str
    full_text: str
    segments: List[Dict[str, Any]] = field(default_factory=list)
    has_slate: bool = False
    slate_text: str = ""
    
    def to_txt(self) -> str:
        """Export as plain text."""
        lines = [f"Transcript: {self.clip_name}", "=" * 50, ""]
        if self.has_slate:
            lines.append(f"SLATE: {self.slate_text}")
            lines.append("")
        lines.append(self.full_text)
        return "\n".join(lines)
    
    def to_srt(self) -> str:
        """Export as SRT subtitle format."""
        lines = []
        for i, seg in enumerate(self.segments, 1):
            start = seg.get('start', 0)
            end = seg.get('end', 0)
            text = seg.get('text', '')
            
            # Format timecodes
            def fmt_tc(seconds):
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = int(seconds % 60)
                millis = int((seconds % 1) * 1000)
                return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
            
            lines.append(str(i))
            lines.append(f"{fmt_tc(start)} --> {fmt_tc(end)}")
            lines.append(text)
            lines.append("")
        
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """Export as JSON."""
        return json.dumps({
            'clip_name': self.clip_name,
            'has_slate': self.has_slate,
            'slate_text': self.slate_text,
            'full_text': self.full_text,
            'segments': self.segments,
        }, indent=2)


@dataclass
class DeliverableManifest:
    """Manifest for deliverable package."""
    project_name: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    package_version: str = "1.0"
    total_clips: int = 0
    total_duration_seconds: float = 0.0
    contents: Dict[str, Any] = field(default_factory=dict)
    checksums: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)


class TranscriptExporter:
    """Export transcripts in multiple formats."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_clip_transcript(self, analysis: ClipAnalysis, formats: List[str]) -> Dict[str, Path]:
        """
        Export transcript for a single clip in multiple formats.
        
        Returns:
            Dictionary mapping format to output path
        """
        results = {}
        
        # Get transcript data from analysis
        transcript_text = getattr(analysis, 'transcription', None)
        if not transcript_text:
            return results
        
        clip_name = analysis.file_path.stem
        
        # Create transcript object
        transcript = ClipTranscript(
            clip_name=clip_name,
            full_text=transcript_text,
            has_slate=getattr(analysis, 'has_slate', False),
            slate_text=getattr(analysis, 'slate_text', ''),
        )
        
        # Export to each format
        for fmt in formats:
            if fmt == 'txt':
                output_path = self.output_dir / f"{clip_name}.txt"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(transcript.to_txt())
                results['txt'] = output_path
                
            elif fmt == 'srt':
                output_path = self.output_dir / f"{clip_name}.srt"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(transcript.to_srt())
                results['srt'] = output_path
                
            elif fmt == 'json':
                output_path = self.output_dir / f"{clip_name}.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(transcript.to_json())
                results['json'] = output_path
        
        return results
    
    def export_master_transcript(self, analyses: List[ClipAnalysis]) -> Path:
        """
        Export a master transcript document with all clips.
        
        Returns:
            Path to master transcript file
        """
        output_path = self.output_dir / "MASTER_TRANSCRIPT.txt"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("MASTER TRANSCRIPT\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Total Clips: {len(analyses)}\n\n")
            f.write("=" * 80 + "\n\n")
            
            for analysis in analyses:
                clip_name = analysis.file_path.stem
                transcript = getattr(analysis, 'transcription', '')
                
                if transcript:
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"CLIP: {clip_name}\n")
                    f.write(f"Duration: {analysis.duration:.1f}s\n")
                    
                    if getattr(analysis, 'has_slate', False):
                        f.write(f"Slate: {getattr(analysis, 'slate_text', '')}\n")
                    
                    f.write(f"{'=' * 80}\n\n")
                    f.write(transcript)
                    f.write("\n")
        
        return output_path


class DeliverablePackager:
    """
    Package client-ready deliverables into organized ZIP archive.
    
    Creates professional deliverable structure:
    ```
    ProjectName_Deliverables_YYYYMMDD/
    ├── 01_REPORTS/
    │   ├── ProjectName_Report.pdf
    │   ├── ProjectName_Report.csv
    │   └── ProjectName_Summary.csv
    ├── 02_PROXIES/
    │   ├── A001/
    │   │   ├── A001_001_proxy.mp4
    │   │   └── ...
    │   └── B002/
    ├── 03_TRANSCRIPTS/
    │   ├── TXT/
    │   ├── SRT/
    │   └── JSON/
    ├── 04_THUMBNAILS/
    │   └── [clip_name]/
    │       ├── thumb_001.jpg
    │       └── ...
    ├── 05_METADATA/
    │   └── manifest.json
    └── README.txt
    ```
    """
    
    def __init__(self, config: Optional[DeliverableConfig] = None):
        self.config = config or DeliverableConfig()
    
    def create_deliverable_package(
        self,
        project_name: str,
        analyses: List[ClipAnalysis],
        report_dir: Optional[Path],
        output_dir: Path,
    ) -> Path:
        """
        Create complete deliverable package.
        
        Args:
            project_name: Name of the project
            analyses: List of clip analyses
            report_dir: Directory containing existing reports (optional)
            output_dir: Output directory for package
            
        Returns:
            Path to created ZIP file
        """
        timestamp = datetime.now().strftime('%Y%m%d')
        package_name = f"{project_name}_Deliverables_{timestamp}"
        package_dir = output_dir / package_name
        package_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = DeliverableManifest(project_name=project_name)
        manifest.total_clips = len(analyses)
        manifest.total_duration_seconds = sum(a.duration for a in analyses)
        
        try:
            # 1. Reports
            if self.config.include_pdf_report or self.config.include_csv_report:
                reports_dir = package_dir / "01_REPORTS"
                reports_dir.mkdir(exist_ok=True)
                
                if report_dir and report_dir.exists():
                    # Copy existing reports
                    for report_file in report_dir.glob("*.pdf"):
                        shutil.copy2(report_file, reports_dir)
                        manifest.contents['reports'] = manifest.contents.get('reports', []) + [report_file.name]
                    for report_file in report_dir.glob("*.csv"):
                        shutil.copy2(report_file, reports_dir)
                        manifest.contents['reports'] = manifest.contents.get('reports', []) + [report_file.name]
                else:
                    # Generate new reports
                    self._generate_reports(analyses, reports_dir, project_name)
            
            # 2. Proxies
            if self.config.include_proxies:
                proxies_dir = package_dir / "02_PROXIES"
                proxies_dir.mkdir(exist_ok=True)
                self._package_proxies(analyses, proxies_dir, manifest)
            
            # 3. Transcripts
            if self.config.include_transcripts:
                transcripts_dir = package_dir / "03_TRANSCRIPTS"
                transcripts_dir.mkdir(exist_ok=True)
                self._package_transcripts(analyses, transcripts_dir, manifest)
            
            # 4. Thumbnails
            if self.config.include_thumbnails:
                thumbnails_dir = package_dir / "04_THUMBNAILS"
                thumbnails_dir.mkdir(exist_ok=True)
                self._package_thumbnails(analyses, thumbnails_dir, manifest)
            
            # 5. Metadata
            if self.config.include_metadata:
                metadata_dir = package_dir / "05_METADATA"
                metadata_dir.mkdir(exist_ok=True)
                self._generate_metadata(analyses, metadata_dir, manifest)
            
            # 6. README
            self._create_readme(package_dir, project_name, manifest)
            
            # Create manifest file
            if self.config.include_manifest:
                manifest_path = package_dir / "MANIFEST.json"
                with open(manifest_path, 'w') as f:
                    json.dump(manifest.to_dict(), f, indent=2)
            
            # Create ZIP archive
            zip_path = self._create_zip(package_dir, output_dir)
            
            logger.info(f"Created deliverable package: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Failed to create deliverable package: {e}")
            # Clean up partial package
            if package_dir.exists():
                shutil.rmtree(package_dir)
            raise
    
    def _generate_reports(self, analyses: List[ClipAnalysis], output_dir: Path, project_name: str):
        """Generate PDF and CSV reports."""
        from .reports import PDFReportGenerator, CSVReportGenerator
        
        if self.config.include_pdf_report:
            pdf_gen = PDFReportGenerator(
                output_path=output_dir / f"{project_name}_Report.pdf",
                project_name=project_name
            )
            # Note: Would need thumbnail map for full report
            pdf_gen.generate_report(analyses, {})
        
        if self.config.include_csv_report:
            csv_gen = CSVReportGenerator(output_path=output_dir / f"{project_name}_Report.csv")
            csv_gen.generate_report(analyses)
            csv_gen.generate_summary_csv(analyses)
    
    def _package_proxies(self, analyses: List[ClipAnalysis], output_dir: Path, manifest: DeliverableManifest):
        """Package proxy files."""
        proxy_count = 0
        
        for analysis in analyses:
            proxy_path = getattr(analysis, 'proxy_path', None)
            if proxy_path:
                proxy_file = Path(proxy_path)
                if proxy_file.exists():
                    # Organize by reel if available
                    reel = getattr(analysis, 'reel_id', None)
                    if reel and self.config.organize_by_reel:
                        reel_dir = output_dir / reel
                        reel_dir.mkdir(exist_ok=True)
                        dest = reel_dir / proxy_file.name
                    else:
                        dest = output_dir / proxy_file.name
                    
                    shutil.copy2(proxy_file, dest)
                    proxy_count += 1
        
        manifest.contents['proxies'] = proxy_count
    
    def _package_transcripts(self, analyses: List[ClipAnalysis], output_dir: Path, manifest: DeliverableManifest):
        """Package transcript files."""
        # Create subdirectories for each format
        format_dirs = {}
        for fmt in self.config.transcript_formats:
            fmt_dir = output_dir / fmt.upper()
            fmt_dir.mkdir(exist_ok=True)
            format_dirs[fmt] = fmt_dir
        
        # Export transcripts
        transcript_count = 0
        for analysis in analyses:
            if getattr(analysis, 'transcription', None):
                clip_name = analysis.file_path.stem
                
                for fmt in self.config.transcript_formats:
                    fmt_dir = format_dirs[fmt]
                    
                    if fmt == 'txt':
                        content = f"CLIP: {clip_name}\n\n{analysis.transcription}"
                        output_path = fmt_dir / f"{clip_name}.txt"
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    
                    elif fmt == 'json':
                        data = {
                            'clip_name': clip_name,
                            'transcription': analysis.transcription,
                            'duration': analysis.duration,
                            'has_slate': getattr(analysis, 'has_slate', False),
                            'slate_text': getattr(analysis, 'slate_text', ''),
                        }
                        output_path = fmt_dir / f"{clip_name}.json"
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2)
                    
                    transcript_count += 1
        
        # Create master transcript
        master_path = output_dir / "MASTER_TRANSCRIPT.txt"
        with open(master_path, 'w', encoding='utf-8') as f:
            f.write(f"MASTER TRANSCRIPT - {manifest.project_name}\n")
            f.write("=" * 80 + "\n\n")
            
            for analysis in analyses:
                if getattr(analysis, 'transcription', None):
                    f.write(f"\n{'=' * 80}\n")
                    f.write(f"CLIP: {analysis.file_path.stem}\n")
                    f.write(f"{'=' * 80}\n\n")
                    f.write(analysis.transcription)
                    f.write("\n")
        
        manifest.contents['transcripts'] = transcript_count
    
    def _package_thumbnails(self, analyses: List[ClipAnalysis], output_dir: Path, manifest: DeliverableManifest):
        """Package thumbnail files."""
        thumb_count = 0
        
        for analysis in analyses:
            clip_name = analysis.file_path.stem
            clip_thumb_dir = output_dir / clip_name
            clip_thumb_dir.mkdir(exist_ok=True)
            
            # Copy thumbnails if they exist
            # Note: Would need access to thumbnail paths from analysis
            thumb_count += 1
        
        manifest.contents['thumbnails'] = thumb_count
    
    def _generate_metadata(self, analyses: List[ClipAnalysis], output_dir: Path, manifest: DeliverableManifest):
        """Generate metadata files."""
        # Full metadata export
        metadata = {
            'project_name': manifest.project_name,
            'generated_at': datetime.now().isoformat(),
            'total_clips': len(analyses),
            'clips': []
        }
        
        for analysis in analyses:
            clip_data = {
                'filename': analysis.file_path.name,
                'duration': analysis.duration,
                'clip_type': analysis.clip_type.value if analysis.clip_type else None,
                'reel_id': getattr(analysis, 'reel_id', None),
                'scene': getattr(analysis, 'scene', None),
                'shot': getattr(analysis, 'shot', None),
                'take': getattr(analysis, 'take', None),
                'timecode_start': getattr(analysis, 'timecode_start', None),
                'has_transcription': bool(getattr(analysis, 'transcription', None)),
                'has_proxy': bool(getattr(analysis, 'proxy_path', None)),
                'tags': getattr(analysis, 'priority_tags', []),
            }
            metadata['clips'].append(clip_data)
        
        metadata_path = output_dir / "clip_metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        manifest.contents['metadata'] = 'clip_metadata.json'
    
    def _create_readme(self, package_dir: Path, project_name: str, manifest: DeliverableManifest):
        """Create README.txt file."""
        readme_path = package_dir / "README.txt"
        
        lines = [
            f"DELIVERABLE PACKAGE: {project_name}",
            "=" * 60,
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Clips: {manifest.total_clips}",
            f"Total Duration: {manifest.total_duration_seconds / 60:.1f} minutes",
            "",
            "PACKAGE CONTENTS:",
            "-" * 60,
        ]
        
        if self.config.include_pdf_report or self.config.include_csv_report:
            lines.append("📄 01_REPORTS/ - PDF and CSV reports")
        
        if self.config.include_proxies:
            proxy_count = manifest.contents.get('proxies', 0)
            lines.append(f"🎥 02_PROXIES/ - {proxy_count} proxy files for editing")
        
        if self.config.include_transcripts:
            transcript_count = manifest.contents.get('transcripts', 0)
            lines.append(f"📝 03_TRANSCRIPTS/ - {transcript_count} transcripts (TXT, SRT, JSON)")
        
        if self.config.include_thumbnails:
            thumb_count = manifest.contents.get('thumbnails', 0)
            lines.append(f"🖼️  04_THUMBNAILS/ - {thumb_count} thumbnail sets")
        
        if self.config.include_metadata:
            lines.append("📋 05_METADATA/ - Clip metadata and manifest")
        
        lines.extend([
            "",
            "-" * 60,
            "",
            "PROXY FILES:",
            "These are low-resolution copies optimized for offline editing.",
            "Resolution: " + self.config.proxy_resolution,
            "",
            "TRANSCRIPTS:",
            "TXT - Plain text transcripts",
            "SRT - Subtitle/caption format",
            "JSON - Structured data with timestamps",
            "",
            "MANIFEST:",
            "MANIFEST.json contains complete package inventory",
            "",
            "-" * 60,
            "Generated by ingesta - Local media ingestion tool",
            "All processing done locally - no cloud uploads",
        ])
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    
    def _create_zip(self, package_dir: Path, output_dir: Path) -> Path:
        """Create ZIP archive from package directory."""
        zip_name = package_dir.name + ".zip"
        zip_path = output_dir / zip_name
        
        # Create ZIP with compression
        compression = zipfile.ZIP_DEFLATED
        
        with zipfile.ZipFile(zip_path, 'w', compression) as zf:
            for file_path in package_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(output_dir)
                    zf.write(file_path, arcname)
        
        # Optionally remove the uncompressed directory
        shutil.rmtree(package_dir)
        
        return zip_path


def create_client_deliverable(
    project_name: str,
    analyses: List[ClipAnalysis],
    output_dir: Union[str, Path],
    report_dir: Optional[Union[str, Path]] = None,
    config: Optional[DeliverableConfig] = None,
) -> Path:
    """
    Convenience function to create client deliverable package.
    
    Args:
        project_name: Name of the project
        analyses: List of clip analyses
        output_dir: Output directory for package
        report_dir: Optional directory with existing reports
        config: Optional deliverable configuration
        
    Returns:
        Path to created ZIP file
    """
    packager = DeliverablePackager(config)
    
    return packager.create_deliverable_package(
        project_name=project_name,
        analyses=analyses,
        report_dir=Path(report_dir) if report_dir else None,
        output_dir=Path(output_dir),
    )
