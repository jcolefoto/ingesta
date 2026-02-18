"""
Adobe Premiere Pro project file generator.

Creates .prproj XML files with organized bins based on content analysis.
Enhanced with assistant-editor-level organization including camera/reel sorting.
"""

import logging
import re
from pathlib import Path
from typing import Union, List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .analysis import ClipAnalysis, ClipType, ContentAnalyzer


@dataclass
class ProjectSettings:
    """Premiere project settings."""
    name: str = "Untitled Project"
    width: int = 1920
    height: int = 1080
    fps: float = 24.0
    audio_sample_rate: int = 48000
    audio_channels: int = 2


@dataclass
class CameraInfo:
    """Information about camera/reel extracted from clip."""
    reel: Optional[str] = None
    camera: Optional[str] = None
    scene: Optional[str] = None
    take: Optional[str] = None


@dataclass
class PremiereClip:
    """Represents a clip in the Premiere project."""
    name: str
    file_path: Path
    duration: float
    clip_type: ClipType
    in_point: float = 0.0
    out_point: float = 0.0
    camera_info: CameraInfo = field(default_factory=CameraInfo)
    slate_detected: bool = False
    scene_number: Optional[str] = None
    take_number: Optional[str] = None
    timecode_start: str = "00:00:00:00"


def extract_camera_reel(file_path: Path) -> CameraInfo:
    """
    Extract camera and reel information from filename.
    
    Handles various naming conventions:
    - A001_C001_20240218_001.mov -> reel: A001, camera: C001
    - B002_01.mov -> reel: B002
    - C003_Take01.mov -> reel: C003
    - A004C001_20240218.mov -> reel: A004, camera: C001
    
    Args:
        file_path: Path to video file
        
    Returns:
        CameraInfo with extracted reel and camera IDs
    """
    name = file_path.stem
    info = CameraInfo()
    
    # Pattern 1: A001_C001_... (common in professional cameras)
    match = re.match(r'^([A-Z]\d{3})[_-]([A-Z]\d{3})', name)
    if match:
        info.reel = match.group(1)
        info.camera = match.group(2)
        return info
    
    # Pattern 2: A001C001_... (no separator)
    match = re.match(r'^([A-Z]\d{3})([A-Z]\d{3})', name)
    if match:
        info.reel = match.group(1)
        info.camera = match.group(2)
        return info
    
    # Pattern 3: B002_01 or B002_Take01
    match = re.match(r'^([A-Z]\d{3})[_-]', name)
    if match:
        info.reel = match.group(1)
    
    # Pattern 4: Card1, Card2, etc.
    match = re.search(r'[Cc]ard[_-]?(\d+)', name)
    if match:
        info.reel = f"Card{match.group(1)}"
    
    # Pattern 5: Scene/Take info
    scene_match = re.search(r'[Ss][Cc](\d+[a-zA-Z]?)', name)
    if scene_match:
        info.scene = scene_match.group(1)
    
    take_match = re.search(r'[Tt][Kk](\d+)', name)
    if take_match:
        info.take = take_match.group(1)
    
    return info


