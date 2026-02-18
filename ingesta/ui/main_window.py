"""Main window for ingesta PySide6 UI - Three panel layout.

Layout:
- Left: Workflow steps sidebar
- Center: Active module (ingestion form, progress, next steps)
- Right: Workflow status + history panel
- Footer: Status line
"""

import sys
import shutil
import time
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QProgressBar, QFrame,
    QSplitter, QMessageBox, QApplication, QMenuBar,
    QMenu, QStatusBar, QSizePolicy, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from .drop_zones import SourceDropZone, DestinationDropZone, count_media_files
from .history_panel import HistoryPanel, HistoryItem
from .enhanced_workflow_steps import EnhancedWorkflowStepsPanel, StepState, DEFAULT_STEPS
from .workflow_status_panel import WorkflowStatusPanel
from .next_steps_panel import NextStepsPanel
from .checksum_dialog import ChecksumSelectionDialog
from .styles import DARK_STYLESHEET, SAFE_BADGE_STYLE, FAIL_BADGE_STYLE, WARNING_BADGE_STYLE
from .feature_cards import FeatureCardsPanel, FeatureStatus, ALL_FEATURES
from .reports_panel import ReportsPanel
from .source_queue import SourceQueueWidget

from ..workflow.events import (
    EventType,
    StepStartedEvent,
    StepCompletedEvent,
    StepFailedEvent,
    StepProgressEvent,
    get_default_event_bus,
)


class IngestionWorker(QThread):
    """Worker thread for running ingestion."""

    progress = Signal(object)  # ProgressEvent
    completed = Signal(object)  # IngestionCompletion
    error = Signal(str)

    def __init__(
        self,
        source: Path,
        destinations: List[Path],
        checksum_algorithm: str = "xxhash64",
        event_bus=None,
        step_index_map: Optional[dict] = None,
        total_steps: int = 0,
    ):
        super().__init__()
        self.source = source
        self.destinations = destinations
        self.checksum_algorithm = checksum_algorithm
        self._is_running = True
        self._event_bus = event_bus
        self._step_index_map = step_index_map or {}
        self._total_steps = total_steps
        self._last_emit_time = {}
        self._started_steps = set()
        self._cancelled = False
    
    def _emit_step_started(self, step_id: str):
        if not self._event_bus or step_id in self._started_steps:
            return
        self._started_steps.add(step_id)
        self._event_bus.emit(StepStartedEvent(
            event_type=EventType.STEP_STARTED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            step_type=step_id,
            input_data={},
        ))
    
    def _emit_step_progress(self, step_id: str, percent: float, current_item: str, 
                            items_processed: int, items_total: int, 
                            current_speed_mbps: Optional[float] = None,
                            eta_seconds: Optional[float] = None):
        if not self._event_bus:
            return
        now = time.monotonic()
        last = self._last_emit_time.get(step_id, 0)
        if now - last < 0.3:
            return
        self._last_emit_time[step_id] = now
        self._event_bus.emit(StepProgressEvent(
            event_type=EventType.STEP_PROGRESS,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            percent_complete=percent,
            current_item=current_item,
            items_processed=items_processed,
            items_total=items_total,
            current_speed_mbps=current_speed_mbps,
            eta_seconds=eta_seconds,
        ))
    
    def _emit_step_completed(self, step_id: str, output_data: Optional[dict] = None):
        if not self._event_bus:
            return
        self._event_bus.emit(StepCompletedEvent(
            event_type=EventType.STEP_COMPLETED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            duration_seconds=0.0,
            output_data=output_data or {},
        ))
    
    def _emit_step_failed(self, step_id: str, message: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepFailedEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            error_message=message,
            error_type="Cancelled" if self._cancelled else "Error",
            error_details={},
        ))

    def run(self):
        """Run the ingestion."""
        try:
            from ..ingestion import ingest_media
            from ..ingestion import IngestionStage

            def progress_callback(event):
                if self._is_running:
                    self.progress.emit(event)
                if self._is_running and self._event_bus:
                    if event.stage == IngestionStage.SCANNING:
                        self._emit_step_started("copy")
                    elif event.stage == IngestionStage.COPYING:
                        self._emit_step_started("copy")
                        percent = 0.0
                        if event.total_source_files > 0:
                            file_progress = (event.bytes_copied / event.total_bytes) if event.total_bytes else 0.0
                            percent = ((event.current_file_index + file_progress) / event.total_source_files) * 100
                        current_item = event.source_file.name if event.source_file else ""
                        self._emit_step_progress(
                            "copy",
                            percent,
                            current_item,
                            event.current_file_index,
                            event.total_source_files,
                            current_speed_mbps=event.current_speed_mb_s,
                            eta_seconds=event.eta_seconds,
                        )
                    elif event.stage == IngestionStage.VERIFYING:
                        self._emit_step_started("verify")
                        percent = 0.0
                        if event.total_source_files > 0:
                            percent = (event.current_file_index / event.total_source_files) * 100
                        current_item = event.source_file.name if event.source_file else ""
                        self._emit_step_progress(
                            "verify",
                            percent,
                            current_item,
                            event.current_file_index,
                            event.total_source_files,
                        )
                    elif event.stage == IngestionStage.COMPLETE:
                        self._emit_step_completed("copy")
                        self._emit_step_completed("verify")

            job = ingest_media(
                source=self.source,
                destinations=[str(p) for p in self.destinations],
                checksum_algorithm=self.checksum_algorithm,
                verify=True,
                progress_event_callback=progress_callback
            )

            if self._is_running:
                completion = job.get_completion()
                self.completed.emit(completion)

        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))
                self._emit_step_failed("copy", str(e))
                self._emit_step_failed("verify", str(e))
    
    def stop(self):
        """Request stop (cooperative)."""
        self._is_running = False
        self._cancelled = True
        self.wait(1000)
        self._emit_step_failed("copy", "Cancelled")
        self._emit_step_failed("verify", "Cancelled")


