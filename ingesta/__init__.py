"""
ingesta - Media Ingestion Tool

A Python-based media ingestion tool that combines Shotput Pro-style offloading 
with verification and Pluralize-style audio sync capabilities.
"""

__version__ = "0.1.0"
__author__ = "jcolefoto"

from .checksum import calculate_checksum, verify_checksum
from .ingestion import ingest_media, IngestionJob
from .sync import sync_audio_video, WaveformSync
from .premiere import create_premiere_project
from .analysis import ClipAnalysis, ClipType, ContentAnalyzer

__all__ = [
    "calculate_checksum",
    "verify_checksum", 
    "ingest_media",
    "IngestionJob",
    "sync_audio_video",
    "WaveformSync",
    "create_premiere_project",
    "ClipAnalysis",
    "ClipType",
    "ContentAnalyzer",
]
