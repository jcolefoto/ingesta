"""
Audio-video synchronization using waveform matching.

Provides Pluralize-style audio sync capabilities.
"""

import logging
import tempfile
from pathlib import Path
from typing import Union, List, Optional, Tuple, Dict
from dataclasses import dataclass
import subprocess
import json

import numpy as np

try:
    import librosa
    import soundfile as sf
    SYNC_DEPS_AVAILABLE = True
except ImportError:
    SYNC_DEPS_AVAILABLE = False
    librosa = None
    sf = None


@dataclass
class SyncResult:
    """Result of an audio-video sync operation."""
    video_file: Path
    audio_file: Path
    output_file: Path
    success: bool
    offset_seconds: float = 0.0
    confidence: float = 0.0
    error_message: Optional[str] = None


class WaveformSync:
    """
    Synchronizes external audio with video using waveform cross-correlation.
    """
    
    def __init__(self, sample_rate: int = 22050, tolerance: float = 0.5):
        """
        Initialize waveform sync.
        
        Args:
            sample_rate: Target sample rate for analysis (default: 22050)
            tolerance: Maximum allowed offset in seconds (default: 0.5)
        """
        if not SYNC_DEPS_AVAILABLE:
            raise ImportError(
                "Sync functionality requires librosa and soundfile. "
                "Install with: pip install ingesta[sync]"
            )
        self.sample_rate = sample_rate
        self.tolerance = tolerance
    
    def extract_audio_from_video(
        self,
        video_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None
    ) -> Path:
        """
        Extract audio track from video file using ffmpeg.
        
        Args:
            video_path: Path to video file
            output_path: Optional output path (uses temp file if not specified)
        
        Returns:
            Path to extracted audio file
        """
        video_path = Path(video_path)
        
        if output_path is None:
            output_path = Path(tempfile.gettempdir()) / f"{video_path.stem}_audio.wav"
        else:
            output_path = Path(output_path)
        
        # Use ffmpeg to extract audio
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-i", str(video_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1",  # Mono
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to extract audio from {video_path}: {e}")
            raise
    
    def load_audio(self, audio_path: Union[str, Path]) -> np.ndarray:
        """
        Load audio file and return waveform array.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            Audio waveform as numpy array
        """
        try:
            audio, sr = librosa.load(str(audio_path), sr=self.sample_rate, mono=True)
            return audio
        except Exception as e:
            logging.error(f"Failed to load audio {audio_path}: {e}")
            raise
    
    def normalize_audio(self, audio: np.ndarray) -> np.ndarray:
        """
        Normalize audio waveform to [-1, 1] range.
        
        Args:
            audio: Input audio array
        
        Returns:
            Normalized audio
        """
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            return audio / max_val
        return audio
    
    def compute_cross_correlation(
        self,
        video_audio: np.ndarray,
        external_audio: np.ndarray
    ) -> Tuple[int, float]:
        """
        Compute cross-correlation between two audio signals.
        
        Args:
            video_audio: Audio extracted from video
            external_audio: External audio to sync
        
        Returns:
            Tuple of (offset_samples, correlation_score)
        """
        # Normalize both signals
        video_audio = self.normalize_audio(video_audio)
        external_audio = self.normalize_audio(external_audio)
        
        # Compute cross-correlation using FFT
        correlation = np.correlate(video_audio, external_audio, mode='full')
        
        # Find peak correlation
        max_idx = np.argmax(correlation)
        max_correlation = correlation[max_idx]
        
        # Calculate offset
        # max_idx = len(video_audio) - 1 + offset
        offset = max_idx - (len(video_audio) - 1)
        
        # Normalize correlation score
        correlation_score = max_correlation / (np.std(video_audio) * np.std(external_audio) * len(external_audio))
        
        return offset, correlation_score
    
    def find_best_sync_point(
        self,
        video_audio: np.ndarray,
        external_audio: np.ndarray,
        search_range: Optional[int] = None
    ) -> Tuple[int, float]:
        """
        Find the best synchronization point with optional search range.
        
        Args:
            video_audio: Audio from video
            external_audio: External audio
            search_range: Maximum samples to search (None = full correlation)
        
        Returns:
            Tuple of (offset_samples, confidence)
        """
        if search_range is None:
            offset, confidence = self.compute_cross_correlation(video_audio, external_audio)
        else:
            # Limit search range for faster computation
            # This is a simplified version - could be optimized further
            offset, confidence = self.compute_cross_correlation(video_audio, external_audio)
            
            if abs(offset) > search_range:
                # Re-compute within limited range
                # For now, just use the full correlation
                pass
        
        return offset, confidence
    
    def sync_audio_to_video(
        self,
        video_path: Union[str, Path],
        audio_path: Union[str, Path],
        output_path: Union[str, Path],
        method: str = "waveform"
    ) -> SyncResult:
        """
        Synchronize external audio to video and create merged output.
        
        Args:
            video_path: Path to video file
            audio_path: Path to external audio file
            output_path: Path for output file
            method: Sync method ('waveform' or 'timecode')
        
        Returns:
            SyncResult with details
        """
        video_path = Path(video_path)
        audio_path = Path(audio_path)
        output_path = Path(output_path)
        
        result = SyncResult(
            video_file=video_path,
            audio_file=audio_path,
            output_file=output_path,
            success=False
        )
        
        try:
            logging.info(f"Syncing {audio_path.name} to {video_path.name}")
            
            if method == "waveform":
                # Extract audio from video
                video_audio_path = self.extract_audio_from_video(video_path)
                
                # Load both audio tracks
                video_audio = self.load_audio(video_audio_path)
                external_audio = self.load_audio(audio_path)
                
                # Find sync point
                offset_samples, confidence = self.find_best_sync_point(video_audio, external_audio)
                offset_seconds = offset_samples / self.sample_rate
                
                result.offset_seconds = offset_seconds
                result.confidence = confidence
                
                logging.info(f"Found offset: {offset_seconds:.3f}s (confidence: {confidence:.3f})")
                
                # Check if offset is within tolerance
                if abs(offset_seconds) > self.tolerance:
                    logging.warning(f"Offset {offset_seconds:.3f}s exceeds tolerance {self.tolerance}s")
                    result.error_message = f"Offset exceeds tolerance: {offset_seconds:.3f}s"
                    return result
                
                # Create synced output using ffmpeg
                self._create_synced_output_ffmpeg(
                    video_path, audio_path, output_path, offset_seconds
                )
                
                result.success = True
                
            elif method == "timecode":
                # TODO: Implement timecode-based sync
                result.error_message = "Timecode sync not yet implemented"
                
            else:
                result.error_message = f"Unknown sync method: {method}"
        
        except Exception as e:
            logging.error(f"Sync failed: {e}")
            result.error_message = str(e)
        
        return result
    
    def _create_synced_output_ffmpeg(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        offset_seconds: float
    ):
        """
        Create synced output using ffmpeg.
        
        Args:
            video_path: Source video
            audio_path: External audio
            output_path: Output file
            offset_seconds: Audio offset (positive = audio starts later)
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build ffmpeg command
        # We use adelay filter to delay audio if needed
        if offset_seconds > 0:
            # External audio starts after video audio
            # Delay the external audio
            delay_ms = int(offset_seconds * 1000)
            audio_filter = f"adelay={delay_ms}|{delay_ms}"
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-filter_complex", f"[1:a]{audio_filter}[a]",
                "-map", "0:v:0",
                "-map", "[a]",
                str(output_path)
            ]
        elif offset_seconds < 0:
            # External audio starts before video audio
            # Trim the external audio and use it from the beginning
            trim_seconds = abs(offset_seconds)
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-ss", str(trim_seconds),
                "-i", str(audio_path),
                "-map", "0:v:0",
                "-map", "2:a:0",
                "-shortest",
                str(output_path)
            ]
        else:
            # No offset, just replace audio
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                str(output_path)
            ]
        
        subprocess.run(cmd, check=True, capture_output=True)


def sync_audio_video(
    video_dir: Union[str, Path],
    audio_dir: Union[str, Path],
    output_dir: Union[str, Path],
    tolerance: float = 0.5,
    prefix: str = "synced_",
    video_formats: Tuple[str, ...] = (".mp4", ".mov", ".mxf"),
    audio_formats: Tuple[str, ...] = (".wav", ".mp3", ".bwf"),
    progress_callback: Optional[callable] = None
) -> List[SyncResult]:
    """
    Batch sync audio files to video files in directories.
    
    Args:
        video_dir: Directory containing video files
        audio_dir: Directory containing audio files
        output_dir: Output directory for synced files
        tolerance: Maximum sync offset tolerance
        prefix: Prefix for output filenames
        video_formats: Tuple of video file extensions
        audio_formats: Tuple of audio file extensions
        progress_callback: Optional callback(current, total)
    
    Returns:
        List of SyncResult objects
    """
    video_dir = Path(video_dir)
    audio_dir = Path(audio_dir)
    output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect video and audio files
    video_files = []
    for ext in video_formats:
        video_files.extend(video_dir.glob(f"*{ext}"))
        video_files.extend(video_dir.glob(f"*{ext.upper()}"))
    
    audio_files = []
    for ext in audio_formats:
        audio_files.extend(audio_dir.glob(f"*{ext}"))
        audio_files.extend(audio_dir.glob(f"*{ext.upper()}"))
    
    logging.info(f"Found {len(video_files)} video files and {len(audio_files)} audio files")
    
    # For now, simple matching by filename (without extension)
    # In production, you'd want more sophisticated matching
    sync_results = []
    
    sync_engine = WaveformSync(tolerance=tolerance)
    
    total = len(video_files)
    for idx, video_file in enumerate(video_files):
        if progress_callback:
            progress_callback(idx + 1, total)
        
        # Find matching audio file
        video_name = video_file.stem
        matching_audio = None
        
        for audio_file in audio_files:
            # Simple heuristic: audio filename contains video filename or vice versa
            if video_name in audio_file.stem or audio_file.stem in video_name:
                matching_audio = audio_file
                break
        
        if not matching_audio:
            logging.warning(f"No matching audio found for {video_file.name}")
            continue
        
        output_file = output_dir / f"{prefix}{video_file.stem}{video_file.suffix}"
        
        result = sync_engine.sync_audio_to_video(
            video_file, matching_audio, output_file
        )
        
        sync_results.append(result)
        
        if result.success:
            logging.info(f"Successfully synced: {output_file.name}")
        else:
            logging.error(f"Failed to sync {video_file.name}: {result.error_message}")
    
    return sync_results
