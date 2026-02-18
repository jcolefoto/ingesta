"""
Transcription helper module that wraps the whisper.cpp tool.
Provides a clean interface for transcribing audio files.
"""

import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional


def transcribe_audio_file(
    file_path: str,
    model: str = "base",
    language: Optional[str] = None,
    timeout: int = 120
) -> Optional[Dict]:
    """
    Transcribe an audio file using the local transcribe_audio tool.
    
    This is a wrapper around the whisper.cpp-based transcribe_audio tool
    that's available in the environment.
    
    Args:
        file_path: Path to audio file
        model: Model size (base, small, medium, large)
        language: Language code (e.g., 'en', 'es') or None for auto-detect
        timeout: Maximum time to wait for transcription
        
    Returns:
        Dictionary with 'text' key containing transcription, or None if failed
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Try using the transcribe_audio tool from the environment
        # This is available as a tool in the system
        import json
        
        # Build the command
        cmd = ["transcribe_audio", file_path, "--model", model]
        
        if language:
            cmd.extend(["--language", language])
        
        # Run transcription
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            # Try to parse as JSON first
            try:
                data = json.loads(result.stdout)
                return data
            except json.JSONDecodeError:
                # Return raw text
                return {"text": result.stdout.strip()}
        else:
            logger.warning(f"Transcription failed: {result.stderr}")
            return None
            
    except FileNotFoundError:
        logger.warning("transcribe_audio tool not found")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"Transcription timeout for {file_path}")
        return None
    except Exception as e:
        logger.warning(f"Transcription error: {e}")
        return None