"""
Local frame analysis module for generating visual descriptions of video clips.

Provides fully offline frame extraction and visual analysis.
All processing happens locally - no data is sent to external services.
"""

import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class ShotType(Enum):
    """Visual shot types based on framing."""
    WIDE = "wide"           # Wide/establishing shot
    MEDIUM = "medium"       # Medium shot
    CLOSE_UP = "close_up"   # Close-up
    EXTREME_CLOSE = "extreme_close"  # Extreme close-up
    UNKNOWN = "unknown"


class SceneType(Enum):
    """Scene content types."""
    INTERIOR = "interior"
    EXTERIOR = "exterior"
    UNKNOWN = "unknown"


@dataclass
class FrameAnalysis:
    """Results of frame analysis."""
    description: str
    shot_type: ShotType
    scene_type: SceneType
    has_faces: bool
    is_static: bool
    dominant_colors: List[str]
    brightness_score: float  # 0-1, higher is brighter
    contrast_score: float    # 0-1, higher is more contrast
    

def extract_key_frames(video_path: Path, 
                       output_dir: Path,
                       num_frames: int = 5) -> List[Path]:
    """
    Extract evenly-spaced key frames from video.
    
    Args:
        video_path: Path to video file
        output_dir: Directory to save frames
        num_frames: Number of frames to extract
        
    Returns:
        List of paths to extracted frames
    """
    logger = logging.getLogger(__name__)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Get video duration
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        # Extract frames at evenly spaced intervals
        frames = []
        for i in range(num_frames):
            # Skip first and last 5% to avoid fade in/out
            timestamp = (duration * 0.05) + (duration * 0.9 * i / max(num_frames - 1, 1))
            
            frame_path = output_dir / f"frame_{i:03d}.jpg"
            
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(frame_path)
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=30)
            
            if frame_path.exists():
                frames.append(frame_path)
        
        return frames
        
    except Exception as e:
        logger.warning(f"Frame extraction failed: {e}")
        return []


