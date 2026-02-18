"""Enhanced drop zone widgets for drag-and-drop file handling.

Features:
- Accept multiple folders
- Repeated additions without clearing
- Duplicate prevention
- Total size and clip count display
- Truncated long filenames with tooltips
"""

from pathlib import Path
from typing import List, Optional, Callable, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QApplication, QMessageBox, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes >= 1024**4:
        return f"{size_bytes / (1024**4):.2f} TB"
    elif size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes} B"


def truncate_filename(filename: str, max_length: int = 35) -> str:
    """Truncate filename with ellipsis if too long."""
    if len(filename) <= max_length:
        return filename
    
    # Keep extension and truncate middle
    name, ext = Path(filename).stem, Path(filename).suffix
    if len(ext) > 10:  # If extension is weirdly long, just truncate end
        return filename[:max_length-3] + "..."
    
    available = max_length - len(ext) - 3  # 3 for "..."
    if available < 5:
        return filename[:max_length-3] + "..."
    
    return name[:available] + "..." + ext


def count_media_files(path: Path) -> tuple:
    """Count media files and total size in a path.
    
    Returns:
        (file_count, total_size_bytes)
    """
    media_extensions = {
        '.mov', '.mp4', '.m4v', '.mkv', '.avi', '.wmv', '.flv', '.webm',
        '.r3d', '.braw', '.arri', '.dpx', '.exr', '.tiff', '.tif', '.tga',
        '.mp3', '.wav', '.aif', '.aiff', '.m4a', '.aac', '.ogg', '.flac',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.raw', '.cr2', '.nef', '.arw'
    }
    
    file_count = 0
    total_size = 0
    
    try:
        if path.is_file():
            if path.suffix.lower() in media_extensions or not media_extensions:
                file_count = 1
                total_size = path.stat().st_size
        elif path.is_dir():
            for f in path.rglob('*'):
                if f.is_file():
                    try:
                        if f.suffix.lower() in media_extensions or not media_extensions:
                            file_count += 1
                            total_size += f.stat().st_size
                        # Limit to prevent hanging on huge directories
                        if file_count > 100000:
                            break
                    except (OSError, PermissionError):
                        continue
    except Exception:
        pass
    
    return (file_count, total_size)


