"""
Content analysis module for video clip classification.

Analyzes video content to identify:
- B-roll (supplemental footage)
- Establishing shots
- Interview/talking head shots
- Action/movement shots
- Static shots
- Audio presence (syncable vs non-syncable)
"""

import logging
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Union, Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

import numpy as np


class ClipType(Enum):
    """Classification types for video clips."""
    SYNCABLE = "syncable"           # Has clear audio for syncing
    B_ROLL = "b_roll"              # Supplemental footage, no clear dialogue
    ESTABLISHING = "establishing"   # Wide shots, scene setting
    INTERVIEW = "interview"         # Talking head, interview footage
    ACTION = "action"              # Movement, dynamic shots
    STATIC = "static"              # Minimal movement, tripod shots
    INSERT = "insert"              # Close-ups, detail shots
    UNKNOWN = "unknown"            # Unable to classify


class AudioType(Enum):
    """Audio classification types."""
    CLEAR_DIALOGUE = "clear_dialogue"
    AMBIENT = "ambient"
    MUSIC = "music"
    SILENCE = "silence"
    NOISE = "noise"
    UNKNOWN = "unknown"


@dataclass
class ClipAnalysis:
    """Results of clip content analysis."""
    file_path: Path
    clip_type: ClipType
    audio_type: AudioType
    duration: float
    has_audio: bool
    is_syncable: bool
    motion_score: float  # 0.0 to 1.0, higher = more motion
    audio_score: float   # 0.0 to 1.0, higher = clearer audio
    confidence: float    # 0.0 to 1.0, classification confidence
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "file_path": str(self.file_path),
            "clip_type": self.clip_type.value,
            "audio_type": self.audio_type.value,
            "duration": self.duration,
            "has_audio": self.has_audio,
            "is_syncable": self.is_syncable,
            "motion_score": self.motion_score,
            "audio_score": self.audio_score,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class ContentAnalyzer:
    """
    Analyzes video content to classify clips for organization.
    """
    
    # Thresholds for classification
    MOTION_THRESHOLD_HIGH = 0.6
    MOTION_THRESHOLD_LOW = 0.2
    AUDIO_THRESHOLD_CLEAR = 0.5
    DURATION_THRESHOLD_ESTABLISHING = 5.0  # seconds
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ingesta_analysis_")
    
    def get_video_info(self, video_path: Path) -> Dict:
        """
        Extract video metadata using ffprobe.
        
        Args:
            video_path: Path to video file
        
        Returns:
            Dictionary with video metadata
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logging.error(f"Failed to get video info for {video_path}: {e}")
            return {}
    
    def analyze_motion(self, video_path: Path) -> float:
        """
        Analyze video motion using frame differencing.
        
        Args:
            video_path: Path to video file
        
        Returns:
            Motion score from 0.0 (static) to 1.0 (high motion)
        """
        try:
            # Use ffmpeg to extract motion vectors or analyze scene changes
            # This is a simplified approach using select=scenedetect
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-vf", "select='gt(scene,0.3)',showinfo",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Count scene changes as proxy for motion
            scene_changes = result.stderr.count("pts_time:")
            
            # Get duration
            info = self.get_video_info(video_path)
            duration = float(info.get('format', {}).get('duration', 0))
            
            if duration > 0:
                # Normalize: more scene changes = more motion
                motion_score = min(scene_changes / (duration / 2), 1.0)
            else:
                motion_score = 0.0
            
            return motion_score
            
        except Exception as e:
            logging.error(f"Motion analysis failed for {video_path}: {e}")
            return 0.0
    
    def analyze_audio(self, video_path: Path) -> Tuple[AudioType, float]:
        """
        Analyze audio characteristics.
        
        Args:
            video_path: Path to video file
        
        Returns:
            Tuple of (audio_type, audio_score)
        """
        try:
            # Extract audio to temp file
            temp_audio = Path(self.temp_dir) / f"{video_path.stem}_audio.wav"
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vn",  # No video
                "-acodec", "pcm_s16le",
                "-ar", "22050",
                "-ac", "1",
                str(temp_audio)
            ]
            
            subprocess.run(cmd, capture_output=True, check=True)
            
            if not temp_audio.exists():
                return AudioType.SILENCE, 0.0
            
            # Use ffprobe to get audio stats
            cmd = [
                "ffprobe",
                "-v", "error",
                "-print_format", "json",
                "-show_streams",
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            info = json.loads(result.stdout)
            
            # Check for audio stream
            has_audio_stream = any(
                stream.get('codec_type') == 'audio'
                for stream in info.get('streams', [])
            )
            
            if not has_audio_stream:
                return AudioType.SILENCE, 0.0
            
            # Analyze audio levels using volumedetect
            cmd = [
                "ffmpeg",
                "-i", str(temp_audio),
                "-af", "volumedetect",
                "-f", "null",
                "-"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Parse mean volume
            mean_volume = -60.0  # Default to silent
            for line in result.stderr.split('\n'):
                if 'mean_volume:' in line:
                    try:
                        mean_volume = float(line.split(':')[1].strip().split()[0])
                        break
                    except (ValueError, IndexError):
                        pass
            
            # Normalize volume score (-60dB to 0dB mapped to 0-1)
            audio_score = (mean_volume + 60) / 60
            audio_score = max(0.0, min(1.0, audio_score))
            
            # Classify audio type based on characteristics
            if audio_score < 0.1:
                audio_type = AudioType.SILENCE
            elif audio_score > 0.6:
                audio_type = AudioType.CLEAR_DIALOGUE
            else:
                audio_type = AudioType.AMBIENT
            
            # Clean up temp file
            temp_audio.unlink(missing_ok=True)
            
            return audio_type, audio_score
            
        except Exception as e:
            logging.error(f"Audio analysis failed for {video_path}: {e}")
            return AudioType.UNKNOWN, 0.0
    
    def analyze_shot_type(
        self,
        video_path: Path,
        motion_score: float,
        duration: float
    ) -> ClipType:
        """
        Determine shot type based on characteristics.
        
        Args:
            video_path: Path to video file
            motion_score: Motion analysis score
            duration: Clip duration in seconds
        
        Returns:
            ClipType classification
        """
        # Heuristic classification based on motion and duration
        if motion_score < self.MOTION_THRESHOLD_LOW and duration > self.DURATION_THRESHOLD_ESTABLISHING:
            # Long static shots are likely establishing shots
            return ClipType.ESTABLISHING
        elif motion_score < self.MOTION_THRESHOLD_LOW:
            # Short static shots could be interviews or inserts
            return ClipType.INTERVIEW
        elif motion_score > self.MOTION_THRESHOLD_HIGH:
            # High motion = action
            return ClipType.ACTION
        else:
            # Medium motion could be B-roll
            return ClipType.B_ROLL
    
    def is_syncable(self, audio_type: AudioType, audio_score: float) -> bool:
        """
        Determine if a clip is suitable for audio syncing.
        
        Args:
            audio_type: Classification of audio
            audio_score: Audio quality score
        
        Returns:
            True if clip is syncable
        """
        # Clips with clear dialogue or distinct audio patterns are syncable
        if audio_type in [AudioType.CLEAR_DIALOGUE] and audio_score > 0.4:
            return True
        
        # Ambient audio might be syncable if it's consistent
        if audio_type == AudioType.AMBIENT and audio_score > 0.5:
            return True
        
        return False
    
    def analyze_clip(self, video_path: Union[str, Path]) -> ClipAnalysis:
        """
        Perform full content analysis on a video clip.
        
        Args:
            video_path: Path to video file
        
        Returns:
            ClipAnalysis with classification results
        """
        video_path = Path(video_path)
        
        logging.info(f"Analyzing clip: {video_path.name}")
        
        # Get basic info
        info = self.get_video_info(video_path)
        duration = float(info.get('format', {}).get('duration', 0))
        
        # Analyze motion
        motion_score = self.analyze_motion(video_path)
        
        # Analyze audio
        audio_type, audio_score = self.analyze_audio(video_path)
        has_audio = audio_type != AudioType.SILENCE
        
        # Determine syncability
        is_syncable = self.is_syncable(audio_type, audio_score)
        
        # Classify shot type
        clip_type = self.analyze_shot_type(video_path, motion_score, duration)
        
        # Override clip type for syncable shots
        if is_syncable and clip_type in [ClipType.ESTABLISHING, ClipType.B_ROLL]:
            clip_type = ClipType.SYNCABLE
        
        # Calculate confidence (simplified)
        confidence = (motion_score + audio_score) / 2
        
        analysis = ClipAnalysis(
            file_path=video_path,
            clip_type=clip_type,
            audio_type=audio_type,
            duration=duration,
            has_audio=has_audio,
            is_syncable=is_syncable,
            motion_score=motion_score,
            audio_score=audio_score,
            confidence=confidence,
            metadata={
                "video_info": info,
            }
        )
        
        logging.info(f"  Type: {clip_type.value}, Audio: {audio_type.value}, Syncable: {is_syncable}")
        
        return analysis
    
    def analyze_directory(
        self,
        directory: Union[str, Path],
        extensions: Tuple[str, ...] = (".mp4", ".mov", ".mxf", ".avi")
    ) -> List[ClipAnalysis]:
        """
        Analyze all video clips in a directory.
        
        Args:
            directory: Directory to scan
            extensions: Video file extensions to include
        
        Returns:
            List of ClipAnalysis for all clips
        """
        directory = Path(directory)
        
        # Collect all video files
        video_files = []
        for ext in extensions:
            video_files.extend(directory.glob(f"*{ext}"))
            video_files.extend(directory.glob(f"*{ext.upper()}"))
        
        logging.info(f"Found {len(video_files)} video files to analyze")
        
        results = []
        for video_file in video_files:
            try:
                analysis = self.analyze_clip(video_file)
                results.append(analysis)
            except Exception as e:
                logging.error(f"Failed to analyze {video_file}: {e}")
                # Add unknown classification
                results.append(ClipAnalysis(
                    file_path=video_file,
                    clip_type=ClipType.UNKNOWN,
                    audio_type=AudioType.UNKNOWN,
                    duration=0.0,
                    has_audio=False,
                    is_syncable=False,
                    motion_score=0.0,
                    audio_score=0.0,
                    confidence=0.0,
                ))
        
        return results
    
    def organize_by_type(self, analyses: List[ClipAnalysis]) -> Dict[ClipType, List[ClipAnalysis]]:
        """
        Organize clips by their classification type.
        
        Args:
            analyses: List of clip analyses
        
        Returns:
            Dictionary mapping ClipType to list of analyses
        """
        organized = {clip_type: [] for clip_type in ClipType}
        
        for analysis in analyses:
            organized[analysis.clip_type].append(analysis)
        
        return organized
    
    def get_syncable_clips(self, analyses: List[ClipAnalysis]) -> List[ClipAnalysis]:
        """
        Get only the syncable clips from analyses.
        
        Args:
            analyses: List of clip analyses
        
        Returns:
            List of syncable clip analyses
        """
        return [a for a in analyses if a.is_syncable]
    
    def generate_report(self, analyses: List[ClipAnalysis]) -> Dict:
        """
        Generate a summary report of clip analyses.
        
        Args:
            analyses: List of clip analyses
        
        Returns:
            Dictionary with report statistics
        """
        organized = self.organize_by_type(analyses)
        syncable = self.get_syncable_clips(analyses)
        
        total_duration = sum(a.duration for a in analyses)
        
        return {
            "total_clips": len(analyses),
            "total_duration": total_duration,
            "by_type": {
                clip_type.value: len(clips)
                for clip_type, clips in organized.items()
            },
            "syncable_clips": len(syncable),
            "syncable_duration": sum(a.duration for a in syncable),
            "clips": [a.to_dict() for a in analyses],
        }
