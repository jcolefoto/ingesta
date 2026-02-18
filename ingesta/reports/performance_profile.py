"""
Performance profile module for ingesta.

Provides three analysis profiles:
- FAST: Quick analysis, minimal processing, basic reports
- STANDARD: Balanced analysis with most features enabled
- DEEP: Comprehensive analysis with all features, maximum quality

Allows users to trade off between speed and analysis depth.
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Any


logger = logging.getLogger(__name__)


class AnalysisProfile(Enum):
    """Analysis performance profiles."""
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class ProfileConfig:
    """Configuration for an analysis profile."""
    # Analysis features
    transcribe: bool = False
    analyze_frames: bool = False
    analyze_audio_tech: bool = True
    extract_metadata: bool = True
    detect_duplicates: bool = False
    check_quality: bool = False
    generate_proxies: bool = True
    extract_keywords: bool = False
    
    # Analysis depth
    thumbnail_count: int = 3
    transcription_model: str = "base"
    motion_analysis_frames: int = 10
    audio_analysis_samples: int = 100
    
    # Report features
    include_thumbnails: bool = True
    include_pdf: bool = True
    include_csv: bool = True
    include_checklist: bool = True
    include_multicam: bool = False
    
    # Quality settings
    proxy_resolution: str = "960x540"
    jpeg_quality: int = 85
    
    # Descriptions
    name: str = ""
    description: str = ""
    estimated_time: str = ""


class ProfileManager:
    """Manage analysis performance profiles."""
    
    PROFILES = {
        AnalysisProfile.FAST: ProfileConfig(
            name="Fast",
            description="Quick analysis for rapid turnaround. Basic metadata and thumbnails only.",
            estimated_time="1-2 min per 10 clips",
            transcribe=False,
            analyze_frames=False,
            analyze_audio_tech=True,
            extract_metadata=True,
            detect_duplicates=False,
            check_quality=False,
            generate_proxies=True,
            extract_keywords=False,
            thumbnail_count=2,
            transcription_model="base",
            motion_analysis_frames=5,
            audio_analysis_samples=50,
            include_thumbnails=True,
            include_pdf=True,
            include_csv=True,
            include_checklist=True,
            include_multicam=False,
            proxy_resolution="640x360",
            jpeg_quality=75,
        ),
        AnalysisProfile.STANDARD: ProfileConfig(
            name="Standard",
            description="Balanced analysis with most features. Good for typical productions.",
            estimated_time="3-5 min per 10 clips",
            transcribe=True,
            analyze_frames=False,
            analyze_audio_tech=True,
            extract_metadata=True,
            detect_duplicates=True,
            check_quality=True,
            generate_proxies=True,
            extract_keywords=True,
            thumbnail_count=4,
            transcription_model="base",
            motion_analysis_frames=10,
            audio_analysis_samples=100,
            include_thumbnails=True,
            include_pdf=True,
            include_csv=True,
            include_checklist=True,
            include_multicam=True,
            proxy_resolution="960x540",
            jpeg_quality=85,
        ),
        AnalysisProfile.DEEP: ProfileConfig(
            name="Deep",
            description="Comprehensive analysis with all features. Maximum quality, slower processing.",
            estimated_time="10-15 min per 10 clips",
            transcribe=True,
            analyze_frames=True,
            analyze_audio_tech=True,
            extract_metadata=True,
            detect_duplicates=True,
            check_quality=True,
            generate_proxies=True,
            extract_keywords=True,
            thumbnail_count=6,
            transcription_model="medium",
            motion_analysis_frames=20,
            audio_analysis_samples=200,
            include_thumbnails=True,
            include_pdf=True,
            include_csv=True,
            include_checklist=True,
            include_multicam=True,
            proxy_resolution="1280x720",
            jpeg_quality=95,
        ),
    }
    
    @classmethod
    def get_profile(cls, profile: AnalysisProfile) -> ProfileConfig:
        """Get configuration for a profile."""
        return cls.PROFILES.get(profile, cls.PROFILES[AnalysisProfile.STANDARD])
    
    @classmethod
    def list_profiles(cls) -> List[Dict[str, str]]:
        """List all available profiles with descriptions."""
        return [
            {
                'id': p.value,
                'name': cfg.name,
                'description': cfg.description,
                'estimated_time': cfg.estimated_time,
            }
            for p, cfg in cls.PROFILES.items()
        ]
    
    @classmethod
    def from_string(cls, profile_str: str) -> AnalysisProfile:
        """Convert string to AnalysisProfile enum."""
        profile_map = {
            'fast': AnalysisProfile.FAST,
            'standard': AnalysisProfile.STANDARD,
            'deep': AnalysisProfile.DEEP,
        }
        return profile_map.get(profile_str.lower(), AnalysisProfile.STANDARD)


def get_analysis_settings(profile: AnalysisProfile) -> Dict[str, Any]:
    """
    Get analysis settings for a profile.
    
    Args:
        profile: AnalysisProfile to use
        
    Returns:
        Dict of settings for the CLI report command
    """
    config = ProfileManager.get_profile(profile)
    
    return {
        'transcribe': config.transcribe,
        'analyze_frames': config.analyze_frames,
        'analyze_audio_tech': config.analyze_audio_tech,
        'extract_metadata': config.extract_metadata,
        'detect_duplicates': config.detect_duplicates,
        'check_quality': config.check_quality,
        'generate_proxies': config.generate_proxies,
        'extract_keywords': config.extract_keywords,
        'thumbnails': config.include_thumbnails,
        'whisper_model': config.transcription_model,
        'proxy_resolution': config.proxy_resolution,
    }


def format_profile_summary(profile: AnalysisProfile) -> str:
    """
    Format a profile configuration as a readable summary.
    
    Args:
        profile: AnalysisProfile to summarize
        
    Returns:
        Formatted summary text
    """
    config = ProfileManager.get_profile(profile)
    
    lines = []
    lines.append(f"Analysis Profile: {config.name}")
    lines.append(f"Description: {config.description}")
    lines.append(f"Estimated Time: {config.estimated_time}")
    lines.append("")
    lines.append("Enabled Features:")
    
    features = []
    if config.transcribe:
        features.append(f"  • Transcription ({config.transcription_model} model)")
    if config.analyze_frames:
        features.append("  • Frame analysis (visual description)")
    if config.analyze_audio_tech:
        features.append("  • Audio technical analysis")
    if config.extract_metadata:
        features.append("  • Metadata extraction")
    if config.detect_duplicates:
        features.append("  • Duplicate detection")
    if config.check_quality:
        features.append("  • Quality control checks")
    if config.generate_proxies:
        features.append(f"  • Proxy generation ({config.proxy_resolution})")
    if config.extract_keywords:
        features.append("  • Keyword extraction")
    
    if features:
        lines.extend(features)
    else:
        lines.append("  • Basic analysis only")
    
    lines.append("")
    lines.append(f"Thumbnails: {config.thumbnail_count} per clip")
    lines.append(f"JPEG Quality: {config.jpeg_quality}%")
    
    return '\n'.join(lines)