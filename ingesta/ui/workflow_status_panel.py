"""Workflow status panel showing current pipeline status."""

from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt


@dataclass
class PipelineStatus:
    """Pipeline status details for the status panel."""
    status: str = "Ready"
    detail: str = "Waiting for source selection"
    percent: float = 0.0
    items_processed: int = 0
    items_total: int = 0
    current_item: str = ""
    elapsed_seconds: float = 0.0
    state: str = "idle"


class WorkflowStatusPanel(QWidget):
    """Right panel showing workflow status and pipeline details."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = PipelineStatus()
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the workflow status panel."""
        self.setObjectName("workflow-status-panel")
        self.setMinimumWidth(260)
        self.setMaximumWidth(320)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QLabel("WORKFLOW STATUS")
        header.setObjectName("panel-header")
        header.setStyleSheet("""
            QLabel#panel-header {
                color: #666;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
                padding: 20px 16px 12px 16px;
            }
        """)
        layout.addWidget(header)
        
        # Current status card
        self.status_card = QFrame()
        self.status_card.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #2d3748;
                border-radius: 10px;
                margin: 0 12px 16px 12px;
            }
        """)
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(8)
        
        status_title = QLabel("Current Status")
        status_title.setStyleSheet("font-size: 12px; color: #888;")
        status_layout.addWidget(status_title)
        
        self.status_value = QLabel("Ready")
        self.status_value.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #60a5fa;
        """)
        status_layout.addWidget(self.status_value)
        
        self.status_detail = QLabel("Waiting for source selection")
        self.status_detail.setStyleSheet("font-size: 11px; color: #666;")
        self.status_detail.setWordWrap(True)
        status_layout.addWidget(self.status_detail)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #1e293b;
                height: 12px;
                text-align: center;
                font-size: 10px;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #3b82f6;
            }
        """)
        status_layout.addWidget(self.progress_bar)

        # Details grid
        details_layout = QVBoxLayout()
        details_layout.setSpacing(6)

        # Items row
        items_row = QHBoxLayout()
        self.items_label = QLabel("Items: 0/0")
        self.items_label.setStyleSheet("font-size: 11px; color: #888;")
        items_row.addWidget(self.items_label)
        items_row.addStretch()

        self.elapsed_label = QLabel("Elapsed: 0.0s")
        self.elapsed_label.setStyleSheet("font-size: 11px; color: #888;")
        items_row.addWidget(self.elapsed_label)
        details_layout.addLayout(items_row)

        # Current item row
        self.current_item_label = QLabel("Current: --")
        self.current_item_label.setStyleSheet("font-size: 10px; color: #666;")
        self.current_item_label.setWordWrap(True)
        details_layout.addWidget(self.current_item_label)

        status_layout.addLayout(details_layout)
        
        layout.addWidget(self.status_card)
    
    def set_status(self, status: str, detail: str = ""):
        """Update the current status display."""
        self.status_value.setText(status)
        if detail:
            self.status_detail.setText(detail)
        
        # Update color based on status
        if status.lower() in ["complete", "success", "done"]:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #4ade80;
            """)
        elif status.lower() in ["error", "failed", "cancelled"]:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #f87171;
            """)
        elif status.lower() in ["running", "active", "copying", "verifying"]:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #f59e0b;
            """)
        elif status.lower() in ["skipped", "cancelled", "canceled"]:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #94a3b8;
            """)
        else:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #60a5fa;
            """)

    def update_pipeline_status(
        self,
        status: str,
        detail: str = "",
        percent: float = 0.0,
        items_processed: int = 0,
        items_total: int = 0,
        current_item: str = "",
        elapsed_seconds: float = 0.0,
        state: str = "idle",
    ):
        """Update pipeline status details."""
        self._status.status = status
        self._status.detail = detail
        self._status.percent = percent
        self._status.items_processed = items_processed
        self._status.items_total = items_total
        self._status.current_item = current_item
        self._status.elapsed_seconds = elapsed_seconds
        self._status.state = state

        self.set_status(status, detail)
        self.progress_bar.setValue(int(percent))
        self.items_label.setText(f"Items: {items_processed}/{items_total}")
        if current_item:
            self.current_item_label.setText(f"Current: {current_item}")
        else:
            self.current_item_label.setText("Current: --")

        if elapsed_seconds < 60:
            self.elapsed_label.setText(f"Elapsed: {elapsed_seconds:.1f}s")
        else:
            mins = int(elapsed_seconds / 60)
            secs = int(elapsed_seconds % 60)
            self.elapsed_label.setText(f"Elapsed: {mins}m {secs}s")
