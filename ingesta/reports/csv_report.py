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
from .bin_organizer import BinOrganizer, ClipOrganization, format_duration


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
        'Confidence',
        'Bin',
        'Bin Type',
        'Reel',
        'Visual Description',
        'Shot Type',
        'Transcription Excerpt',
        'Has Slate',
        'Slate Text',
        'Has End Mark',
        # Audio technical
        'Audio Peak dBFS',
        'Audio RMS dBFS',
        'Audio Clipping',
        'Audio Channels',
        'Audio Sample Rate',
        # Metadata
        'Timecode Start',
        'Timecode End',
        'Scene',
        'Shot',
        'Take',
        'Camera ID',
        'Camera Model',
        'Camera Serial',
        'Lens Info',
        'ISO',
        'White Balance',
        # Quality warnings
        'Quality Warnings',
        'Is Corrupted',
        'Black Frame Count',
        'Blur Score',
        'Silence Ratio',
        # Duplicate detection
        'Is Duplicate',
        'Duplicate Of',
        'Duplicate Type',
        # Keywords
        'Keyword Tags',
        'Priority Tags',
        # Proxy paths
        'Proxy Path',
        'Hero Still Path',
        'Web Proxy Path',
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
            'Resolution': resolution if resolution else (analysis.resolution or ""),
            'Frame Rate': frame_rate if frame_rate else (f"{analysis.frame_rate:.2f} fps" if analysis.frame_rate else ""),
            'Codec': codec,
            'Motion Score': f"{analysis.motion_score:.2f}",
            'Audio Score': f"{analysis.audio_score:.2f}",
            'Confidence': f"{analysis.confidence:.2f}",
            'Bin': "",
            'Bin Type': "",
            'Reel': analysis.reel_id or "",
            'Visual Description': analysis.visual_description or "",
            'Shot Type': analysis.shot_type or "",
            'Transcription Excerpt': analysis.transcription_excerpt or "",
            'Has Slate': 'Yes' if analysis.has_slate else 'No',
            'Slate Text': analysis.slate_text or "",
            'Has End Mark': 'Yes' if analysis.has_end_mark else 'No',
            # Audio technical
            'Audio Peak dBFS': f"{analysis.audio_peak_dbfs:.1f}" if analysis.audio_peak_dbfs is not None else "",
            'Audio RMS dBFS': f"{analysis.audio_rms_dbfs:.1f}" if analysis.audio_rms_dbfs is not None else "",
            'Audio Clipping': 'Yes' if analysis.audio_clipping else 'No',
            'Audio Channels': str(analysis.audio_channels) if analysis.audio_channels else "",
            'Audio Sample Rate': f"{analysis.audio_sample_rate} Hz" if analysis.audio_sample_rate else "",
            # Metadata
            'Timecode Start': analysis.timecode_start or "",
            'Timecode End': analysis.timecode_end or "",
            'Scene': analysis.scene or "",
            'Shot': analysis.shot or "",
            'Take': analysis.take or "",
            'Camera ID': analysis.camera_id or "",
            'Camera Model': analysis.camera_model or "",
            'Camera Serial': analysis.camera_serial or "",
            'Lens Info': analysis.lens_info or "",
            'ISO': str(analysis.iso) if analysis.iso else "",
            'White Balance': analysis.white_balance or "",
            # Quality warnings
            'Quality Warnings': '; '.join(analysis.quality_warnings) if analysis.quality_warnings else "",
            'Is Corrupted': 'Yes' if analysis.is_corrupted else 'No',
            'Black Frame Count': str(analysis.black_frame_count) if analysis.black_frame_count else "",
            'Blur Score': f"{analysis.blur_score:.2f}" if analysis.blur_score else "",
            'Silence Ratio': f"{analysis.silence_ratio:.2%}" if analysis.silence_ratio else "",
            # Duplicate detection
            'Is Duplicate': 'Yes' if analysis.is_duplicate else 'No',
            'Duplicate Of': ', '.join(analysis.duplicate_of) if analysis.duplicate_of else "",
            'Duplicate Type': analysis.duplicate_type or "",
            # Keywords
            'Keyword Tags': ', '.join(analysis.keyword_tags[:10]) if analysis.keyword_tags else "",
            'Priority Tags': ', '.join(analysis.priority_tags[:5]) if analysis.priority_tags else "",
            # Proxy paths
            'Proxy Path': analysis.proxy_path or "",
            'Hero Still Path': analysis.hero_still_path or "",
            'Web Proxy Path': analysis.web_proxy_path or "",
        }
        
        return row
    
    def create_row_with_bin(self, analysis: ClipAnalysis,
                           bin_name: str,
                           bin_type: str,
                           reel: str = "",
                           metadata: Optional[CameraMetadata] = None,
                           checksum: Optional[str] = None) -> Dict[str, str]:
        """
        Create a CSV row from clip analysis with bin information.
        
        Args:
            analysis: ClipAnalysis object
            bin_name: Name of the bin this clip belongs to
            bin_type: Type of the bin
            reel: Reel identifier
            metadata: Optional CameraMetadata from XML sidecar
            checksum: Optional checksum string
            
        Returns:
            Dictionary representing a CSV row
        """
        row = self.create_row(analysis, metadata, checksum)
        row['Bin'] = bin_name
        row['Bin Type'] = bin_type
        row['Reel'] = reel
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
    
    def generate_binned_report(self, organization: ClipOrganization,
                              checksums: Optional[Dict[Path, str]] = None,
                              output_path: Optional[Path] = None) -> Path:
        """
        Generate CSV report with ShotPut-style bin organization.
        
        Args:
            organization: ClipOrganization with binned clips
            checksums: Optional dict mapping file paths to checksums
            output_path: Override output path
            
        Returns:
            Path to generated CSV file
        """
        if output_path:
            csv_path = Path(output_path)
        else:
            csv_path = self.output_path.parent / f"{self.output_path.stem}_binned.csv"
        
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Generating binned CSV report: {csv_path}")
        
        checksums = checksums or {}
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.DEFAULT_COLUMNS)
            writer.writeheader()
            
            # Write clips from each bin
            for bin_obj in organization.bins:
                for analysis in bin_obj.clips:
                    # Try to get XML metadata
                    metadata = self.xml_parser.get_metadata_for_clip(analysis.file_path)
                    
                    # Get checksum if available
                    checksum = checksums.get(analysis.file_path)
                    
                    # Create row with bin info
                    reel = bin_obj.name if bin_obj.bin_type.value == 'camera_reel' else ""
                    row = self.create_row_with_bin(
                        analysis,
                        bin_name=bin_obj.name,
                        bin_type=bin_obj.bin_type.value.replace('_', ' ').title(),
                        reel=reel,
                        metadata=metadata,
                        checksum=checksum
                    )
                    writer.writerow(row)
            
            # Write unclassified clips
            for analysis in organization.unclassified:
                metadata = self.xml_parser.get_metadata_for_clip(analysis.file_path)
                checksum = checksums.get(analysis.file_path)
                row = self.create_row_with_bin(
                    analysis,
                    bin_name="Unclassified",
                    bin_type="Unclassified",
                    reel="",
                    metadata=metadata,
                    checksum=checksum
                )
                writer.writerow(row)
        
        self.logger.info(f"Binned CSV report generated: {csv_path}")
        return csv_path
    
    def generate_bin_summary_csv(self, organization: ClipOrganization,
                                  output_path: Optional[Path] = None) -> Path:
        """
        Generate a summary CSV of bins.
        
        Args:
            organization: ClipOrganization with binned clips
            output_path: Override output path
            
        Returns:
            Path to generated summary CSV file
        """
        if output_path:
            csv_path = Path(output_path)
        else:
            csv_path = self.output_path.parent / f"{self.output_path.stem}_bin_summary.csv"
        
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow(['Bin Name', 'Bin Type', 'Clip Count', 'Total Duration', 'Percentage'])
            
            # Bin rows
            total_clips = organization.total_clips
            for bin_obj in organization.bins:
                percentage = f"{bin_obj.clip_count/total_clips*100:.1f}%" if total_clips > 0 else "0%"
                writer.writerow([
                    bin_obj.name,
                    bin_obj.bin_type.value.replace('_', ' ').title(),
                    bin_obj.clip_count,
                    format_duration(bin_obj.total_duration),
                    percentage
                ])
            
            # Unclassified row
            if organization.unclassified:
                unclass_count = len(organization.unclassified)
                unclass_duration = sum(c.duration for c in organization.unclassified)
                percentage = f"{unclass_count/total_clips*100:.1f}%" if total_clips > 0 else "0%"
                writer.writerow([
                    "Unclassified",
                    "Unclassified",
                    unclass_count,
                    format_duration(unclass_duration),
                    percentage
                ])
        
        self.logger.info(f"Bin summary CSV generated: {csv_path}")
        return csv_path
    
    def generate_summary_csv(self, analyses: List[ClipAnalysis],
                            output_path: Optional[Path] = None,
                            safe_to_format_status: Optional[dict] = None) -> Path:
        """
        Generate summary statistics CSV.

        Args:
            analyses: List of ClipAnalysis objects
            output_path: Override output path
            safe_to_format_status: Optional safe to format status from ingestion job

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

            # Safe to format section
            if safe_to_format_status:
                writer.writerow(['SAFE TO FORMAT STATUS'])
                writer.writerow(['Status', safe_to_format_status['badge']])
                writer.writerow(['Safe to Format', 'YES' if safe_to_format_status['safe'] else 'NO'])
                writer.writerow(['Reason', safe_to_format_status['reason']])
                writer.writerow(['Verified Files', safe_to_format_status['verified_count']])
                writer.writerow(['Failed Files', safe_to_format_status['failed_count']])
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
