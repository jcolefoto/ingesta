"""Main window for ingesta PySide6 UI - Three panel layout.

Layout:
- Left: Workflow steps sidebar
- Center: Active module (ingestion form, progress, next steps)
- Right: Workflow status + history panel
- Footer: Status line
"""

import sys
import shutil
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

from .drop_zones import SourceDropZone, DestinationDropZone
from .history_panel import HistoryPanel, HistoryItem
from .workflow_steps import WorkflowStepsPanel, WorkflowStep
from .workflow_status_panel import WorkflowStatusPanel
from .next_steps_panel import NextStepsPanel
from .checksum_dialog import ChecksumSelectionDialog
from .styles import DARK_STYLESHEET, SAFE_BADGE_STYLE, FAIL_BADGE_STYLE, WARNING_BADGE_STYLE


class IngestionWorker(QThread):
    """Worker thread for running ingestion."""

    progress = Signal(object)  # ProgressEvent
    completed = Signal(object)  # IngestionCompletion
    error = Signal(str)

    def __init__(self, source: Path, destinations: List[Path], checksum_algorithm: str = "xxhash64"):
        super().__init__()
        self.source = source
        self.destinations = destinations
        self.checksum_algorithm = checksum_algorithm
        self._is_running = True

    def run(self):
        """Run the ingestion."""
        try:
            from ..ingestion import ingest_media

            def progress_callback(event):
                if self._is_running:
                    self.progress.emit(event)

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
    
    def stop(self):
        """Request stop (cooperative)."""
        self._is_running = False
        self.wait(1000)


class IngestaMainWindow(QMainWindow):
    """Main window for ingesta desktop UI with three-panel layout."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ingesta - Media Ingestion Tool")
        self.setMinimumSize(1200, 800)
        
        self.source_path: Optional[Path] = None
        self.dest_paths: List[Path] = []
        self.current_worker: Optional[IngestionWorker] = None
        self.current_history_item: Optional[HistoryItem] = None
        self.total_files: int = 0
        self.total_size_bytes: int = 0
        self.checksum_algorithm: str = "xxhash64"  # Default checksum algorithm

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._setup_shortcuts()
        self._update_start_button()
        self._update_workflow_step()
    
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
        
        # === LEFT PANEL: Workflow Steps ===
        self.workflow_steps = WorkflowStepsPanel()
        self.workflow_steps.stepClicked.connect(self._on_workflow_step_clicked)
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
    
    def _on_workflow_step_clicked(self, step: WorkflowStep):
        """Handle workflow step click."""
        # Could navigate to different views in the future
        pass
    
    def _update_workflow_step(self):
        """Update current workflow step based on state."""
        if self.current_worker and self.current_worker.isRunning():
            self.workflow_steps.set_current_step(WorkflowStep.INGEST)
            self.workflow_status.set_status("Ingesting", "Copying and verifying media files")
        elif self.next_steps_panel.is_visible():
            self.workflow_steps.set_current_step(WorkflowStep.COMPLETE)
            self.workflow_steps.mark_step_complete(WorkflowStep.INGEST)
            self.workflow_status.set_status("Complete", "Ingestion finished successfully")
        elif self.dest_paths and self.source_path:
            self.workflow_steps.set_current_step(WorkflowStep.INGEST)
            self.workflow_steps.mark_step_complete(WorkflowStep.SOURCE)
            self.workflow_steps.mark_step_complete(WorkflowStep.DESTINATIONS)
            self.workflow_status.set_status("Ready to Ingest", "All set to start copying")
        elif self.source_path:
            self.workflow_steps.set_current_step(WorkflowStep.DESTINATIONS)
            self.workflow_steps.mark_step_complete(WorkflowStep.SOURCE)
            self.workflow_status.set_status("Select Destinations", "Choose where to copy the media")
        else:
            self.workflow_steps.set_current_step(WorkflowStep.SOURCE)
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

        # Start worker with selected checksum algorithm
        self.current_worker = IngestionWorker(
            self.source_path,
            self.dest_paths,
            checksum_algorithm=self.checksum_algorithm
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
        self._update_footer_status("Report generation...")
        QMessageBox.information(
            self,
            "Generate Report",
            "Report generation will be available in a future update.\n\n"
            "Use the CLI: ingesta report -m ./media -o ./reports"
        )
    
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
        
        event.accept()
