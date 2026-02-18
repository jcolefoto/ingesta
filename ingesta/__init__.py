"""
ingesta - Media Ingestion Tool

A Python-based media ingestion tool that combines Shotput Pro-style offloading 
with verification and Pluralize-style audio sync capabilities.
"""

__version__ = "1.0.0"
__author__ = "jcolefoto"

from .checksum import calculate_checksum, verify_checksum
from .ingestion import ingest_media, IngestionJob
from .analysis import ClipAnalysis, ClipType, ContentAnalyzer

# Optional: sync functionality (requires librosa)
try:
    from .sync import sync_audio_video, WaveformSync
    SYNC_AVAILABLE = True
except ImportError:
    SYNC_AVAILABLE = False
    sync_audio_video = None
    WaveformSync = None

# Optional: premiere export
try:
    from .premiere import create_premiere_project
    PREMIERE_AVAILABLE = True
except ImportError:
    PREMIERE_AVAILABLE = False
    create_premiere_project = None

__all__ = [
    "calculate_checksum",
    "verify_checksum",
    "ingest_media",
    "IngestionJob",
    "ClipAnalysis",
    "ClipType",
    "ContentAnalyzer",
]

if SYNC_AVAILABLE:
    __all__.extend(["sync_audio_video", "WaveformSync"])

if PREMIERE_AVAILABLE:
    __all__.append("create_premiere_project")
