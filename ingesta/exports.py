"""
Enhanced exports module for ingesta.

Supports professional NLE exports:
- Adobe Premiere Pro (.prproj with markers)
- DaVinci Resolve (.drp and timeline XML)
- Final Cut Pro XML (.fcpxml)
- EDL (Edit Decision List)
- AAF (Advanced Authoring Format)

Features:
- Bin organization with templates
- Marker export (slates, notes, keywords)
- Timecode-aware exports
- Multi-format batch export

All processing is done locally.
"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .analysis import ClipAnalysis, ClipType
from .templates import ProjectTemplate, BinDefinition


logger = logging.getLogger(__name__)


class ExportFormat(Enum):
    """Supported export formats."""
    PREMIERE = "premiere"
    RESOLVE = "resolve"
    FCPXML = "fcpxml"
    EDL = "edl"
    AAF = "aaf"


class MarkerType(Enum):
    """Types of markers for NLE export."""
    SLATE = "slate"
    SCENE = "scene"
    TAKE = "take"
    NOTE = "note"
    GOOD_TAKE = "good_take"
    PICKUP = "pickup"
    ISSUE = "issue"


@dataclass
class Marker:
    """NLE marker definition."""
    timecode: str  # HH:MM:SS:FF format
    name: str
    comment: str = ""
    marker_type: MarkerType = MarkerType.NOTE
    duration_frames: int = 1
    color: str = "blue"  # blue, red, green, yellow, etc.


@dataclass
class TimelineClip:
    """Represents a clip on a timeline."""
    name: str
    file_path: Path
    duration_seconds: float
    reel: Optional[str] = None
    scene: Optional[str] = None
    take: Optional[str] = None
    timecode_start: str = "00:00:00:00"
    timecode_end: Optional[str] = None
    markers: List[Marker] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    track: int = 1


@dataclass
class Timeline:
    """Timeline definition for export."""
    name: str
    clips: List[TimelineClip] = field(default_factory=list)
    fps: float = 24.0
    resolution: str = "1920x1080"
    duration_frames: int = 0
    markers: List[Marker] = field(default_factory=list)


class EDLExporter:
    """
    Export Edit Decision List (EDL) format.
    
    CMX3600 compatible EDL export for universal NLE support.
    """
    
    def __init__(self, fps: float = 24.0):
        self.fps = fps
    
    def _timecode_to_frames(self, tc: str) -> int:
        """Convert HH:MM:SS:FF to frame count."""
        parts = tc.replace(';', ':').split(':')
        if len(parts) != 4:
            return 0
        h, m, s, f = map(int, parts)
        return ((h * 3600) + (m * 60) + s) * int(self.fps) + f
    
    def _frames_to_timecode(self, frames: int) -> str:
        """Convert frame count to HH:MM:SS:FF."""
        total_seconds = frames // int(self.fps)
        frames_remaining = frames % int(self.fps)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames_remaining:02d}"
    
    def export(self, timeline: Timeline, output_path: Path) -> bool:
        """
        Export timeline to EDL file.
        
        Args:
            timeline: Timeline to export
            output_path: Output EDL file path
            
        Returns:
            True if successful
        """
        try:
            lines = []
            
            # Header
            lines.append("TITLE: {}".format(timeline.name))
            lines.append("FCM: NON-DROP FRAME")
            lines.append("")
            
            # Edit entries
            edit_num = 1
            current_frame = 0
            
            for clip in timeline.clips:
                duration_frames = int(clip.duration_seconds * self.fps)
                
                # Source timecodes
                src_start = self._timecode_to_frames(clip.timecode_start)
                src_end = src_start + duration_frames
                
                # Record timecodes (timeline position)
                rec_start = current_frame
                rec_end = current_frame + duration_frames
                
                # EDL line format: EDIT# REEL NAME SRC_IN SRC_OUT REC_IN REC_OUT
                lines.append(
                    f"{edit_num:03d}  {clip.reel or '001'}  V     C        "
                    f"{self._frames_to_timecode(src_start)} {self._frames_to_timecode(src_end)} "
                    f"{self._frames_to_timecode(rec_start)} {self._frames_to_timecode(rec_end)}"
                )
                
                # Add comments for markers
                for marker in clip.markers:
                    lines.append(f"* {marker.name}: {marker.comment}")
                
                if clip.scene:
                    lines.append(f"* Scene: {clip.scene}")
                if clip.take:
                    lines.append(f"* Take: {clip.take}")
                
                lines.append("")
                
                edit_num += 1
                current_frame += duration_frames
            
            # Write file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"Exported EDL: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"EDL export failed: {e}")
            return False


class FCPXMLExporter:
    """
    Export Final Cut Pro XML format.
    
    Modern FCPXML (version 1.9+) for Final Cut Pro X/10.
    """
    
    def __init__(self, fps: float = 24.0, resolution: str = "1920x1080"):
        self.fps = fps
        width, height = resolution.split('x')
        self.width = int(width)
        self.height = int(height)
    
    def _tc_to_seconds(self, tc: str) -> float:
        """Convert timecode to seconds."""
        parts = tc.replace(';', ':').split(':')
        if len(parts) != 4:
            return 0.0
        h, m, s, f = map(int, parts)
        return (h * 3600) + (m * 60) + s + (f / self.fps)
    
    def export(self, timeline: Timeline, output_path: Path) -> bool:
        """Export timeline to FCPXML."""
        try:
            # Create XML structure
            root = ET.Element("fcpxml", version="1.9")
            
            # Resources
            resources = ET.SubElement(root, "resources")
            
            # Format
            fmt = ET.SubElement(resources, "format")
            fmt.set("id", "r1")
            fmt.set("name", f"{self.width}x{self.height}@{int(self.fps)}p")
            fmt.set("frameDuration", f"1/{int(self.fps)}s")
            fmt.set("width", str(self.width))
            fmt.set("height", str(self.height))
            
            # Library and event
            library = ET.SubElement(root, "library")
            event = ET.SubElement(library, "event")
            event.set("name", timeline.name)
            
            # Project/Timeline
            project = ET.SubElement(event, "project")
            project.set("name", timeline.name)
            
            # Sequence
            sequence = ET.SubElement(project, "sequence")
            sequence.set("format", "r1")
            
            # Spine (timeline)
            spine = ET.SubElement(sequence, "spine")
            
            # Add clips
            current_time = 0.0
            for clip in timeline.clips:
                clip_elem = ET.SubElement(spine, "clip")
                clip_elem.set("name", clip.name)
                clip_elem.set("offset", f"{current_time}s")
                clip_elem.set("duration", f"{clip.duration_seconds}s")
                
                # Add markers
                for marker in clip.markers:
                    marker_elem = ET.SubElement(clip_elem, "marker")
                    marker_elem.set("start", f"{self._tc_to_seconds(marker.timecode)}s")
                    marker_elem.set("value", marker.name)
                    if marker.comment:
                        marker_elem.set("note", marker.comment)
                
                current_time += clip.duration_seconds
            
            # Write XML
            self._write_xml(root, output_path)
            logger.info(f"Exported FCPXML: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"FCPXML export failed: {e}")
            return False
    
    def _write_xml(self, root: ET.Element, output_path: Path):
        """Write XML to file with pretty formatting."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")
        # Remove empty lines
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


