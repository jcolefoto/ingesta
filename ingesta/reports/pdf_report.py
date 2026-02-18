"""
PDF report generator for ingesta media ingestion tool.

Generates professional formatted PDF reports with:
- Cover page with project info
- Clip details with thumbnails
- Summary statistics
- Metadata from camera XML files
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from ..analysis import ClipAnalysis, ClipType
from .xml_parser import XMLParser, CameraMetadata
from .thumbnails import ThumbnailExtractor


class PDFReportGenerator:
    """Generate professional PDF reports from clip analyses."""
    
    PAGE_SIZE = A4
    MARGIN = 0.75 * inch
    THUMBNAIL_WIDTH = 1.8 * inch
    THUMBNAIL_HEIGHT = 1.0 * inch
    
    def __init__(self, output_path: Optional[Path] = None,
                 project_name: Optional[str] = None,
                 source_path: Optional[str] = None,
                 destination_paths: Optional[List[str]] = None):
        """
        Initialize PDF report generator.
        
        Args:
            output_path: Path to save PDF file
            project_name: Name of the project
            source_path: Source media path
            destination_paths: List of destination/archive paths
        """
        self.output_path = output_path or Path("report.pdf")
        self.project_name = project_name or "Media Ingest Report"
        self.source_path = source_path or ""
        self.destination_paths = destination_paths or []
        self.logger = logging.getLogger(__name__)
        self.xml_parser = XMLParser()
        
        # Setup styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='CoverTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.HexColor('#1a1a1a')
        ))
        
        self.styles.add(ParagraphStyle(
            name='CoverSubtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor('#666666')
        ))
        
        self.styles.add(ParagraphStyle(
            name='ClipTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
            textColor=colors.HexColor('#2c5aa0')
        ))
        
        self.styles.add(ParagraphStyle(
            name='ClipInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=2
        ))
        
        self.styles.add(ParagraphStyle(
            name='SummaryTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2c5aa0')
        ))
    
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
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
    
    def get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes."""
        try:
            return file_path.stat().st_size
        except (OSError, FileNotFoundError):
            return 0
    
    def create_cover_page(self) -> List[Any]:
        """Create the cover page content."""
        elements = []
        
        # Add space at top
        elements.append(Spacer(1, 2 * inch))
        
        # Title
        elements.append(Paragraph(self.project_name, self.styles['CoverTitle']))
        
        # Subtitle
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph("Media Ingestion Report", self.styles['CoverSubtitle']))
        
        # Date
        elements.append(Spacer(1, 0.25 * inch))
        date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
        elements.append(Paragraph(f"Generated: {date_str}", self.styles['CoverSubtitle']))
        
        # Horizontal line
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cccccc')))
        elements.append(Spacer(1, 0.5 * inch))
        
        # Source and destination info
        if self.source_path:
            elements.append(Paragraph(f"<b>Source:</b> {self.source_path}", self.styles['CoverSubtitle']))
        
        if self.destination_paths:
            elements.append(Spacer(1, 0.25 * inch))
            elements.append(Paragraph("<b>Destinations:</b>", self.styles['CoverSubtitle']))
            for dest in self.destination_paths:
                elements.append(Paragraph(f"  • {dest}", self.styles['CoverSubtitle']))
        
        # Page break
        elements.append(PageBreak())
        
        return elements
    
    def create_summary_section(self, analyses: List[ClipAnalysis]) -> List[Any]:
        """Create the summary statistics section."""
        elements = []
        
        elements.append(Paragraph("Summary Statistics", self.styles['SummaryTitle']))
        elements.append(Spacer(1, 0.2 * inch))
        
        # Calculate statistics
        total_clips = len(analyses)
        total_duration = sum(a.duration for a in analyses)
        total_size = sum(self.get_file_size(a.file_path) for a in analyses)
        syncable_count = sum(1 for a in analyses if a.is_syncable)
        
        # Summary table data
        summary_data = [
            ['Metric', 'Value'],
            ['Total Clips', str(total_clips)],
            ['Total Duration', self.format_duration(total_duration)],
            ['Total Size', self.format_size(total_size)],
            ['Syncable Clips', f"{syncable_count} ({syncable_count/total_clips*100:.1f}%)" if total_clips > 0 else "0"],
        ]
        
        summary_table = Table(summary_data, colWidths=[2.5 * inch, 3.5 * inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        elements.append(summary_table)
        elements.append(Spacer(1, 0.3 * inch))
        
        # Breakdown by type
        elements.append(Paragraph("Clips by Type", self.styles['SummaryTitle']))
        elements.append(Spacer(1, 0.2 * inch))
        
        type_counts = {}
        for analysis in analyses:
            clip_type = analysis.clip_type.value.replace('_', ' ').title()
            type_counts[clip_type] = type_counts.get(clip_type, 0) + 1
        
        type_data = [['Type', 'Count', 'Percentage']]
        for clip_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = f"{count/total_clips*100:.1f}%" if total_clips > 0 else "0%"
            type_data.append([clip_type, str(count), percentage])
        
        type_table = Table(type_data, colWidths=[2.5 * inch, 1.5 * inch, 2 * inch])
        type_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5aa0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(type_table)
        elements.append(PageBreak())
        
        return elements
    
    def create_clip_section(self, analysis: ClipAnalysis, 
                           thumbnails: List[Path],
                           metadata: Optional[CameraMetadata] = None) -> List[Any]:
        """Create a section for a single clip."""
        elements = []
        
        file_path = analysis.file_path
        file_size = self.get_file_size(file_path)
        
        # Clip header
        elements.append(Paragraph(file_path.name, self.styles['ClipTitle']))
        
        # Basic info table
        info_data = [
            ['Duration:', self.format_duration(analysis.duration)],
            ['Size:', self.format_size(file_size)],
            ['Type:', analysis.clip_type.value.replace('_', ' ').title()],
            ['Audio:', analysis.audio_type.value.replace('_', ' ').title()],
            ['Syncable:', 'Yes' if analysis.is_syncable else 'No'],
        ]
        
        # Add camera metadata if available
        if metadata:
            if metadata.camera_model:
                info_data.append(['Camera:', metadata.camera_model])
            if metadata.date_created:
                date_str = metadata.date_created.strftime("%Y-%m-%d %H:%M")
                info_data.append(['Date:', date_str])
            if metadata.lens:
                info_data.append(['Lens:', metadata.lens])
            if metadata.iso:
                info_data.append(['ISO:', str(metadata.iso)])
        
        info_table = Table(info_data, colWidths=[1.2 * inch, 2.5 * inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        elements.append(info_table)
        elements.append(Spacer(1, 0.15 * inch))
        
        # Thumbnails
        if thumbnails:
            thumb_row = []
            for thumb_path in thumbnails[:6]:  # Max 6 thumbnails
                if thumb_path.exists():
                    try:
                        img = Image(str(thumb_path), width=self.THUMBNAIL_WIDTH, height=self.THUMBNAIL_HEIGHT)
                        thumb_row.append(img)
                    except Exception as e:
                        self.logger.warning(f"Failed to load thumbnail {thumb_path}: {e}")
            
            if thumb_row:
                # Arrange thumbnails in a table (3 per row)
                rows = []
                current_row = []
                for i, thumb in enumerate(thumb_row):
                    current_row.append(thumb)
                    if len(current_row) == 3:
                        rows.append(current_row)
                        current_row = []
                if current_row:
                    # Pad with empty cells
                    while len(current_row) < 3:
                        current_row.append('')
                    rows.append(current_row)
                
                thumb_table = Table(rows, colWidths=[self.THUMBNAIL_WIDTH] * 3,
                                   rowHeights=[self.THUMBNAIL_HEIGHT] * len(rows))
                thumb_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ]))
                
                elements.append(thumb_table)
        
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#dddddd')))
        elements.append(Spacer(1, 0.1 * inch))
        
        return elements
    
    def generate_report(self, analyses: List[ClipAnalysis],
                       thumbnails: Optional[Dict[Path, List[Path]]] = None,
                       output_path: Optional[Path] = None) -> Path:
        """
        Generate PDF report from clip analyses.
        
        Args:
            analyses: List of ClipAnalysis objects
            thumbnails: Optional dict mapping video paths to thumbnail paths
            output_path: Override output path
            
        Returns:
            Path to generated PDF file
        """
        if output_path:
            pdf_path = Path(output_path)
        else:
            pdf_path = self.output_path
        
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Generating PDF report: {pdf_path}")
        
        thumbnails = thumbnails or {}
        
        # Create document
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=self.PAGE_SIZE,
            rightMargin=self.MARGIN,
            leftMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=self.MARGIN
        )
        
        # Build document elements
        elements = []
        
        # Cover page
        elements.extend(self.create_cover_page())
        
        # Summary section
        elements.extend(self.create_summary_section(analyses))
        
        # Individual clip sections
        elements.append(Paragraph("Clip Details", self.styles['Heading1']))
        elements.append(Spacer(1, 0.2 * inch))
        
        for i, analysis in enumerate(analyses):
            self.logger.debug(f"Processing clip {i+1}/{len(analyses)}: {analysis.file_path.name}")
            
            # Get metadata
            metadata = self.xml_parser.get_metadata_for_clip(analysis.file_path)
            
            # Get thumbnails
            clip_thumbnails = thumbnails.get(analysis.file_path, [])
            
            # Create clip section
            clip_elements = self.create_clip_section(analysis, clip_thumbnails, metadata)
            
            # Add to document (keep together if possible)
            elements.extend(clip_elements)
        
        # Build PDF
        doc.build(elements)
        
        self.logger.info(f"PDF report generated: {pdf_path}")
        return pdf_path
