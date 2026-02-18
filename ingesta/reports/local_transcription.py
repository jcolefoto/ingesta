"""
Local audio transcription module for video clips.

Provides fully offline transcription using whisper.cpp (via transcribe_audio tool).
All processing happens locally - no data is sent to external services.
"""

import re
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    """Results of audio transcription."""
    text: str
    excerpt: str  # First ~100 chars for display
    has_slate: bool  # Detected slate/mark at beginning
    has_end_mark: bool  # Detected mark at end
    slate_text: Optional[str]  # The slate/mark text if detected
    end_mark_text: Optional[str]  # The end mark text if detected
    duration: float
    

def extract_audio(video_path: Path, output_path: Path, 
                  start_time: Optional[float] = None,
                  duration: Optional[float] = None) -> bool:
    """
    Extract audio from video file to WAV format.
    
    Args:
        video_path: Path to video file
        output_path: Path for output WAV file
        start_time: Start time in seconds (None for beginning)
        duration: Duration to extract in seconds (None for all)
        
    Returns:
        True if successful
    """
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",
            "-ar", "16000",  # 16kHz for whisper
            "-ac", "1",  # Mono
        ]
        
        if start_time is not None:
            cmd.extend(["-ss", str(start_time)])
        if duration is not None:
            cmd.extend(["-t", str(duration)])
            
        cmd.append(str(output_path))
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        return result.returncode == 0 and output_path.exists()
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Audio extraction failed: {e}")
        return False


def transcribe_with_whisper(audio_path: Path, 
                            model: str = "base",
                            language: Optional[str] = None) -> Optional[str]:
    """
    Transcribe audio file using local whisper.cpp via transcribe_audio tool.
    
    All processing is done locally. No data leaves the machine.
    
    Args:
        audio_path: Path to audio file
        model: Model size (base, small, medium, large)
        language: Language code or None for auto-detect
        
    Returns:
        Transcription text or None if failed
    """
    try:
        import json
        
        cmd = ["transcribe_audio", str(audio_path), "--model", model]
        
        if language:
            cmd.extend(["--language", language])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return data.get("text", "").strip()
            except json.JSONDecodeError:
                return result.stdout.strip()
        else:
            logging.getLogger(__name__).warning(f"Transcription failed: {result.stderr}")
            return None
            
    except FileNotFoundError:
        logging.getLogger(__name__).warning("transcribe_audio tool not available")
        return None
    except Exception as e:
        logging.getLogger(__name__).warning(f"Transcription error: {e}")
        return None


def detect_slate_markers(text: str) -> Tuple[bool, bool, Optional[str], Optional[str]]:
    """
    Detect slate/scene markers in transcription.
    
    Looks for patterns like:
    - "Scene 1", "Shot 1", "Take 1"
    - "Slate", "Marker", "Mark"
    - Numbers at beginning/end
    - Clapboard-style announcements
    
    Args:
        text: Transcription text
        
    Returns:
        Tuple of (has_slate, has_end_mark, slate_text, end_mark_text)
    """
    text_upper = text.upper()
    
    # Slate patterns at beginning (first 50 chars)
    beginning = text[:100].upper()
    slate_patterns = [
        r'\b(SCENE\s+\d+|SHOT\s+\d+|TAKE\s+\d+)\b',
        r'\b(SLATE|MARKER|MARK)\s*\d*\b',
        r'\b(CAMERA\s+\w+|ROLL\s+\w+)\b',
        r'\b(SCENE\s+[A-Z]\d+|SCENE\s+\d+[A-Z])\b',
    ]
    
    has_slate = False
    slate_text = None
    
    for pattern in slate_patterns:
        match = re.search(pattern, beginning)
        if match:
            has_slate = True
            slate_text = match.group(0)
            break
    
    # End markers (last 50 chars)
    ending = text[-100:].upper() if len(text) > 100 else text.upper()
    end_patterns = [
        r'\b(CUT|AND\s+CUT)\b',
        r'\b(END\s+SCENE|END\s+SHOT)\b',
        r'\b(STOPPING|STOP)\b',
    ]
    
    has_end_mark = False
    end_mark_text = None
    
    for pattern in end_patterns:
        match = re.search(pattern, ending)
        if match:
            has_end_mark = True
            end_mark_text = match.group(0)
            break
    
    return has_slate, has_end_mark, slate_text, end_mark_text


def transcribe_video_clip(
    video_path: Path,
    model: str = "base",
    language: Optional[str] = None,
    extract_beginning: bool = True,
    beginning_duration: float = 30.0
) -> Optional[TranscriptionResult]:
    """
    Transcribe a video clip using local whisper.cpp.
    
    All processing is done locally - no internet connection required,
    no data sent to external services.
    
    Args:
        video_path: Path to video file
        model: Whisper model size (base, small, medium, large)
        language: Language code or None for auto-detect
        extract_beginning: Only transcribe beginning portion (for slates)
        beginning_duration: Duration in seconds to transcribe from beginning
        
    Returns:
        TranscriptionResult or None if failed
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Transcribing: {video_path.name}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_path = temp_path / "extracted_audio.wav"
        
        # Extract audio
        duration = beginning_duration if extract_beginning else None
        if not extract_audio(video_path, audio_path, duration=duration):
            logger.warning(f"Failed to extract audio from {video_path}")
            return None
        
        # Transcribe
        text = transcribe_with_whisper(audio_path, model, language)
        
        if not text:
            return None
        
        # Detect slate markers
        has_slate, has_end_mark, slate_text, end_mark_text = detect_slate_markers(text)
        
        # Create excerpt (first ~150 chars)
        excerpt = text[:150] + "..." if len(text) > 150 else text
        
        result = TranscriptionResult(
            text=text,
            excerpt=excerpt,
            has_slate=has_slate,
            has_end_mark=has_end_mark,
            slate_text=slate_text,
            end_mark_text=end_mark_text,
            duration=beginning_duration if extract_beginning else 0
        )
        
        logger.info(f"  Transcription: {excerpt[:50]}...")
        if has_slate:
            logger.info(f"  Slate detected: {slate_text}")
        
        return result


class LocalTranscriber:
    """
    Local-only video transcriber using whisper.cpp.
    
    Security: All processing is done locally on your machine.
    No audio or transcription data is sent to any external service.
    """
    
    def __init__(self, model: str = "base", language: Optional[str] = None):
        """
        Initialize transcriber.
        
        Args:
            model: Whisper model size (base, small, medium, large)
            language: Language code or None for auto-detect
        """
        self.model = model
        self.language = language
        self.logger = logging.getLogger(__name__)
    
    def transcribe(self, video_path: Path) -> Optional[TranscriptionResult]:
        """
        Transcribe a video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            TranscriptionResult or None if failed
        """
        return transcribe_video_clip(
            video_path,
            model=self.model,
            language=self.language,
            extract_beginning=True,
            beginning_duration=30.0
        )
    
    def transcribe_full(self, video_path: Path) -> Optional[TranscriptionResult]:
        """
        Transcribe entire video file (slower but complete).
        
        Args:
            video_path: Path to video file
            
        Returns:
            TranscriptionResult or None if failed
        """
        return transcribe_video_clip(
            video_path,
            model=self.model,
            language=self.language,
            extract_beginning=False
        )