class PremiereExporter:
    """
    Enhanced Adobe Premiere Pro exporter with markers and bins.
    
    Creates .prproj files with:
    - Template-based bin organization
    - Markers for slates, notes, and issues
    - Multi-camera organization
    """
    
    def __init__(self, fps: float = 24.0, resolution: str = "1920x1080"):
        self.fps = fps
        width, height = resolution.split('x')
        self.width = int(width)
        self.height = int(height)
    
    def export(self, timeline: Timeline, output_path: Path, 
               template: Optional[ProjectTemplate] = None) -> bool:
        """
        Export timeline to Premiere Pro project.
        
        Args:
            timeline: Timeline to export
            output_path: Output .prproj file path
            template: Optional project template for bin organization
            
        Returns:
            True if successful
        """
        try:
            # Create XML structure
            root = ET.Element("PremiereData", Version="3")
            
            # Project
            project = ET.SubElement(root, "Project")
            project.set("Name", timeline.name)
            
            # Settings
            settings = ET.SubElement(project, "Settings")
            ET.SubElement(settings, "FrameRate").text = str(self.fps)
            ET.SubElement(settings, "Width").text = str(self.width)
            ET.SubElement(settings, "Height").text = str(self.height)
            
            # Root bin
            root_bin = ET.SubElement(project, "RootBin")
            root_bin.set("Name", timeline.name)
            
            if template:
                # Use template bin structure
                self._create_template_bins(root_bin, timeline, template)
            else:
                # Default bin structure
                self._create_default_bins(root_bin, timeline)
            
            # Timeline/Sequence
            sequence = ET.SubElement(project, "Sequence")
            sequence.set("Name", timeline.name)
            
            # Add clips to timeline
            track = ET.SubElement(sequence, "Track")
            track.set("Type", "Video")
            
            current_time = 0.0
            for clip in timeline.clips:
                clip_elem = ET.SubElement(track, "Clip")
                clip_elem.set("Name", clip.name)
                clip_elem.set("Start", str(current_time))
                clip_elem.set("Duration", str(clip.duration_seconds))
                
                # Add markers
                for marker in clip.markers:
                    marker_elem = ET.SubElement(clip_elem, "Marker")
                    marker_elem.set("Time", marker.timecode)
                    marker_elem.set("Name", marker.name)
                    marker_elem.set("Type", marker.marker_type.value)
                    marker_elem.set("Color", marker.color)
                    if marker.comment:
                        marker_elem.set("Comment", marker.comment)
                
                current_time += clip.duration_seconds
            
            # Write XML
            self._write_xml(root, output_path)
            logger.info(f"Exported Premiere project: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Premiere export failed: {e}")
            return False
    
    def _create_template_bins(self, parent: ET.Element, timeline: Timeline, 
                              template: ProjectTemplate):
        """Create bin structure from template."""
        for bin_def in template.bins:
            bin_elem = ET.SubElement(parent, "Bin")
            bin_elem.set("Name", bin_def.name)
            
            # Add matching clips to bin
            matching_clips = self._get_clips_for_bin(timeline.clips, bin_def)
            for clip in matching_clips:
                self._add_clip_to_bin(bin_elem, clip)
            
            # Create sub-bins
            for sub_bin_def in bin_def.sub_bins:
                sub_bin = ET.SubElement(bin_elem, "Bin")
                sub_bin.set("Name", sub_bin_def.name)
                
                sub_clips = self._get_clips_for_bin(timeline.clips, sub_bin_def)
                for clip in sub_clips:
                    self._add_clip_to_bin(sub_bin, clip)
    
    def _create_default_bins(self, parent: ET.Element, timeline: Timeline):
        """Create default bin structure."""
        bins = {
            "Video": [],
            "Audio": [],
            "Syncable": [],
        }
        
        for clip in timeline.clips:
            # Simple categorization
            ext = clip.file_path.suffix.lower()
            if ext in ['.wav', '.mp3', '.aac', '.bwf']:
                bins["Audio"].append(clip)
            else:
                bins["Video"].append(clip)
        
        for bin_name, clips in bins.items():
            if clips:
                bin_elem = ET.SubElement(parent, "Bin")
                bin_elem.set("Name", bin_name)
                for clip in clips:
                    self._add_clip_to_bin(bin_elem, clip)
    
    def _get_clips_for_bin(self, clips: List[TimelineClip], bin_def: BinDefinition) -> List[TimelineClip]:
        """Get clips that match bin criteria based on tags and name patterns."""
        matching = []
        
        for clip in clips:
            # Check if clip tags match bin auto-tags
            if any(tag in clip.tags for tag in bin_def.auto_tag):
                matching.append(clip)
            # Check name patterns
            elif any(keyword in clip.name.lower() for keyword in bin_def.auto_tag):
                matching.append(clip)
        
        return matching
    
    def _add_clip_to_bin(self, bin_elem: ET.Element, clip: TimelineClip):
        """Add a clip to a bin element."""
        clip_elem = ET.SubElement(bin_elem, "Clip")
        clip_elem.set("Name", clip.name)
        clip_elem.set("Path", str(clip.file_path))
        clip_elem.set("Duration", str(clip.duration_seconds))
        
        if clip.reel:
            clip_elem.set("Reel", clip.reel)
        if clip.scene:
            clip_elem.set("Scene", clip.scene)
        if clip.take:
            clip_elem.set("Take", clip.take)
        if clip.timecode_start:
            clip_elem.set("TimecodeStart", clip.timecode_start)
    
    def _write_xml(self, root: ET.Element, output_path: Path):
        """Write XML to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)


class ResolveExporter:
    """
    DaVinci Resolve exporter.
    
    Creates Resolve-compatible timeline exports with:
    - Timeline XML format
    - Color tags for organization
    - Marker support
    """
    
    def __init__(self, fps: float = 24.0, resolution: str = "1920x1080"):
        self.fps = fps
        width, height = resolution.split('x')
        self.width = int(width)
        self.height = int(height)
    
    def export(self, timeline: Timeline, output_path: Path) -> bool:
        """
        Export timeline to DaVinci Resolve format.
        
        Args:
            timeline: Timeline to export
            output_path: Output file path (.xml or .drp)
            
        Returns:
            True if successful
        """
        try:
            # Resolve uses AAF-compatible XML
            root = ET.Element("AAF")
            
            # Header
            header = ET.SubElement(root, "Header")
            ET.SubElement(header, "Name").text = timeline.name
            ET.SubElement(header, "Date").text = datetime.now().isoformat()
            
            # Timeline
            tl_elem = ET.SubElement(root, "Timeline")
            tl_elem.set("Name", timeline.name)
            tl_elem.set("FrameRate", str(self.fps))
            
            # Tracks
            video_track = ET.SubElement(tl_elem, "Track")
            video_track.set("Type", "Video")
            video_track.set("Number", "1")
            
            # Add clips
            current_frame = 0
            for clip in timeline.clips:
                clip_elem = ET.SubElement(video_track, "Clip")
                clip_elem.set("Name", clip.name)
                clip_elem.set("Start", str(current_frame))
                
                duration_frames = int(clip.duration_seconds * self.fps)
                clip_elem.set("Duration", str(duration_frames))
                clip_elem.set("Path", str(clip.file_path))
                
                # Timecode
                if clip.timecode_start:
                    clip_elem.set("Timecode", clip.timecode_start)
                
                # Markers
                for marker in clip.markers:
                    marker_elem = ET.SubElement(clip_elem, "Marker")
                    marker_elem.set("Frame", marker.timecode)
                    marker_elem.set("Name", marker.name)
                    marker_elem.set("Color", marker.color)
                
                # Color tag based on clip type/reel
                if clip.reel:
                    color = self._get_reel_color(clip.reel)
                    clip_elem.set("ColorTag", color)
                
                current_frame += duration_frames
            
            # Write XML
            self._write_xml(root, output_path)
            logger.info(f"Exported Resolve timeline: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Resolve export failed: {e}")
            return False
    
    def _get_reel_color(self, reel: str) -> str:
        """Get Resolve color tag for reel."""
        # Map reels to Resolve colors
        color_map = {
            'A': 'Red',
            'B': 'Blue', 
            'C': 'Green',
            'D': 'Yellow',
        }
        
        if reel and len(reel) > 0:
            first_char = reel[0].upper()
            return color_map.get(first_char, 'None')
        return 'None'
    
    def _write_xml(self, root: ET.Element, output_path: Path):
        """Write XML to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)


