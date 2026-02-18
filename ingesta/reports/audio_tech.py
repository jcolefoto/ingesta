"""
Audio technical analysis module for detailed audio metrics.

Analyzes:
- Peak levels (dBFS)
- RMS levels (dBFS)
- Clipping detection
- Channel configuration
- Sample rate
- Bit depth
- Silence detection

All processing is done locally using FFmpeg.
"""

import re
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class AudioTechAnalysis:
    """Technical audio analysis results."""
    peak_dbfs: float
    rms_dbfs: float
    true_peak_dbfs: Optional[float]
    clipping_detected: bool
    clipping_count: int
    channels: int
    sample_rate: int
    bit_depth: Optional[int]
    codec: str
    silence_detected: bool
    silence_duration: float
    warnings: List[str]


def analyze_audio_tech(video_path: Path) -> Optional[AudioTechAnalysis]:
    """
    Perform detailed technical audio analysis on a video file.
    
    Args:
        video_path: Path to video file
        
    Returns:
        AudioTechAnalysis or None if no audio/no analysis possible
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Analyzing audio tech: {video_path.name}")
    
    # First check if video has audio
    has_audio, audio_info = get_audio_info(video_path)
    if not has_audio:
        logger.info(f"  No audio stream found")
        return None
    
    # Extract audio to temp file for analysis
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_audio = Path(temp_dir) / "audio.wav"
        
        if not extract_audio(video_path, temp_audio):
            logger.warning(f"  Failed to extract audio")
            return None
        
        # Analyze levels
        levels = analyze_levels(temp_audio)
        
        # Detect clipping
        clipping_detected, clipping_count = detect_clipping(temp_audio)
        
        # Detect silence
        silence_detected, silence_duration = detect_silence(temp_audio)
        
        # Build warnings list
        warnings = []
        if clipping_detected:
            warnings.append(f"Clipping detected ({clipping_count} instances)")
        if silence_detected and silence_duration > 2.0:
            warnings.append(f"Long silence ({silence_duration:.1f}s)")
        if levels.get('peak_dbfs', 0) > -1.0:
            warnings.append("Near-clipping levels")
        if levels.get('peak_dbfs', -60) < -40:
            warnings.append("Low audio levels")
        
        result = AudioTechAnalysis(
            peak_dbfs=levels.get('peak_dbfs', -96.0),
            rms_dbfs=levels.get('rms_dbfs', -96.0),
            true_peak_dbfs=levels.get('true_peak_dbfs'),
            clipping_detected=clipping_detected,
            clipping_count=clipping_count,
            channels=audio_info.get('channels', 0),
            sample_rate=audio_info.get('sample_rate', 0),
            bit_depth=audio_info.get('bit_depth'),
            codec=audio_info.get('codec', 'unknown'),
            silence_detected=silence_detected,
            silence_duration=silence_duration,
            warnings=warnings
        )
        
        logger.info(f"  Peak: {result.peak_dbfs:.1f} dBFS, RMS: {result.rms_dbfs:.1f} dBFS, "
                   f"Channels: {result.channels}, Clipping: {clipping_detected}")
        
        return result


def get_audio_info(video_path: Path) -> Tuple[bool, Dict]:
    """
    Get basic audio stream information.
    
    Returns:
        Tuple of (has_audio, info_dict)
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=channels,sample_rate,bits_per_raw_sample,codec_name",
            "-of", "default=noprint_wrappers=1",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0 or not result.stdout.strip():
            return False, {}
        
        info = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                if key == 'channels':
                    info['channels'] = int(value)
                elif key == 'sample_rate':
                    info['sample_rate'] = int(value)
                elif key == 'bits_per_raw_sample':
                    info['bit_depth'] = int(value) if value != 'N/A' else None
                elif key == 'codec_name':
                    info['codec'] = value
        
        return True, info
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Audio info extraction failed: {e}")
        return False, {}


def extract_audio(video_path: Path, output_path: Path) -> bool:
    """Extract audio to WAV for analysis."""
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        return result.returncode == 0 and output_path.exists()
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Audio extraction failed: {e}")
        return False


