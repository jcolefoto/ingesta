"""
Auto mode for ingesta - Complete workflow automation.

Provides a single command that automates the entire pipeline:
1. Auto-detect memory cards
2. Ingest with verification
3. Analyze clips
4. Extract thumbnails
5. Detect slates
6. Generate reports
7. Create organized Premiere project

Usage:
    ingesta auto --project "ClientName_Project" --template corporate
    ingesta auto  # Uses defaults and auto-detection
"""

import logging
import platform
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import time

from .ingestion import ingest_media, IngestionJob
from .analysis import ContentAnalyzer, ClipAnalysis
from .premiere import create_premiere_project
from .slate_detector import SlateDetector, extract_scene_take
from .reports import ThumbnailExtractor, PDFReportGenerator, CSVReportGenerator


# Video file extensions to look for
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mxf', '.avi', '.mkv', '.mts', '.m2ts')

# Common memory card mount points by OS
MEMORY_CARD_PATHS = {
    'Darwin': [  # macOS
        '/Volumes',
    ],
    'Linux': [  # Linux
        '/media',
        '/mnt',
        '/run/media',
    ],
    'Windows': [  # Windows
        'D:\\',
        'E:\\',
        'F:\\',
        'G:\\',
        'H:\\',
    ]
}

# Card identifiers (files/folders that indicate a camera card)
CARD_IDENTIFIERS = [
    'DCIM',
    'PRIVATE',
    'AVCHD',
    'BPAV',
    'CLIP',
    '.Sony',
    'M4ROOT',
]


@dataclass
class AutoWorkflowResult:
    """Results from an auto workflow run."""
    success: bool
    source_path: Optional[Path] = None
    ingest_dest: Optional[Path] = None
    project_path: Optional[Path] = None
    report_path: Optional[Path] = None
    premiere_project: Optional[Path] = None
    clips_analyzed: int = 0
    slates_detected: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> float:
        """Get workflow duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'source_path': str(self.source_path) if self.source_path else None,
            'ingest_dest': str(self.ingest_dest) if self.ingest_dest else None,
            'project_path': str(self.project_path) if self.project_path else None,
            'report_path': str(self.report_path) if self.report_path else None,
            'premiere_project': str(self.premiere_project) if self.premiere_project else None,
            'clips_analyzed': self.clips_analyzed,
            'slates_detected': self.slates_detected,
            'errors': self.errors,
            'duration': self.duration,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
        }


class MemoryCardDetector:
    """Detects mounted memory cards and storage devices."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = platform.system()
    
    def get_mount_points(self) -> List[Path]:
        """Get potential memory card mount points for this OS."""
        paths = MEMORY_CARD_PATHS.get(self.system, [])
        return [Path(p) for p in paths if Path(p).exists()]
    
    def is_memory_card(self, path: Path) -> bool:
        """Check if a path appears to be a memory card."""
        if not path.is_dir():
            return False
        
        # Check for card identifier files/folders
        for identifier in CARD_IDENTIFIERS:
            if (path / identifier).exists():
                return True
            if any(identifier in p.name for p in path.iterdir()):
                return True
        
        # Check for video files
        for ext in VIDEO_EXTENSIONS:
            if list(path.rglob(f'*{ext}')) or list(path.rglob(f'*{ext.upper()}')):
                return True
        
        return False
    
    def detect_cards(self) -> List[Path]:
        """
        Detect all mounted memory cards.
        
        Returns:
            List of paths to detected memory cards
        """
        cards = []
        mount_points = self.get_mount_points()
        
        for mount_point in mount_points:
            if not mount_point.exists():
                continue
            
            # Check direct children
            try:
                for item in mount_point.iterdir():
                    if self.is_memory_card(item):
                        cards.append(item)
                        self.logger.info(f"Detected memory card: {item}")
            except PermissionError:
                self.logger.debug(f"Permission denied accessing {mount_point}")
        
        return cards
    
    def auto_select_source(self) -> Optional[Path]:
        """
        Automatically select the best source (memory card or current directory).
        
        Returns:
            Path to use as source, or None if no cards found
        """
        cards = self.detect_cards()
        
        if len(cards) == 1:
            self.logger.info(f"Auto-selected memory card: {cards[0]}")
            return cards[0]
        elif len(cards) > 1:
            self.logger.info(f"Found {len(cards)} memory cards. Using first: {cards[0]}")
            return cards[0]
        else:
            self.logger.info("No memory cards detected")
            return None


