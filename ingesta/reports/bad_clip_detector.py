"""
Bad clip detection module for quality warnings.

Detects:
- Black frames (completely black or near-black)
- Out of focus / blurry frames
- Long silence periods
- No audio stream
- Corrupted frames
- Extreme exposure issues

All processing is done locally using FFmpeg.
"""

import re
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class QualityWarning:
    """Quality warning information."""
    warning_type: str
    severity: str  # 'critical', 'warning', 'info'
    message: str
    details: Dict = field(default_factory=dict)


@dataclass
class BadClipAnalysis:
    """Bad clip detection results."""
    has_issues: bool
    warnings: List[QualityWarning]
    black_frame_count: int
    blur_score: float  # 0-1, higher = more blurry
    silence_ratio: float  # 0-1, portion of clip that's silent
    is_corrupted: bool
    exposure_issues: List[str]


def detect_bad_clips(video_path: Path, duration: float) -> BadClipAnalysis:
    """
    Analyze video for quality issues.
    
    Args:
        video_path: Path to video file
        duration: Video duration in seconds
        
    Returns:
        BadClipAnalysis with all quality warnings
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Checking quality: {video_path.name}")
    
    warnings = []
    
    # Check for black frames
    black_count = detect_black_frames(video_path)
    if black_count > 0:
        severity = 'critical' if black_count > 10 else 'warning'
        warnings.append(QualityWarning(
            warning_type='black_frames',
            severity=severity,
            message=f"Detected {black_count} black frames",
            details={'count': black_count}
        ))
    
    # Check for blur/out of focus
    blur_score = detect_blur(video_path)
    if blur_score > 0.7:
        warnings.append(QualityWarning(
            warning_type='out_of_focus',
            severity='warning',
            message=f"Video appears blurry (score: {blur_score:.2f})",
            details={'blur_score': blur_score}
        ))
    
    # Check audio issues
    has_audio, silence_ratio = analyze_audio_issues(video_path)
    
    if not has_audio:
        warnings.append(QualityWarning(
            warning_type='no_audio',
            severity='warning',
            message="No audio stream detected",
            details={}
        ))
    elif silence_ratio > 0.5:
        warnings.append(QualityWarning(
            warning_type='long_silence',
            severity='warning',
            message=f"Long silence detected ({silence_ratio*100:.0f}% of clip)",
            details={'silence_ratio': silence_ratio}
        ))
    
    # Check exposure issues
    exposure_issues = detect_exposure_issues(video_path)
    for issue in exposure_issues:
        warnings.append(QualityWarning(
            warning_type='exposure',
            severity='warning',
            message=issue,
            details={}
        ))
    
    # Check for corruption
    is_corrupted = detect_corruption(video_path)
    if is_corrupted:
        warnings.append(QualityWarning(
            warning_type='corrupted',
            severity='critical',
            message="Video may be corrupted",
            details={}
        ))
    
    result = BadClipAnalysis(
        has_issues=len(warnings) > 0,
        warnings=warnings,
        black_frame_count=black_count,
        blur_score=blur_score,
        silence_ratio=silence_ratio,
        is_corrupted=is_corrupted,
        exposure_issues=exposure_issues
    )
    
    if result.has_issues:
        logger.warning(f"  Found {len(warnings)} quality issues")
        for w in warnings:
            logger.warning(f"    - {w.warning_type}: {w.message}")
    else:
        logger.info(f"  No quality issues detected")
    
    return result


def detect_black_frames(video_path: Path, threshold: int = 32) -> int:
    """
    Detect black frames in video.
    
    Args:
        video_path: Path to video file
        threshold: Luminance threshold (0-255, lower = darker)
        
    Returns:
        Count of black frames detected
    """
    try:
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"blackdetect=d={0.5}:pic_th={threshold/255}",
            "-an",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Count blackdetect events
        black_count = 0
        for line in result.stderr.split('\n'):
            if 'blackdetect' in line and 'black_start' in line:
                black_count += 1
        
        return black_count
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Black frame detection failed: {e}")
        return 0


def detect_blur(video_path: Path) -> float:
    """
    Detect blur/out of focus using variance of Laplacian approximation.
    
    Returns:
        Blur score 0-1 (higher = more blurry)
    """
    try:
        # Extract a few frames and analyze
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract frames at different points
            timestamps = ['00:00:01', '00:00:05', '00:00:10']
            blur_scores = []
            
            for ts in timestamps:
                frame_path = temp_path / f"frame_{ts.replace(':', '')}.jpg"
                
                # Extract frame
                cmd = [
                    "ffmpeg",
                    "-ss", ts,
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(frame_path)
                ]
                
                subprocess.run(cmd, capture_output=True, timeout=30)
                
                if frame_path.exists():
                    # Use edge detection filter as blur indicator
                    cmd = [
                        "ffmpeg",
                        "-i", str(frame_path),
                        "-vf", "edgedetect=mode=colormix:high=20",
                        "-f", "null",
                        "-"
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    
                    # Parse mean and max for edge intensity
                    mean_edge = 0
                    for line in result.stderr.split('\n'):
                        if 'Parsed_edgedetect' in line and 'mean:' in line:
                            try:
                                match = re.search(r'mean:(\d+\.?\d*)', line)
                                if match:
                                    mean_edge = float(match.group(1))
                            except:
                                pass
                    
                    # Low edge intensity suggests blur
                    # Normalize to 0-1 scale (arbitrary thresholds)
                    blur_score = max(0, min(1, 1 - (mean_edge / 50)))
                    blur_scores.append(blur_score)
            
            if blur_scores:
                return sum(blur_scores) / len(blur_scores)
            
            return 0.0
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Blur detection failed: {e}")
        return 0.0


def analyze_audio_issues(video_path: Path) -> Tuple[bool, float]:
    """
    Analyze audio for issues.
    
    Returns:
        Tuple of (has_audio, silence_ratio)
    """
    try:
        # Check if has audio
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        has_audio = 'audio' in result.stdout.lower()
        
        if not has_audio:
            return False, 1.0
        
        # Extract and analyze audio for silence
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_audio = Path(temp_dir) / "audio.wav"
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(temp_audio)
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=60)
            
            if not temp_audio.exists():
                return True, 0.0
            
            # Detect silence
            cmd = [
                "ffmpeg",
                "-i", str(temp_audio),
                "-af", "silencedetect=noise=-50dB:d=1",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            # Calculate total silence duration
            silence_starts = []
            silence_ends = []
            
            for line in result.stderr.split('\n'):
                if 'silence_start:' in line:
                    try:
                        match = re.search(r'silence_start:\s*(\d+\.?\d*)', line)
                        if match:
                            silence_starts.append(float(match.group(1)))
                    except:
                        pass
                elif 'silence_end:' in line:
                    try:
                        match = re.search(r'silence_end:\s*(\d+\.?\d*)', line)
                        if match:
                            silence_ends.append(float(match.group(1)))
                    except:
                        pass
            
            total_silence = 0
            for i, start in enumerate(silence_starts):
                if i < len(silence_ends):
                    total_silence += silence_ends[i] - start
            
            # Get duration
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            try:
                duration = float(result.stdout.strip())
            except:
                duration = 1
            
            silence_ratio = total_silence / duration if duration > 0 else 0
            
            return True, silence_ratio
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Audio analysis failed: {e}")
        return True, 0.0


def detect_exposure_issues(video_path: Path) -> List[str]:
    """
    Detect exposure issues (over/under exposure).
    
    Returns:
        List of exposure issue descriptions
    """
    issues = []
    
    try:
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", "signalstats",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Parse YMAX (max luminance)
        ymax_values = []
        ymin_values = []
        
        for line in result.stderr.split('\n'):
            if 'YMAX=' in line:
                try:
                    match = re.search(r'YMAX=(\d+)', line)
                    if match:
                        ymax_values.append(int(match.group(1)))
                except:
                    pass
            if 'YMIN=' in line:
                try:
                    match = re.search(r'YMIN=(\d+)', line)
                    if match:
                        ymin_values.append(int(match.group(1)))
                except:
                    pass
        
        if ymax_values:
            avg_ymax = sum(ymax_values) / len(ymax_values)
            if avg_ymax > 240:  # Near max
                issues.append("Overexposed highlights detected")
        
        if ymin_values:
            avg_ymin = sum(ymin_values) / len(ymin_values)
            if avg_ymin < 15:  # Near black
                issues.append("Underexposed shadows detected")
        
        return issues
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Exposure detection failed: {e}")
        return []


def detect_corruption(video_path: Path) -> bool:
    """
    Detect potential video corruption.
    
    Returns:
        True if corruption suspected
    """
    try:
        # Run FFmpeg decode test
        cmd = [
            "ffmpeg",
            "-v", "error",
            "-i", str(video_path),
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # Check for corruption indicators in stderr
        corruption_indicators = [
            'corrupt',
            'invalid',
            'error while decoding',
            'truncated',
            'missing picture',
            'decode error'
        ]
        
        stderr_lower = result.stderr.lower()
        for indicator in corruption_indicators:
            if indicator in stderr_lower:
                return True
        
        return False
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Corruption detection failed: {e}")
        return False


class BadClipDetector:
    """
    Detector for quality issues in video clips.
    
    Detects black frames, blur, silence, corruption, and exposure issues.
    All processing is done locally using FFmpeg.
    """
    
    def detect(self, video_path: Path, duration: float) -> BadClipAnalysis:
        """
        Detect quality issues in a video clip.
        
        Args:
            video_path: Path to video file
            duration: Video duration in seconds
            
        Returns:
            BadClipAnalysis with all detected issues
        """
        return detect_bad_clips(video_path, duration)