def analyze_levels(audio_path: Path) -> Dict[str, float]:
    """
    Analyze audio levels using volumedetect and astats filters.
    
    Returns:
        Dictionary with peak_dbfs, rms_dbfs, true_peak_dbfs
    """
    levels = {
        'peak_dbfs': -96.0,
        'rms_dbfs': -96.0,
        'true_peak_dbfs': None
    }
    
    try:
        # Use volumedetect filter
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", "volumedetect",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Parse volumedetect output
        for line in result.stderr.split('\n'):
            if 'max_volume:' in line:
                try:
                    # max_volume is a negative number or -91 dB for silence
                    match = re.search(r'max_volume:\s*(-?\d+\.?\d*)\s*dB', line)
                    if match:
                        max_vol = float(match.group(1))
                        # Convert to dBFS (0 dBFS = full scale)
                        levels['peak_dbfs'] = max_vol
                except:
                    pass
            
            if 'mean_volume:' in line:
                try:
                    match = re.search(r'mean_volume:\s*(-?\d+\.?\d*)\s*dB', line)
                    if match:
                        levels['rms_dbfs'] = float(match.group(1))
                except:
                    pass
        
        # Use astats for true peak
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", "astats=metadata=1",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Parse astats output for true peak
        for line in result.stderr.split('\n'):
            if 'Peak level dB:' in line:
                try:
                    match = re.search(r'Peak level dB:\s*(-?\d+\.?\d*)', line)
                    if match:
                        levels['true_peak_dbfs'] = float(match.group(1))
                except:
                    pass
        
        return levels
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Level analysis failed: {e}")
        return levels


def detect_clipping(audio_path: Path, threshold_db: float = -0.5) -> Tuple[bool, int]:
    """
    Detect audio clipping by analyzing samples over threshold.
    
    Args:
        audio_path: Path to audio file
        threshold_db: Threshold in dBFS (default -0.5 dBFS)
        
    Returns:
        Tuple of (clipping_detected, clipping_count)
    """
    try:
        # Convert dB threshold to linear
        threshold_linear = 10 ** (threshold_db / 20)
        
        # Use astats to find clipping
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", f"astats=metadata=1:reset=1",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        clipping_count = 0
        
        # Look for peak levels near 0 dB
        for line in result.stderr.split('\n'):
            if 'Peak level dB:' in line:
                try:
                    match = re.search(r'Peak level dB:\s*(-?\d+\.?\d*)', line)
                    if match:
                        peak_db = float(match.group(1))
                        if peak_db >= threshold_db:
                            clipping_count += 1
                except:
                    pass
        
        # Alternative: use volumedetect max_volume
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", "volumedetect",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        for line in result.stderr.split('\n'):
            if 'max_volume:' in line and 'dB' in line:
                try:
                    match = re.search(r'max_volume:\s*(-?\d+\.?\d*)\s*dB', line)
                    if match:
                        max_vol = float(match.group(1))
                        # If max is near 0 dB, likely clipping
                        if max_vol > -0.1:
                            clipping_count = max(clipping_count, 1)
                except:
                    pass
        
        return clipping_count > 0, clipping_count
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Clipping detection failed: {e}")
        return False, 0


def detect_silence(audio_path: Path, noise_db: int = -50, min_duration: float = 0.5) -> Tuple[bool, float]:
    """
    Detect silence in audio.
    
    Args:
        audio_path: Path to audio file
        noise_db: Noise threshold in dB (default -50)
        min_duration: Minimum silence duration to report
        
    Returns:
        Tuple of (silence_detected, total_silence_duration)
    """
    try:
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
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
        
        # Calculate total silence duration
        total_silence = 0.0
        for i, start in enumerate(silence_starts):
            if i < len(silence_ends):
                total_silence += silence_ends[i] - start
        
        return total_silence > 0, total_silence
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Silence detection failed: {e}")
        return False, 0.0


class AudioTechAnalyzer:
    """
    Analyzer for detailed audio technical metrics.
    
    All processing is done locally using FFmpeg.
    """
    
    def analyze(self, video_path: Path) -> Optional[AudioTechAnalysis]:
        """
        Analyze audio technical aspects of a video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            AudioTechAnalysis or None if no audio
        """
        return analyze_audio_tech(video_path)
