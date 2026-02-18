"""
Adobe Premiere Pro project file generator.

Creates .prproj XML files with organized bins based on content analysis.
"""

import logging
from pathlib import Path
from typing import Union, List, Dict, Optional
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
class PremiereClip:
    """Represents a clip in the Premiere project."""
    name: str
    file_path: Path
    duration: float
    clip_type: ClipType
    in_point: float = 0.0
    out_point: float = 0.0


class PremiereProjectGenerator:
    """
    Generates Adobe Premiere Pro project files (.prproj).
    
    Organizes clips into bins based on content analysis:
    - Syncable: Clips with clear audio for syncing
    - B-Roll: Supplemental footage
    - Interviews: Talking head shots
    - Establishing: Wide establishing shots
    - Other: Uncategorized clips
    """
    
    def __init__(self, settings: Optional[ProjectSettings] = None):
        self.settings = settings or ProjectSettings()
        self.clips: List[PremiereClip] = []
    
    def add_clip(self, clip: PremiereClip):
        """Add a clip to the project."""
        self.clips.append(clip)
    
    def add_clips_from_analysis(self, analyses: List[ClipAnalysis]):
        """
        Add clips from content analysis results.
        
        Args:
            analyses: List of ClipAnalysis objects
        """
        for analysis in analyses:
            clip = PremiereClip(
                name=analysis.file_path.stem,
                file_path=analysis.file_path,
                duration=analysis.duration,
                clip_type=analysis.clip_type
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
    
    def _create_project_xml(self) -> ET.Element:
        """
        Create the root Premiere project XML structure.
        
        Returns:
            Root XML element
        """
        # Premiere uses a specific XML format
        # This is a simplified version that creates a valid structure
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
    
    def _create_bin_xml(self, parent: ET.Element, name: str, clips: List[PremiereClip]):
        """
        Create a bin (folder) in the project XML.
        
        Args:
            parent: Parent XML element
            name: Bin name
            clips: List of clips in this bin
        """
        bin_elem = ET.SubElement(parent, "Bin")
        bin_elem.set("Name", name)
        
        for clip in clips:
            clip_elem = ET.SubElement(bin_elem, "Clip")
            clip_elem.set("Name", clip.name)
            clip_elem.set("Path", str(clip.file_path))
            clip_elem.set("Duration", str(clip.duration))
            clip_elem.set("Type", clip.clip_type.value)
    
    def generate_xml(self) -> ET.Element:
        """
        Generate the complete project XML.
        
        Returns:
            Root XML element
        """
        root = self._create_project_xml()
        root_bin = root.find("RootBin")
        
        # Organize clips by type
        organized = self.organize_clips_by_type()
        
        # Create bins for each clip type that has clips
        bin_mapping = {
            ClipType.SYNCABLE: ("01_Syncable", "Clips ready for audio sync"),
            ClipType.INTERVIEW: ("02_Interviews", "Interview and talking head footage"),
            ClipType.B_ROLL: ("03_B_Roll", "Supplemental B-roll footage"),
            ClipType.ESTABLISHING: ("04_Establishing", "Establishing shots and wide views"),
            ClipType.ACTION: ("05_Action", "Action and movement shots"),
            ClipType.INSERT: ("06_Inserts", "Close-up and detail shots"),
            ClipType.STATIC: ("07_Static", "Static tripod shots"),
            ClipType.UNKNOWN: ("08_Other", "Other clips"),
        }
        
        for clip_type, clips in organized.items():
            if clips:  # Only create bin if there are clips
                bin_name, _ = bin_mapping.get(clip_type, (f"Other_{clip_type.value}", ""))
                self._create_bin_xml(root_bin, bin_name, clips)
        
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
        
        return {
            "project_name": self.settings.name,
            "total_clips": len(self.clips),
            "total_duration": total_duration,
            "bins": {
                clip_type.value: {
                    "count": len(clips),
                    "duration": sum(c.duration for c in clips),
                    "clips": [c.name for c in clips],
                }
                for clip_type, clips in organized.items()
                if clips  # Only include non-empty bins
            },
        }


def create_premiere_project(
    media_dir: Union[str, Path],
    output_path: Union[str, Path],
    name: Optional[str] = None,
    fps: float = 24.0,
    resolution: str = "1920x1080",
    analyze_content: bool = True,
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
        generator.add_clips_from_analysis(analyses)
    else:
        # Just collect files without analysis
        for ext in video_formats:
            for video_file in media_dir.glob(f"*{ext}"):
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
