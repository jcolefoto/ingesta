"""
Metadata extraction module for timecode, reel IDs, and camera metadata.

Extracts professional metadata from:
- Timecode (start, end, duration)
- Reel IDs (from filename, folder, or metadata)
- Camera information (model, serial, settings)
- Production metadata (scene, shot, take from filenames)

All processing is done locally using FFmpeg and file analysis.
"""

import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple
from dataclasses import dataclass


@dataclass
class TimecodeInfo:
    """Timecode information."""
    start_tc: Optional[str]  # HH:MM:SS:FF
    end_tc: Optional[str]
    duration_tc: Optional[str]
    frame_rate: Optional[float]
    drop_frame: bool


@dataclass
class ReelInfo:
    """Reel and production information."""
    reel_id: Optional[str]
    scene: Optional[str]
    shot: Optional[str]
    take: Optional[str]
    camera_id: Optional[str]
    source_from: str  # 'filename', 'folder', 'metadata'


@dataclass
class MetadataExtraction:
    """Complete metadata extraction results."""
    timecode: TimecodeInfo
    reel: ReelInfo
    camera_model: Optional[str]
    camera_serial: Optional[str]
    lens_info: Optional[str]
    iso: Optional[int]
    white_balance: Optional[str]
    resolution: Optional[str]
    frame_rate: Optional[float]


def extract_metadata(video_path: Path) -> MetadataExtraction:
    """
    Extract comprehensive metadata from video file.
    
    Args:
        video_path: Path to video file
        
    Returns:
        MetadataExtraction with all available metadata
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Extracting metadata: {video_path.name}")
    
    # Get FFmpeg metadata
    ffprobe_data = get_ffprobe_metadata(video_path)
    
    # Extract timecode
    timecode = extract_timecode(ffprobe_data, video_path)
    
    # Extract reel/scene/shot/take info
    reel = extract_reel_info(video_path, ffprobe_data)
    
    # Extract camera info
    camera_model = extract_camera_model(ffprobe_data)
    camera_serial = extract_camera_serial(ffprobe_data)
    lens_info = extract_lens_info(ffprobe_data)
    iso = extract_iso(ffprobe_data)
    white_balance = extract_white_balance(ffprobe_data)
    
    # Video technical info
    resolution = extract_resolution(ffprobe_data)
    frame_rate = extract_frame_rate(ffprobe_data)
    
    result = MetadataExtraction(
        timecode=timecode,
        reel=reel,
        camera_model=camera_model,
        camera_serial=camera_serial,
        lens_info=lens_info,
        iso=iso,
        white_balance=white_balance,
        resolution=resolution,
        frame_rate=frame_rate
    )
    
    logger.info(f"  Timecode: {timecode.start_tc}, Reel: {reel.reel_id}, "
                f"Scene: {reel.scene}, Camera: {camera_model}")
    
    return result


def get_ffprobe_metadata(video_path: Path) -> Dict:
    """Get metadata from ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        
        return {}
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"FFprobe failed: {e}")
        return {}


