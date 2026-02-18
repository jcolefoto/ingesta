"""Main window for ingesta PySide6 UI."""

import sys
import shutil
from pathlib import Path
from typing import List, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QProgressBar, QFrame,
    QSplitter, QMessageBox, QApplication, QMenuBar,
    QMenu, QStatusBar, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from .drop_zones import SourceDropZone, DestinationDropZone
from .history_panel import HistoryPanel, HistoryItem
from .styles import DARK_STYLESHEET, SAFE_BADGE_STYLE, FAIL_BADGE_STYLE, WARNING_BADGE_STYLE


class IngestionWorker(QThread):
    """Worker thread for running ingestion."""
    
    progress = Signal(object)  # ProgressEvent
    completed = Signal(object)  # IngestionCompletion
    error = Signal(str)
    
    def __init__(self, source: Path, destinations: List[Path]):
        super().__init__()
        self.source = source
        self.destinations = destinations
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
                destinations=self.destinations,
                checksum_algorithm="xxhash64",
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
    """Main window for ingesta desktop UI."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ingesta - Media Ingestion Tool")
        self.setMinimumSize(900, 700)
        
        self.source_path: Optional[Path] = None
        self.dest_paths: List[Path] = []
        self.current_worker: Optional[IngestionWorker] = None
        self.current_history_item: Optional[HistoryItem] = None
        self.total_files: int = 0
        self.total_size_bytes: int = 0
        
        self._setup_menu_bar()
        self._setup_ui()
        self._setup_status_bar()
        self._update_start_button()
        self._setup_shortcuts()
    
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
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_status_bar(self):
        """Setup status bar with file info."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # File count label
        self.status_files_label = QLabel("Files: 0")
        self.status_bar.addWidget(self.status_files_label)
        
        # Size label
        self.status_size_label = QLabel("Size: 0 GB")
        self.status_bar.addWidget(self.status_size_label)
        
        # Status message
        self.status_msg_label = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.status_msg_label)
    
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
        
        self.source_zone.clear()
        self.dest_zone.clear()
        self.source_badge.setText("No source selected")
        self._update_destination_badges()
        self._update_start_button()
        self._update_status_bar()
    
    def _update_status_bar(self):
        """Update status bar labels."""
        self.status_files_label.setText(f"Files: {self.total_files}")
        size_gb = self.total_size_bytes / (1024**3)
        self.status_size_label.setText(f"Size: {size_gb:.2f} GB")
    
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
        """Setup the main UI."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout with splitter
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - main content
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(16)
        
        # Header
        header = QLabel("Ingesta")
        header.setObjectName("title")
        left_layout.addWidget(header)
        
        subtitle = QLabel("Media Ingestion & Verification")
        subtitle.setStyleSheet("color: #888; margin-bottom: 10px;")
        left_layout.addWidget(subtitle)
        
        # Source section
        source_label = QLabel("SOURCE")
        source_label.setObjectName("section-title")
        left_layout.addWidget(source_label)
        
        self.source_zone = SourceDropZone()
        self.source_zone.filesDropped.connect(self._on_source_dropped)
        self.source_zone.set_validation_callback(self._validate_source)
        left_layout.addWidget(self.source_zone)
        
        # Source badge
        self.source_badge = QLabel("No source selected")
        self.source_badge.setObjectName("badge-info")
        self.source_badge.setStyleSheet("QLabel { background-color: #2d3a5a; color: #60a5fa; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }")
        left_layout.addWidget(self.source_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Destination section
        dest_label = QLabel("DESTINATIONS")
        dest_label.setObjectName("section-title")
        left_layout.addWidget(dest_label)
        
        self.dest_zone = DestinationDropZone()
        self.dest_zone.filesDropped.connect(self._on_destinations_dropped)
        self.dest_zone.set_validation_callback(self._validate_destinations)
        left_layout.addWidget(self.dest_zone)
        
        # Destination badges
        self.dest_badges_layout = QHBoxLayout()
        self.dest_badges_layout.setSpacing(8)
        left_layout.addLayout(self.dest_badges_layout)
        
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
        left_layout.addWidget(self.progress_frame)
        
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
        
        left_layout.addLayout(button_layout)
        
        left_layout.addStretch()
        
        # Right panel - history
        self.history_panel = HistoryPanel()
        self.history_panel.itemSelected.connect(self._on_history_selected)
        self.history_panel.itemDropped.connect(self._on_history_drop)
        
        # Add to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(self.history_panel)
        splitter.setSizes([650, 250])
        splitter.setStretchFactor(0, 1)
        
        main_layout.addWidget(splitter)
    
    def _on_source_dropped(self, paths: List[Path]):
        """Handle source drop."""
        if paths:
            self.source_path = paths[0]
            self.source_badge.setText(f"📁 {self.source_path.name}")
            
            # Calculate file count and size
            try:
                if self.source_path.is_dir():
                    files = [f for f in self.source_path.rglob('*') if f.is_file()]
                    self.total_files = len(files)
                    self.total_size_bytes = sum(f.stat().st_size for f in files)
                else:
                    self.total_files = 1
                    self.total_size_bytes = self.source_path.stat().st_size
            except Exception:
                self.total_files = 0
                self.total_size_bytes = 0
            
            self._update_status_bar()
            self._update_start_button()
    
    def _on_destinations_dropped(self, paths: List[Path]):
        """Handle destinations drop."""
        self.dest_paths = paths
        self._update_destination_badges()
        self._update_start_button()
    
    def _update_destination_badges(self):
        """Update destination badges display."""
        # Clear existing
        while self.dest_badges_layout.count():
            item = self.dest_badges_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add badges
        if not self.dest_paths:
            badge = QLabel("No destinations")
            badge.setStyleSheet("QLabel { background-color: #2d3a5a; color: #60a5fa; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }")
            self.dest_badges_layout.addWidget(badge)
        else:
            for path in self.dest_paths:
                badge = QLabel(f"💾 {path.name}")
                badge.setStyleSheet("QLabel { background-color: #2d5a3d; color: #4ade80; padding: 6px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; }")
                badge.setToolTip(str(path))
                self.dest_badges_layout.addWidget(badge)
            
            self.dest_badges_layout.addStretch()
    
    def _validate_source(self, path: Path) -> tuple:
        """Validate source path."""
        if not path.exists():
            return (False, "Path does not exist")
        
        if not path.is_dir() and not path.is_file():
            return (False, "Not a valid file or folder")
        
        # Check readability
        try:
            if path.is_dir():
                # Try to list directory
                next(path.iterdir(), None)
            else:
                # Try to read first byte
                with open(path, 'rb') as f:
                    f.read(1)
        except PermissionError:
            return (False, "Permission denied - cannot read")
        except Exception as e:
            return (False, f"Cannot read: {e}")
        
        # Calculate size
        try:
            if path.is_dir():
                total_size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            else:
                total_size = path.stat().st_size
            size_gb = total_size / (1024**3)
            return (True, f"Valid ({size_gb:.2f} GB)")
        except:
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
                
                # Calculate source size if available
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
        """Start ingestion."""
        if not self.source_path or not self.dest_paths:
            return
        
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
        
        # Start worker
        self.current_worker = IngestionWorker(self.source_path, self.dest_paths)
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
    
    def _on_progress(self, event):
        """Handle progress update."""
        from ..ingestion import IngestionStage
        
        if event.stage == IngestionStage.COPYING:
            self.progress_label.setText("Copying...")
            self.progress_bar.setProperty("phase", "copying")
            
            if event.total_source_files > 0:
                # Calculate overall progress
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
                # Verification is 50-100%
                progress = 50 + (event.current_file_index / event.total_source_files) * 50
                self.progress_bar.setValue(int(progress))
            
            if event.source_file:
                self.progress_bar.setFormat(f"Verifying {event.source_file.name}")
        
        elif event.stage == IngestionStage.COMPLETE:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Complete")
    
    def _on_completed(self, completion):
        """Handle completion."""
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
        
        # Reset for next
        self.source_path = None
        self.dest_paths = []
        self.source_zone.clear()
        self.dest_zone.clear()
        self.source_badge.setText("No source selected")
        self._update_destination_badges()
        self._update_start_button()
    
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
        
        QMessageBox.critical(self, "Ingestion Error", f"An error occurred:\n{error_msg}")
    
    def _on_history_selected(self, item: HistoryItem):
        """Handle history item selection."""
        # Load into current UI
        self.source_path = item.source
        self.dest_paths = item.destinations.copy()
        
        self.source_zone.set_paths([self.source_path])
        self.dest_zone.set_paths(self.dest_paths)
        
        self.source_badge.setText(f"📁 {self.source_path.name}")
        self._update_destination_badges()
        self._update_start_button()
    
    def _on_history_drop(self, paths: List[Path]):
        """Handle drop on history panel for quick-create."""
        # Auto-detect source vs destinations based on number
        if len(paths) == 1:
            # Single item - assume source, ask for destinations
            self.source_path = paths[0]
            self.source_zone.set_paths([self.source_path])
            self.source_badge.setText(f"📁 {self.source_path.name}")
            self._update_start_button()
            
            QMessageBox.information(
                self, "Source Selected",
                f"Set source to: {self.source_path.name}\n\nNow drop destinations in the main area."
            )
        elif len(paths) >= 2:
            # Multiple items - first is source, rest are destinations
            self.source_path = paths[0]
            self.dest_paths = paths[1:]
            
            self.source_zone.set_paths([self.source_path])
            self.dest_zone.set_paths(self.dest_paths)
            
            self.source_badge.setText(f"📁 {self.source_path.name}")
            self._update_destination_badges()
            self._update_start_button()
    
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