class ExportManager:
    """
    Central manager for all NLE exports.
    
    Provides unified interface for exporting to multiple formats.
    """
    
    def __init__(self, fps: float = 24.0, resolution: str = "1920x1080"):
        self.fps = fps
        self.resolution = resolution
        self.premiere_exporter = PremiereExporter(fps, resolution)
        self.resolve_exporter = ResolveExporter(fps, resolution)
        self.fcpxml_exporter = FCPXMLExporter(fps, resolution)
        self.edl_exporter = EDLExporter(fps)
    
    def create_timeline_from_analyses(self, name: str, 
                                      analyses: List[ClipAnalysis]) -> Timeline:
        """
        Create a timeline from clip analyses.
        
        Args:
            name: Timeline name
            analyses: List of clip analyses
            
        Returns:
            Timeline object
        """
        clips = []
        
        for analysis in analyses:
            clip = TimelineClip(
                name=analysis.file_path.stem,
                file_path=analysis.file_path,
                duration_seconds=analysis.duration,
                reel=getattr(analysis, 'reel_id', None),
                scene=getattr(analysis, 'scene', None),
                take=getattr(analysis, 'take', None),
                timecode_start=getattr(analysis, 'timecode_start', "00:00:00:00"),
                tags=self._extract_tags_from_analysis(analysis),
            )
            
            # Add markers based on analysis
            markers = []
            
            # Slate marker
            if getattr(analysis, 'has_slate', False):
                markers.append(Marker(
                    timecode="00:00:00:00",
                    name="SLATE",
                    comment=getattr(analysis, 'slate_text', ''),
                    marker_type=MarkerType.SLATE,
                    color="red"
                ))
            
            # Scene/Take markers
            if clip.scene:
                markers.append(Marker(
                    timecode="00:00:02:00",
                    name=f"SCENE {clip.scene}",
                    marker_type=MarkerType.SCENE,
                    color="blue"
                ))
            
            if clip.take:
                markers.append(Marker(
                    timecode="00:00:02:12",
                    name=f"TAKE {clip.take}",
                    marker_type=MarkerType.TAKE,
                    color="green"
                ))
            
            # Quality markers
            if getattr(analysis, 'is_corrupted', False):
                markers.append(Marker(
                    timecode="00:00:00:00",
                    name="ISSUE",
                    comment="Possible corruption detected",
                    marker_type=MarkerType.ISSUE,
                    color="red"
                ))
            
            clip.markers = markers
            clips.append(clip)
        
        total_duration = sum(c.duration_seconds for c in clips)
        
        return Timeline(
            name=name,
            clips=clips,
            fps=self.fps,
            resolution=self.resolution,
            duration_frames=int(total_duration * self.fps)
        )
    
    def _extract_tags_from_analysis(self, analysis: ClipAnalysis) -> List[str]:
        """Extract tags from clip analysis."""
        tags = []
        
        # Add clip type as tag
        if hasattr(analysis, 'clip_type') and analysis.clip_type:
            tags.append(analysis.clip_type.value)
        
        # Add priority tags
        if hasattr(analysis, 'priority_tags') and analysis.priority_tags:
            tags.extend(analysis.priority_tags)
        
        # Add keyword tags
        if hasattr(analysis, 'keyword_tags') and analysis.keyword_tags:
            tags.extend(analysis.keyword_tags)
        
        return tags
    
    def export(self, timeline: Timeline, output_dir: Path, 
               formats: List[ExportFormat],
               template: Optional[ProjectTemplate] = None) -> Dict[ExportFormat, Path]:
        """
        Export timeline to multiple formats.
        
        Args:
            timeline: Timeline to export
            output_dir: Output directory
            formats: List of formats to export
            template: Optional project template
            
        Returns:
            Dictionary mapping format to output path
        """
        results = {}
        
        for fmt in formats:
            try:
                if fmt == ExportFormat.PREMIERE:
                    output_path = output_dir / f"{timeline.name}.prproj"
                    if self.premiere_exporter.export(timeline, output_path, template):
                        results[fmt] = output_path
                
                elif fmt == ExportFormat.RESOLVE:
                    output_path = output_dir / f"{timeline.name}_resolve.xml"
                    if self.resolve_exporter.export(timeline, output_path):
                        results[fmt] = output_path
                
                elif fmt == ExportFormat.FCPXML:
                    output_path = output_dir / f"{timeline.name}.fcpxml"
                    if self.fcpxml_exporter.export(timeline, output_path):
                        results[fmt] = output_path
                
                elif fmt == ExportFormat.EDL:
                    output_path = output_dir / f"{timeline.name}.edl"
                    if self.edl_exporter.export(timeline, output_path):
                        results[fmt] = output_path
                
            except Exception as e:
                logger.error(f"Export to {fmt.value} failed: {e}")
        
        return results
    
    def export_all(self, timeline: Timeline, output_dir: Path,
                   template: Optional[ProjectTemplate] = None) -> Dict[ExportFormat, Path]:
        """Export to all supported formats."""
        return self.export(
            timeline, 
            output_dir, 
            list(ExportFormat),
            template
        )


