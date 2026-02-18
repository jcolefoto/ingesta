"""History panel widget for ingesta UI."""

from pathlib import Path
from typing import List, Optional
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QUrl


class HistoryItem:
    """Represents a history entry."""
    
    def __init__(self, source: Path, destinations: List[Path], 
                 status: str = "pending", timestamp: Optional[datetime] = None):
        self.source = source
        self.destinations = destinations
        self.status = status  # pending, running, success, failed
        self.timestamp = timestamp or datetime.now()
        self.id = f"{self.timestamp.isoformat()}_{source.name}"
    
    @property
    def display_title(self) -> str:
        return f"{self.source.name} → {len(self.destinations)} destination(s)"
    
    @property
    def display_subtitle(self) -> str:
        return self.timestamp.strftime("%H:%M")


class HistoryPanel(QWidget):
    """Side panel showing ingestion history."""
    
    itemSelected = Signal(HistoryItem)
    itemDropped = Signal(list)  # For drop-to-create
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[HistoryItem] = []
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI."""
        self.setObjectName("history-panel")
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QLabel("History")
        header.setObjectName("panel-title")
        layout.addWidget(header)
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)
        
        # Empty state
        self.empty_label = QLabel("No history yet\n\nDrop sources here\nto quick-create")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #666; padding: 40px;")
        layout.addWidget(self.empty_label)
        
        # Clear button
        self.clear_btn = QPushButton("Clear History")
        self.clear_btn.setObjectName("secondary")
        self.clear_btn.clicked.connect(self.clear)
        layout.addWidget(self.clear_btn)
        
        self.setLayout(layout)
        self._update_empty_state()
    
    def dragEnterEvent(self, event):
        """Accept drops to create new history items."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event):
        """Handle drops for quick-create."""
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    paths.append(Path(url.toLocalFile()))
            if paths:
                self.itemDropped.emit(paths)
            event.acceptProposedAction()
    
    def add_item(self, item: HistoryItem):
        """Add a history item."""
        self.items.append(item)
        
        list_item = QListWidgetItem(item.display_title)
        list_item.setData(Qt.ItemDataRole.UserRole, item.id)
        list_item.setToolTip(f"{item.source}\n→\n" + "\n→ ".join(str(d) for d in item.destinations))
        
        # Set icon based on status
        status_icons = {
            "pending": "⏳",
            "running": "🔄",
            "success": "✅",
            "failed": "❌"
        }
        list_item.setText(f"{status_icons.get(item.status, '○')} {item.display_title}")
        
        self.list_widget.addItem(list_item)
        self._update_empty_state()
    
    def update_item_status(self, item_id: str, status: str):
        """Update the status of a history item."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == item_id:
                status_icons = {
                    "pending": "⏳",
                    "running": "🔄",
                    "success": "✅",
                    "failed": "❌"
                }
                # Find the history item to get title
                hist_item = next((h for h in self.items if h.id == item_id), None)
                if hist_item:
                    hist_item.status = status
                    item.setText(f"{status_icons.get(status, '○')} {hist_item.display_title}")
                break
    
    def _on_item_clicked(self, list_item: QListWidgetItem):
        """Handle item selection."""
        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        history_item = next((h for h in self.items if h.id == item_id), None)
        if history_item:
            self.itemSelected.emit(history_item)
    
    def _update_empty_state(self):
        """Show/hide empty state label."""
        has_items = self.list_widget.count() > 0
        self.empty_label.setVisible(not has_items)
        self.list_widget.setVisible(has_items)
    
    def clear(self):
        """Clear all history."""
        self.items.clear()
        self.list_widget.clear()
        self._update_empty_state()
