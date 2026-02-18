"""
ShotPut-style bin/clip organization module.

Provides editor-ready organization by grouping clips into bins based on:
- Top-level folder names (e.g., A001, B002, Sound_001)
- Filename conventions as fallback (e.g., A001_001.MOV -> Bin A001)
- Camera/reel metadata extraction
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

from ..analysis import ClipAnalysis


class BinType(Enum):
    """Types of bins for organization."""
    CAMERA_REEL = "camera_reel"      # A001, B002, etc. - traditional camera reels
    SOUND_ROLL = "sound_roll"        # Sound_001, Audio_A, etc. - audio rolls
    SCENE = "scene"                  # Scene-based organization
    GENERIC = "generic"              # Generic/uncategorized


@dataclass
class ClipBin:
    """Represents a bin/folder for organizing clips."""
    name: str
    bin_type: BinType
    clip_count: int = 0
    total_duration: float = 0.0
    clips: List[ClipAnalysis] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ClipOrganization:
    """Complete organization of clips into bins."""
    bins: List[ClipBin] = field(default_factory=list)
    unclassified: List[ClipAnalysis] = field(default_factory=list)
    media_dir: Optional[Path] = None
    
    @property
    def total_clips(self) -> int:
        """Total number of clips across all bins."""
        return sum(b.clip_count for b in self.bins) + len(self.unclassified)
    
    @property
    def total_duration(self) -> float:
        """Total duration of all clips."""
        return sum(b.total_duration for b in self.bins) + \
               sum(c.duration for c in self.unclassified)
    
    def get_bin(self, name: str) -> Optional[ClipBin]:
        """Get a bin by name."""
        for bin in self.bins:
            if bin.name == name:
                return bin
        return None


class BinOrganizer:
    """
    Organizes clips into ShotPut-style bins for editor-ready workflows.
    
    Supports:
    - Folder-based grouping (e.g., A001/, B002/, Sound_001/)
    - Filename pattern extraction (e.g., A001_001.MOV -> Bin A001)
    - Camera/reel metadata detection
    """
    
    # Patterns for detecting camera reels (A001, B002, CAM1, etc.)
    REEL_PATTERNS = [
        r'^([A-Z]\d{3,4})',           # A001, B002, etc.
        r'^(CAM\d{1,2})',              # CAM1, CAM01, etc.
        r'^(CAMERA_?\d{1,2})',         # CAMERA1, CAMERA_01, etc.
        r'^(REEL_?\d{1,3})',           # REEL1, REEL_001, etc.
        r'^(CARD_?\d{1,2})',           # CARD1, CARD_01, etc.
    ]
    
    # Patterns for detecting sound/audio rolls
    SOUND_PATTERNS = [
        r'^(SOUND_?\d{1,3})',          # SOUND1, SOUND_001, etc.
        r'^(AUDIO_?\d{1,3})',          # AUDIO_A, AUDIO_01, etc.
        r'^(BOOM_?\d{1,2})',           # BOOM1, BOOM_01, etc.
        r'^(LAV_?\d{1,2})',             # LAV1, LAV_01, etc.
    ]
    
    # Scene-based patterns
    SCENE_PATTERNS = [
        r'^(SCENE_?\d{1,3})',          # SCENE1, SCENE_001, etc.
        r'^(SHOT_?\d{1,3})',           # SHOT1, SHOT_001, etc.
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_reel_from_folder(self, folder_name: str) -> Optional[Tuple[str, BinType]]:
        """
        Extract reel/bin name from folder name.
        
        Args:
            folder_name: Name of the folder
            
        Returns:
            Tuple of (bin_name, bin_type) or None if no match
        """
        folder_upper = folder_name.upper()
        
        # Check sound patterns first (more specific)
        for pattern in self.SOUND_PATTERNS:
            match = re.match(pattern, folder_upper)
            if match:
                return (folder_name, BinType.SOUND_ROLL)
        
        # Check reel patterns
        for pattern in self.REEL_PATTERNS:
            match = re.match(pattern, folder_upper)
            if match:
                return (folder_name, BinType.CAMERA_REEL)
        
        # Check scene patterns
        for pattern in self.SCENE_PATTERNS:
            match = re.match(pattern, folder_upper)
            if match:
                return (folder_name, BinType.SCENE)
        
        return None
    
    def extract_reel_from_filename(self, filename: str) -> Optional[Tuple[str, BinType]]:
        """
        Extract reel/bin name from filename using common naming conventions.
        
        Args:
            filename: Name of the file (without path)
            
        Returns:
            Tuple of (bin_name, bin_type) or None if no match
        """
        # Remove extension
        name = Path(filename).stem
        name_upper = name.upper()
        
        # Common patterns: A001_001.MOV, CAM01_CLIP001.MP4, etc.
        
        # Pattern: A001_001 (reel_clip)
        reel_clip_match = re.match(r'^([A-Z]\d{3,4})[_-]', name_upper)
        if reel_clip_match:
            reel = reel_clip_match.group(1)
            return (reel, BinType.CAMERA_REEL)
        
        # Pattern: CAM01_001, CAMERA1_001
        cam_match = re.match(r'^(CAM(?:ERA)?_?\d{1,2})[_-]', name_upper)
        if cam_match:
            reel = cam_match.group(1)
            return (reel, BinType.CAMERA_REEL)
        
        # Pattern: SOUND_001, AUDIO_A
        sound_match = re.match(r'^(SOUND|AUDIO|BOOM|LAV)_?(\d{1,3}|[A-Z])', name_upper)
        if sound_match:
            reel = sound_match.group(0)
            return (reel, BinType.SOUND_ROLL)
        
        return None
    
    def get_top_level_folder(self, file_path: Path, media_dir: Path) -> Optional[str]:
        """
        Get the top-level folder name within the media directory.
        
        Args:
            file_path: Path to the media file
            media_dir: Root media directory
            
        Returns:
            Top-level folder name or None if file is directly in media_dir
        """
        try:
            # Get relative path from media_dir
            rel_path = file_path.relative_to(media_dir)
            parts = rel_path.parts
            
            # If there are subdirectories, return the first one
            if len(parts) > 1:
                return parts[0]
            
            return None
        except ValueError:
            # file_path is not under media_dir
            return None
    
    def organize_by_folder(self, 
                          analyses: List[ClipAnalysis],
                          media_dir: Path) -> ClipOrganization:
        """
        Organize clips by their top-level folder structure.
        
        Args:
            analyses: List of clip analyses
            media_dir: Root media directory
            
        Returns:
            ClipOrganization with bins populated
        """
        organization = ClipOrganization(media_dir=media_dir)
        bins_dict: Dict[str, ClipBin] = {}
        
        for analysis in analyses:
            file_path = analysis.file_path
            
            # Try to get bin from folder structure
            folder = self.get_top_level_folder(file_path, media_dir)
            
            if folder:
                # Use folder as bin name
                bin_info = self.extract_reel_from_folder(folder)
                if bin_info:
                    bin_name, bin_type = bin_info
                else:
                    # Use folder name as generic bin
                    bin_name = folder
                    bin_type = BinType.GENERIC
            else:
                # Try filename fallback
                bin_info = self.extract_reel_from_filename(file_path.name)
                if bin_info:
                    bin_name, bin_type = bin_info
                else:
                    # Unclassified
                    organization.unclassified.append(analysis)
                    continue
            
            # Add to bin
            if bin_name not in bins_dict:
                bins_dict[bin_name] = ClipBin(
                    name=bin_name,
                    bin_type=bin_type
                )
            
            bin_obj = bins_dict[bin_name]
            bin_obj.clips.append(analysis)
            bin_obj.clip_count += 1
            bin_obj.total_duration += analysis.duration
        
        # Convert dict to list and sort
        organization.bins = sorted(bins_dict.values(), key=lambda b: b.name)
        
        self.logger.info(f"Organized {len(analyses)} clips into {len(organization.bins)} bins")
        for bin_obj in organization.bins:
            self.logger.info(f"  {bin_obj.name}: {bin_obj.clip_count} clips")
        
        return organization
    
    def organize_by_filename(self, analyses: List[ClipAnalysis]) -> ClipOrganization:
        """
        Organize clips by filename patterns only (no folder structure).
        
        Args:
            analyses: List of clip analyses
            
        Returns:
            ClipOrganization with bins populated
        """
        organization = ClipOrganization()
        bins_dict: Dict[str, ClipBin] = {}
        
        for analysis in analyses:
            file_path = analysis.file_path
            
            # Try filename pattern extraction
            bin_info = self.extract_reel_from_filename(file_path.name)
            
            if bin_info:
                bin_name, bin_type = bin_info
            else:
                # Unclassified
                organization.unclassified.append(analysis)
                continue
            
            # Add to bin
            if bin_name not in bins_dict:
                bins_dict[bin_name] = ClipBin(
                    name=bin_name,
                    bin_type=bin_type
                )
            
            bin_obj = bins_dict[bin_name]
            bin_obj.clips.append(analysis)
            bin_obj.clip_count += 1
            bin_obj.total_duration += analysis.duration
        
        # Convert dict to list and sort
        organization.bins = sorted(bins_dict.values(), key=lambda b: b.name)
        
        return organization
    
    def get_bin_summary(self, organization: ClipOrganization) -> Dict[str, Dict]:
        """
        Get a summary dictionary of bins for reporting.
        
        Args:
            organization: ClipOrganization object
            
        Returns:
            Dictionary mapping bin names to summary info
        """
        summary = {}
        
        for bin_obj in organization.bins:
            summary[bin_obj.name] = {
                'type': bin_obj.bin_type.value,
                'count': bin_obj.clip_count,
                'total_duration': bin_obj.total_duration,
                'clips': [str(c.file_path.name) for c in bin_obj.clips]
            }
        
        if organization.unclassified:
            summary['Unclassified'] = {
                'type': 'unclassified',
                'count': len(organization.unclassified),
                'total_duration': sum(c.duration for c in organization.unclassified),
                'clips': [str(c.file_path.name) for c in organization.unclassified]
            }
        
        return summary


def format_duration(seconds: float) -> str:
    """Format duration as HH:MM:SS or MM:SS."""
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
