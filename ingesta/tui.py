"""
TUI (Text User Interface) workflow module for ingesta.

Provides an interactive, step-by-step workflow for:
1. New Project - Create and configure a new project
2. Offload - Ingest media from cards/devices
3. Report - Generate comprehensive reports
4. Deliverables - Package client-ready deliverables

All processing is done locally - no data sent to external services.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

import click
from tqdm import tqdm

from .project_manager import ProjectManager, get_project_manager
from .ingestion import ingest_media
from .analysis import ContentAnalyzer
from .reports import (
    ThumbnailExtractor, PDFReportGenerator, CSVReportGenerator,
    LocalTranscriber, LocalFrameAnalyzer, AudioTechAnalyzer,
    MetadataExtractor, ProxyGenerator, KeywordTagger
)


logger = logging.getLogger(__name__)


class WorkflowStep(Enum):
    """Workflow step enumeration."""
    PROJECT = "project"
    OFFLOAD = "offload"
    REPORT = "report"
    DELIVERABLES = "deliverables"


@dataclass
class WorkflowState:
    """Maintains state across workflow steps."""
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    shoot_day_id: Optional[str] = None
    source_path: Optional[Path] = None
    destination_paths: List[Path] = field(default_factory=list)
    media_paths: List[Path] = field(default_factory=list)
    report_path: Optional[Path] = None
    deliverable_path: Optional[Path] = None
    analyses: List[Any] = field(default_factory=list)
    completed_steps: List[WorkflowStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Convert state to dictionary."""
        return {
            'project_id': self.project_id,
            'project_name': self.project_name,
            'shoot_day_id': self.shoot_day_id,
            'source_path': str(self.source_path) if self.source_path else None,
            'destination_paths': [str(p) for p in self.destination_paths],
            'media_paths': [str(p) for p in self.media_paths],
            'report_path': str(self.report_path) if self.report_path else None,
            'deliverable_path': str(self.deliverable_path) if self.deliverable_path else None,
            'completed_steps': [s.value for s in self.completed_steps],
            'created_at': self.created_at,
        }
    
    def save(self, path: Path):
        """Save state to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


class TUIWorkflow:
    """
    Interactive TUI workflow for ingesta.
    
    Guides users through:
    1. Project creation/setup
    2. Media offloading with verification
    3. Report generation
    4. Deliverable packaging
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.state = WorkflowState()
        self.pm = get_project_manager()
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging for workflow."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    
    def _print_header(self, title: str):
        """Print a section header."""
        click.echo("\n" + "=" * 60)
        click.echo(f"  {title}")
        click.echo("=" * 60)
    
    def _print_success(self, message: str):
        """Print a success message."""
        click.echo(f"\n✅ {message}")
    
    def _print_info(self, message: str):
        """Print an info message."""
        click.echo(f"ℹ️  {message}")
    
    def _print_warning(self, message: str):
        """Print a warning message."""
        click.echo(f"⚠️  {message}")
    
    def _ask_yes_no(self, question: str, default: bool = True) -> bool:
        """Ask a yes/no question."""
        return click.confirm(question, default=default)
    
    def run_full_workflow(self):
        """Run the complete workflow from start to finish."""
        click.echo("\n🎬 Welcome to ingesta TUI Workflow")
        click.echo("   Local media ingestion with verification and reporting\n")
        
        # Step 1: Project
        if not self.run_project_step():
            return False
        
        # Step 2: Offload
        if not self.run_offload_step():
            return False
        
        # Step 3: Report
        if not self.run_report_step():
            return False
        
        # Step 4: Deliverables
        if not self.run_deliverables_step():
            return False
        
        # Complete
        self._print_header("WORKFLOW COMPLETE")
        click.echo(f"\nProject: {self.state.project_name}")
        click.echo(f"Project ID: {self.state.project_id}")
        click.echo(f"Deliverables: {self.state.deliverable_path}")
        click.echo("\n✨ All steps completed successfully!")
        
        return True
    
    def run_project_step(self) -> bool:
        """
        Step 1: Create or select a project.
        
        Returns:
            True if successful, False otherwise
        """
        self._print_header("STEP 1: NEW PROJECT")
        
        # Ask if user wants to use existing project or create new
        use_existing = self._ask_yes_no("Use existing project?", default=False)
        
        if use_existing:
            return self._select_existing_project()
        else:
            return self._create_new_project()
    
    def _select_existing_project(self) -> bool:
        """Select an existing project."""
        projects = self.pm.list_projects(status='active')
        
        if not projects:
            self._print_warning("No existing projects found. Creating new project.")
            return self._create_new_project()
        
        click.echo("\nAvailable projects:")
        for i, proj in enumerate(projects, 1):
            click.echo(f"  {i}. {proj.name} (ID: {proj.project_id})")
        
        choice = click.prompt(
            "\nSelect project number",
            type=click.IntRange(1, len(projects)),
            default=1
        )
        
        selected = projects[choice - 1]
        self.state.project_id = selected.project_id
        self.state.project_name = selected.name
        
        # Ask if adding to existing shoot day or new one
        if selected.shoot_days:
            click.echo(f"\nExisting shoot days:")
            for i, sd in enumerate(selected.shoot_days, 1):
                click.echo(f"  {i}. {sd.label} ({sd.date})")
            click.echo(f"  {len(selected.shoot_days) + 1}. Create new shoot day")
            
            sd_choice = click.prompt(
                "Select shoot day",
                type=click.IntRange(1, len(selected.shoot_days) + 1),
                default=1
            )
            
            if sd_choice <= len(selected.shoot_days):
                self.state.shoot_day_id = selected.shoot_days[sd_choice - 1].shoot_day_id
            else:
                return self._create_shoot_day(selected.project_id)
        else:
            return self._create_shoot_day(selected.project_id)
        
        self._print_success(f"Using project: {selected.name}")
        self.state.completed_steps.append(WorkflowStep.PROJECT)
        return True
    
    def _create_new_project(self) -> bool:
        """Create a new project."""
        click.echo("\nCreating new project...")
        
        name = click.prompt("Project name", type=str)
        client = click.prompt("Client name (optional)", type=str, default="")
        director = click.prompt("Director (optional)", type=str, default="")
        
        # Optional fields
        add_details = self._ask_yes_no("Add more details?", default=False)
        
        producer = ""
        dp = ""
        description = ""
        
        if add_details:
            producer = click.prompt("Producer (optional)", type=str, default="")
            dp = click.prompt("DP (optional)", type=str, default="")
            description = click.prompt("Description (optional)", type=str, default="")
        
        # Create project
        project = self.pm.create_project(
            name=name,
            client=client or None,
            director=director or None,
            producer=producer or None,
            dp=dp or None,
            description=description or None
        )
        
        self.state.project_id = project.project_id
        self.state.project_name = project.name
        
        self._print_success(f"Created project: {project.name}")
        click.echo(f"   Project ID: {project.project_id}")
        
        # Create first shoot day
        return self._create_shoot_day(project.project_id)
    
    def _create_shoot_day(self, project_id: str) -> bool:
        """Create a shoot day for the project."""
        click.echo("\nCreating shoot day...")
        
        label = click.prompt("Shoot day label (e.g., 'Day 1')", type=str)
        date_str = click.prompt("Date (YYYY-MM-DD)", type=str, 
                                default=datetime.now().strftime('%Y-%m-%d'))
        location = click.prompt("Location (optional)", type=str, default="")
        
        shoot_day = self.pm.add_shoot_day(
            project_id=project_id,
            label=label,
            date=date_str,
            location=location or None
        )
        
        if shoot_day:
            self.state.shoot_day_id = shoot_day.shoot_day_id
            self._print_success(f"Created shoot day: {shoot_day.label}")
            self.state.completed_steps.append(WorkflowStep.PROJECT)
            return True
        else:
            self._print_warning("Failed to create shoot day")
            return False
    
    def run_offload_step(self) -> bool:
        """
        Step 2: Offload media from source to destination(s).
        
        Returns:
            True if successful, False otherwise
        """
        self._print_header("STEP 2: OFFLOAD MEDIA")
        
        # Get source
        source = click.prompt(
            "Source path (card/drive directory)",
            type=click.Path(exists=True, file_okay=False, dir_okay=True)
        )
        self.state.source_path = Path(source)
        
        # Get destinations
        destinations = []
        while True:
            dest = click.prompt(
                f"Destination path #{len(destinations) + 1}",
                type=click.Path(file_okay=False, dir_okay=True)
            )
            destinations.append(Path(dest))
            
            if not self._ask_yes_no("Add another destination?", default=False):
                break
        
        self.state.destination_paths = destinations
        
        # Card label
        card_label = click.prompt(
            "Card label (e.g., 'A001')",
            type=str,
            default=self._auto_detect_card_label()
        )
        
        # Notes
        notes = click.prompt("Notes (optional)", type=str, default="")
        
        # Checksum algorithm
        checksum = click.prompt(
            "Checksum algorithm",
            type=click.Choice(['xxhash64', 'md5', 'sha256'], case_sensitive=False),
            default='xxhash64'
        )
        
        # Confirm
        click.echo("\nOffload Summary:")
        click.echo(f"  Source: {source}")
        click.echo(f"  Destinations: {', '.join(str(d) for d in destinations)}")
        click.echo(f"  Card label: {card_label}")
        click.echo(f"  Checksum: {checksum}")
        
        if not self._ask_yes_no("\nStart offload?", default=True):
            self._print_info("Offload cancelled")
            return False
        
        # Perform offload
        try:
            click.echo("\nStarting offload...")
            
            pbar = tqdm(unit="files")
            
            def progress_callback(filename, total, current):
                pbar.total = total
                pbar.set_description(f"Copying {filename}")
                pbar.update(1)
            
            job = ingest_media(
                source=source,
                destinations=[str(d) for d in destinations],
                checksum_algorithm=checksum,
                verify=True,
                progress_callback=progress_callback
            )
            
            pbar.close()
            
            # Track in project
            session = self.pm.add_ingest_session(
                project_id=self.state.project_id,
                shoot_day_id=self.state.shoot_day_id,
                source_path=source,
                destination_paths=[str(d) for d in destinations],
                files_count=job.success_count,
                total_size_bytes=job.total_bytes,
                card_label=card_label,
                notes=notes or None
            )
            
            self._print_success("Offload complete!")
            click.echo(f"  Files processed: {job.success_count}")
            click.echo(f"  Total size: {job.total_bytes / (1024**3):.2f} GB")
            
            # Store media paths
            for dest in destinations:
                self.state.media_paths.append(dest)
            
            self.state.completed_steps.append(WorkflowStep.OFFLOAD)
            return True
            
        except Exception as e:
            self._print_warning(f"Offload failed: {e}")
            logger.error(f"Offload error: {e}", exc_info=True)
            return False
    
    def _auto_detect_card_label(self) -> str:
        """Auto-detect card label from source path."""
        if not self.state.source_path:
            return ""
        
        # Try to extract from path name
        name = self.state.source_path.name
        
        # Common patterns: A001, B002, Card1, etc.
        import re
        match = re.match(r'^([A-Z]\d{3})', name)
        if match:
            return match.group(1)
        
        match = re.search(r'[Cc]ard[_-]?(\d+)', name)
        if match:
            return f"CARD{match.group(1)}"
        
        return ""
    
    def run_report_step(self) -> bool:
        """
        Step 3: Generate comprehensive reports.
        
        Returns:
            True if successful, False otherwise
        """
        self._print_header("STEP 3: GENERATE REPORTS")
        
        if not self.state.media_paths:
            self._print_warning("No media paths available. Skipping reports.")
            return False
        
        # Use first destination as media directory
        media_dir = self.state.media_paths[0]
        
        # Output directory
        default_output = media_dir / "reports"
        output_str = click.prompt(
            "Output directory for reports",
            type=click.Path(file_okay=False, dir_okay=True),
            default=str(default_output)
        )
        output_dir = Path(output_str)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Report format
        report_format = click.prompt(
            "Report format",
            type=click.Choice(['pdf', 'csv', 'both'], case_sensitive=False),
            default='both'
        )
        
        # Optional features
        click.echo("\nOptional features:")
        
        options = {
            'transcribe': self._ask_yes_no("Transcribe audio?", default=False),
            'analyze_frames': self._ask_yes_no("Analyze frames?", default=False),
            'analyze_audio_tech': self._ask_yes_no("Analyze audio technical details?", default=True),
            'extract_metadata': self._ask_yes_no("Extract metadata?", default=True),
            'generate_proxies': self._ask_yes_no("Generate proxies?", default=True),
            'thumbnails': self._ask_yes_no("Generate thumbnails?", default=True),
        }
        
        # Confirm
        click.echo("\nReport Configuration:")
        click.echo(f"  Media directory: {media_dir}")
        click.echo(f"  Output directory: {output_dir}")
        click.echo(f"  Format: {report_format}")
        for opt, val in options.items():
            click.echo(f"  {opt}: {'Yes' if val else 'No'}")
        
        if not self._ask_yes_no("\nGenerate reports?", default=True):
            self._print_info("Report generation cancelled")
            return False
        
        try:
            # Analyze media
            click.echo("\nAnalyzing media...")
            analyzer = ContentAnalyzer()
            analyses = analyzer.analyze_directory(media_dir)
            
            if not analyses:
                self._print_warning("No media files found")
                return False
            
            self._print_info(f"Found {len(analyses)} clips")
            self.state.analyses = analyses
            
            # Extract thumbnails
            thumbnail_map = {}
            if options['thumbnails']:
                click.echo("\nExtracting thumbnails...")
                thumb_dir = output_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                
                with ThumbnailExtractor(output_dir=thumb_dir) as extractor:
                    for i, analysis in enumerate(analyses, 1):
                        click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                        thumbs = extractor.extract_thumbnails_for_clip(analysis.file_path)
                        thumbnail_map[analysis.file_path] = thumbs
            
            # Optional: Transcribe
            if options['transcribe']:
                click.echo("\nTranscribing audio...")
                transcriber = LocalTranscriber()
                for i, analysis in enumerate(analyses, 1):
                    click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                    result = transcriber.transcribe(analysis.file_path)
                    if result:
                        analysis.transcription = result.text
                        analysis.has_slate = result.has_slate
            
            # Optional: Analyze frames
            if options['analyze_frames']:
                click.echo("\nAnalyzing frames...")
                frame_analyzer = LocalFrameAnalyzer()
                for i, analysis in enumerate(analyses, 1):
                    click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                    result = frame_analyzer.analyze(analysis.file_path)
                    if result:
                        analysis.visual_description = result.description
            
            # Optional: Audio tech analysis
            if options['analyze_audio_tech']:
                click.echo("\nAnalyzing audio technical details...")
                audio_analyzer = AudioTechAnalyzer()
                for i, analysis in enumerate(analyses, 1):
                    result = audio_analyzer.analyze(analysis.file_path)
                    if result:
                        analysis.audio_peak_dbfs = result.peak_dbfs
                        analysis.audio_rms_dbfs = result.rms_dbfs
            
            # Optional: Extract metadata
            if options['extract_metadata']:
                click.echo("\nExtracting metadata...")
                metadata_extractor = MetadataExtractor()
                for i, analysis in enumerate(analyses, 1):
                    result = metadata_extractor.extract(analysis.file_path)
                    if result:
                        analysis.reel_id = result.reel.reel_id
                        analysis.timecode_start = result.timecode.start_tc
            
            # Optional: Generate proxies
            if options['generate_proxies']:
                click.echo("\nGenerating proxies...")
                proxy_dir = output_dir / "proxies"
                proxy_dir.mkdir(parents=True, exist_ok=True)
                proxy_gen = ProxyGenerator()
                
                for i, analysis in enumerate(analyses, 1):
                    click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                    result = proxy_gen.generate(analysis.file_path, proxy_dir)
                    if result.success and result.proxy_path:
                        analysis.proxy_path = str(result.proxy_path.relative_to(output_dir))
            
            # Generate reports
            generated_files = []
            
            if report_format in ['pdf', 'both']:
                click.echo("\nGenerating PDF report...")
                pdf_gen = PDFReportGenerator(
                    output_path=output_dir / "report.pdf",
                    project_name=self.state.project_name or "Report",
                    source_path=str(self.state.source_path) if self.state.source_path else None,
                    destination_paths=[str(d) for d in self.state.destination_paths]
                )
                pdf_path = pdf_gen.generate_report(analyses, thumbnail_map)
                generated_files.append(pdf_path)
                click.echo(f"  ✓ PDF: {pdf_path}")
            
            if report_format in ['csv', 'both']:
                click.echo("\nGenerating CSV reports...")
                csv_gen = CSVReportGenerator(output_path=output_dir / "report.csv")
                csv_path = csv_gen.generate_report(analyses)
                generated_files.append(csv_path)
                click.echo(f"  ✓ CSV: {csv_path}")
                
                summary_path = csv_gen.generate_summary_csv(analyses)
                generated_files.append(summary_path)
                click.echo(f"  ✓ Summary: {summary_path}")
            
            self.state.report_path = output_dir
            self._print_success("Reports generated!")
            click.echo(f"\nOutput files:")
            for f in generated_files:
                click.echo(f"  - {f}")
            
            self.state.completed_steps.append(WorkflowStep.REPORT)
            return True
            
        except Exception as e:
            self._print_warning(f"Report generation failed: {e}")
            logger.error(f"Report error: {e}", exc_info=True)
            return False
    
    def run_deliverables_step(self) -> bool:
        """
        Step 4: Package client-ready deliverables.
        
        Returns:
            True if successful, False otherwise
        """
        self._print_header("STEP 4: PACKAGE DELIVERABLES")
        
        # For now, this creates a summary and shows where files are
        # Full deliverable packaging implemented in Feature 4
        
        if not self.state.destination_paths:
            self._print_warning("No destination paths available")
            return False
        
        primary_dest = self.state.destination_paths[0]
        deliverables_dir = primary_dest / "DELIVERABLES"
        deliverables_dir.mkdir(parents=True, exist_ok=True)
        
        # Create summary document
        summary = {
            'project_name': self.state.project_name,
            'project_id': self.state.project_id,
            'created_at': datetime.now().isoformat(),
            'steps_completed': [s.value for s in self.state.completed_steps],
            'source': str(self.state.source_path) if self.state.source_path else None,
            'destinations': [str(d) for d in self.state.destination_paths],
            'report_path': str(self.state.report_path) if self.state.report_path else None,
        }
        
        summary_path = deliverables_dir / "workflow_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Create README
        readme_path = deliverables_dir / "README.txt"
        with open(readme_path, 'w') as f:
            f.write(f"Project: {self.state.project_name}\n")
            f.write(f"Project ID: {self.state.project_id}\n")
            f.write(f"Created: {datetime.now().isoformat()}\n\n")
            f.write("Completed Steps:\n")
            for step in self.state.completed_steps:
                f.write(f"  - {step.value}\n")
            f.write(f"\nReports: {self.state.report_path}\n")
        
        self.state.deliverable_path = deliverables_dir
        self._print_success("Deliverables directory created!")
        click.echo(f"   Location: {deliverables_dir}")
        
        self.state.completed_steps.append(WorkflowStep.DELIVERABLES)
        return True


def run_tui_workflow(verbose: bool = False) -> bool:
    """
    Run the TUI workflow.
    
    Args:
        verbose: Enable verbose output
        
    Returns:
        True if workflow completed successfully
    """
    workflow = TUIWorkflow(verbose=verbose)
    return workflow.run_full_workflow()
