"""
Slate detection module using audio transcription.

Uses whisper.cpp (via local transcribe_audio tool) to detect slates in video clips.
Extracts scene and take numbers from audio cues like "Scene 1 Take 3 mark".
"""

import re
import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import subprocess


@dataclass
class SlateInfo:
    """Information extracted from a slate."""
    detected: bool
    scene_number: Optional[str] = None
    take_number: Optional[str] = None
    slate_text: Optional[str] = None
    confidence: float = 0.0
    timestamp: float = 0.0  # When in the clip the slate was detected


class SlateDetector:
    """
    Detects slates in video clips using audio transcription.
    
    Uses whisper.cpp to transcribe the first 30 seconds of each clip
    and looks for patterns like:
    - "Scene 1 Take 3"
    - "Slate 5 Take 2"
    - "Marker"
    """
    
    # Regex patterns for slate detection
    SLATE_PATTERNS = [
        # Scene X Take Y
        r'(?:scene|sc)\s*(\d+[a-z]?)\s*(?:take|tk)\s*(\d+)',
        # Slate X Take Y  
        r'(?:slate|sl)\s*(\d+[a-z]?)\s*(?:take|tk)\s*(\d+)',
        # Take X Scene Y (reversed)
        r'(?:take|tk)\s*(\d+)\s*(?:scene|sc)\s*(\d+[a-z]?)',
        # Just "Scene X" or "Slate X"
        r'(?:scene|sc|slate|sl)\s*(\d+[a-z]?)',
        # Marker/ mark
        r'\b(?:marker|mark)\b',
        # Numbers at the beginning
        r'^(\d+[a-z]?)\s+(\d+)',
    ]
    
    def __init__(self, whisper_model: str = "base", max_duration: float = 30.0):
        """
        Initialize slate detector.
        
        Args:
            whisper_model: Whisper model size (base, small, medium, large)
            max_duration: Maximum seconds to transcribe from start of clip
        """
        self.whisper_model = whisper_model
        self.max_duration = max_duration
        self.logger = logging.getLogger(__name__)
    
    def extract_audio_segment(
        self, 
        video_path: Path, 
        output_path: Path,
        duration: Optional[float] = None
    ) -> bool:
        """
        Extract audio segment from video for transcription.
        
        Args:
            video_path: Path to video file
            output_path: Path for output audio file
            duration: Duration to extract in seconds (default: self.max_duration)
            
        Returns:
            True if successful
        """
        duration = duration or self.max_duration
        
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-t", str(duration),
                "-vn",  # No video
                "-acodec", "pcm_s16le",
                "-ar", "16000",  # 16kHz for whisper
                "-ac", "1",  # Mono
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=60
            )
            
            if result.returncode == 0 and output_path.exists():
                return True
            else:
                self.logger.warning(f"FFmpeg failed for {video_path}: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"FFmpeg timeout for {video_path}")
            return False
        except Exception as e:
            self.logger.warning(f"Audio extraction failed for {video_path}: {e}")
            return False
    
    def transcribe_audio(self, audio_path: Path) -> Optional[str]:
        """
        Transcribe audio file using local whisper.cpp.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Transcribed text or None if failed
        """
        try:
            # Use the transcribe_audio tool which uses whisper.cpp
            from ..transcribe_tool import transcribe_audio_file
            
            result = transcribe_audio_file(
                str(audio_path),
                model=self.whisper_model,
                language="en"
            )
            
            if result and result.get("text"):
                return result["text"].strip()
            return None
            
        except ImportError:
            self.logger.warning("Transcription tool not available")
            return None
        except Exception as e:
            self.logger.warning(f"Transcription failed: {e}")
            return None
    
    def detect_slate_in_text(self, text: str) -> SlateInfo:
        """
        Detect slate information in transcribed text.
        
        Args:
            text: Transcribed audio text
            
        Returns:
            SlateInfo with extracted data
        """
        text_lower = text.lower()
        
        # Try each pattern
        for pattern in self.SLATE_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                scene = None
                take = None
                
                if len(groups) >= 2:
                    # First group might be scene, second might be take
                    if any(word in text_lower[:match.start()] for word in ['take', 'tk']):
                        take = groups[0]
                        scene = groups[1] if len(groups) > 1 else None
                    else:
                        scene = groups[0]
                        take = groups[1]
                elif len(groups) == 1:
                    scene = groups[0]
                
                return SlateInfo(
                    detected=True,
                    scene_number=scene,
                    take_number=take,
                    slate_text=text[:200],  # First 200 chars
                    confidence=0.8,
                    timestamp=0.0
                )
        
        # Check for "marker" or "mark" as a fallback
        if any(word in text_lower for word in ['marker', 'mark', 'action', 'speed']):
            return SlateInfo(
                detected=True,
                slate_text=text[:200],
                confidence=0.5,
                timestamp=0.0
            )
        
        return SlateInfo(detected=False)
    
    def detect_slate(self, video_path: Path) -> SlateInfo:
        """
        Detect slate in a video clip.
        
        Args:
            video_path: Path to video file
            
        Returns:
            SlateInfo with detection results
        """
        self.logger.info(f"Detecting slate in: {video_path.name}")
        
        # Create temp directory for audio extraction
        with tempfile.TemporaryDirectory(prefix="ingesta_slate_") as temp_dir:
            temp_audio = Path(temp_dir) / "temp_audio.wav"
            
            # Extract audio segment
            if not self.extract_audio_segment(video_path, temp_audio):
                return SlateInfo(detected=False)
            
            # Transcribe
            transcription = self.transcribe_audio(temp_audio)
            
            if not transcription:
                return SlateInfo(detected=False)
            
            self.logger.debug(f"Transcription: {transcription[:100]}...")
            
            # Detect slate in transcription
            slate_info = self.detect_slate_in_text(transcription)
            
            if slate_info.detected:
                self.logger.info(
                    f"  ✓ Slate detected: Scene {slate_info.scene_number}, "
                    f"Take {slate_info.take_number}"
                )
            else:
                self.logger.debug("  No slate detected")
            
            return slate_info
    
    def detect_slates_in_directory(
        self, 
        directory: Path,
        extensions: Tuple[str, ...] = (".mp4", ".mov", ".mxf", ".avi")
    ) -> Dict[Path, SlateInfo]:
        """
        Detect slates in all video files in a directory.
        
        Args:
            directory: Directory to scan
            extensions: Video file extensions to include
            
        Returns:
            Dictionary mapping video paths to SlateInfo
        """
        directory = Path(directory)
        results = {}
        
        # Find all video files
        video_files = []
        for ext in extensions:
            video_files.extend(directory.rglob(f"*{ext}"))
            video_files.extend(directory.rglob(f"*{ext.upper()}"))
        
        self.logger.info(f"Scanning {len(video_files)} clips for slates...")
        
        for video_file in video_files:
            try:
                slate_info = self.detect_slate(video_file)
                results[video_file] = slate_info
            except Exception as e:
                self.logger.error(f"Failed to detect slate in {video_file}: {e}")
                results[video_file] = SlateInfo(detected=False)
        
        # Summary
        detected_count = sum(1 for s in results.values() if s.detected)
        self.logger.info(f"Slate detection complete: {detected_count}/{len(results)} clips have slates")
        
        return results


def extract_scene_take(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract scene/take info from filename patterns.
    
    Args:
        filename: Filename to parse
        
    Returns:
        Tuple of (scene_number, take_number) or (None, None)
    """
    # Common filename patterns
    patterns = [
        # SC001_TK01 or Scene01_Take01
        r'[Ss][Cc](\d+[a-zA-Z]?)_?[Tt][Kk](\d+)',
        r'[Ss]cene[_\s]?(\d+[a-zA-Z]?)_?[Tt]ake[_\s]?(\d+)',
        # 01_01 pattern
        r'^(\d+[a-zA-Z]?)_(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1), match.group(2)
    
    return None, None