def analyze_frame_brightness(frame_path: Path) -> Tuple[float, float]:
    """
    Analyze frame brightness and contrast using FFmpeg.
    
    Args:
        frame_path: Path to frame image
        
    Returns:
        Tuple of (brightness_score, contrast_score) 0-1
    """
    try:
        cmd = [
            "ffmpeg",
            "-i", str(frame_path),
            "-vf", "signalstats",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse signalstats output
        brightness = 0.5
        contrast = 0.5
        
        for line in result.stderr.split('\n'):
            if 'YAVG' in line:
                try:
                    # YAVG is average luma (0-255)
                    parts = line.split()
                    for part in parts:
                        if part.startswith('YAVG='):
                            yavg = float(part.split('=')[1])
                            brightness = yavg / 255.0
                        elif part.startswith('YMAX='):
                            ymax = float(part.split('=')[1])
                        elif part.startswith('YMIN='):
                            ymin = float(part.split('=')[1])
                            contrast = (ymax - ymin) / 255.0 if 'ymax' in dir() else 0.5
                except:
                    pass
        
        return brightness, contrast
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Brightness analysis failed: {e}")
        return 0.5, 0.5


def detect_motion_between_frames(frame1: Path, frame2: Path) -> float:
    """
    Detect motion between two frames using scene change detection.
    
    Args:
        frame1: First frame path
        frame2: Second frame path
        
    Returns:
        Motion score 0-1
    """
    try:
        # Use ffmpeg to compare frames
        cmd = [
            "ffmpeg",
            "-i", str(frame1),
            "-i", str(frame2),
            "-lavfi", "ssim",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Parse SSIM (Structural Similarity Index)
        # Lower SSIM = more difference = more motion
        ssim_value = 1.0
        
        for line in result.stderr.split('\n'):
            if 'SSIM' in line and 'All:' in line:
                try:
                    # Extract SSIM value
                    match = line.split('All:')[1].split('(')[0].strip()
                    ssim_value = float(match)
                except:
                    pass
        
        # Convert SSIM to motion score (inverse, 0-1)
        motion = 1.0 - ssim_value
        return motion
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Motion detection failed: {e}")
        return 0.0


def estimate_shot_type(brightness: float, contrast: float, 
                       video_info: Dict) -> ShotType:
    """
    Estimate shot type based on visual characteristics.
    
    This is a heuristic based on typical shot characteristics:
    - Wide shots often have more detail, lower contrast edges
    - Close-ups often have smoother gradients
    
    Args:
        brightness: Average brightness
        contrast: Contrast score
        video_info: Video metadata
        
    Returns:
        Estimated shot type
    """
    # Simple heuristics - in a real implementation, you'd use
    # more sophisticated computer vision techniques
    
    # High contrast often indicates close-up (clear subject separation)
    if contrast > 0.7:
        return ShotType.CLOSE_UP
    elif contrast > 0.5:
        return ShotType.MEDIUM
    elif contrast < 0.3:
        return ShotType.WIDE
    else:
        return ShotType.UNKNOWN


def generate_visual_description(
    shot_type: ShotType,
    scene_type: SceneType,
    is_static: bool,
    brightness: float,
    contrast: float,
    has_faces: bool = False
) -> str:
    """
    Generate a human-readable description of the visual content.
    
    Args:
        shot_type: Type of shot framing
        scene_type: Interior/exterior
        is_static: Whether camera is static
        brightness: Brightness score
        contrast: Contrast score
        has_faces: Whether faces detected (would need face detection)
        
    Returns:
        Description string
    """
    parts = []
    
    # Shot type
    if shot_type == ShotType.WIDE:
        parts.append("Wide establishing shot")
    elif shot_type == ShotType.MEDIUM:
        parts.append("Medium shot")
    elif shot_type == ShotType.CLOSE_UP:
        parts.append("Close-up")
    elif shot_type == ShotType.EXTREME_CLOSE:
        parts.append("Extreme close-up")
    else:
        parts.append("Shot")
    
    # Scene type
    if scene_type == SceneType.INTERIOR:
        parts.append("interior")
    elif scene_type == SceneType.EXTERIOR:
        parts.append("exterior")
    
    # Lighting
    if brightness > 0.7:
        parts.append("brightly lit")
    elif brightness < 0.3:
        parts.append("low lighting")
    
    # Camera movement
    if is_static:
        parts.append("static camera")
    else:
        parts.append("with camera movement")
    
    # Content hint
    if has_faces:
        parts.append("featuring subject")
    
    return " - ".join(parts) if len(parts) > 1 else parts[0]


def analyze_video_frames(video_path: Path) -> Optional[FrameAnalysis]:
    """
    Analyze key frames from a video to generate visual description.
    
    All processing is done locally using FFmpeg.
    
    Args:
        video_path: Path to video file
        
    Returns:
        FrameAnalysis or None if failed
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Analyzing frames: {video_path.name}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract key frames
        frames = extract_key_frames(video_path, temp_path, num_frames=5)
        
        if not frames:
            logger.warning(f"No frames extracted from {video_path}")
            return None
        
        # Analyze frames
        brightness_scores = []
        contrast_scores = []
        motion_scores = []
        
        for frame in frames:
            b, c = analyze_frame_brightness(frame)
            brightness_scores.append(b)
            contrast_scores.append(c)
        
        # Detect motion between consecutive frames
        for i in range(len(frames) - 1):
            motion = detect_motion_between_frames(frames[i], frames[i+1])
            motion_scores.append(motion)
        
        # Calculate averages
        avg_brightness = sum(brightness_scores) / len(brightness_scores)
        avg_contrast = sum(contrast_scores) / len(contrast_scores)
        avg_motion = sum(motion_scores) / len(motion_scores) if motion_scores else 0
        
        # Determine characteristics
        is_static = avg_motion < 0.1
        shot_type = estimate_shot_type(avg_brightness, avg_contrast, {})
        
        # Guess scene type based on brightness (exteriors often brighter)
        scene_type = SceneType.EXTERIOR if avg_brightness > 0.6 else SceneType.INTERIOR
        
        # Generate description
        description = generate_visual_description(
            shot_type=shot_type,
            scene_type=scene_type,
            is_static=is_static,
            brightness=avg_brightness,
            contrast=avg_contrast,
            has_faces=False  # Would need face detection
        )
        
        result = FrameAnalysis(
            description=description,
            shot_type=shot_type,
            scene_type=scene_type,
            has_faces=False,
            is_static=is_static,
            dominant_colors=[],  # Would need color analysis
            brightness_score=avg_brightness,
            contrast_score=avg_contrast
        )
        
        logger.info(f"  Visual: {description}")
        
        return result


class LocalFrameAnalyzer:
    """
    Local-only video frame analyzer.
    
    Security: All processing is done locally on your machine.
    No video frames or analysis data is sent to any external service.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def analyze(self, video_path: Path) -> Optional[FrameAnalysis]:
        """
        Analyze a video file and generate visual description.
        
        Args:
            video_path: Path to video file
            
        Returns:
            FrameAnalysis or None if failed
        """
        return analyze_video_frames(video_path)