class ReportsWorker(QThread):
    """Worker thread for real report generation using existing report modules."""

    progress = Signal(float, str)  # percent, status message
    completed = Signal(list)  # artifacts
    error = Signal(str)

    def __init__(self, config, media_path=None, event_bus=None, step_index_map=None, total_steps: int = 0):
        super().__init__()
        self.config = config
        self.media_path = media_path
        self._event_bus = event_bus
        self._step_index_map = step_index_map or {}
        self._total_steps = total_steps
        self._is_running = True

    def _check_cancelled(self) -> bool:
        """Check if worker should stop."""
        return not self._is_running

    def run(self):
        """Generate real reports using the report module logic."""
        import logging
        from pathlib import Path
        from ..analysis import ContentAnalyzer
        from ..reports import (
            ThumbnailExtractor, PDFReportGenerator, CSVReportGenerator,
            LocalTranscriber, LocalFrameAnalyzer, AudioTechAnalyzer, MetadataExtractor,
            DuplicateDetector, BadClipDetector, ProxyGenerator, KeywordTagger,
            DeliveryChecklistGenerator
        )

        logger = logging.getLogger(__name__)

        try:
            self._emit_started("reports")

            # Determine media path
            if self.media_path and self.media_path.exists():
                media_path = Path(self.media_path)
            else:
                # Try to use source path from main window context
                media_path = Path("./media")

            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            self._emit_progress("reports", 5, "Scanning for media files...", 0, 100)

            # Step 1: Analyze media
            logger.info(f"Analyzing clips in: {media_path}")
            analyzer = ContentAnalyzer()
            analyses = analyzer.analyze_directory(media_path)

            if not analyses:
                raise ValueError("No video files found in media directory")

            self._emit_progress("reports", 15, f"Found {len(analyses)} clips", len(analyses), len(analyses))

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            # Step 2: Transcribe audio if requested
            if self.config.transcribe:
                self._emit_progress("reports", 25, "Transcribing audio (local AI)...", 0, len(analyses))
                transcriber = LocalTranscriber(model="base")
                for i, analysis in enumerate(analyses):
                    if self._check_cancelled():
                        raise InterruptedError("Report generation cancelled")
                    self._emit_progress("reports", 25 + (i / len(analyses)) * 15,
                                      f"Transcribing: {analysis.file_path.name}", i, len(analyses))
                    result = transcriber.transcribe(analysis.file_path)
                    if result:
                        analysis.transcription = result.text
                        analysis.transcription_excerpt = result.excerpt
                        analysis.has_slate = result.has_slate
                        analysis.has_end_mark = result.has_end_mark
                        analysis.slate_text = result.slate_text

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            # Step 3: Analyze frames if requested
            if self.config.analyze_frames:
                self._emit_progress("reports", 40, "Analyzing frames...", 0, len(analyses))
                frame_analyzer = LocalFrameAnalyzer()
                for i, analysis in enumerate(analyses):
                    if self._check_cancelled():
                        raise InterruptedError("Report generation cancelled")
                    self._emit_progress("reports", 40 + (i / len(analyses)) * 10,
                                      f"Analyzing frames: {analysis.file_path.name}", i, len(analyses))
                    result = frame_analyzer.analyze(analysis.file_path)
                    if result:
                        analysis.visual_description = result.description
                        analysis.shot_type = result.shot_type.value

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            # Step 4: Extract thumbnails if requested
            thumbnail_map = {}
            if self.config.include_thumbnails:
                self._emit_progress("reports", 50, "Extracting thumbnails...", 0, len(analyses))
                thumb_dir = output_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)

                with ThumbnailExtractor(output_dir=thumb_dir) as extractor:
                    for i, analysis in enumerate(analyses):
                        if self._check_cancelled():
                            raise InterruptedError("Report generation cancelled")
                        self._emit_progress("reports", 50 + (i / len(analyses)) * 15,
                                          f"Extracting thumbnails: {analysis.file_path.name}", i, len(analyses))
                        thumbs = extractor.extract_thumbnails_for_clip(analysis.file_path)
                        thumbnail_map[analysis.file_path] = thumbs

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            # Step 5: Generate delivery checklist
            self._emit_progress("reports", 65, "Generating delivery checklist...", 0, 100)
            checklist_gen = DeliveryChecklistGenerator()
            checklist = checklist_gen.generate_checklist(analyses)

            # Export checklist files
            checklist_txt_path = checklist_gen.export_checklist_text(checklist, output_dir / "delivery_checklist.txt")
            checklist_csv_path = checklist_gen.export_checklist_csv(checklist, output_dir / "delivery_checklist.csv")

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            # Step 6: Generate reports
            artifacts = []
            proj_name = self.config.report_name or media_path.name or "Media Ingest Report"

            # Add checklist artifacts
            artifacts.append({
                "name": checklist_txt_path.name,
                "path": checklist_txt_path,
                "type": "txt",
                "size_bytes": checklist_txt_path.stat().st_size if checklist_txt_path.exists() else 0
            })
            artifacts.append({
                "name": checklist_csv_path.name,
                "path": checklist_csv_path,
                "type": "csv",
                "size_bytes": checklist_csv_path.stat().st_size if checklist_csv_path.exists() else 0
            })

            if self.config.generate_pdf:
                self._emit_progress("reports", 75, "Generating PDF report...", 0, 100)
                pdf_generator = PDFReportGenerator(
                    output_path=output_dir / "report.pdf",
                    project_name=proj_name,
                    source_path=str(media_path),
                    destination_paths=[]
                )
                pdf_path = pdf_generator.generate_report(analyses, thumbnail_map, checklist=checklist)
                artifacts.append({
                    "name": pdf_path.name,
                    "path": pdf_path,
                    "type": "pdf",
                    "size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0
                })

            if self._check_cancelled():
                raise InterruptedError("Report generation cancelled")

            if self.config.generate_csv:
                self._emit_progress("reports", 90, "Generating CSV reports...", 0, 100)
                csv_generator = CSVReportGenerator(output_path=output_dir / "report.csv")
                csv_path = csv_generator.generate_report(analyses)
                artifacts.append({
                    "name": csv_path.name,
                    "path": csv_path,
                    "type": "csv",
                    "size_bytes": csv_path.stat().st_size if csv_path.exists() else 0
                })

                # Also generate summary CSV
                summary_path = csv_generator.generate_summary_csv(analyses)
                artifacts.append({
                    "name": summary_path.name,
                    "path": summary_path,
                    "type": "csv",
                    "size_bytes": summary_path.stat().st_size if summary_path.exists() else 0
                })

            self._emit_progress("reports", 100, "Complete", 100, 100)
            self._emit_completed("reports", {"artifacts": [a["name"] for a in artifacts]})
            self.completed.emit(artifacts)

        except InterruptedError:
            self._emit_failed("reports", "Cancelled")
            self.error.emit("Report generation was cancelled")
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            self._emit_failed("reports", str(e))
            self.error.emit(str(e))

    def stop(self):
        """Request stop."""
        self._is_running = False

    def _emit_started(self, step_id: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepStartedEvent(
            event_type=EventType.STEP_STARTED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            step_type=step_id,
            input_data={},
        ))

    def _emit_progress(self, step_id: str, percent: float, current_item: str,
                       items_processed: int, items_total: int):
        if not self._event_bus:
            return
        self._event_bus.emit(StepProgressEvent(
            event_type=EventType.STEP_PROGRESS,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            percent_complete=percent,
            current_item=current_item,
            items_processed=items_processed,
            items_total=items_total,
        ))

    def _emit_completed(self, step_id: str, output_data: Optional[dict] = None):
        if not self._event_bus:
            return
        self._event_bus.emit(StepCompletedEvent(
            event_type=EventType.STEP_COMPLETED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            duration_seconds=0.0,
            output_data=output_data or {},
        ))

    def _emit_failed(self, step_id: str, message: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepFailedEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            error_message=message,
            error_type="Error",
            error_details={},
        ))


