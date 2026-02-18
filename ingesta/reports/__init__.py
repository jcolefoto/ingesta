"""
Reporting module for ingesta media ingestion tool.

Provides comprehensive reporting capabilities including:
- PDF reports with thumbnails and metadata
- CSV reports for spreadsheet analysis
- Thumbnail extraction from video clips
- XML sidecar file parsing
- ShotPut-style bin/clip organization
"""

from .xml_parser import XMLParser, CameraMetadata
from .thumbnails import ThumbnailExtractor
from .csv_report import CSVReportGenerator
from .pdf_report import PDFReportGenerator
from .bin_organizer import BinOrganizer, ClipBin, ClipOrganization, BinType

__all__ = [
    'XMLParser',
    'CameraMetadata',
    'ThumbnailExtractor',
    'CSVReportGenerator',
    'PDFReportGenerator',
    'BinOrganizer',
    'ClipBin',
    'ClipOrganization',
    'BinType',
]
