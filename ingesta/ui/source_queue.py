"""
Enhanced source queue widget for ingesta UI.

Provides editable queue with:
- Remove icon per row
- File size display
- Media type badges
- Multi-select remove
- Clear all
- Undo last removal
- Immediate count updates
"""

from pathlib import Path
from typing import List, Optional, Callable, Set, Dict
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QApplication, QMessageBox,
    QMenu, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QClipboard


# Media type definitions
MEDIA_TYPES = {
    'video': {
        'extensions': {'.mov', '.mp4', '.m4v', '.mkv', '.avi', '.wmv', '.flv', 
                       '.webm', '.r3d', '.braw', '.arri'},
        'badge': '🎬',
        'label': 'Video',
        'color': '#3b82f6'
    },
    'audio': {
        'extensions': {'.mp3', '.wav', '.aif', '.aiff', '.m4a', '.aac', '.ogg', 
                       '.flac', '.bwf'},
        'badge': '🎵',
        'label': 'Audio',
        'color': '#22c55e'
    },
    'image': {
        'extensions': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.raw', '.cr2', 
                       '.nef', '.arw', '.tiff', '.tif', '.tga', '.dpx', '.exr'},
        'badge': '🖼',
        'label': 'Image',
        'color': '#f59e0b'
    },
}


def get_media_type(path: Path) -> Dict:
    """Get media type info for a file."""
    ext = path.suffix.lower()
    for media_type, info in MEDIA_TYPES.items():
        if ext in info['extensions']:
            return {'type': media_type, **info}
    return {'type': 'other', 'badge': '📄', 'label': 'File', 'color': '#6b7280'}


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


@dataclass
class SourceItem:
    """Represents an item in the source queue."""
    path: Path
    size_bytes: int = 0
    file_count: int = 0
    media_type: str = "other"
    added_at: datetime = field(default_factory=datetime.now)
    is_selected: bool = False
    
    def __post_init__(self):
        if not self.media_type or self.media_type == "other":
            type_info = get_media_type(self.path)
            self.media_type = type_info['type']