class TranscriptionWorker(QThread):
    """Worker thread for background transcription with progress events."""

    progress = Signal(float, str, int, int)  # percent, current_item, items_processed, items_total
    clip_completed = Signal(str, object)  # clip_name, TranscriptionResult
    completed = Signal(list)  # list of (clip_path, result) tuples
    error = Signal(str)

    def __init__(self, media_path: Path, event_bus=None, step_index_map=None, total_steps: int = 0, whisper_model: str = "base"):
        super().__init__()
        self.media_path = media_path
        self._event_bus = event_bus
        self._step_index_map = step_index_map or {}
        self._total_steps = total_steps
        self.whisper_model = whisper_model
        self._is_running = True
        self.results = []

    def _check_cancelled(self) -> bool:
        """Check if worker should stop."""
        return not self._is_running

    def run(self):
        """Run transcription workflow on media files."""
        import logging
        from pathlib import Path
        from ..reports import LocalTranscriber

        logger = logging.getLogger(__name__)

        try:
            self._emit_started("transcribe")

            # Find video files
            video_extensions = ('.mp4', '.mov', '.mxf', '.avi', '.mkv', '.mts', '.m2ts')
            video_files = []
            for ext in video_extensions:
                video_files.extend(self.media_path.glob(f"**/*{ext}"))
                video_files.extend(self.media_path.glob(f"**/*{ext.upper()}"))

            video_files = list(set(video_files))  # Remove duplicates
            total_files = len(video_files)

            if total_files == 0:
                raise ValueError(f"No video files found in {self.media_path}")

            logger.info(f"Found {total_files} video files to transcribe")
            self._emit_progress("transcribe", 0, f"Found {total_files} clips", 0, total_files)

            # Initialize transcriber
            transcriber = LocalTranscriber(model=self.whisper_model)

            # Transcribe each file
            for i, video_file in enumerate(video_files):
                if self._check_cancelled():
                    raise InterruptedError("Transcription cancelled")

                percent = (i / total_files) * 100
                self._emit_progress("transcribe", percent, f"Transcribing: {video_file.name}", i, total_files)
                self.progress.emit(percent, video_file.name, i, total_files)

                try:
                    result = transcriber.transcribe(video_file)
                    if result:
                        self.results.append((str(video_file), result))
                        self.clip_completed.emit(video_file.name, result)
                        logger.info(f"Transcribed {video_file.name}: {result.excerpt[:50]}...")
                except Exception as e:
                    logger.warning(f"Failed to transcribe {video_file.name}: {e}")
                    # Continue with other files even if one fails

            self._emit_progress("transcribe", 100, "Transcription complete", total_files, total_files)
            self._emit_completed("transcribe", {"transcribed_clips": len(self.results)})
            self.completed.emit(self.results)

        except InterruptedError:
            self._emit_failed("transcribe", "Cancelled")
            self.error.emit("Transcription was cancelled")
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            self._emit_failed("transcribe", str(e))
            self.error.emit(str(e))

    def stop(self):
        """Request stop."""
        self._is_running = False

    def _emit_started(self, step_id: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepStartedEvent(
            event_type=EventType.STEP_STARTED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            step_type=step_id,
            input_data={"media_path": str(self.media_path)},
        ))

    def _emit_progress(self, step_id: str, percent: float, current_item: str,
                       items_processed: int, items_total: int):
        if not self._event_bus:
            return
        self._event_bus.emit(StepProgressEvent(
            event_type=EventType.STEP_PROGRESS,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            percent_complete=percent,
            current_item=current_item,
            items_processed=items_processed,
            items_total=items_total,
        ))

    def _emit_completed(self, step_id: str, output_data: Optional[dict] = None):
        if not self._event_bus:
            return
        self._event_bus.emit(StepCompletedEvent(
            event_type=EventType.STEP_COMPLETED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            duration_seconds=0.0,
            output_data=output_data or {},
        ))

    def _emit_failed(self, step_id: str, message: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepFailedEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            error_message=message,
            error_type="Error",
            error_details={},
        ))


class FeatureWorker(QThread):
    """Generic worker for feature actions (UI adapter)."""

    completed = Signal(str)
    error = Signal(str)

    def __init__(self, feature_id: str, event_bus=None, step_index_map=None, total_steps: int = 0):
        super().__init__()
        self.feature_id = feature_id
        self._event_bus = event_bus
        self._step_index_map = step_index_map or {}
        self._total_steps = total_steps

    def run(self):
        try:
            self._emit_started(self.feature_id)
            for percent in range(0, 101, 10):
                time.sleep(0.25)
                self._emit_progress(self.feature_id, percent, f"Running {self.feature_id}", percent, 100)
            self._emit_completed(self.feature_id)
            self.completed.emit(self.feature_id)
        except Exception as e:
            self._emit_failed(self.feature_id, str(e))
            self.error.emit(str(e))

    def _emit_started(self, step_id: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepStartedEvent(
            event_type=EventType.STEP_STARTED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            step_type=step_id,
            input_data={},
        ))

    def _emit_progress(self, step_id: str, percent: float, current_item: str,
                       items_processed: int, items_total: int):
        if not self._event_bus:
            return
        self._event_bus.emit(StepProgressEvent(
            event_type=EventType.STEP_PROGRESS,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            percent_complete=percent,
            current_item=current_item,
            items_processed=items_processed,
            items_total=items_total,
        ))

    def _emit_completed(self, step_id: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepCompletedEvent(
            event_type=EventType.STEP_COMPLETED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            duration_seconds=0.0,
            output_data={},
        ))

    def _emit_failed(self, step_id: str, message: str):
        if not self._event_bus:
            return
        self._event_bus.emit(StepFailedEvent(
            event_type=EventType.STEP_FAILED,
            workflow_id="ingest-ui",
            step_name=step_id,
            step_index=self._step_index_map.get(step_id, 0),
            total_steps=self._total_steps,
            error_message=message,
            error_type="Error",
            error_details={},
        ))


