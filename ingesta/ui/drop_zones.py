"""Drop zone widgets for drag-and-drop file handling."""

from pathlib import Path
from typing import List, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QApplication
)
from PySide6.QtCore import Qt, Signal, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent


class DropZone(QWidget):
    """A widget that accepts file/folder drops from Finder."""
    
    filesDropped = Signal(list)  # Emits list of Path objects
    
    def __init__(self, title: str, subtitle: str, accept_multiple: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.accept_multiple = accept_multiple
        self.dropped_paths: List[Path] = []
        self.is_drag_active = False
        self.validation_callback: Optional[Callable[[Path], tuple]] = None
        
        self._setup_ui()
        self._update_appearance()
    
    def _setup_ui(self):
        """Setup the UI layout."""
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setProperty("active", False)
        self.setProperty("valid", None)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)
        
        # Icon label
        self.icon_label = QLabel("📁")
        self.icon_label.setStyleSheet("font-size: 32px;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Subtitle
        self.subtitle_label = QLabel(self.subtitle)
        self.subtitle_label.setStyleSheet("font-size: 11px; color: #888;")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_label)
        
        # Browse button
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setObjectName("secondary")
        self.browse_btn.setFixedWidth(100)
        self.browse_btn.clicked.connect(self._on_browse)
        layout.addWidget(self.browse_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Files display area
        self.files_widget = QWidget()
        self.files_layout = QVBoxLayout(self.files_widget)
        self.files_layout.setSpacing(4)
        self.files_layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(self.files_widget)
        
        self.setLayout(layout)
    
    def _on_browse(self):
        """Open file dialog to select files/folders."""
        if self.accept_multiple:
            # For multiple destinations, use directory selection multiple times
            paths = []
            while True:
                path = QFileDialog.getExistingDirectory(
                    self, f"Select Destination {len(paths) + 1}",
                    options=QFileDialog.Option.ShowDirsOnly
                )
                if not path:
                    break
                paths.append(Path(path))
                # Ask if they want to add more
                from PySide6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, "Add More?",
                    f"Added {len(paths)} destination(s). Add another?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    break
            if paths:
                self.set_paths(paths)
                self.filesDropped.emit(paths)
        else:
            # Single source - can be file or folder
            path = QFileDialog.getExistingDirectory(
                self, "Select Source",
                options=QFileDialog.Option.ShowDirsOnly
            )
            if path:
                p = Path(path)
                self.set_paths([p])
                self.filesDropped.emit([p])
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            self.is_drag_active = True
            self.setProperty("active", True)
            self._update_appearance()
            event.acceptProposedAction()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave."""
        self.is_drag_active = False
        self.setProperty("active", False)
        self._update_appearance()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
        self.is_drag_active = False
        self.setProperty("active", False)
        
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            paths = []
            for url in mime_data.urls():
                if url.isLocalFile():
                    paths.append(Path(url.toLocalFile()))
            
            if paths:
                if not self.accept_multiple:
                    # Only take first for single selection
                    paths = [paths[0]]
                self.set_paths(paths)
                self.filesDropped.emit(paths)
            
            event.acceptProposedAction()
        self._update_appearance()
    
    def set_paths(self, paths: List[Path]):
        """Set the dropped paths and update display."""
        self.dropped_paths = paths
        self._update_files_display()
        
        # Run validation if callback set
        if self.validation_callback and paths:
            result = self.validation_callback(paths[0] if len(paths) == 1 else paths)
            self.set_validation_state(result[0], result[1] if len(result) > 1 else "")
        else:
            self.set_validation_state(True, "")
    
    def clear(self):
        """Clear all paths."""
        self.dropped_paths = []
        self._update_files_display()
        self.set_validation_state(None, "")
    
    def set_validation_callback(self, callback: Callable):
        """Set a callback for validation."""
        self.validation_callback = callback
    
    def set_validation_state(self, valid: Optional[bool], message: str = ""):
        """Set validation state (True=valid, False=invalid, None=neutral)."""
        if valid is True:
            self.setProperty("valid", True)
            self.subtitle_label.setText(message or "Valid")
            self.subtitle_label.setStyleSheet("font-size: 11px; color: #4ade80;")
        elif valid is False:
            self.setProperty("valid", False)
            self.subtitle_label.setText(message or "Invalid")
            self.subtitle_label.setStyleSheet("font-size: 11px; color: #f87171;")
        else:
            self.setProperty("valid", None)
            self.subtitle_label.setText(self.subtitle)
            self.subtitle_label.setStyleSheet("font-size: 11px; color: #888;")
        self._update_appearance()
    
    def _update_files_display(self):
        """Update the files display widget."""
        # Clear existing
        while self.files_layout.count():
            item = self.files_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add path labels
        for path in self.dropped_paths:
            path_label = QLabel(f"📄 {path.name}")
            path_label.setObjectName("file-path")
            path_label.setToolTip(str(path))
            self.files_layout.addWidget(path_label)
        
        self.files_widget.setVisible(bool(self.dropped_paths))
    
    def _update_appearance(self):
        """Update visual appearance based on state."""
        self.style().unpolish(self)
        self.style().polish(self)


class SourceDropZone(DropZone):
    """Specialized drop zone for source selection."""
    
    def __init__(self, parent=None):
        super().__init__(
            title="Drop Source Here",
            subtitle="Drag card/drive from Finder or click Browse",
            accept_multiple=False,
            parent=parent
        )
        self.browse_btn.setToolTip("Select source folder or file (Ctrl+O)")
    
    def _on_browse(self):
        """Override to allow file or folder selection."""
        from PySide6.QtWidgets import QMessageBox
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Select Source")
        msg.setText("What would you like to select?")
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | 
            QMessageBox.StandardButton.No | 
            QMessageBox.StandardButton.Cancel
        )
        msg.button(QMessageBox.StandardButton.Yes).setText("Folder")
        msg.button(QMessageBox.StandardButton.No).setText("File")
        msg.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
        
        reply = msg.exec()
        
        if reply == QMessageBox.StandardButton.Yes:
            # Select folder
            path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
            if path:
                p = Path(path)
                self.set_paths([p])
                self.filesDropped.emit([p])
        elif reply == QMessageBox.StandardButton.No:
            # Select file
            path, _ = QFileDialog.getOpenFileName(self, "Select Source File")
            if path:
                p = Path(path)
                self.set_paths([p])
                self.filesDropped.emit([p])


class DestinationDropZone(DropZone):
    """Specialized drop zone for destination selection."""
    
    def __init__(self, parent=None):
        super().__init__(
            title="Drop Destinations Here",
            subtitle="Drag one or more drives/folders from Finder",
            accept_multiple=True,
            parent=parent
        )
        self.browse_btn.setText("Add Destinations...")
        self.browse_btn.setToolTip("Select destination folders (Ctrl+D)")