class PremiereProjectGenerator:
    """
    Generates Adobe Premiere Pro project files (.prproj).
    
    Organizes clips into bins based on content analysis:
    - Syncable: Clips with clear audio for syncing
    - B-Roll: Supplemental footage
    - Interviews: Talking head shots
    - Establishing: Wide establishing shots
    - Other: Uncategorized clips
    
    Enhanced with:
    - Camera/reel sorting within bins
    - Assistant editor folder structure
    - Slate detection metadata
    """
    
    def __init__(self, settings: Optional[ProjectSettings] = None):
        self.settings = settings or ProjectSettings()
        self.clips: List[PremiereClip] = []
    
    def add_clip(self, clip: PremiereClip):
        """Add a clip to the project."""
        self.clips.append(clip)
    
    def add_clips_from_analysis(
        self, 
        analyses: List[ClipAnalysis],
        slate_info: Optional[Dict[Path, dict]] = None
    ):
        """
        Add clips from content analysis results.
        
        Args:
            analyses: List of ClipAnalysis objects
            slate_info: Optional dict mapping file paths to slate detection results
        """
        slate_info = slate_info or {}
        
        for analysis in analyses:
            # Extract camera/reel info
            cam_info = extract_camera_reel(analysis.file_path)
            
            # Get slate info if available
            slate_data = slate_info.get(analysis.file_path, {})
            
            clip = PremiereClip(
                name=analysis.file_path.stem,
                file_path=analysis.file_path,
                duration=analysis.duration,
                clip_type=analysis.clip_type,
                camera_info=cam_info,
                slate_detected=slate_data.get('detected', False),
                scene_number=slate_data.get('scene_number') or cam_info.scene,
                take_number=slate_data.get('take_number') or cam_info.take,
            )
            self.add_clip(clip)
    
    def organize_clips_by_type(self) -> Dict[ClipType, List[PremiereClip]]:
        """
        Organize clips by their content type.
        
        Returns:
            Dictionary mapping ClipType to list of clips
        """
        organized: Dict[ClipType, List[PremiereClip]] = {
            clip_type: [] for clip_type in ClipType
        }
        
        for clip in self.clips:
            organized[clip.clip_type].append(clip)
        
        return organized
    
    def organize_by_camera_reel(
        self, 
        clips: List[PremiereClip]
    ) -> Dict[str, List[PremiereClip]]:
        """
        Organize clips by camera/reel within a bin.
        
        Args:
            clips: List of clips to organize
            
        Returns:
            Dictionary mapping reel/camera ID to list of clips
        """
        organized: Dict[str, List[PremiereClip]] = {}
        
        for clip in clips:
            # Determine the reel/camera identifier
            if clip.camera_info.reel:
                if clip.camera_info.camera:
                    key = f"{clip.camera_info.reel}_{clip.camera_info.camera}"
                else:
                    key = clip.camera_info.reel
            elif clip.camera_info.camera:
                key = clip.camera_info.camera
            else:
                key = "Unknown"
            
            if key not in organized:
                organized[key] = []
            organized[key].append(clip)
        
        # Sort clips within each reel by filename
        for key in organized:
            organized[key].sort(key=lambda c: c.file_path.name)
        
        return organized
    
    def _create_project_xml(self) -> ET.Element:
        """
        Create the root Premiere project XML structure.
        
        Returns:
            Root XML element
        """
        root = ET.Element("Project")
        root.set("Version", "1.0")
        root.set("Name", self.settings.name)
        
        # Project settings
        settings = ET.SubElement(root, "Settings")
        ET.SubElement(settings, "Width").text = str(self.settings.width)
        ET.SubElement(settings, "Height").text = str(self.settings.height)
        ET.SubElement(settings, "FrameRate").text = str(self.settings.fps)
        ET.SubElement(settings, "AudioSampleRate").text = str(self.settings.audio_sample_rate)
        ET.SubElement(settings, "AudioChannels").text = str(self.settings.audio_channels)
        
        # Root bin
        root_bin = ET.SubElement(root, "RootBin")
        root_bin.set("Name", "Project")
        
        return root
    
    def _create_bin_xml(
        self, 
        parent: ET.Element, 
        name: str, 
        clips: List[PremiereClip],
        organize_by_camera: bool = True
    ):
        """
        Create a bin (folder) in the project XML.
        
        Args:
            parent: Parent XML element
            name: Bin name
            clips: List of clips in this bin
            organize_by_camera: Whether to create sub-bins by camera/reel
        """
        bin_elem = ET.SubElement(parent, "Bin")
        bin_elem.set("Name", name)
        
        if organize_by_camera and len(clips) > 0:
            # Create sub-bins by camera/reel
            by_camera = self.organize_by_camera_reel(clips)
            
            for camera_key in sorted(by_camera.keys()):
                camera_clips = by_camera[camera_key]
                camera_bin = ET.SubElement(bin_elem, "Bin")
                camera_bin.set("Name", camera_key)
                
                for clip in camera_clips:
                    self._add_clip_to_bin(camera_bin, clip)
        else:
            # Add clips directly to bin
            for clip in clips:
                self._add_clip_to_bin(bin_elem, clip)
    
    def _add_clip_to_bin(self, bin_elem: ET.Element, clip: PremiereClip):
        """Add a single clip to a bin element."""
        clip_elem = ET.SubElement(bin_elem, "Clip")
        clip_elem.set("Name", clip.name)
        clip_elem.set("Path", str(clip.file_path))
        clip_elem.set("Duration", str(clip.duration))
        clip_elem.set("Type", clip.clip_type.value)
        
        # Add metadata if available
        if clip.slate_detected:
            clip_elem.set("SlateDetected", "true")
        if clip.scene_number:
            clip_elem.set("Scene", clip.scene_number)
        if clip.take_number:
            clip_elem.set("Take", clip.take_number)
        if clip.camera_info.reel:
            clip_elem.set("Reel", clip.camera_info.reel)
        if clip.camera_info.camera:
            clip_elem.set("Camera", clip.camera_info.camera)
    
    def generate_xml(self) -> ET.Element:
        """
        Generate the complete project XML with assistant-editor organization.
        
        Returns:
            Root XML element
        """
        root = self._create_project_xml()
        root_bin_elem = root.find("RootBin")
        
        if root_bin_elem is None:
            raise ValueError("RootBin not found in project XML")
        
        # Cast to Element for type checking
        root_bin: ET.Element = root_bin_elem
        
        # Organize clips by type
        organized = self.organize_clips_by_type()
        
        # Assistant editor bin structure with camera/reel sorting
        bin_structure = [
            (ClipType.INTERVIEW, "01_INTERVIEWS", "Interview and talking head footage"),
            (ClipType.SYNCABLE, "02_SYNCABLE_AUDIO", "Clips with clear audio for syncing"),
            (ClipType.B_ROLL, "03_B_ROLL", "Supplemental B-roll footage"),
            (ClipType.ESTABLISHING, "04_ESTABLISHING_SHOTS", "Establishing shots and wide views"),
            (ClipType.ACTION, "05_ACTION", "Action and movement shots"),
            (ClipType.INSERT, "06_INSERTS", "Close-up and detail shots"),
            (ClipType.STATIC, "07_STATIC", "Static tripod shots"),
            (ClipType.UNKNOWN, "08_OTHER", "Other clips"),
        ]
        
        for clip_type, bin_name, description in bin_structure:
            clips = organized.get(clip_type, [])
            if clips:  # Only create bin if there are clips
                self._create_bin_xml(root_bin, bin_name, clips, organize_by_camera=True)
        
        return root
    
    def save_project(self, output_path: Union[str, Path]):
        """
        Save the project to a file.
        
        Args:
            output_path: Path for the .prproj file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate XML
        root = self.generate_xml()
        
        # Pretty print XML
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logging.info(f"Saved Premiere project: {output_path}")
    
    def generate_report(self) -> Dict:
        """
        Generate a report of the project organization.
        
        Returns:
            Dictionary with project statistics
        """
        organized = self.organize_clips_by_type()
        
        total_duration = sum(clip.duration for clip in self.clips)
        
        # Count by camera/reel
        camera_counts: Dict[str, int] = {}
        for clip in self.clips:
            if clip.camera_info.reel:
                key = clip.camera_info.reel
                camera_counts[key] = camera_counts.get(key, 0) + 1
        
        # Count slates detected
        slate_count = sum(1 for c in self.clips if c.slate_detected)
        
        bins_report = {}
        for clip_type, clips in organized.items():
            if clips:
                by_camera = self.organize_by_camera_reel(clips)
                bins_report[clip_type.value] = {
                    "count": len(clips),
                    "duration": sum(c.duration for c in clips),
                    "cameras": {
                        cam: len(cam_clips) 
                        for cam, cam_clips in by_camera.items()
                    },
                    "clips": [c.name for c in clips],
                }
        
        return {
            "project_name": self.settings.name,
            "total_clips": len(self.clips),
            "total_duration": total_duration,
            "slates_detected": slate_count,
            "cameras_reels": camera_counts,
            "bins": bins_report,
        }


def create_premiere_project(
    media_dir: Union[str, Path],
    output_path: Union[str, Path],
    name: Optional[str] = None,
    fps: float = 24.0,
    resolution: str = "1920x1080",
    analyze_content: bool = True,
    slate_info: Optional[Dict[Path, dict]] = None,
    video_formats: tuple = (".mp4", ".mov", ".mxf", ".avi")
) -> Dict:
    """
    Create a Premiere Pro project from a directory of media files.
    
    Args:
        media_dir: Directory containing media files
        output_path: Output path for .prproj file
        name: Project name (default: directory name)
        fps: Frame rate
        resolution: Resolution as "WIDTHxHEIGHT"
        analyze_content: Whether to analyze and classify clips
        slate_info: Optional dict of slate detection results
        video_formats: Video file extensions to include
    
    Returns:
        Dictionary with project report
    """
    media_dir = Path(media_dir)
    output_path = Path(output_path)
    
    if name is None:
        name = media_dir.name
    
    # Parse resolution
    try:
        width, height = map(int, resolution.split('x'))
    except ValueError:
        width, height = 1920, 1080
    
    # Create project settings
    settings = ProjectSettings(
        name=name,
        width=width,
        height=height,
        fps=fps
    )
    
    generator = PremiereProjectGenerator(settings)
    
    if analyze_content:
        # Analyze all clips
        logging.info(f"Analyzing clips in {media_dir}...")
        analyzer = ContentAnalyzer()
        analyses = analyzer.analyze_directory(media_dir, video_formats)
        generator.add_clips_from_analysis(analyses, slate_info)
    else:
        # Just collect files without analysis
        for ext in video_formats:
            for video_file in media_dir.rglob(f"*{ext}"):
                clip = PremiereClip(
                    name=video_file.stem,
                    file_path=video_file,
                    duration=0.0,
                    clip_type=ClipType.UNKNOWN
                )
                generator.add_clip(clip)
    
    # Save project
    generator.save_project(output_path)
    
    # Return report
    return generator.generate_report()