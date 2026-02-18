"""
Proxy generator module for creating proxy files and hero stills.

Generates:
- Low-resolution proxy videos for editing
- Hero still (best frame) for thumbnails
- Web-optimized versions

All processing is done locally using FFmpeg.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class ProxyResult:
    """Proxy generation results."""
    proxy_path: Optional[Path]
    hero_still_path: Optional[Path]
    web_proxy_path: Optional[Path]
    success: bool
    errors: list


def generate_proxy(video_path: Path, 
                   output_dir: Path,
                   resolution: str = "960x540",
                   codec: str = "h264",
                   quality: str = "medium") -> ProxyResult:
    """
    Generate proxy video file.
    
    Args:
        video_path: Original video path
        output_dir: Directory for output
        resolution: Proxy resolution (e.g., "960x540", "1280x720")
        codec: Codec to use ("h264", "prores")
        quality: Quality preset ("low", "medium", "high")
        
    Returns:
        ProxyResult with paths and status
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Generating proxy for: {video_path.name}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    
    # Determine output filename
    proxy_name = f"{video_path.stem}_proxy.mp4"
    proxy_path = output_dir / proxy_name
    
    # Quality settings
    crf_values = {"low": 28, "medium": 23, "high": 18}
    crf = crf_values.get(quality, 23)
    
    # Preset for speed vs quality
    preset = "fast" if quality == "low" else "medium"
    
    try:
        if codec == "prores":
            # ProRes proxy (for professional workflows)
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vf", f"scale={resolution}",
                "-c:v", "prores_ks",
                "-profile:v", "0",  # Proxy
                "-qscale:v", "9",
                "-c:a", "copy",
                str(proxy_path)
            ]
        else:
            # H.264 proxy
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vf", f"scale={resolution}",
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                str(proxy_path)
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            errors.append(f"Proxy generation failed: {result.stderr[:200]}")
            proxy_path = None
        else:
            logger.info(f"  Proxy created: {proxy_path.name}")
    
    except Exception as e:
        errors.append(f"Proxy generation error: {e}")
        proxy_path = None
    
    return ProxyResult(
        proxy_path=proxy_path,
        hero_still_path=None,
        web_proxy_path=None,
        success=proxy_path is not None,
        errors=errors
    )


def generate_hero_still(video_path: Path, output_dir: Path, 
                       offset_percent: float = 0.1) -> Optional[Path]:
    """
    Extract hero still from video (best frame for thumbnail).
    
    Args:
        video_path: Path to video file
        output_dir: Directory for output
        offset_percent: Position in video (0-1, default 10% in to avoid slates)
        
    Returns:
        Path to hero still or None if failed
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Extracting hero still: {video_path.name}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    hero_name = f"{video_path.stem}_hero.jpg"
    hero_path = output_dir / hero_name
    
    try:
        # Get video duration
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip())
        
        # Calculate timestamp (offset from start to avoid slates)
        timestamp = duration * offset_percent
        
        # Extract frame
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            "-vf", "scale=1920:-1",  # Max width 1920, maintain aspect
            str(hero_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        
        if result.returncode == 0 and hero_path.exists():
            logger.info(f"  Hero still created: {hero_path.name}")
            return hero_path
        else:
            logger.warning(f"  Hero still extraction failed")
            return None
            
    except Exception as e:
        logger.warning(f"  Hero still error: {e}")
        return None


def generate_web_proxy(video_path: Path, output_dir: Path) -> Optional[Path]:
    """
    Generate web-optimized proxy (small file size for web viewing).
    
    Args:
        video_path: Path to video file
        output_dir: Directory for output
        
    Returns:
        Path to web proxy or None if failed
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Generating web proxy: {video_path.name}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    web_name = f"{video_path.stem}_web.mp4"
    web_path = output_dir / web_name
    
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",  # Web optimization
            "-c:a", "aac",
            "-b:a", "96k",
            str(web_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        
        if result.returncode == 0 and web_path.exists():
            logger.info(f"  Web proxy created: {web_path.name}")
            return web_path
        else:
            return None
            
    except Exception as e:
        logger.warning(f"  Web proxy error: {e}")
        return None


class ProxyGenerator:
    """
    Generator for proxy files and hero stills.
    
    Creates editing proxies and preview images.
    All processing is done locally using FFmpeg.
    """
    
    def generate(self, video_path: Path, output_dir: Path,
                 resolution: str = "960x540",
                 create_web: bool = True,
                 extract_hero: bool = True) -> ProxyResult:
        """
        Generate all proxy versions for a video.
        
        Args:
            video_path: Original video path
            output_dir: Output directory
            resolution: Proxy resolution
            create_web: Also create web-optimized version
            extract_hero: Also extract hero still
            
        Returns:
            ProxyResult with all generated files
        """
        # Generate main proxy
        result = generate_proxy(video_path, output_dir, resolution)
        
        # Generate hero still
        if extract_hero:
            result.hero_still_path = generate_hero_still(video_path, output_dir)
        
        # Generate web proxy
        if create_web:
            result.web_proxy_path = generate_web_proxy(video_path, output_dir)
        
        return result