class DropZone(QWidget):
    """A widget that accepts file/folder drops from Finder."""
    
    filesDropped = Signal(list)  # Emits list of Path objects
    filesChanged = Signal()  # Emitted when files are added or removed
    
    def __init__(self, title: str, subtitle: str, accept_multiple: bool = True, show_list: bool = True, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.accept_multiple = accept_multiple
        self.show_list = show_list
        self.dropped_paths: List[Path] = []
        self._path_set: Set[str] = set()  # For duplicate prevention
        self.is_drag_active = False
        self.validation_callback: Optional[Callable[[Path], tuple]] = None
        self._total_files = 0
        self._total_size = 0
        
        self._setup_ui()
        self._update_appearance()
    
    def _setup_ui(self):
        """Setup the UI layout."""
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)
        self.setProperty("active", False)
        self.setProperty("valid", None)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(12)
        
        # Header with icon and title
        header = QHBoxLayout()
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.icon_label = QLabel("📁")
        self.icon_label.setStyleSheet("font-size: 28px;")
        header.addWidget(self.icon_label)
        
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.title_label)
        
        self.subtitle_label = QLabel(self.subtitle)
        self.subtitle_label.setStyleSheet("font-size: 11px; color: #888;")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.subtitle_label)
        
        header.addLayout(header_layout)
        layout.addLayout(header)
        
        # Stats row
        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(16)
        
        self.files_count_label = QLabel("0 clips")
        self.files_count_label.setStyleSheet("font-size: 12px; color: #aaa;")
        self.stats_layout.addWidget(self.files_count_label)
        
        self.size_label = QLabel("0 GB")
        self.size_label.setStyleSheet("font-size: 12px; color: #aaa;")
        self.stats_layout.addWidget(self.size_label)
        
        self.stats_layout.addStretch()
        layout.addLayout(self.stats_layout)
        
        # Scroll area for file list
        if self.show_list:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setMaximumHeight(150)
            scroll.setStyleSheet("""
                QScrollArea {
                    background-color: transparent;
                    border: none;
                }
            """)
            
            self.files_widget = QWidget()
            self.files_layout = QVBoxLayout(self.files_widget)
            self.files_layout.setSpacing(6)
            self.files_layout.setContentsMargins(0, 0, 0, 0)
            self.files_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            
            scroll.setWidget(self.files_widget)
            layout.addWidget(scroll)
        else:
            self.files_widget = None
            self.files_layout = None
        
        # Buttons row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setObjectName("secondary")
        self.browse_btn.setFixedWidth(100)
        self.browse_btn.clicked.connect(self._on_browse)
        button_layout.addWidget(self.browse_btn)
        
        if self.accept_multiple:
            self.clear_btn = QPushButton("Clear")
            self.clear_btn.setObjectName("secondary")
            self.clear_btn.setFixedWidth(80)
            self.clear_btn.clicked.connect(self.clear)
            button_layout.addWidget(self.clear_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _on_browse(self):
        """Open file dialog to select files/folders."""
        if self.accept_multiple:
            path = QFileDialog.getExistingDirectory(
                self, f"Select Folder",
                options=QFileDialog.Option.ShowDirsOnly
            )
            if path:
                self._add_paths([Path(path)])
        else:
            # Single source - can be file or folder
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
                path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
                if path:
                    self._add_paths([Path(path)])
            elif reply == QMessageBox.StandardButton.No:
                path, _ = QFileDialog.getOpenFileName(self, "Select Source File")
                if path:
                    self._add_paths([Path(path)])
    
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
        """Handle drop with support for multiple folders."""
        self.is_drag_active = False
        self.setProperty("active", False)
        
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            paths = []
            for url in mime_data.urls():
                if url.isLocalFile():
                    paths.append(Path(url.toLocalFile()))
            
            if paths:
                self._add_paths(paths)
            
            event.acceptProposedAction()
        self._update_appearance()
    
    def _add_paths(self, paths: List[Path]):
        """Add paths to the drop zone, preventing duplicates."""
        added = []
        duplicates = []
        
        for path in paths:
            path_str = str(path.resolve())
            if path_str in self._path_set:
                duplicates.append(path.name)
                continue
            
            self._path_set.add(path_str)
            self.dropped_paths.append(path)
            added.append(path)
        
        if added:
            self._update_stats()
            self._update_files_display()
            self.filesDropped.emit(self.dropped_paths.copy())
            self.filesChanged.emit()
            
            # Run validation on first path
            if self.validation_callback and self.dropped_paths:
                result = self.validation_callback(self.dropped_paths[0])
                self.set_validation_state(result[0], result[1] if len(result) > 1 else "")
        
        # Show duplicate warning if any
        if duplicates and len(duplicates) <= 3:
            self.subtitle_label.setText(f"Skipped {len(duplicates)} duplicate(s)")
            self.subtitle_label.setStyleSheet("font-size: 11px; color: #f59e0b;")
    
    def _update_stats(self):
        """Update file count and size statistics."""
        self._total_files = 0
        self._total_size = 0
        
        for path in self.dropped_paths:
            count, size = count_media_files(path)
            self._total_files += count
            self._total_size += size
        
        # Update labels
        self.files_count_label.setText(f"{self._total_files} clips")
        self.size_label.setText(format_size(self._total_size))
    
    def _update_files_display(self):
        """Update the files display widget with truncated names and tooltips."""
        if not self.show_list or not self.files_layout:
            return
        # Clear existing
        while self.files_layout.count():
            item = self.files_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Add path labels
        for path in self.dropped_paths:
            row = QHBoxLayout()
            row.setSpacing(8)
            
            # File icon
            icon = QLabel("📄")
            icon.setStyleSheet("font-size: 12px;")
            row.addWidget(icon)
            
            # Filename (truncated with tooltip)
            display_name = truncate_filename(path.name, max_length=40)
            path_label = QLabel(display_name)
            path_label.setObjectName("file-path")
            path_label.setStyleSheet("""
                font-size: 12px;
                color: #ccc;
                font-family: 'SF Mono', Monaco, monospace;
            """)
            path_label.setToolTip(str(path))
            row.addWidget(path_label, stretch=1)
            
            # Individual file stats
            count, size = count_media_files(path)
            stats_label = QLabel(f"{count} clips, {format_size(size)}")
            stats_label.setStyleSheet("font-size: 10px; color: #666;")
            row.addWidget(stats_label)
            
            # Remove button (for multi-selection)
            if self.accept_multiple and len(self.dropped_paths) > 0:
                remove_btn = QPushButton("✕")
                remove_btn.setFixedSize(18, 18)
                remove_btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #666;
                        border: none;
                        border-radius: 9px;
                        font-size: 10px;
                        padding: 0;
                    }
                    QPushButton:hover {
                        background-color: #374151;
                        color: #f87171;
                    }
                """)
                remove_btn.clicked.connect(lambda checked, p=path: self._remove_path(p))
                row.addWidget(remove_btn)
            
            container = QWidget()
            container.setLayout(row)
            container.setStyleSheet("""
                QWidget {
                    background-color: #1e293b;
                    border-radius: 6px;
                    padding: 4px;
                }
            """)
            self.files_layout.addWidget(container)
        
        self.files_layout.addStretch()
    
    def _remove_path(self, path: Path):
        """Remove a specific path from the list."""
        path_str = str(path.resolve())
        if path_str in self._path_set:
            self._path_set.discard(path_str)
            self.dropped_paths = [p for p in self.dropped_paths if str(p.resolve()) != path_str]
            self._update_stats()
            self._update_files_display()
            self.filesChanged.emit()
    
    def get_total_stats(self) -> tuple:
        """Get total file count and size.
        
        Returns:
            (file_count, size_bytes)
        """
        return (self._total_files, self._total_size)
    
    def set_paths(self, paths: List[Path]):
        """Set the dropped paths (clears existing)."""
        self.clear()
        self._add_paths(paths)
    
    def clear(self):
        """Clear all paths."""
        self.dropped_paths.clear()
        self._path_set.clear()
        self._total_files = 0
        self._total_size = 0
        self._update_stats()
        
        # Clear display
        if self.show_list and self.files_layout:
            while self.files_layout.count():
                item = self.files_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            
            self.files_layout.addStretch()
        self.set_validation_state(None, "")
        self.filesChanged.emit()
    
    def set_validation_callback(self, callback: Callable):
        """Set a callback for validation."""
        self.validation_callback = callback
    
    def set_validation_state(self, valid: Optional[bool], message: str = ""):
        """Set validation state (True=valid, False=invalid, None=neutral)."""
        if valid is True:
            self.setProperty("valid", True)
            self.subtitle_label.setText(message or f"{len(self.dropped_paths)} item(s) valid")
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
    
    def _update_appearance(self):
        """Update visual appearance based on state."""
        self.style().unpolish(self)
        self.style().polish(self)


class SourceDropZone(DropZone):
    """Specialized drop zone for source selection."""
    
    def __init__(self, show_list: bool = False, parent=None):
        super().__init__(
            title="Drop Source Here",
            subtitle="Drag card/drive from Finder or click Browse",
            accept_multiple=False,
            show_list=show_list,
            parent=parent
        )
        self.browse_btn.setToolTip("Select source folder or file (Ctrl+O)")


class DestinationDropZone(DropZone):
    """Specialized drop zone for destination selection."""
    
    def __init__(self, parent=None):
        super().__init__(
            title="Drop Destinations Here",
            subtitle="Drag one or more drives/folders from Finder",
            accept_multiple=True,
            show_list=True,
            parent=parent
        )
        self.browse_btn.setText("Add Destination...")
        self.browse_btn.setToolTip("Select destination folders (Ctrl+D)")
