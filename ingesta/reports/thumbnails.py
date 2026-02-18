"""
Thumbnail extraction module for generating preview images from video clips.

Uses FFmpeg to extract evenly distributed frames throughout each clip.
"""

import subprocess
import logging
from pathlib import Path
from typing import List, Optional
import tempfile


class ThumbnailExtractor:
    """Extract thumbnails from video clips using FFmpeg."""
    
    DEFAULT_THUMBNAIL_COUNT = 6
    DEFAULT_THUMBNAIL_SIZE = (320, 180)
    
    def __init__(self, output_dir: Optional[Path] = None, 
                 thumbnail_count: int = DEFAULT_THUMBNAIL_COUNT,
                 thumbnail_size: tuple = DEFAULT_THUMBNAIL_SIZE):
        """
        Initialize thumbnail extractor.
        
        Args:
            output_dir: Directory to save thumbnails (default: temp directory)
            thumbnail_count: Number of thumbnails to extract per clip (default: 6)
            thumbnail_size: Size of thumbnails as (width, height) tuple
        """
        self.thumbnail_count = thumbnail_count
        self.thumbnail_size = thumbnail_size
        self.logger = logging.getLogger(__name__)
        
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._is_temp = False
        else:
            self.output_dir = Path(tempfile.mkdtemp(prefix="ingesta_thumbnails_"))
            self._is_temp = True
    
    def get_video_duration(self, video_path: Path) -> float:
        """
        Get video duration in seconds using ffprobe.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Duration in seconds, or 0 if unable to determine
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            return duration
            
        except (subprocess.CalledProcessError, ValueError) as e:
            self.logger.error(f"Failed to get duration for {video_path}: {e}")
            return 0.0
    
    def calculate_timestamps(self, duration: float, count: Optional[int] = None) -> List[float]:
        """
        Calculate timestamps for thumbnail extraction.
        
        Pattern: First frame, last frame, and (count-2) equally spaced in between.
        For 6 thumbnails:
            - thumb_01: 0%  (first frame)
            - thumb_02: 20%
            - thumb_03: 40%
            - thumb_04: 60%
            - thumb_05: 80%
            - thumb_06: 100% (last frame)
        
        Args:
            duration: Total video duration in seconds
            count: Number of thumbnails (default: self.thumbnail_count)
            
        Returns:
            List of timestamps in seconds
        """
        if count is None:
            count = self.thumbnail_count
        
        if duration <= 0 or count <= 0:
            return []
        
        if count == 1:
            return [duration / 2]
        
        if count == 2:
            return [0.0, duration]
        
        # Pattern: First (0%), Last (100%), and (count-2) equally spaced in between
        timestamps = [0.0]  # First frame
        
        # Calculate positions for middle frames (excluding first and last)
        # For count=6: we need positions at 20%, 40%, 60%, 80%
        # That's 4 positions = count - 2
        for i in range(1, count - 1):
            position = i / (count - 1)
            timestamps.append(position * duration)
        
        timestamps.append(duration)  # Last frame
        
        return timestamps
    
    def extract_thumbnail(self, video_path: Path, timestamp: float, 
                         output_path: Path) -> bool:
        """
        Extract a single thumbnail at a specific timestamp.
        
        Args:
            video_path: Path to video file
            timestamp: Time in seconds to extract frame
            output_path: Path to save thumbnail
            
        Returns:
            True if successful, False otherwise
        """
        try:
            width, height = self.thumbnail_size
            
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output file if exists
                "-ss", str(timestamp),  # Seek to timestamp
                "-i", str(video_path),  # Input file
                "-vframes", "1",  # Extract 1 frame
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                "-q:v", "2",  # High quality
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and output_path.exists():
                return True
            else:
                self.logger.error(f"FFmpeg failed for {video_path} at {timestamp}s: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to extract thumbnail for {video_path}: {e}")
            return False
    
    def extract_thumbnails_for_clip(self, video_path: Path,
                                    base_name: Optional[str] = None) -> List[Path]:
        """
        Extract multiple thumbnails for a single video clip.
        
        Args:
            video_path: Path to video file
            base_name: Base name for thumbnail files (default: video stem)
            
        Returns:
            List of paths to extracted thumbnails
        """
        if base_name is None:
            base_name = video_path.stem
        
        # Get video duration
        duration = self.get_video_duration(video_path)
        if duration <= 0:
            self.logger.warning(f"Could not determine duration for {video_path}")
            return []
        
        # Calculate timestamps
        timestamps = self.calculate_timestamps(duration)
        
        # Extract thumbnails
        thumbnails = []
        for i, timestamp in enumerate(timestamps):
            output_filename = f"{base_name}_thumb_{i+1:02d}.jpg"
            output_path = self.output_dir / output_filename
            
            if self.extract_thumbnail(video_path, timestamp, output_path):
                thumbnails.append(output_path)
        
        return thumbnails
    
    def extract_thumbnails_for_directory(self, directory: Path,
                                        extensions: tuple = (".mp4", ".mov", ".mxf", ".avi", ".mkv")) -> dict:
        """
        Extract thumbnails for all video files in a directory.
        
        Args:
            directory: Directory to scan
            extensions: Video file extensions to include
            
        Returns:
            Dictionary mapping video paths to lists of thumbnail paths
        """
        directory = Path(directory)
        results = {}
        
        # Find all video files
        video_files = []
        for ext in extensions:
            video_files.extend(directory.glob(f"*{ext}"))
            video_files.extend(directory.glob(f"*{ext.upper()}"))
        
        self.logger.info(f"Found {len(video_files)} video files to process")
        
        for video_file in video_files:
            self.logger.info(f"Extracting thumbnails for: {video_file.name}")
            thumbnails = self.extract_thumbnails_for_clip(video_file)
            results[video_file] = thumbnails
        
        return results
    
    def cleanup(self):
        """Clean up temporary thumbnail files if using temp directory."""
        if self._is_temp and self.output_dir.exists():
            import shutil
            shutil.rmtree(self.output_dir, ignore_errors=True)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup temp files."""
        self.cleanup()