class IngestaMainWindow(QMainWindow):
    """Main window for ingesta desktop UI with three-panel layout."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ingesta - Media Ingestion Tool")
        self.setMinimumSize(1400, 900)

        self.source_path: Optional[Path] = None
        self.dest_paths: List[Path] = []
        self.current_worker: Optional[IngestionWorker] = None
        self.current_history_item: Optional[HistoryItem] = None
        self.total_files: int = 0
        self.total_size_bytes: int = 0
        self.checksum_algorithm: str = "xxhash64"  # Default checksum algorithm

        # Event bus for unified UI updates
        self._event_bus = get_default_event_bus()
        self._step_index_map = {step_id: idx for idx, (step_id, _, _) in enumerate(DEFAULT_STEPS)}
        self._total_steps = len(DEFAULT_STEPS)
        self._running_features: set = set()
        self._cancelled_features: set = set()
        self._current_reports_worker: Optional[ReportsWorker] = None
        self._current_transcription_worker: Optional[TranscriptionWorker] = None

        # Subscribe to workflow events
        self._subscribe_to_events()

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._setup_shortcuts()
        self._update_start_button()
        self._update_workflow_step()

    def _subscribe_to_events(self):
        """Subscribe to workflow events for unified UI updates."""
        self._event_bus.subscribe(EventType.STEP_STARTED, self._on_step_started)
        self._event_bus.subscribe(EventType.STEP_PROGRESS, self._on_step_progress)
        self._event_bus.subscribe(EventType.STEP_COMPLETED, self._on_step_completed)
        self._event_bus.subscribe(EventType.STEP_FAILED, self._on_step_failed)

    def _on_step_started(self, event):
        """Handle step started event."""
        if isinstance(event, StepStartedEvent):
            step_id = event.step_name
            # Update workflow steps panel
            if hasattr(self, 'workflow_steps') and step_id in self._step_index_map:
                self.workflow_steps.set_step_state(step_id, StepState.RUNNING)
            # Update feature cards
            if hasattr(self, 'feature_cards'):
                from .feature_cards import FeatureStatus
                card = self.feature_cards.get_card(step_id)
                if card:
                    card.set_status(FeatureStatus.RUNNING)
            # Update workflow status
            if hasattr(self, 'workflow_status'):
                self.workflow_status.set_status(step_id.replace('_', ' ').title(), "Running")
            self._update_footer_status(f"Started: {step_id}")

    def _on_step_progress(self, event):
        """Handle step progress event."""
        if isinstance(event, StepProgressEvent):
            step_id = event.step_name
            percent = event.percent_complete
            current_item = event.current_item or ""
            items_processed = event.items_processed
            items_total = event.items_total
            # Update workflow steps
            if hasattr(self, 'workflow_steps') and step_id in self._step_index_map:
                self.workflow_steps.set_step_progress(
                    step_id, percent, current_item, items_processed, items_total
                )
            # Update feature cards
            if hasattr(self, 'feature_cards'):
                card = self.feature_cards.get_card(step_id)
                if card:
                    card.set_progress(percent, current_item, items_processed, items_total)
            # Update workflow status panel
            if hasattr(self, 'workflow_status'):
                self.workflow_status.update_pipeline_status(
                    status=step_id.replace('_', ' ').title(),
                    detail=current_item,
                    percent=percent,
                    items_processed=items_processed,
                    items_total=items_total,
                    current_item=current_item,
                )

    def _on_step_completed(self, event):
        """Handle step completed event."""
        if isinstance(event, StepCompletedEvent):
            step_id = event.step_name
            # Update workflow steps
            if hasattr(self, 'workflow_steps') and step_id in self._step_index_map:
                self.workflow_steps.set_step_state(step_id, StepState.COMPLETE)
            # Update feature cards
            if hasattr(self, 'feature_cards'):
                from .feature_cards import FeatureStatus
                card = self.feature_cards.get_card(step_id)
                if card:
                    card.set_status(FeatureStatus.COMPLETE)
                    card.set_result(event.output_data)
            # Update workflow status
            if hasattr(self, 'workflow_status'):
                self.workflow_status.set_status(step_id.replace('_', ' ').title(), "Complete")
            self._running_features.discard(step_id)
            self._update_footer_status(f"Completed: {step_id}")

    def _on_step_failed(self, event):
        """Handle step failed event."""
        if isinstance(event, StepFailedEvent):
            step_id = event.step_name
            error_msg = event.error_message
            # Update workflow steps
            if hasattr(self, 'workflow_steps') and step_id in self._step_index_map:
                self.workflow_steps.set_step_error(step_id, error_msg)
            # Update feature cards
            if hasattr(self, 'feature_cards'):
                from .feature_cards import FeatureStatus
                card = self.feature_cards.get_card(step_id)
                if card:
                    card.set_error(error_msg)
            # Update workflow status
            if hasattr(self, 'workflow_status'):
                self.workflow_status.set_status(step_id.replace('_', ' ').title(), f"Error: {error_msg}")
            self._running_features.discard(step_id)
            self._update_footer_status(f"Error in {step_id}: {error_msg}")

    def _setup_menu_bar(self):
        """Setup menu bar with File and Help menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # Clear All action
        clear_action = QAction("&Clear All", self)
        clear_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        clear_action.triggered.connect(self._on_clear_all)
        file_menu.addAction(clear_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        # Sync action
        sync_action = QAction("&Sync Audio/Video...", self)
        sync_action.setShortcut(QKeySequence("Ctrl+S"))
        sync_action.triggered.connect(self._on_sync_action)
        tools_menu.addAction(sync_action)
        
        tools_menu.addSeparator()
        
        # Report action
        report_action = QAction("&Generate Report...", self)
        report_action.setShortcut(QKeySequence("Ctrl+R"))
        report_action.triggered.connect(self._on_report_action)
        tools_menu.addAction(report_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_status_bar(self):
        """Setup footer status bar."""
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #0f172a;
                border-top: 1px solid #1e293b;
                color: #888;
                padding: 4px 16px;
            }
        """)
        self.setStatusBar(self.status_bar)
        
        # Status message (left)
        self.footer_status = QLabel("Ready")
        self.footer_status.setStyleSheet("color: #aaa;")
        self.status_bar.addWidget(self.footer_status)
        
        # Spacer
        self.status_bar.addStretch()
        
        # Stats (right side)
        self.footer_stats = QLabel("")
        self.footer_stats.setStyleSheet("color: #666; font-size: 11px;")
        self.status_bar.addPermanentWidget(self.footer_stats)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Cmd/Ctrl+O - Select Source
        shortcut_source = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut_source.activated.connect(self._on_shortcut_source)
        
        # Cmd/Ctrl+D - Select Destinations  
        shortcut_dest = QShortcut(QKeySequence("Ctrl+D"), self)
        shortcut_dest.activated.connect(self._on_shortcut_dest)
        
        # Cmd/Ctrl+Return - Start Ingestion
        shortcut_start = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut_start.activated.connect(self._on_start)
    
    def _on_shortcut_source(self):
        """Handle Cmd+O shortcut."""
        self.source_zone._on_browse()
    
    def _on_shortcut_dest(self):
        """Handle Cmd+D shortcut."""
        self.dest_zone._on_browse()
    
    def _on_clear_all(self):
        """Clear all selections."""
        self.source_path = None
        self.dest_paths = []
        self.total_files = 0
        self.total_size_bytes = 0
        self.checksum_algorithm = "xxhash64"  # Reset to default

        self.source_zone.clear()
        self.dest_zone.clear()

        self._update_start_button()
        self._update_workflow_step()
        self._update_footer_status("Ready")

        # Hide next steps if visible
        self.next_steps_panel.hide_panel()

        # Reset workflow progress
        self.workflow_steps.reset_progress()
    
    def _update_footer_status(self, message: str):
        """Update footer status line."""
        self.footer_status.setText(message)
    
    def _update_footer_stats(self):
        """Update footer statistics display."""
        parts = []

        if self.source_path:
            src_count, src_size = self.source_zone.get_total_stats()
            parts.append(f"Source: {src_count} clips, {src_size / (1024**3):.2f} GB")

        if self.dest_paths:
            parts.append(f"Destinations: {len(self.dest_paths)}")

        # Always show checksum algorithm (with default)
        parts.append(f"Verification: {self.checksum_algorithm.upper()}")

        if parts:
            self.footer_stats.setText(" | ".join(parts))
        else:
            self.footer_stats.setText(f"Verification: {self.checksum_algorithm.upper()}")
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Ingesta",
            "<h2>Ingesta</h2>"
            "<p>Media Ingestion & Verification Tool</p>"
            "<p>Version 1.0.0</p>"
            "<p>Drag and drop media cards or folders to copy with verification.</p>"
        )
    
    def _setup_ui(self):
        """Setup the main three-panel UI."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Horizontal splitter for three panels
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # === LEFT PANEL: Enhanced Workflow Steps ===
        self.workflow_steps = EnhancedWorkflowStepsPanel()
        self.workflow_steps.stepClicked.connect(self._on_workflow_step_clicked)
        self.workflow_steps.stepCancelRequested.connect(self._on_step_cancel_requested)
        # Add default steps
        for step_id, name, desc in DEFAULT_STEPS:
            self.workflow_steps.add_step(step_id, name, desc)
        h_splitter.addWidget(self.workflow_steps)
        
        # === CENTER PANEL: Active Module ===
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(20, 20, 20, 20)
        center_layout.setSpacing(16)
        
        # Header
        header = QLabel("Ingesta")
        header.setObjectName("title")
        center_layout.addWidget(header)
        
        subtitle = QLabel("Media Ingestion & Verification")
        subtitle.setStyleSheet("color: #888; margin-bottom: 10px;")
        center_layout.addWidget(subtitle)
        
        # Source section
        source_label = QLabel("SOURCE")
        source_label.setObjectName("section-title")
        center_layout.addWidget(source_label)
        
        self.source_zone = SourceDropZone()
        self.source_zone.filesDropped.connect(self._on_source_dropped)
        self.source_zone.filesChanged.connect(self._on_source_changed)
        self.source_zone.set_validation_callback(self._validate_source)
        center_layout.addWidget(self.source_zone)
        
        # Destination section
        dest_label = QLabel("DESTINATIONS")
        dest_label.setObjectName("section-title")
        center_layout.addWidget(dest_label)
        
        self.dest_zone = DestinationDropZone()
        self.dest_zone.filesDropped.connect(self._on_destinations_dropped)
        self.dest_zone.filesChanged.connect(self._on_destinations_changed)
        self.dest_zone.set_validation_callback(self._validate_destinations)
        center_layout.addWidget(self.dest_zone)
        
        # Progress section
        self.progress_frame = QFrame()
        self.progress_frame.setObjectName("card")
        progress_layout = QVBoxLayout(self.progress_frame)
        
        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("section-title")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - Waiting to start")
        progress_layout.addWidget(self.progress_bar)
        
        # Stats row
        stats_layout = QHBoxLayout()
        
        self.speed_label = QLabel("Speed: --")
        self.speed_label.setObjectName("status-text")
        stats_layout.addWidget(self.speed_label)
        
        stats_layout.addStretch()
        
        self.eta_label = QLabel("ETA: --")
        self.eta_label.setObjectName("status-text")
        stats_layout.addWidget(self.eta_label)
        
        progress_layout.addLayout(stats_layout)
        
        # Status badge
        self.status_badge = QLabel("")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setVisible(False)
        progress_layout.addWidget(self.status_badge)
        
        self.progress_frame.setVisible(False)
        center_layout.addWidget(self.progress_frame)

        # Feature Cards Panel
        self.feature_cards = FeatureCardsPanel()
        self.feature_cards.featureRunRequested.connect(self._on_feature_run_requested)
        self.feature_cards.featureCancelRequested.connect(self._on_feature_cancel_requested)
        self.feature_cards.featureEnabledChanged.connect(self._on_feature_enabled_changed)
        center_layout.addWidget(self.feature_cards)

        # Add default feature cards
        for feature_id, title, desc, icon in ALL_FEATURES:
            self.feature_cards.add_card(feature_id, title, desc, icon)

        # Reports Panel (initially hidden)
        self.reports_panel = ReportsPanel()
        self.reports_panel.setVisible(False)
        self.reports_panel.generateRequested.connect(self._on_reports_generate)
        center_layout.addWidget(self.reports_panel)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        self.start_btn = QPushButton("Start Ingestion")
        self.start_btn.setObjectName("success")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.setEnabled(False)
        self.start_btn.setToolTip("Start copying and verifying files (Ctrl+Enter)")
        self.start_btn.clicked.connect(self._on_start)
        button_layout.addWidget(self.start_btn, stretch=1)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setToolTip("Cancel the current ingestion")
        self.cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_btn)
        
        center_layout.addLayout(button_layout)
        
        # Next Steps Panel (initially hidden)
        self.next_steps_panel = NextStepsPanel()
        self.next_steps_panel.stepActionClicked.connect(self._on_next_step_action)
        self.next_steps_panel.dismissed.connect(self._on_next_steps_dismissed)
        center_layout.addWidget(self.next_steps_panel)
        
        center_layout.addStretch()
        
        h_splitter.addWidget(center_panel)
        
        # === RIGHT PANEL: Workflow Status + History ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Workflow status panel
        self.workflow_status = WorkflowStatusPanel()
        right_layout.addWidget(self.workflow_status, stretch=1)
        
        # History panel (moved to bottom of right panel)
        self.history_panel = HistoryPanel()
        self.history_panel.setMaximumHeight(250)
        self.history_panel.itemSelected.connect(self._on_history_selected)
        self.history_panel.itemDropped.connect(self._on_history_drop)
        right_layout.addWidget(self.history_panel)
        
        h_splitter.addWidget(right_panel)
        
        # Set splitter sizes (left, center, right)
        h_splitter.setSizes([240, 600, 300])
        h_splitter.setStretchFactor(0, 0)
        h_splitter.setStretchFactor(1, 1)
        h_splitter.setStretchFactor(2, 0)
        
        main_layout.addWidget(h_splitter, stretch=1)
    
    def _on_workflow_step_clicked(self, step_id: str):
        """Handle workflow step click."""
        # Could navigate to different views in the future
        pass

    def _on_step_cancel_requested(self, step_id: str):
        """Handle step cancel request."""
        if step_id in self._running_features:
            self._cancelled_features.add(step_id)
            if self.current_worker and self.current_worker.isRunning():
                self.current_worker.stop()
            self._update_footer_status(f"Cancelled: {step_id}")

    def _update_workflow_step(self):
        """Update current workflow step based on state."""
        if self.current_worker and self.current_worker.isRunning():
            self.workflow_steps.set_step_state("copy", StepState.RUNNING)
            self.workflow_status.set_status("Ingesting", "Copying and verifying media files")
        elif self.next_steps_panel.is_visible():
            self.workflow_steps.set_step_state("copy", StepState.COMPLETE)
            self.workflow_steps.set_step_state("verify", StepState.COMPLETE)
            self.workflow_status.set_status("Complete", "Ingestion finished successfully")
        elif self.dest_paths and self.source_path:
            self.workflow_status.set_status("Ready to Ingest", "All set to start copying")
        elif self.source_path:
            self.workflow_status.set_status("Select Destinations", "Choose where to copy the media")
        else:
            self.workflow_status.set_status("Select Source", "Choose media to ingest")
    
    def _on_source_dropped(self, paths: List[Path]):
        """Handle source drop."""
        if paths:
            self.source_path = paths[0]
            self.total_files, self.total_size_bytes = self.source_zone.get_total_stats()
            self._update_workflow_step()
            self._update_start_button()
            self._update_footer_stats()
            self._update_footer_status(f"Source selected: {self.source_path.name}")
    
    def _on_source_changed(self):
        """Handle source selection change."""
        paths = self.source_zone.dropped_paths
        if paths:
            self.source_path = paths[0]
            self.total_files, self.total_size_bytes = self.source_zone.get_total_stats()
        else:
            self.source_path = None
            self.total_files = 0
            self.total_size_bytes = 0
        
        self._update_workflow_step()
        self._update_start_button()
        self._update_footer_stats()
    
    def _on_destinations_dropped(self, paths: List[Path]):
        """Handle destinations drop."""
        self.dest_paths = paths
        self._update_workflow_step()
        self._update_start_button()
        self._update_footer_stats()
        self._update_footer_status(f"{len(paths)} destination(s) selected")
    
    def _on_destinations_changed(self):
        """Handle destinations selection change."""
        self.dest_paths = self.dest_zone.dropped_paths
        self._update_workflow_step()
        self._update_start_button()
        self._update_footer_stats()
    
    def _validate_source(self, path: Path) -> tuple:
        """Validate source path."""
        if not path.exists():
            return (False, "Path does not exist")
        
        if not path.is_dir() and not path.is_file():
            return (False, "Not a valid file or folder")
        
        # Check readability
        try:
            if path.is_dir():
                next(path.iterdir(), None)
            else:
                with open(path, 'rb') as f:
                    f.read(1)
        except PermissionError:
            return (False, "Permission denied - cannot read")
        except Exception as e:
            return (False, f"Cannot read: {e}")
        
        # Calculate size
        try:
            if path.is_dir():
                total_size = 0
                file_count = 0
                for f in path.rglob('*'):
                    if f.is_file():
                        try:
                            total_size += f.stat().st_size
                            file_count += 1
                            if file_count > 100000:
                                return (True, f"Valid (>{100000} files)")
                        except (OSError, PermissionError):
                            continue
            else:
                total_size = path.stat().st_size
            size_gb = total_size / (1024**3)
            return (True, f"Valid ({size_gb:.2f} GB)")
        except Exception:
            return (True, "Valid")
    
    def _validate_destinations(self, paths) -> tuple:
        """Validate destination paths."""
        if isinstance(paths, Path):
            paths = [paths]
        
        errors = []
        warnings_list = []
        
        for path in paths:
            if not path.exists():
                errors.append(f"{path.name}: does not exist")
                continue
            
            if not path.is_dir():
                errors.append(f"{path.name}: not a folder")
                continue
            
            # Check if same as source
            if self.source_path and path.resolve() == self.source_path.resolve():
                errors.append(f"{path.name}: same as source")
                continue
            
            # Check writability
            try:
                test_file = path / ".ingesta_write_test"
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                errors.append(f"{path.name}: not writable")
                continue
            except Exception as e:
                errors.append(f"{path.name}: {e}")
                continue
            
            # Check space
            try:
                usage = shutil.disk_usage(path)
                free_gb = usage.free / (1024**3)
                
                if self.source_path:
                    try:
                        if self.source_path.is_dir():
                            source_size = sum(f.stat().st_size for f in self.source_path.rglob('*') if f.is_file())
                        else:
                            source_size = self.source_path.stat().st_size
                        source_gb = source_size / (1024**3)
                        
                        if usage.free < source_size:
                            errors.append(f"{path.name}: not enough space ({free_gb:.1f} GB free, need {source_gb:.1f} GB)")
                        elif usage.free < source_size * 1.2:
                            warnings_list.append(f"{path.name}: low space ({free_gb:.1f} GB free)")
                    except:
                        pass
            except:
                pass
        
        if errors:
            return (False, "; ".join(errors[:2]))
        elif warnings_list:
            return (True, "⚠️ " + "; ".join(warnings_list[:2]))
        else:
            return (True, f"{len(paths)} valid destination(s)")
    
    def _update_start_button(self):
        """Update start button state."""
        can_start = self.source_path is not None and len(self.dest_paths) > 0
        self.start_btn.setEnabled(can_start)
    
    def _on_start(self):
        """Start ingestion - show checksum selection dialog first."""
        if not self.source_path or not self.dest_paths:
            return

        # Show checksum selection dialog (mandatory)
        selected_algo = ChecksumSelectionDialog.get_algorithm(
            parent=self,
            default=self.checksum_algorithm
        )

        if selected_algo is None:
            # User cancelled - don't start ingestion
            self._update_footer_status("Ingestion cancelled - no verification method selected")
            return

        # Store selected algorithm
        self.checksum_algorithm = selected_algo

        # Create history item
        self.current_history_item = HistoryItem(
            source=self.source_path,
            destinations=self.dest_paths.copy(),
            status="running",
            file_count=self.total_files,
            total_size_bytes=self.total_size_bytes
        )
        self.history_panel.add_item(self.current_history_item)

        # Update UI
        self.start_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.progress_frame.setVisible(True)
        self.status_badge.setVisible(False)
        self.next_steps_panel.hide_panel()

        # Update workflow step
        self._update_workflow_step()
        self._update_footer_status(f"Ingesting with {self.checksum_algorithm.upper()} verification...")

        # Start worker with selected checksum algorithm and event bus
        self.current_worker = IngestionWorker(
            self.source_path,
            self.dest_paths,
            checksum_algorithm=self.checksum_algorithm,
            event_bus=self._event_bus,
            step_index_map=self._step_index_map,
            total_steps=self._total_steps
        )
        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.completed.connect(self._on_completed)
        self.current_worker.error.connect(self._on_error)
        self.current_worker.start()
    
    def _on_cancel(self):
        """Cancel ingestion."""
        if self.current_worker:
            self.current_worker.stop()
            self.current_worker = None
            
            if self.current_history_item:
                self.history_panel.update_item_status(self.current_history_item.id, "failed")
            
            self.progress_label.setText("Cancelled")
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Cancelled")
            
            self.start_btn.setVisible(True)
            self.cancel_btn.setVisible(False)
            
            self._update_workflow_step()
            self._update_footer_status("Ingestion cancelled")

    def _on_feature_run_requested(self, feature_id: str):
        """Handle feature run request from feature cards."""
        if feature_id in self._running_features:
            return
        self._running_features.add(feature_id)
        self._cancelled_features.discard(feature_id)

        # Handle transcription specially with real implementation
        if feature_id == "transcribe":
            self._start_transcription_worker()
            return

        # Create and start generic worker for other features
        worker = FeatureWorker(
            feature_id=feature_id,
            event_bus=self._event_bus,
            step_index_map=self._step_index_map,
            total_steps=self._total_steps
        )
        worker.completed.connect(lambda fid: self._on_feature_completed(fid))
        worker.error.connect(lambda msg: self._on_feature_error(feature_id, msg))
        worker.start()

        self._update_footer_status(f"Running: {feature_id}")

    def _start_transcription_worker(self):
        """Start the real transcription worker."""
        # Determine media path
        media_path = None
        if self.source_path and self.source_path.exists():
            media_path = self.source_path
        elif self.dest_paths and len(self.dest_paths) > 0:
            media_path = self.dest_paths[0]
        else:
            # Prompt user to select media directory
            from PySide6.QtWidgets import QFileDialog
            path = QFileDialog.getExistingDirectory(
                self, "Select Media Directory for Transcription",
                str(Path.home()),
                QFileDialog.Option.ShowDirsOnly
            )
            if path:
                media_path = Path(path)
            else:
                self._running_features.discard("transcribe")
                self._update_footer_status("Transcription cancelled - no media directory selected")
                return

        # Create and start transcription worker
        worker = TranscriptionWorker(
            media_path=media_path,
            event_bus=self._event_bus,
            step_index_map=self._step_index_map,
            total_steps=self._total_steps,
            whisper_model="base"
        )

        # Connect signals
        worker.progress.connect(self._on_transcription_progress)
        worker.clip_completed.connect(self._on_transcription_clip_completed)
        worker.completed.connect(self._on_transcription_completed)
        worker.error.connect(self._on_transcription_error)

        self._current_transcription_worker = worker
        worker.start()
        self._update_footer_status(f"Starting transcription on: {media_path}")

    def _on_transcription_progress(self, percent: float, current_item: str, items_processed: int, items_total: int):
        """Handle transcription progress."""
        if hasattr(self, 'feature_cards'):
            card = self.feature_cards.get_card("transcribe")
            if card:
                card.set_progress(percent, current_item, items_processed, items_total)

    def _on_transcription_clip_completed(self, clip_name: str, result):
        """Handle completion of a single clip transcription."""
        # Could update UI to show transcription results per clip
        self._update_footer_status(f"Transcribed: {clip_name}")

    def _on_transcription_completed(self, results):
        """Handle transcription workflow completion."""
        self._running_features.discard("transcribe")
        self._current_transcription_worker = None
        transcribed_count = len(results)
        self._update_footer_status(f"✓ Transcription complete: {transcribed_count} clips processed")

        # Show results in a dialog or panel
        if results:
            QMessageBox.information(
                self,
                "Transcription Complete",
                f"Successfully transcribed {transcribed_count} clips.\n\n"
                f"Transcriptions are included in reports when 'Transcribe audio' is enabled."
            )

    def _on_transcription_error(self, message: str):
        """Handle transcription error."""
        self._running_features.discard("transcribe")
        self._current_transcription_worker = None
        self._update_footer_status(f"✗ Transcription failed: {message}")

        QMessageBox.critical(
            self,
            "Transcription Failed",
            f"Failed to transcribe media:\n\n{message}"
        )

    def _on_feature_cancel_requested(self, feature_id: str):
        """Handle feature cancel request."""
        self._cancelled_features.add(feature_id)
        self._running_features.discard(feature_id)

        # Cancel specific workers
        if feature_id == "transcribe" and self._current_transcription_worker:
            self._current_transcription_worker.stop()
            self._current_transcription_worker = None
        elif feature_id == "reports" and self._current_reports_worker:
            self._current_reports_worker.stop()
            self._current_reports_worker = None

        self._update_footer_status(f"Cancelled: {feature_id}")

    def _on_feature_enabled_changed(self, feature_id: str, enabled: bool):
        """Handle feature enable/disable change."""
        self._update_footer_status(f"{feature_id}: {'enabled' if enabled else 'disabled'}")

    def _on_feature_completed(self, feature_id: str):
        """Handle feature completion."""
        self._running_features.discard(feature_id)
        self._update_footer_status(f"Completed: {feature_id}")

    def _on_feature_error(self, feature_id: str, message: str):
        """Handle feature error."""
        self._running_features.discard(feature_id)
        self._update_footer_status(f"Error in {feature_id}: {message}")

    def _on_reports_generate(self):
        """Handle reports generation request with real report generation."""
        config = self.reports_panel.get_config()

        # Determine media path - use source path if available, otherwise ask user
        media_path = None
        if self.source_path and self.source_path.exists():
            media_path = self.source_path
        elif self.dest_paths and len(self.dest_paths) > 0:
            # Use first destination as media path
            media_path = self.dest_paths[0]
        else:
            # Prompt user to select media directory
            from PySide6.QtWidgets import QFileDialog
            path = QFileDialog.getExistingDirectory(
                self, "Select Media Directory",
                str(Path.home()),
                QFileDialog.Option.ShowDirsOnly
            )
            if path:
                media_path = Path(path)
            else:
                self._update_footer_status("Report generation cancelled - no media directory selected")
                return

        # Clear previous artifacts
        self.reports_panel.clear_artifacts()

        # Create and start worker
        worker = ReportsWorker(
            config=config,
            media_path=media_path,
            event_bus=self._event_bus,
            step_index_map=self._step_index_map,
            total_steps=self._total_steps
        )

        # Connect signals
        worker.progress.connect(self._on_reports_progress)
        worker.completed.connect(self._on_reports_completed)
        worker.error.connect(self._on_reports_error)

        # Store reference for potential cancellation
        self._current_reports_worker = worker

        worker.start()
        self.reports_panel.set_generating(True, "Starting report generation...")
        self._update_footer_status(f"Generating reports from: {media_path}")

    def _on_reports_progress(self, percent: float, status: str):
        """Handle report generation progress updates."""
        self.reports_panel.set_progress(percent, status)

    def _on_reports_completed(self, artifacts):
        """Handle reports completion - populate artifact list and enable open actions."""
        self.reports_panel.set_generating(False)

        # Add artifacts to the panel
        for artifact in artifacts:
            self.reports_panel.add_artifact(
                name=artifact["name"],
                path=artifact["path"],
                artifact_type=artifact["type"],
                size_bytes=artifact.get("size_bytes", 0)
            )

        # Show success message
        artifact_count = len(artifacts)
        self._update_footer_status(f"✓ Reports generated successfully: {artifact_count} artifacts created")

        # Clean up worker reference
        self._current_reports_worker = None

    def _on_reports_error(self, message: str):
        """Handle reports error."""
        self.reports_panel.set_generating(False)
        self._update_footer_status(f"✗ Report generation failed: {message}")

        # Show error dialog
        QMessageBox.critical(
            self,
            "Report Generation Failed",
            f"Failed to generate reports:\n\n{message}"
        )

        # Clean up worker reference
        self._current_reports_worker = None

    def _on_progress(self, event):
        """Handle progress update."""
        from ..ingestion import IngestionStage
        
        if event.stage == IngestionStage.COPYING:
            self.progress_label.setText("Copying...")
            self.progress_bar.setProperty("phase", "copying")
            
            if event.total_source_files > 0:
                files_progress = event.current_file_index / event.total_source_files
                if event.total_bytes > 0:
                    file_progress = event.bytes_copied / event.total_bytes
                else:
                    file_progress = 0
                total_progress = ((event.current_file_index + file_progress) / event.total_source_files) * 50
                self.progress_bar.setValue(int(total_progress))
            
            if event.source_file:
                self.progress_bar.setFormat(
                    f"Copying {event.source_file.name} ({event.current_file_index + 1}/{event.total_source_files})"
                )
                self._update_footer_status(f"Copying: {event.source_file.name}")
            
            if event.current_speed_mb_s:
                self.speed_label.setText(f"Speed: {event.current_speed_mb_s:.1f} MB/s")
            
            if event.eta_seconds:
                eta_mins = int(event.eta_seconds / 60)
                eta_secs = int(event.eta_seconds % 60)
                self.eta_label.setText(f"ETA: {eta_mins}:{eta_secs:02d}")
        
        elif event.stage == IngestionStage.VERIFYING:
            self.progress_label.setText("Verifying...")
            self.progress_bar.setProperty("phase", "verifying")
            
            if event.total_source_files > 0:
                progress = 50 + (event.current_file_index / event.total_source_files) * 50
                self.progress_bar.setValue(int(progress))
            
            if event.source_file:
                self.progress_bar.setFormat(f"Verifying {event.source_file.name}")
                self._update_footer_status(f"Verifying: {event.source_file.name}")
        
        elif event.stage == IngestionStage.COMPLETE:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Complete")
    
    def _on_completed(self, completion):
        """Handle completion - show next steps panel."""
        self.current_worker = None
        
        # Update history
        if self.current_history_item:
            status = "success" if completion.safe_to_format else "failed"
            self.history_panel.update_item_status(self.current_history_item.id, status)
        
        # Update UI
        self.start_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self.progress_label.setText("Complete")
        
        # Show status badge
        self.status_badge.setVisible(True)
        if completion.safe_to_format:
            self.status_badge.setText("✓ SAFE TO FORMAT")
            self.status_badge.setStyleSheet(SAFE_BADGE_STYLE)
        else:
            failed = completion.failed_operations
            if failed > 0:
                self.status_badge.setText(f"✗ DO NOT FORMAT - {failed} failed")
            else:
                self.status_badge.setText("⚠ DO NOT FORMAT - Not verified")
            self.status_badge.setStyleSheet(FAIL_BADGE_STYLE)
        
        # Show next steps panel
        self.next_steps_panel.show_panel(self.source_path, self.dest_paths)
        
        # Update workflow step
        self._update_workflow_step()
        self._update_footer_status("Ingestion complete - Next steps available")
        
        # Reset for next (but keep showing completion state)
        # Don't clear immediately - let user see the completion state
    
    def _on_next_step_action(self, step_id: str):
        """Handle next step action."""
        if step_id == "verify":
            self._update_footer_status("Opening destinations for verification...")
            # Could open file manager to destinations
        elif step_id == "report":
            self._on_report_action()
        elif step_id == "format":
            reply = QMessageBox.warning(
                self,
                "Format Media",
                "⚠️ WARNING: This will erase all data on the source media.\n\n"
                "Have you verified that all files were copied correctly to ALL destinations?\n\n"
                "This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._update_footer_status("Formatting media... (not implemented)")
        else:
            QMessageBox.information(
                self,
                "Coming Soon",
                f"The '{step_id}' feature will be available in a future update."
            )
    
    def _on_next_steps_dismissed(self):
        """Handle next steps panel dismissal."""
        # Reset the form for next ingestion
        self.source_path = None
        self.dest_paths = []
        self.checksum_algorithm = "xxhash64"  # Reset to default
        self.source_zone.clear()
        self.dest_zone.clear()
        self.progress_frame.setVisible(False)
        self.status_badge.setVisible(False)
        self.workflow_steps.reset_progress()
        self._update_workflow_step()
        self._update_start_button()
        self._update_footer_stats()
        self._update_footer_status("Ready for next ingestion")
    
    def _on_error(self, error_msg: str):
        """Handle error."""
        self.current_worker = None
        
        if self.current_history_item:
            self.history_panel.update_item_status(self.current_history_item.id, "failed")
        
        self.start_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        
        self.status_badge.setVisible(True)
        self.status_badge.setText(f"✗ ERROR: {error_msg}")
        self.status_badge.setStyleSheet(WARNING_BADGE_STYLE)
        
        self._update_workflow_step()
        self._update_footer_status(f"Error: {error_msg}")
        
        QMessageBox.critical(self, "Ingestion Error", f"An error occurred:\n{error_msg}")
    
    def _on_history_selected(self, item: HistoryItem):
        """Handle history item selection."""
        # Load into current UI
        self.source_path = item.source
        self.dest_paths = item.destinations.copy()
        
        self.source_zone.set_paths([self.source_path])
        self.dest_zone.set_paths(self.dest_paths)
        
        self.total_files = item.file_count
        self.total_size_bytes = item.total_size_bytes
        
        self._update_workflow_step()
        self._update_start_button()
        self._update_footer_stats()
        self._update_footer_status(f"Loaded from history: {item.source.name}")
    
    def _on_history_drop(self, paths: List[Path]):
        """Handle drop on history panel for quick-create."""
        if len(paths) == 1:
            self.source_path = paths[0]
            self.source_zone.set_paths([self.source_path])
            self._update_workflow_step()
            self._update_start_button()
            self._update_footer_stats()
            
            QMessageBox.information(
                self, "Source Selected",
                f"Set source to: {self.source_path.name}\n\nNow drop destinations in the main area."
            )
        elif len(paths) >= 2:
            self.source_path = paths[0]
            self.dest_paths = paths[1:]
            
            self.source_zone.set_paths([self.source_path])
            self.dest_zone.set_paths(self.dest_paths)
            
            self._update_workflow_step()
            self._update_start_button()
            self._update_footer_stats()
    
    def _on_sync_action(self):
        """Handle sync action from Tools menu."""
        from .sync_dialog import SyncSourceDialog
        
        sync_source = SyncSourceDialog.get_sync_source(self)
        
        if sync_source:
            self._update_footer_status(f"Sync source selected: {sync_source}")
            QMessageBox.information(
                self,
                "Sync Source Selected",
                f"Sync source set to: {sync_source.upper()}\n\n"
                f"This selection will be used for the next sync operation."
            )
        else:
            self._update_footer_status("Sync cancelled")
    
    def _on_report_action(self):
        """Handle report action from Tools menu."""
        self._update_footer_status("Opening reports panel...")
        # Toggle reports panel visibility
        is_visible = self.reports_panel.isVisible()
        self.reports_panel.setVisible(not is_visible)
        if not is_visible:
            self._update_footer_status("Reports panel opened")
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.current_worker and self.current_worker.isRunning():
            reply = QMessageBox.question(
                self, "Confirm Exit",
                "Ingestion is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.current_worker.stop()

        # Stop any running report workers
        if self._current_reports_worker and self._current_reports_worker.isRunning():
            self._current_reports_worker.stop()
            self._current_reports_worker.wait(1000)

        # Stop any running transcription workers
        if self._current_transcription_worker and self._current_transcription_worker.isRunning():
            self._current_transcription_worker.stop()
            self._current_transcription_worker.wait(1000)

        event.accept()
