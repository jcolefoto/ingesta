"""
Reporting module for ingesta media ingestion tool.

Provides comprehensive reporting capabilities including:
- PDF reports with thumbnails and metadata
- CSV reports for spreadsheet analysis
- Thumbnail extraction from video clips
- XML sidecar file parsing
- ShotPut-style bin/clip organization
- Local transcription (whisper.cpp)
- Local frame analysis for visual descriptions

SECURITY: All processing is done locally. No data is sent to external services.
"""

from .xml_parser import XMLParser, CameraMetadata
from .thumbnails import ThumbnailExtractor
from .csv_report import CSVReportGenerator
from .pdf_report import PDFReportGenerator
from .bin_organizer import BinOrganizer, ClipBin, ClipOrganization, BinType
from .local_transcription import LocalTranscriber, TranscriptionResult, transcribe_video_clip
from .frame_analysis import LocalFrameAnalyzer, FrameAnalysis, analyze_video_frames

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
    'LocalTranscriber',
    'TranscriptionResult',
    'transcribe_video_clip',
    'LocalFrameAnalyzer',
    'FrameAnalysis',
    'analyze_video_frames',
]