class ProjectTemplate:
    """Project template for auto workflow configuration."""
    
    def __init__(self, template_path: Optional[Path] = None):
        self.settings = self._load_default_settings()
        
        if template_path:
            self._load_template(template_path)
    
    def _load_default_settings(self) -> Dict[str, Any]:
        """Load default template settings."""
        return {
            'fps': 24.0,
            'resolution': '1920x1080',
            'checksum_algorithm': 'xxhash64',
            'verify': True,
            'thumbnails': True,
            'slate_detection': True,
            'analyze_content': True,
            'generate_reports': True,
            'create_premiere': True,
            'thumbnail_count': 6,
        }
    
    def _load_template(self, template_path: Path):
        """Load settings from a template JSON file."""
        try:
            with open(template_path, 'r') as f:
                template_data = json.load(f)
                self.settings.update(template_data)
        except Exception as e:
            logging.warning(f"Failed to load template {template_path}: {e}")


class AutoWorkflow:
    """
    Automated workflow orchestrator.
    
    Handles the complete pipeline from card detection to Premiere project.
    """
    
    def __init__(
        self,
        project_name: Optional[str] = None,
        template: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verbose: bool = False
    ):
        self.project_name = project_name or f"Ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.output_dir = output_dir or Path.cwd() / self.project_name
        self.verbose = verbose
        self.logger = logging.getLogger(__name__)
        
        # Load template
        template_path = None
        if template:
            template_path = Path(template)
            if not template_path.exists():
                # Try templates directory
                template_path = Path('templates') / f"{template}.json"
        
        self.template = ProjectTemplate(template_path if template_path and template_path.exists() else None)
        
        # Results
        self.result = AutoWorkflowResult(success=False)
    
    def run(
        self,
        source: Optional[Path] = None,
        destinations: Optional[List[Path]] = None
    ) -> AutoWorkflowResult:
        """
        Run the complete automated workflow.
        
        Args:
            source: Source directory (auto-detect if None)
            destinations: Destination directories (uses output_dir if None)
            
        Returns:
            AutoWorkflowResult with all results
        """
        self.result.start_time = datetime.now()
        self.logger.info("=" * 60)
        self.logger.info("INGESTA AUTO WORKFLOW")
        self.logger.info("=" * 60)
        self.logger.info(f"Project: {self.project_name}")
        
        try:
            # Step 1: Auto-detect source if not provided
            if source is None:
                detector = MemoryCardDetector()
                source = detector.auto_select_source()
                
                if source is None:
                    self.result.errors.append("No memory card detected and no source specified")
                    self.logger.error("No source found. Please specify --source")
                    return self.result
            
            self.result.source_path = source
            self.logger.info(f"Source: {source}")
            
            # Step 2: Setup destinations
            if destinations is None:
                ingest_dest = self.output_dir / "media"
                ingest_dest.mkdir(parents=True, exist_ok=True)
                destinations = [ingest_dest]
            
            self.result.ingest_dest = destinations[0]
            self.logger.info(f"Destination: {destinations[0]}")
            
            # Step 3: Ingest with verification
            self.logger.info("\n" + "-" * 40)
            self.logger.info("STEP 1: Ingesting media...")
            self.logger.info("-" * 40)
            
            job = ingest_media(
                source=source,
                destinations=destinations,
                checksum_algorithm=self.template.settings['checksum_algorithm'],
                verify=self.template.settings['verify'],
                include_patterns=[f'*{ext}' for ext in VIDEO_EXTENSIONS]
            )
            
            self.logger.info(f"✓ Ingested {job.success_count}/{len(job.files_processed)} files")
            
            if job.failure_count > 0:
                self.result.errors.append(f"{job.failure_count} files failed ingestion")
            
            # Step 4: Analyze clips
            media_dir = destinations[0]
            
            if self.template.settings['analyze_content']:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("STEP 2: Analyzing clips...")
                self.logger.info("-" * 40)
                
                analyzer = ContentAnalyzer()
                analyses = analyzer.analyze_directory(media_dir, VIDEO_EXTENSIONS)
                self.result.clips_analyzed = len(analyses)
                
                self.logger.info(f"✓ Analyzed {len(analyses)} clips")
                
                # Print summary by type
                organized = analyzer.organize_by_type(analyses)
                for clip_type, clips in organized.items():
                    if clips:
                        self.logger.info(f"  - {clip_type.value}: {len(clips)} clips")
            else:
                analyses = []
            
            # Step 5: Detect slates
            slate_info = {}
            if self.template.settings['slate_detection']:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("STEP 3: Detecting slates...")
                self.logger.info("-" * 40)
                
                detector = SlateDetector()
                slate_results = detector.detect_slates_in_directory(media_dir, VIDEO_EXTENSIONS)
                
                # Convert to serializable format
                for path, info in slate_results.items():
                    slate_info[path] = {
                        'detected': info.detected,
                        'scene_number': info.scene_number,
                        'take_number': info.take_number,
                        'slate_text': info.slate_text,
                    }
                    if info.detected:
                        self.result.slates_detected += 1
                
                self.logger.info(f"✓ Detected slates in {self.result.slates_detected} clips")
            
            # Step 6: Extract thumbnails
            thumbnail_map = {}
            if self.template.settings['thumbnails']:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("STEP 4: Extracting thumbnails...")
                self.logger.info("-" * 40)
                
                thumb_dir = self.output_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                
                with ThumbnailExtractor(
                    output_dir=thumb_dir,
                    thumbnail_count=self.template.settings['thumbnail_count']
                ) as extractor:
                    for analysis in analyses:
                        thumbs = extractor.extract_thumbnails_for_clip(analysis.file_path)
                        thumbnail_map[analysis.file_path] = thumbs
                
                self.logger.info(f"✓ Extracted thumbnails to {thumb_dir}")
            
            # Step 7: Generate reports
            if self.template.settings['generate_reports'] and analyses:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("STEP 5: Generating reports...")
                self.logger.info("-" * 40)
                
                report_dir = self.output_dir / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                
                # PDF Report
                pdf_gen = PDFReportGenerator(
                    output_path=report_dir / "report.pdf",
                    project_name=self.project_name,
                    source_path=str(source),
                    destination_paths=[str(d) for d in destinations]
                )
                pdf_path = pdf_gen.generate_report(analyses, thumbnail_map)
                self.logger.info(f"✓ PDF Report: {pdf_path}")
                
                # CSV Report
                csv_gen = CSVReportGenerator(output_path=report_dir / "report.csv")
                csv_path = csv_gen.generate_report(analyses)
                self.logger.info(f"✓ CSV Report: {csv_path}")
                
                # Save slate info
                if slate_info:
                    slate_path = report_dir / "slate_detection.json"
                    # Convert paths to strings for JSON serialization
                    slate_serializable = {str(k): v for k, v in slate_info.items()}
                    with open(slate_path, 'w') as f:
                        json.dump(slate_serializable, f, indent=2)
                    self.logger.info(f"✓ Slate Info: {slate_path}")
                
                self.result.report_path = report_dir
            
            # Step 8: Create Premiere project
            if self.template.settings['create_premiere']:
                self.logger.info("\n" + "-" * 40)
                self.logger.info("STEP 6: Creating Premiere project...")
                self.logger.info("-" * 40)
                
                premiere_path = self.output_dir / f"{self.project_name}.prproj"
                
                report = create_premiere_project(
                    media_dir=media_dir,
                    output_path=premiere_path,
                    name=self.project_name,
                    fps=self.template.settings['fps'],
                    resolution=self.template.settings['resolution'],
                    analyze_content=self.template.settings['analyze_content'],
                    slate_info=slate_info,
                    video_formats=VIDEO_EXTENSIONS
                )
                
                self.logger.info(f"✓ Premiere Project: {premiere_path}")
                self.logger.info(f"  Total clips: {report['total_clips']}")
                self.logger.info(f"  Slates detected: {report['slates_detected']}")
                
                if report.get('cameras_reels'):
                    self.logger.info("  Cameras/Reels:")
                    for cam, count in report['cameras_reels'].items():
                        self.logger.info(f"    - {cam}: {count} clips")
                
                self.result.premiere_project = premiere_path
            
            # Save workflow result
            self.result.end_time = datetime.now()
            self.result.success = len(self.result.errors) == 0
            self.result.project_path = self.output_dir
            
            result_path = self.output_dir / "workflow_result.json"
            with open(result_path, 'w') as f:
                json.dump(self.result.to_dict(), f, indent=2)
            
            self.logger.info("\n" + "=" * 60)
            self.logger.info("WORKFLOW COMPLETE")
            self.logger.info("=" * 60)
            self.logger.info(f"Duration: {self.result.duration:.1f} seconds")
            self.logger.info(f"Output: {self.output_dir}")
            
        except Exception as e:
            self.result.end_time = datetime.now()
            self.result.errors.append(str(e))
            self.logger.error(f"Workflow failed: {e}")
            raise
        
        return self.result