def extract_timecode(ffprobe_data: Dict, video_path: Path) -> TimecodeInfo:
    """Extract timecode information."""
    start_tc = None
    frame_rate = None
    drop_frame = False
    
    # Look in format tags
    format_tags = ffprobe_data.get('format', {}).get('tags', {})
    
    # Common timecode tag names
    tc_tags = ['timecode', 'TIMECODE', 'TimeCode', 'com.apple.quicktime.timecode']
    
    for tag in tc_tags:
        if tag in format_tags:
            start_tc = format_tags[tag]
            break
    
    # Look in stream tags
    for stream in ffprobe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            stream_tags = stream.get('tags', {})
            
            # Get frame rate
            fps_str = stream.get('r_frame_rate', '')
            if fps_str and '/' in fps_str:
                try:
                    num, den = fps_str.split('/')
                    frame_rate = float(num) / float(den)
                except:
                    pass
            
            # Get timecode from stream
            for tag in tc_tags:
                if tag in stream_tags:
                    start_tc = stream_tags[tag]
                    break
            
            # Check for drop frame
            if 'drop_frame' in stream_tags:
                drop_frame = stream_tags['drop_frame'].lower() in ['true', '1', 'yes']
    
    # Calculate duration timecode if we have start and duration
    duration_tc = None
    end_tc = None
    
    if start_tc and frame_rate:
        duration_sec = float(ffprobe_data.get('format', {}).get('duration', 0))
        
        # Parse start timecode
        try:
            parts = start_tc.replace(';', ':').split(':')
            if len(parts) == 4:
                hours, minutes, seconds, frames = map(int, parts)
                total_frames = (hours * 3600 + minutes * 60 + seconds) * frame_rate + frames
                
                # Add duration
                duration_frames = int(duration_sec * frame_rate)
                end_frames = total_frames + duration_frames
                
                # Convert back to timecode
                end_hours = int(end_frames / (3600 * frame_rate))
                end_frames %= (3600 * frame_rate)
                end_mins = int(end_frames / (60 * frame_rate))
                end_frames %= (60 * frame_rate)
                end_secs = int(end_frames / frame_rate)
                end_frames %= int(frame_rate)
                
                sep = ';' if drop_frame else ':'
                end_tc = f"{end_hours:02d}:{end_mins:02d}:{end_secs:02d}{sep}{end_frames:02d}"
                
                # Duration TC
                dur_hours = int(duration_frames / (3600 * frame_rate))
                duration_frames %= (3600 * frame_rate)
                dur_mins = int(duration_frames / (60 * frame_rate))
                duration_frames %= (60 * frame_rate)
                dur_secs = int(duration_frames / frame_rate)
                dur_frms = duration_frames % int(frame_rate)
                
                duration_tc = f"{dur_hours:02d}:{dur_mins:02d}:{dur_secs:02d}:{dur_frms:02d}"
        except:
            pass
    
    return TimecodeInfo(
        start_tc=start_tc,
        end_tc=end_tc,
        duration_tc=duration_tc,
        frame_rate=frame_rate,
        drop_frame=drop_frame
    )


def extract_reel_info(video_path: Path, ffprobe_data: Dict) -> ReelInfo:
    """Extract reel, scene, shot, take information."""
    reel_id = None
    scene = None
    shot = None
    take = None
    camera_id = None
    source_from = 'filename'
    
    filename = video_path.stem.upper()
    parent_folder = video_path.parent.name.upper()
    
    # Pattern 1: Scene_Shot_Take (e.g., "SCENE01_SHOT02_TAKE03")
    pattern1 = re.search(r'SCENE[_\-]?(\d+)[A-Z]?[_\-]?SHOT[_\-]?(\d+)[_\-]?TAKE[_\-]?(\d+)', filename)
    if pattern1:
        scene = f"Scene {pattern1.group(1)}"
        shot = f"Shot {pattern1.group(2)}"
        take = f"Take {pattern1.group(3)}"
    
    # Pattern 2: S_S_T (e.g., "01_02_03" or "01_02_03A")
    if not scene:
        pattern2 = re.search(r'\b(\d{2,3})[_\-](\d{1,2})[_\-](\d{1,2}[A-Z]?)\b', filename)
        if pattern2:
            scene = f"Scene {pattern2.group(1)}"
            shot = f"Shot {pattern2.group(2)}"
            take = f"Take {pattern2.group(3)}"
    
    # Pattern 3: Reel ID from folder (e.g., "A001", "B002")
    reel_pattern = re.search(r'^([A-Z]\d{3,4})$', parent_folder)
    if reel_pattern:
        reel_id = parent_folder
        camera_id = reel_id[0]  # First letter is camera
    
    # Pattern 4: Reel from filename (e.g., "A001_001.MOV")
    if not reel_id:
        reel_pattern = re.search(r'^([A-Z]\d{3,4})[_\-]', filename)
        if reel_pattern:
            reel_id = reel_pattern.group(1)
            camera_id = reel_id[0]
    
    # Pattern 5: Camera roll (e.g., "CAM01", "CAMERA_A")
    if not camera_id:
        cam_pattern = re.search(r'CAM(?:ERA)?[_\-]?(\w+)', filename)
        if cam_pattern:
            camera_id = f"CAM{cam_pattern.group(1)}"
    
    # Pattern 6: Production naming (e.g., "PROD_101_01_01")
    prod_pattern = re.search(r'PROD[_\-]?(\d+)[_\-](\d+)[_\-](\d+)', filename)
    if prod_pattern and not scene:
        scene = f"Scene {prod_pattern.group(1)}"
        shot = f"Shot {prod_pattern.group(2)}"
        take = f"Take {prod_pattern.group(3)}"
    
    # Check metadata for reel info
    format_tags = ffprobe_data.get('format', {}).get('tags', {})
    
    if not reel_id:
        for tag in ['reel', 'REEL', 'Reel', 'reel_name']:
            if tag in format_tags:
                reel_id = format_tags[tag]
                source_from = 'metadata'
                break
    
    if not scene:
        for tag in ['scene', 'SCENE', 'Scene']:
            if tag in format_tags:
                scene = format_tags[tag]
                source_from = 'metadata'
                break
    
    return ReelInfo(
        reel_id=reel_id,
        scene=scene,
        shot=shot,
        take=take,
        camera_id=camera_id,
        source_from=source_from
    )


