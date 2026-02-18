"""
CSV report generator for ingesta media ingestion tool.

Generates CSV reports containing clip metadata for spreadsheet analysis.
"""

import csv
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..analysis import ClipAnalysis
from .xml_parser import XMLParser, CameraMetadata


class CSVReportGenerator:
    """Generate CSV reports from clip analyses."""
    
    DEFAULT_COLUMNS = [
        'Filename',
        'Duration',
        'Size',
        'Type',
        'Audio Type',
        'Syncable',
        'Camera',
        'Date Created',
        'Destination Path',
        'Checksum',
        'Resolution',
        'Frame Rate',
        'Codec',
        'Motion Score',
        'Audio Score',
        'Confidence'
    ]
    
    def __init__(self, output_path: Optional[Path] = None):
        """
        Initialize CSV report generator.
        
        Args:
            output_path: Path to save CSV file (default: report.csv in current dir)
        """
        self.output_path = output_path or Path("report.csv")
        self.logger = logging.getLogger(__name__)
        self.xml_parser = XMLParser()
    
    def format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS or HH:MM:SS."""
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes:02d}:{secs:02d}"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def format_size(self, bytes_size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} PB"
    
    def get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        try:
            return file_path.stat().st_size
        except (OSError, FileNotFoundError):
            return 0
    
    def format_datetime(self, dt: Optional[datetime]) -> str:
        """Format datetime for CSV."""
        if dt is None:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def create_row(self, analysis: ClipAnalysis, 
                   metadata: Optional[CameraMetadata] = None,
                   checksum: Optional[str] = None) -> Dict[str, str]:
        """
        Create a CSV row from clip analysis and metadata.
        
        Args:
            analysis: ClipAnalysis object
            metadata: Optional CameraMetadata from XML sidecar
            checksum: Optional checksum string
            
        Returns:
            Dictionary representing a CSV row
        """
        file_path = analysis.file_path
        file_size = self.get_file_size(file_path)
        
        # Get video metadata from analysis
        video_info = analysis.metadata.get('video_info', {})
        format_info = video_info.get('format', {})
        streams = video_info.get('streams', [])
        
        # Find video stream
        video_stream = None
        for stream in streams:
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        # Get resolution and frame rate from video stream or metadata
        resolution = ""
        frame_rate = ""
        codec = ""
        
        if metadata:
            if metadata.resolution:
                resolution = metadata.resolution
            if metadata.frame_rate:
                frame_rate = f"{metadata.frame_rate:.2f} fps"
            if metadata.codec:
                codec = metadata.codec
        
        if video_stream:
            if not resolution:
                width = video_stream.get('width', '')
                height = video_stream.get('height', '')
                if width and height:
                    resolution = f"{width}x{height}"
            
            if not frame_rate:
                fps = video_stream.get('r_frame_rate', '')
                if fps and '/' in str(fps):
                    num, den = str(fps).split('/')
                    try:
                        frame_rate = f"{float(num)/float(den):.2f} fps"
                    except (ValueError, ZeroDivisionError):
                        frame_rate = str(fps)
                elif fps:
                    frame_rate = f"{fps} fps"
            
            if not codec:
                codec = video_stream.get('codec_name', '')
        
        row = {
            'Filename': file_path.name,
            'Duration': self.format_duration(analysis.duration),
            'Size': self.format_size(file_size),
            'Type': analysis.clip_type.value.replace('_', ' ').title(),
            'Audio Type': analysis.audio_type.value.replace('_', ' ').title(),
            'Syncable': 'Yes' if analysis.is_syncable else 'No',
            'Camera': metadata.camera_model if metadata else "",
            'Date Created': self.format_datetime(metadata.date_created if metadata else None),
            'Destination Path': str(file_path.parent),
            'Checksum': checksum or "",
            'Resolution': resolution,
            'Frame Rate': frame_rate,
            'Codec': codec,
            'Motion Score': f"{analysis.motion_score:.2f}",
            'Audio Score': f"{analysis.audio_score:.2f}",
            'Confidence': f"{analysis.confidence:.2f}"
        }
        
        return row
    
    def generate_report(self, analyses: List[ClipAnalysis],
                       checksums: Optional[Dict[Path, str]] = None,
                       output_path: Optional[Path] = None) -> Path:
        """
        Generate CSV report from clip analyses.
        
        Args:
            analyses: List of ClipAnalysis objects
            checksums: Optional dict mapping file paths to checksums
            output_path: Override output path
            
        Returns:
            Path to generated CSV file
        """
        if output_path:
            csv_path = Path(output_path)
        else:
            csv_path = self.output_path
        
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Generating CSV report: {csv_path}")
        
        checksums = checksums or {}
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.DEFAULT_COLUMNS)
            writer.writeheader()
            
            for analysis in analyses:
                # Try to get XML metadata
                metadata = self.xml_parser.get_metadata_for_clip(analysis.file_path)
                
                # Get checksum if available
                checksum = checksums.get(analysis.file_path)
                
                # Create row
                row = self.create_row(analysis, metadata, checksum)
                writer.writerow(row)
        
        self.logger.info(f"CSV report generated: {csv_path}")
        return csv_path
    
    def generate_summary_csv(self, analyses: List[ClipAnalysis],
                            output_path: Optional[Path] = None) -> Path:
        """
        Generate summary statistics CSV.
        
        Args:
            analyses: List of ClipAnalysis objects
            output_path: Override output path
            
        Returns:
            Path to generated summary CSV file
        """
        if output_path:
            csv_path = Path(output_path)
        else:
            csv_path = self.output_path.parent / f"{self.output_path.stem}_summary.csv"
        
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Calculate statistics
        from ..analysis import ClipType
        
        total_clips = len(analyses)
        total_duration = sum(a.duration for a in analyses)
        total_size = sum(self.get_file_size(a.file_path) for a in analyses)
        syncable_count = sum(1 for a in analyses if a.is_syncable)
        
        # Count by type
        type_counts = {}
        for analysis in analyses:
            clip_type = analysis.clip_type.value
            type_counts[clip_type] = type_counts.get(clip_type, 0) + 1
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write summary
            writer.writerow(['Report Generated', datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            writer.writerow([])
            writer.writerow(['Summary Statistics'])
            writer.writerow(['Total Clips', total_clips])
            writer.writerow(['Total Duration', self.format_duration(total_duration)])
            writer.writerow(['Total Size', self.format_size(total_size)])
            writer.writerow(['Syncable Clips', syncable_count])
            writer.writerow([])
            writer.writerow(['Clips by Type'])
            writer.writerow(['Type', 'Count'])
            for clip_type, count in sorted(type_counts.items()):
                writer.writerow([clip_type.replace('_', ' ').title(), count])
        
        self.logger.info(f"Summary CSV generated: {csv_path}")
        return csv_path
