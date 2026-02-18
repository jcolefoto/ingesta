"""
Quick thumbnail browser module for ingesta.

Generates a lightweight HTML-based thumbnail gallery for quick visual browsing
of clips before/during/after ingestion. Opens in default browser.
"""

import logging
import webbrowser
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import base64
import mimetypes

from ..analysis import ClipAnalysis


logger = logging.getLogger(__name__)


@dataclass
class ThumbnailClip:
    """Clip info for thumbnail browser."""
    filename: str
    thumbnail_path: Optional[Path] = None
    duration: float = 0.0
    file_size: int = 0
    resolution: Optional[str] = None
    codec: Optional[str] = None
    clip_type: Optional[str] = None


class ThumbnailBrowser:
    """Generate HTML thumbnail browser."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_browser(self, 
                        clips: List[ThumbnailClip],
                        output_path: Path,
                        title: str = "Clip Browser") -> Path:
        """Generate HTML thumbnail browser."""
        html_content = self._generate_html(clips, title)
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"Generated thumbnail browser: {output_path}")
        return output_path
    
    def _generate_html(self, clips: List[ThumbnailClip], title: str) -> str:
        """Generate HTML content."""
        
        # Simple inline CSS
        css = """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: system-ui, sans-serif; background: #1a1a1a; color: #fff; padding: 20px; }
        .header { position: sticky; top: 0; background: #1a1a1a; padding: 20px 0; border-bottom: 2px solid #333; margin-bottom: 20px; }
        h1 { font-size: 24px; margin-bottom: 10px; }
        .stats { color: #888; font-size: 14px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
        .clip-card { background: #2a2a2a; border-radius: 8px; overflow: hidden; transition: transform 0.2s; cursor: pointer; }
        .clip-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
        .thumbnail { width: 100%; height: 160px; background: #1a1a1a; display: flex; align-items: center; justify-content: center; overflow: hidden; position: relative; }
        .thumbnail img { width: 100%; height: 100%; object-fit: cover; }
        .thumbnail .placeholder { color: #555; font-size: 48px; }
        .duration { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.8); padding: 4px 8px; border-radius: 4px; font-size: 12px; font-family: monospace; }
        .clip-info { padding: 12px; }
        .filename { font-size: 14px; font-weight: 500; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .meta { display: flex; gap: 12px; font-size: 12px; color: #888; }
        """
        
        # Generate clip cards
        clip_cards_html = ""
        for clip in clips:
            clip_cards_html += self._generate_clip_card(clip)
        
        if not clip_cards_html:
            clip_cards_html = '<div style="text-align: center; padding: 60px; color: #666;">No clips to display</div>'
        
        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <div class="stats">{len(clips)} clips • Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </div>
    <div class="grid">{clip_cards_html}</div>
</body>
</html>"""
        
        return html
    
    def _generate_clip_card(self, clip: ThumbnailClip) -> str:
        """Generate HTML for a single clip card."""
        
        # Format duration
        if clip.duration < 60:
            duration_str = f"{int(clip.duration)}s"
        else:
            mins = int(clip.duration // 60)
            secs = int(clip.duration % 60)
            duration_str = f"{mins}:{secs:02d}"
        
        # Format file size
        size_mb = clip.file_size / (1024 * 1024)
        if size_mb < 1024:
            size_str = f"{size_mb:.1f} MB"
        else:
            size_str = f"{size_mb / 1024:.1f} GB"
        
        # Get thumbnail
        if clip.thumbnail_path and clip.thumbnail_path.exists():
            try:
                with open(clip.thumbnail_path, 'rb') as f:
                    image_data = base64.b64encode(f.read()).decode()
                thumbnail_html = f'<img src="data:image/jpeg;base64,{image_data}" alt="Thumbnail">'
            except Exception:
                thumbnail_html = '<div class="placeholder">🎬</div>'
        else:
            thumbnail_html = '<div class="placeholder">🎬</div>'
        
        return f"""
        <div class="clip-card">
            <div class="thumbnail">{thumbnail_html}<div class="duration">{duration_str}</div></div>
            <div class="clip-info">
                <div class="filename" title="{clip.filename}">{clip.filename}</div>
                <div class="meta"><span>📁 {size_str}</span></div>
            </div>
        </div>
        """
    
    def open_browser(self, clips: List[ThumbnailClip],
                    output_path: Optional[Path] = None,
                    title: str = "Clip Browser") -> Path:
        """Generate and open thumbnail browser."""
        if output_path is None:
            import tempfile
            output_path = Path(tempfile.gettempdir()) / f"ingesta_browser_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        html_path = self.generate_browser(clips, output_path, title)
        webbrowser.open(f"file://{html_path.absolute()}")
        return html_path


def quick_preview(media_dir: Path) -> Optional[Path]:
    """Quick preview of media directory without full analysis."""
    from ..analysis import ContentAnalyzer
    from ..reports.thumbnails import ThumbnailExtractor
    import tempfile
    
    logger.info(f"Creating quick preview for: {media_dir}")
    
    # Quick scan for video files
    video_extensions = ['.mp4', '.mov', '.mxf', '.avi', '.mkv']
    video_files = []
    for ext in video_extensions:
        video_files.extend(media_dir.glob(f"**/*{ext}"))
        video_files.extend(media_dir.glob(f"**/*{ext.upper()}"))
    
    if not video_files:
        logger.warning("No video files found")
        return None
    
    # Limit for speed
    video_files = video_files[:50]
    
    # Quick analysis (just duration)
    analyzer = ContentAnalyzer()
    clips = []
    
    logger.info(f"Analyzing {len(video_files)} files...")
    for video_file in video_files:
        try:
            info = analyzer.get_video_info(video_file)
            duration = float(info.get('format', {}).get('duration', 0))
            
            tc = ThumbnailClip(
                filename=video_file.name,
                duration=duration,
                file_size=video_file.stat().st_size
            )
            clips.append(tc)
        except Exception as e:
            logger.debug(f"Could not analyze {video_file}: {e}")
    
    # Extract thumbnails
    browser = ThumbnailBrowser()
    output_path = Path(tempfile.gettempdir()) / f"ingesta_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        thumb_dir = Path(tmpdir)
        with ThumbnailExtractor(output_dir=thumb_dir) as extractor:
            for clip in clips:
                try:
                    video_file = media_dir / clip.filename
                    thumbs = extractor.extract_thumbnails_for_clip(video_file)
                    if thumbs:
                        clip.thumbnail_path = thumbs[0]
                except Exception:
                    pass
        
        html_path = browser.generate_browser(clips, output_path, f"Quick Preview - {media_dir.name}")
        webbrowser.open(f"file://{html_path.absolute()}")
        return html_path