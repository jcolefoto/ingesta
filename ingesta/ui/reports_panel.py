"""
Reports module UI for ingesta.

Provides UI for choosing output location, report name preview,
auto-generate toggle, Generate now button, and post-completion actions.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QCheckBox, QFileDialog,
    QListWidget, QListWidgetItem, QScrollArea, QMenu,
    QMessageBox, QComboBox, QGroupBox, QProgressBar,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QDesktopServices


@dataclass
class ReportArtifact:
    """Represents a generated report artifact."""
    name: str
    path: Path
    artifact_type: str  # pdf, csv, json, etc.
    size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    output_dir: Path = field(default_factory=lambda: Path("./reports"))
    report_name: str = ""
    auto_generate: bool = False
    generate_pdf: bool = True
    generate_csv: bool = True
    include_thumbnails: bool = True
    group_by_folder: bool = False
    transcribe: bool = False
    analyze_frames: bool = False


class ReportsPanel(QWidget):
    """
    Reports module UI panel.
    
    Features:
    - Choose output location
    - Report name preview
    - Auto-generate toggle
    - Generate now button
    - After completion: Open report folder/file, artifact list
    """
    
    generateRequested = Signal()  # User clicked Generate
    openArtifactRequested = Signal(Path)  # User wants to open an artifact
    configChanged = Signal()  # Configuration changed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ReportConfig()
        self.artifacts: List[ReportArtifact] = []
        self._is_generating = False
        self._setup_ui()
        self._update_preview()
    
    def _setup_ui(self):
        """Setup the reports panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Header
        header = QLabel("📊 Reports")
        header.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #fff;
        """)
        layout.addWidget(header)
        
        desc = QLabel("Generate professional PDF and CSV reports with metadata and thumbnails")
        desc.setStyleSheet("font-size: 12px; color: #888;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Output location section
        output_group = QGroupBox("Output Location")
        output_group.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-weight: bold;
                border: 1px solid #2d3748;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        output_layout = QVBoxLayout(output_group)
        output_layout.setSpacing(8)
        
        # Output path row
        path_row = QHBoxLayout()
        
        self.output_path = QLineEdit()
        self.output_path.setText(str(self.config.output_dir))
        self.output_path.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px 12px;
                color: #eee;
                font-family: 'SF Mono', Monaco, monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.output_path.textChanged.connect(self._on_output_changed)
        path_row.addWidget(self.output_path, stretch=1)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        browse_btn.clicked.connect(self._on_browse)
        path_row.addWidget(browse_btn)
        
        output_layout.addLayout(path_row)
        
        # Report name preview
        name_row = QHBoxLayout()
        
        name_label = QLabel("Report Name:")
        name_label.setStyleSheet("font-size: 12px; color: #888;")
        name_row.addWidget(name_label)
        
        self.report_name_input = QLineEdit()
        self.report_name_input.setPlaceholderText("Auto-generated from project")
        self.report_name_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px 12px;
                color: #eee;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.report_name_input.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self.report_name_input, stretch=1)
        
        output_layout.addLayout(name_row)
        
        # Preview label
        self.preview_label = QLabel("Preview: report_2024-01-15.pdf")
        self.preview_label.setStyleSheet("font-size: 11px; color: #666; font-style: italic;")
        output_layout.addWidget(self.preview_label)
        
        layout.addWidget(output_group)
        
        # Options section
        options_group = QGroupBox("Report Options")
        options_group.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-weight: bold;
                border: 1px solid #2d3748;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(8)
        
        # Format checkboxes
        self.pdf_check = QCheckBox("Generate PDF report")
        self.pdf_check.setChecked(self.config.generate_pdf)
        self.pdf_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.pdf_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.pdf_check)
        
        self.csv_check = QCheckBox("Generate CSV report")
        self.csv_check.setChecked(self.config.generate_csv)
        self.csv_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.csv_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.csv_check)
        
        self.thumbnails_check = QCheckBox("Include thumbnails")
        self.thumbnails_check.setChecked(self.config.include_thumbnails)
        self.thumbnails_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.thumbnails_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.thumbnails_check)
        
        self.group_by_folder_check = QCheckBox("Group by folder (production bins)")
        self.group_by_folder_check.setChecked(self.config.group_by_folder)
        self.group_by_folder_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.group_by_folder_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.group_by_folder_check)
        
        # Advanced options
        advanced_header = QLabel("Advanced Analysis:")
        advanced_header.setStyleSheet("font-size: 11px; color: #888; padding-top: 8px;")
        options_layout.addWidget(advanced_header)
        
        self.transcribe_check = QCheckBox("Transcribe audio (local AI)")
        self.transcribe_check.setChecked(self.config.transcribe)
        self.transcribe_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.transcribe_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.transcribe_check)
        
        self.analyze_frames_check = QCheckBox("Analyze frames")
        self.analyze_frames_check.setChecked(self.config.analyze_frames)
        self.analyze_frames_check.setStyleSheet("color: #ccc; font-size: 12px;")
        self.analyze_frames_check.stateChanged.connect(self._on_option_changed)
        options_layout.addWidget(self.analyze_frames_check)
        
        layout.addWidget(options_group)
        
        # Auto-generate toggle
        auto_row = QHBoxLayout()
        
        self.auto_generate_check = QCheckBox("Auto-generate after ingestion")
        self.auto_generate_check.setChecked(self.config.auto_generate)
        self.auto_generate_check.setStyleSheet("""
            QCheckBox {
                color: #ccc;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #374151;
                background-color: #1e293b;
            }
            QCheckBox::indicator:checked {
                background-color: #3b82f6;
                border-color: #3b82f6;
            }
        """)
        self.auto_generate_check.stateChanged.connect(self._on_auto_generate_changed)
        auto_row.addWidget(self.auto_generate_check)
        
        auto_row.addStretch()
        layout.addLayout(auto_row)
        
        # Generate button
        self.generate_btn = QPushButton("Generate Reports Now")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #6b7280;
            }
        """)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_btn)
        
        # Progress bar (hidden by default)
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #1e293b;
                height: 20px;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #3b82f6;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #888;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(self.progress_frame)
        
        # Completion section (hidden by default)
        self.completion_frame = QFrame()
        self.completion_frame.setVisible(False)
        self.completion_frame.setStyleSheet("""
            QFrame {
                background-color: #16653422;
                border: 1px solid #22c55e;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        completion_layout = QVBoxLayout(self.completion_frame)
        completion_layout.setSpacing(12)
        
        # Success header
        success_header = QLabel("✓ Reports Generated Successfully")
        success_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #4ade80;")
        completion_layout.addWidget(success_header)
        
        # Action buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        
        self.open_folder_btn = QPushButton("📁 Open Folder")
        self.open_folder_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        actions_row.addWidget(self.open_folder_btn)
        
        self.open_pdf_btn = QPushButton("📄 Open PDF")
        self.open_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.open_pdf_btn.clicked.connect(self._on_open_pdf)
        actions_row.addWidget(self.open_pdf_btn)
        
        actions_row.addStretch()
        completion_layout.addLayout(actions_row)
        
        # Artifacts list
        artifacts_label = QLabel("Generated Artifacts:")
        artifacts_label.setStyleSheet("font-size: 12px; color: #aaa; padding-top: 8px;")
        completion_layout.addWidget(artifacts_label)
        
        self.artifacts_list = QListWidget()
        self.artifacts_list.setStyleSheet("""
            QListWidget {
                background-color: #0f172a;
                border: 1px solid #2d3748;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                color: #ccc;
                font-size: 12px;
                font-family: 'SF Mono', Monaco, monospace;
            }
            QListWidget::item:hover {
                background-color: #1e293b;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
            }
        """)
        self.artifacts_list.setMaximumHeight(150)
        self.artifacts_list.itemDoubleClicked.connect(self._on_artifact_double_clicked)
        self.artifacts_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.artifacts_list.customContextMenuRequested.connect(self._show_artifact_context_menu)
        completion_layout.addWidget(self.artifacts_list)
        
        layout.addWidget(self.completion_frame)
        
        layout.addStretch()
    
    def _on_output_changed(self, text: str):
        """Handle output path change."""
        self.config.output_dir = Path(text)
        self._update_preview()
        self.configChanged.emit()
    
    def _on_name_changed(self, text: str):
        """Handle report name change."""
        self.config.report_name = text
        self._update_preview()
        self.configChanged.emit()
    
    def _on_browse(self):
        """Open folder browser dialog."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            str(self.config.output_dir),
            QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.config.output_dir = Path(path)
            self.output_path.setText(path)
            self._update_preview()
            self.configChanged.emit()
    
    def _on_option_changed(self):
        """Handle option checkbox changes."""
        self.config.generate_pdf = self.pdf_check.isChecked()
        self.config.generate_csv = self.csv_check.isChecked()
        self.config.include_thumbnails = self.thumbnails_check.isChecked()
        self.config.group_by_folder = self.group_by_folder_check.isChecked()
        self.config.transcribe = self.transcribe_check.isChecked()
        self.config.analyze_frames = self.analyze_frames_check.isChecked()
        self.configChanged.emit()
    
    def _on_auto_generate_changed(self, state):
        """Handle auto-generate toggle change."""
        self.config.auto_generate = bool(state)
        self.configChanged.emit()
    
    def _on_generate_clicked(self):
        """Handle generate button click."""
        if not self._is_generating:
            self.generateRequested.emit()
    
    def _on_open_folder(self):
        """Open the output folder."""
        if self.config.output_dir.exists():
            QDesktopServices.openUrl(
                Qt.QUrl.fromLocalFile(str(self.config.output_dir))
            )
    
    def _on_open_pdf(self):
        """Open the PDF report."""
        pdf_artifacts = [a for a in self.artifacts if a.artifact_type == "pdf"]
        if pdf_artifacts:
            QDesktopServices.openUrl(
                Qt.QUrl.fromLocalFile(str(pdf_artifacts[0].path))
            )
    
    def _on_artifact_double_clicked(self, item: QListWidgetItem):
        """Handle artifact double-click."""
        artifact_name = item.text().split("  ")[0]  # Extract name from display text
        for artifact in self.artifacts:
            if artifact.name == artifact_name:
                self.openArtifactRequested.emit(artifact.path)
                QDesktopServices.openUrl(Qt.QUrl.fromLocalFile(str(artifact.path)))
                break
    
    def _show_artifact_context_menu(self, position):
        """Show context menu for artifact."""
        item = self.artifacts_list.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self._on_artifact_double_clicked(item))
        menu.addAction(open_action)
        
        show_in_folder = QAction("Show in Folder", self)
        show_in_folder.triggered.connect(self._on_open_folder)
        menu.addAction(show_in_folder)
        
        menu.exec(self.artifacts_list.mapToGlobal(position))
    
    def _update_preview(self):
        """Update the report name preview."""
        if self.config.report_name:
            base_name = self.config.report_name
        else:
            base_name = f"report_{datetime.now().strftime('%Y-%m-%d')}"
        
        parts = []
        if self.config.generate_pdf:
            parts.append(f"{base_name}.pdf")
        if self.config.generate_csv:
            parts.append(f"{base_name}.csv")
        
        if parts:
            self.preview_label.setText(f"Preview: {', '.join(parts)}")
        else:
            self.preview_label.setText("Preview: (select at least one format)")
    
    def set_generating(self, generating: bool, status: str = ""):
        """Set the generating state."""
        self._is_generating = generating
        self.generate_btn.setEnabled(not generating)
        self.generate_btn.setText("Generating..." if generating else "Generate Reports Now")
        self.progress_frame.setVisible(generating)
        
        if status:
            self.status_label.setText(status)
        
        if not generating:
            self.completion_frame.setVisible(False)
    
    def set_progress(self, percent: float, status: str = ""):
        """Update generation progress."""
        self.progress_bar.setValue(int(percent))
        if status:
            self.status_label.setText(status)
    
    def add_artifact(self, name: str, path: Path, artifact_type: str, size_bytes: int = 0):
        """Add a generated artifact."""
        artifact = ReportArtifact(
            name=name,
            path=path,
            artifact_type=artifact_type,
            size_bytes=size_bytes
        )
        self.artifacts.append(artifact)
        self._update_artifacts_list()
    
    def clear_artifacts(self):
        """Clear all artifacts."""
        self.artifacts.clear()
        self.artifacts_list.clear()
    
    def _update_artifacts_list(self):
        """Update the artifacts list widget."""
        self.artifacts_list.clear()
        
        for artifact in self.artifacts:
            size_str = self._format_size(artifact.size_bytes)
            display_text = f"{artifact.name}  ({size_str})"
            
            item = QListWidgetItem(display_text)
            item.setToolTip(str(artifact.path))
            
            # Set icon based on type
            if artifact.artifact_type == "pdf":
                item.setText("📄 " + display_text)
            elif artifact.artifact_type == "csv":
                item.setText("📊 " + display_text)
            elif artifact.artifact_type == "json":
                item.setText("📋 " + display_text)
            else:
                item.setText("📄 " + display_text)
            
            self.artifacts_list.addItem(item)
        
        # Show completion frame if we have artifacts
        if self.artifacts:
            self.completion_frame.setVisible(True)
            self.progress_frame.setVisible(False)
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable string."""
        if size_bytes >= 1024**3:
            return f"{size_bytes / (1024**3):.2f} GB"
        elif size_bytes >= 1024**2:
            return f"{size_bytes / (1024**2):.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes} B"
    
    def set_config(self, config: ReportConfig):
        """Set the report configuration."""
        self.config = config
        self.output_path.setText(str(config.output_dir))
        self.report_name_input.setText(config.report_name)
        self.auto_generate_check.setChecked(config.auto_generate)
        self.pdf_check.setChecked(config.generate_pdf)
        self.csv_check.setChecked(config.generate_csv)
        self.thumbnails_check.setChecked(config.include_thumbnails)
        self.group_by_folder_check.setChecked(config.group_by_folder)
        self.transcribe_check.setChecked(config.transcribe)
        self.analyze_frames_check.setChecked(config.analyze_frames)
        self._update_preview()
    
    def get_config(self) -> ReportConfig:
        """Get the current report configuration."""
        return self.config
    
    def reset(self):
        """Reset the panel to initial state."""
        self.set_generating(False)
        self.clear_artifacts()
        self.progress_bar.setValue(0)
        self.completion_frame.setVisible(False)
        self.progress_frame.setVisible(False)
        self.generate_btn.setEnabled(True)
