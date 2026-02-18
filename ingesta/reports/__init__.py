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
- Audio technical analysis (peak, RMS, clipping)
- Metadata extraction (timecode, reel IDs)
- Duplicate detection
- Quality warnings (bad clip detection)
- Proxy generation
- Keyword tagging

SECURITY: All processing is done locally. No data is sent to external services.
"""

from .xml_parser import XMLParser, CameraMetadata
from .thumbnails import ThumbnailExtractor
from .csv_report import CSVReportGenerator
from .pdf_report import PDFReportGenerator
from .bin_organizer import BinOrganizer, ClipBin, ClipOrganization, BinType
from .local_transcription import LocalTranscriber, TranscriptionResult, transcribe_video_clip
from .frame_analysis import LocalFrameAnalyzer, FrameAnalysis, analyze_video_frames
from .audio_tech import AudioTechAnalyzer, AudioTechAnalysis, analyze_audio_tech
from .metadata_extractor import MetadataExtractor, MetadataExtraction, extract_metadata
from .duplicate_detector import DuplicateDetector, DuplicateInfo, find_duplicates
from .bad_clip_detector import BadClipDetector, BadClipAnalysis, detect_bad_clips
from .proxy_generator import ProxyGenerator, ProxyResult, generate_proxy
from .keyword_tagger import KeywordTagger, KeywordTags, extract_keywords
from .delivery_checklist import (
    DeliveryChecklistGenerator, EditorDeliveryChecklist, ChecklistItem,
    ChecklistItemSeverity, ChecklistCategory, generate_delivery_checklist
)
from .multicam_detector import (
    MulticamDetector, MulticamGroup, UnsyncedClipAnalysis, SyncAnalysisResult,
    UnsyncedCategory, MulticamReason, detect_multicam_sequences, analyze_sync_failure
)
from .editor_handoff import (
    EditorHandoffGenerator, EditorHandoffPackage, generate_editor_handoff
)
from .performance_profile import (
    AnalysisProfile, ProfileConfig, ProfileManager,
    get_analysis_settings, format_profile_summary
)

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
    'AudioTechAnalyzer',
    'AudioTechAnalysis',
    'analyze_audio_tech',
    'MetadataExtractor',
    'MetadataExtraction',
    'extract_metadata',
    'DuplicateDetector',
    'DuplicateInfo',
    'find_duplicates',
    'BadClipDetector',
    'BadClipAnalysis',
    'detect_bad_clips',
    'ProxyGenerator',
    'ProxyResult',
    'generate_proxy',
    'KeywordTagger',
    'KeywordTags',
    'extract_keywords',
    'DeliveryChecklistGenerator',
    'EditorDeliveryChecklist',
    'ChecklistItem',
    'ChecklistItemSeverity',
    'ChecklistCategory',
    'generate_delivery_checklist',
    'MulticamDetector',
    'MulticamGroup',
    'UnsyncedClipAnalysis',
    'SyncAnalysisResult',
    'UnsyncedCategory',
    'MulticamReason',
    'detect_multicam_sequences',
    'analyze_sync_failure',
    'EditorHandoffGenerator',
    'EditorHandoffPackage',
    'generate_editor_handoff',
    'AnalysisProfile',
    'ProfileConfig',
    'ProfileManager',
    'get_analysis_settings',
    'format_profile_summary',
]