class SourceQueueItemWidget(QFrame):
    """Widget representing a single item in the source queue."""
    
    removeRequested = Signal(Path)  # path
    selectionChanged = Signal(Path, bool)  # path, selected
    clicked = Signal(Path)  # path
    
    def __init__(self, item: SourceItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._setup_ui()
        self._update_appearance()
    
    def _setup_ui(self):
        """Setup the item widget UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("source-queue-item")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(50)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        
        # Selection checkbox area (invisible but clickable)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Media type badge
        type_info = get_media_type(self.item.path)
        self.badge_label = QLabel(type_info['badge'])
        self.badge_label.setStyleSheet(f"font-size: 16px;")
        layout.addWidget(self.badge_label)
        
        # Name and path
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        # Filename
        name = self.item.path.name
        if len(name) > 40:
            name = name[:37] + "..."
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-size: 12px; font-weight: 500; color: #fff;")
        self.name_label.setToolTip(str(self.item.path))
        text_layout.addWidget(self.name_label)
        
        # Type label and stats
        stats_text = f"{type_info['label']} • {format_size(self.item.size_bytes)}"
        if self.item.file_count > 1:
            stats_text += f" • {self.item.file_count} files"
        
        self.stats_label = QLabel(stats_text)
        self.stats_label.setStyleSheet(f"font-size: 10px; color: {type_info['color']};")
        text_layout.addWidget(self.stats_label)
        
        layout.addLayout(text_layout, stretch=1)
        
        # Remove button
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedSize(24, 24)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #374151;
                color: #f87171;
            }
        """)
        self.remove_btn.setToolTip("Remove from queue")
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self.remove_btn)
        
        # Selection indicator
        self.selection_indicator = QLabel("✓")
        self.selection_indicator.setStyleSheet("font-size: 14px; color: #3b82f6;")
        self.selection_indicator.setVisible(self.item.is_selected)
        layout.addWidget(self.selection_indicator)
    
    def _update_appearance(self):
        """Update visual appearance based on selection state."""
        if self.item.is_selected:
            bg_color = "#1e3a5f"
            border_color = "#3b82f6"
        else:
            bg_color = "#1e293b"
            border_color = "transparent"
        
        self.setStyleSheet(f"""
            QFrame#source-queue-item {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#source-queue-item:hover {{
                background-color: #2d3748;
                border-color: #4b5563;
            }}
        """)
        
        self.selection_indicator.setVisible(self.item.is_selected)
    
    def mousePressEvent(self, event):
        """Handle mouse press for selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Toggle selection with Ctrl/Cmd, otherwise single select
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.item.is_selected = not self.item.is_selected
                self.selectionChanged.emit(self.item.path, self.item.is_selected)
                self._update_appearance()
            else:
                self.clicked.emit(self.item.path)
        
        super().mousePressEvent(event)
    
    def _on_remove_clicked(self):
        """Handle remove button click."""
        self.removeRequested.emit(self.item.path)
    
    def set_selected(self, selected: bool):
        """Set the selection state."""
        self.item.is_selected = selected
        self._update_appearance()


class SourceQueueWidget(QWidget):
    """
    Enhanced source queue widget.
    
    Features:
    - Remove icon per row
    - File size display
    - Media type badges
    - Multi-select remove
    - Clear all
    - Undo last removal
    - Immediate count updates
    """
    
    itemAdded = Signal(Path)
    itemRemoved = Signal(Path)
    itemsCleared = Signal()
    selectionChanged = Signal()
    itemDoubleClicked = Signal(Path)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: Dict[str, SourceItem] = {}  # path_str -> SourceItem
        self._removed_history: deque = deque(maxlen=10)  # For undo
        self._total_size = 0
        self._total_files = 0
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        
        # Header
        header = QHBoxLayout()
        header.setSpacing(10)
        
        header_label = QLabel("📁 Source Queue")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
        header.addWidget(header_label)
        
        header.addStretch()
        
        # Stats label
        self.stats_label = QLabel("0 items, 0 GB")
        self.stats_label.setStyleSheet("font-size: 11px; color: #888;")
        header.addWidget(self.stats_label)
        
        layout.addLayout(header)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        # Clear all button
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        self.clear_btn.clicked.connect(self._on_clear_all)
        self.clear_btn.setEnabled(False)
        toolbar.addWidget(self.clear_btn)
        
        # Remove selected button
        self.remove_selected_btn = QPushButton("Remove Selected")
        self.remove_selected_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #6b7280;
            }
        """)
        self.remove_selected_btn.clicked.connect(self._on_remove_selected)
        self.remove_selected_btn.setEnabled(False)
        toolbar.addWidget(self.remove_selected_btn)
        
        # Undo button
        self.undo_btn = QPushButton("↩ Undo")
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #6b7280;
            }
        """)
        self.undo_btn.clicked.connect(self._on_undo)
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Undo last removal (Ctrl+Z)")
        toolbar.addWidget(self.undo_btn)
        
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Items scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        scroll.setMinimumHeight(200)
        scroll.setMaximumHeight(400)
        
        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(6)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(self.items_container)
        layout.addWidget(scroll)
        
        # Empty state message
        self.empty_label = QLabel("Drag files or folders here to add to queue")
        self.empty_label.setStyleSheet("font-size: 12px; color: #666; font-style: italic;")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.items_layout.addWidget(self.empty_label)
        
        self.items_layout.addStretch()
        
        # Footer with type breakdown
        self.footer_label = QLabel("")
        self.footer_label.setStyleSheet("font-size: 10px; color: #666; padding-top: 8px;")
        layout.addWidget(self.footer_label)
        
        # Setup keyboard shortcut for undo
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._on_undo()
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self._on_remove_selected()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._select_all()
        else:
            super().keyPressEvent(event)
    
    def _select_all(self):
        """Select all items."""
        for item in self._items.values():
            item.is_selected = True
        self._refresh_display()
        self._update_toolbar()
    
    def _deselect_all(self):
        """Deselect all items."""
        for item in self._items.values():
            item.is_selected = False
        self._refresh_display()
        self._update_toolbar()
        self.selectionChanged.emit()
    
    def add_item(self, path: Path, size_bytes: int = 0, file_count: int = 0) -> bool:
        """Add an item to the queue. Returns False if already exists."""
        path_str = str(path.resolve())
        if path_str in self._items:
            return False
        
        item = SourceItem(
            path=path,
            size_bytes=size_bytes,
            file_count=file_count
        )
        
        self._items[path_str] = item
        self._total_size += size_bytes
        self._total_files += file_count
        
        self._refresh_display()
        self._update_stats()
        self._update_toolbar()
        
        self.itemAdded.emit(path)
        return True

    def select_item(self, path: Path, exclusive: bool = True):
        """Select a single item, optionally clearing others."""
        if exclusive:
            for item in self._items.values():
                item.is_selected = False
        path_str = str(path.resolve())
        if path_str in self._items:
            self._items[path_str].is_selected = True
        self._refresh_display()
        self._update_toolbar()
        self.selectionChanged.emit()

    def clear_selection(self):
        """Clear all selections."""
        self._deselect_all()
    
    def remove_item(self, path: Path, save_to_history: bool = True):
        """Remove an item from the queue."""
        path_str = str(path.resolve())
        if path_str not in self._items:
            return
        
        item = self._items.pop(path_str)
        
        # Save to history for undo
        if save_to_history:
            self._removed_history.append(item)
            self.undo_btn.setEnabled(True)
        
        self._total_size -= item.size_bytes
        self._total_files -= item.file_count
        
        self._refresh_display()
        self._update_stats()
        self._update_toolbar()
        
        self.itemRemoved.emit(path)
    
    def _on_clear_all(self):
        """Clear all items."""
        if not self._items:
            return
        
        # Save all to history
        for item in self._items.values():
            self._removed_history.append(item)
        
        self._items.clear()
        self._total_size = 0
        self._total_files = 0
        
        self._refresh_display()
        self._update_stats()
        self._update_toolbar()
        self.undo_btn.setEnabled(True)
        
        self.itemsCleared.emit()
    
    def _on_remove_selected(self):
        """Remove all selected items."""
        selected_paths = [
            item.path for item in self._items.values() 
            if item.is_selected
        ]
        
        if not selected_paths:
            return
        
        for path in selected_paths:
            self.remove_item(path)
    
    def _on_undo(self):
        """Undo the last removal."""
        if not self._removed_history:
            return
        
        item = self._removed_history.pop()
        path_str = str(item.path.resolve())
        
        # Check if item was already re-added
        if path_str not in self._items:
            self._items[path_str] = item
            self._total_size += item.size_bytes
            self._total_files += item.file_count
            
            self._refresh_display()
            self._update_stats()
            self._update_toolbar()
        
        if not self._removed_history:
            self.undo_btn.setEnabled(False)
    
    def _on_item_clicked(self, path: Path):
        """Handle item click for selection."""
        # Deselect all others if not holding Ctrl
        modifiers = QApplication.keyboardModifiers()
        if not (modifiers & Qt.KeyboardModifier.ControlModifier):
            for item in self._items.values():
                item.is_selected = False
        
        # Toggle clicked item
        path_str = str(path.resolve())
        if path_str in self._items:
            self._items[path_str].is_selected = not self._items[path_str].is_selected
        
        self._refresh_display()
        self._update_toolbar()
        self.selectionChanged.emit()
    
    def _on_item_selection_changed(self, path: Path, selected: bool):
        """Handle item selection change."""
        path_str = str(path.resolve())
        if path_str in self._items:
            self._items[path_str].is_selected = selected
        self._update_toolbar()
        self.selectionChanged.emit()
    
    def _refresh_display(self):
        """Refresh the items display."""
        # Clear existing widgets
        while self.items_layout.count() > 1:  # Keep stretch at end
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget and widget != self.empty_label:
                widget.deleteLater()
        
        # Show/hide empty label
        self.empty_label.setVisible(len(self._items) == 0)
        
        # Add items
        for path_str, item in self._items.items():
            widget = SourceQueueItemWidget(item)
            widget.removeRequested.connect(self.remove_item)
            widget.selectionChanged.connect(self._on_item_selection_changed)
            widget.clicked.connect(self._on_item_clicked)
            self.items_layout.insertWidget(self.items_layout.count() - 1, widget)
    
    def _update_stats(self):
        """Update statistics display."""
        count = len(self._items)
        size_str = format_size(self._total_size)
        
        self.stats_label.setText(f"{count} items, {size_str}")
        
        # Type breakdown for footer
        type_counts = {}
        for item in self._items.values():
            type_counts[item.media_type] = type_counts.get(item.media_type, 0) + 1
        
        if type_counts:
            breakdown = []
            for media_type, count in sorted(type_counts.items()):
                type_info = MEDIA_TYPES.get(media_type, MEDIA_TYPES['video'])
                breakdown.append(f"{type_info['badge']} {count} {type_info['label']}")
            self.footer_label.setText("  •  ".join(breakdown))
        else:
            self.footer_label.setText("")
    
    def _update_toolbar(self):
        """Update toolbar button states."""
        has_items = len(self._items) > 0
        has_selection = any(item.is_selected for item in self._items.values())
        
        self.clear_btn.setEnabled(has_items)
        self.remove_selected_btn.setEnabled(has_selection)
    
    def get_items(self) -> List[Path]:
        """Get all items in the queue."""
        return [item.path for item in self._items.values()]
    
    def get_selected_items(self) -> List[Path]:
        """Get selected items."""
        return [
            item.path for item in self._items.values() 
            if item.is_selected
        ]
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        return {
            'item_count': len(self._items),
            'total_size_bytes': self._total_size,
            'total_files': self._total_files,
            'type_breakdown': self._get_type_breakdown()
        }
    
    def _get_type_breakdown(self) -> Dict[str, int]:
        """Get breakdown by media type."""
        breakdown = {}
        for item in self._items.values():
            breakdown[item.media_type] = breakdown.get(item.media_type, 0) + 1
        return breakdown
    
    def clear(self):
        """Clear all items."""
        self._on_clear_all()
    
    def set_items(self, items: List[SourceItem]):
        """Set all items at once."""
        self._items.clear()
        self._total_size = 0
        self._total_files = 0
        
        for item in items:
            path_str = str(item.path.resolve())
            self._items[path_str] = item
            self._total_size += item.size_bytes
            self._total_files += item.file_count
        
        self._refresh_display()
        self._update_stats()
        self._update_toolbar()