def extract_camera_model(ffprobe_data: Dict) -> Optional[str]:
    """Extract camera model from metadata."""
    tags = ffprobe_data.get('format', {}).get('tags', {})
    
    # Common camera model tags
    model_tags = ['encoder', 'ENCODER', 'com.apple.quicktime.model']
    
    for tag in model_tags:
        if tag in tags:
            model = tags[tag]
            # Clean up common patterns
            if 'Apple' in model or 'iPhone' in model:
                return model
            return model
    
    return None


def extract_camera_serial(ffprobe_data: Dict) -> Optional[str]:
    """Extract camera serial number."""
    tags = ffprobe_data.get('format', {}).get('tags', {})
    
    serial_tags = ['serial', 'SERIAL', 'com.apple.quicktime.serial']
    
    for tag in serial_tags:
        if tag in tags:
            return tags[tag]
    
    return None


def extract_lens_info(ffprobe_data: Dict) -> Optional[str]:
    """Extract lens information."""
    tags = ffprobe_data.get('format', {}).get('tags', {})
    
    lens_tags = ['lens', 'LENS', 'lens_model']
    
    for tag in lens_tags:
        if tag in tags:
            return tags[tag]
    
    return None


def extract_iso(ffprobe_data: Dict) -> Optional[int]:
    """Extract ISO value."""
    tags = ffprobe_data.get('format', {}).get('tags', {})
    
    iso_tags = ['iso', 'ISO', 'ISOSpeedRatings']
    
    for tag in iso_tags:
        if tag in tags:
            try:
                return int(tags[tag])
            except:
                pass
    
    return None


def extract_white_balance(ffprobe_data: Dict) -> Optional[str]:
    """Extract white balance setting."""
    tags = ffprobe_data.get('format', {}).get('tags', {})
    
    wb_tags = ['white_balance', 'WhiteBalance', 'whitebalance']
    
    for tag in wb_tags:
        if tag in tags:
            return tags[tag]
    
    return None


def extract_resolution(ffprobe_data: Dict) -> Optional[str]:
    """Extract video resolution."""
    for stream in ffprobe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            width = stream.get('width')
            height = stream.get('height')
            if width and height:
                return f"{width}x{height}"
    
    return None


def extract_frame_rate(ffprobe_data: Dict) -> Optional[float]:
    """Extract frame rate."""
    for stream in ffprobe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            fps_str = stream.get('r_frame_rate', '')
            if fps_str and '/' in fps_str:
                try:
                    num, den = fps_str.split('/')
                    return float(num) / float(den)
                except:
                    pass
    
    return None


class MetadataExtractor:
    """
    Extractor for professional video metadata.
    
    Extracts timecode, reel IDs, scene/shot/take, and camera info.
    All processing is done locally using FFmpeg.
    """
    
    def extract(self, video_path: Path) -> MetadataExtraction:
        """
        Extract all metadata from a video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            MetadataExtraction with all available metadata
        """
        return extract_metadata(video_path)