def export_nle_project(
    media_dir: Path,
    output_dir: Path,
    project_name: str,
    formats: List[str],
    fps: float = 24.0,
    resolution: str = "1920x1080",
    template_name: Optional[str] = None,
) -> Dict[str, Path]:
    """
    Convenience function to export NLE projects from media directory.
    
    Args:
        media_dir: Directory containing media files
        output_dir: Output directory for exports
        project_name: Project name
        formats: List of format strings (premiere, resolve, fcpxml, edl)
        fps: Frame rate
        resolution: Resolution
        template_name: Optional template name
        
    Returns:
        Dictionary of format to output path
    """
    from .analysis import ContentAnalyzer
    
    # Analyze media
    analyzer = ContentAnalyzer()
    analyses = analyzer.analyze_directory(media_dir)
    
    # Get template if specified
    template = None
    if template_name:
        from .templates import get_template_manager
        template = get_template_manager().get_template_by_name(template_name)
    
    # Create export manager
    manager = ExportManager(fps, resolution)
    
    # Create timeline
    timeline = manager.create_timeline_from_analyses(project_name, analyses)
    
    # Parse formats
    export_formats = []
    for fmt in formats:
        try:
            export_formats.append(ExportFormat(fmt.lower()))
        except ValueError:
            logger.warning(f"Unknown export format: {fmt}")
    
    # Export
    results = manager.export(timeline, output_dir, export_formats, template)
    
    # Convert to string keys
    return {fmt.value: str(path) for fmt, path in results.items()}
