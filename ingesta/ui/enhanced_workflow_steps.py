"""
Enhanced workflow steps panel with real pipeline status.

Shows percent/item count, current file, elapsed time, and statuses including Skipped.
"""

from enum import Enum, auto
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer


class StepState(Enum):
    """Step execution state."""
    PENDING = ("Pending", "#6b7280", "⏸")
    QUEUED = ("Queued", "#f59e0b", "⏳")
    RUNNING = ("Running", "#3b82f6", "▶")
    COMPLETE = ("Complete", "#22c55e", "✓")
    ERROR = ("Error", "#ef4444", "✗")
    SKIPPED = ("Skipped", "#6b7280", "⊘")
    CANCELLED = ("Cancelled", "#6b7280", "⊘")
    
    def __init__(self, label: str, color: str, icon: str):
        self.label = label
        self.color = color
        self.icon = icon


@dataclass
class StepInfo:
    """Information about a workflow step."""
    step_id: str
    name: str
    description: str
    state: StepState = StepState.PENDING
    progress: float = 0.0
    current_item: str = ""
    items_processed: int = 0
    items_total: int = 0
    elapsed_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: str = ""
    can_cancel: bool = True


class StepListItem(QFrame):
    """Individual step item in the workflow steps list."""
    
    cancelRequested = Signal(str)  # step_id
    clicked = Signal(str)  # step_id
    
    def __init__(self, step_info: StepInfo, parent=None):
        super().__init__(parent)
        self.step_info = step_info
        self._timer: Optional[QTimer] = None
        self._setup_ui()
        self._update_appearance()
    
    def _setup_ui(self):
        """Setup the step item UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("step-list-item")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header row: Icon + Name + Status badge + Cancel button
        header = QHBoxLayout()
        header.setSpacing(10)
        
        # Status icon
        self.icon_label = QLabel(self.step_info.state.icon)
        self.icon_label.setStyleSheet(f"font-size: 14px; color: {self.step_info.state.color};")
        header.addWidget(self.icon_label)
        
        # Step name
        self.name_label = QLabel(self.step_info.name)
        self.name_label.setObjectName("step-name")
        self.name_label.setStyleSheet("""
            font-size: 13px;
            font-weight: 600;
            color: #fff;
        """)
        header.addWidget(self.name_label, stretch=1)
        
        # Status badge
        self.status_badge = QLabel(self.step_info.state.label)
        self.status_badge.setStyleSheet(self._get_status_badge_style(self.step_info.state))
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setMinimumWidth(70)
        header.addWidget(self.status_badge)
        
        # Cancel button (only visible when running)
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedSize(24, 24)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #f87171;
                border: 1px solid #f87171;
                border-radius: 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f87171;
                color: #fff;
            }
        """)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        header.addWidget(self.cancel_btn)
        
        layout.addLayout(header)
        
        # Description
        self.desc_label = QLabel(self.step_info.description)
        self.desc_label.setStyleSheet("font-size: 11px; color: #888;")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        
        # Current item (when running)
        self.current_item_label = QLabel("")
        self.current_item_label.setStyleSheet("""
            font-size: 10px;
            color: #aaa;
            font-family: 'SF Mono', Monaco, monospace;
            padding: 2px 0;
        """)
        self.current_item_label.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.current_item_label.setVisible(False)
        layout.addWidget(self.current_item_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #1e293b;
                height: 6px;
                text-align: center;
                font-size: 9px;
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background-color: #3b82f6;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(12)
        
        # Count
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("font-size: 10px; color: #666;")
        stats.addWidget(self.count_label)
        
        stats.addStretch()
        
        # Elapsed time
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("font-size: 10px; color: #666;")
        stats.addWidget(self.time_label)
        
        layout.addLayout(stats)
        
        # Error message (hidden by default)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("""
            font-size: 11px;
            color: #fca5a5;
            background-color: #3a1a1a;
            padding: 6px;
            border-radius: 4px;
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
    
    def _get_status_badge_style(self, state: StepState) -> str:
        """Get the stylesheet for a status badge."""
        return f"""
            background-color: {state.color}22;
            color: {state.color};
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 10px;
            font-weight: bold;
        """
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        self.cancelRequested.emit(self.step_info.step_id)
    
    def mousePressEvent(self, event):
        """Handle mouse press."""
        self.clicked.emit(self.step_info.step_id)
    
    def update_state(self, state: StepState):
        """Update the step state."""
        old_state = self.step_info.state
        self.step_info.state = state
        
        # Update icon
        self.icon_label.setText(state.icon)
        self.icon_label.setStyleSheet(f"font-size: 14px; color: {state.color};")
        
        # Update badge
        self.status_badge.setText(state.label)
        self.status_badge.setStyleSheet(self._get_status_badge_style(state))
        
        # Handle state transitions
        if state == StepState.RUNNING:
            self.progress_bar.setVisible(True)
            self.current_item_label.setVisible(True)
            self.cancel_btn.setVisible(self.step_info.can_cancel)
            if not self._timer:
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._update_elapsed)
                self._timer.start(100)  # Update every 100ms
            if not self.step_info.started_at:
                self.step_info.started_at = datetime.now()
        elif state in [StepState.COMPLETE, StepState.ERROR, StepState.SKIPPED, StepState.CANCELLED]:
            self.cancel_btn.setVisible(False)
            if self._timer:
                self._timer.stop()
                self._timer = None
            if not self.step_info.completed_at:
                self.step_info.completed_at = datetime.now()
            if state == StepState.ERROR:
                self.error_label.setVisible(True)
        else:
            self.cancel_btn.setVisible(False)
            self.current_item_label.setVisible(False)
            if self._timer:
                self._timer.stop()
                self._timer = None
        
        self._update_appearance()
    
    def set_progress(self, percent: float, current_item: str = "",
                     items_processed: int = 0, items_total: int = 0):
        """Update progress information."""
        self.step_info.progress = max(0.0, min(100.0, percent))
        self.step_info.current_item = current_item
        self.step_info.items_processed = items_processed
        self.step_info.items_total = items_total
        
        self.progress_bar.setValue(int(self.step_info.progress))
        
        if current_item:
            self.current_item_label.setText(current_item)
        
        if items_total > 0:
            self.count_label.setText(f"{items_processed}/{items_total} items")
        else:
            self.count_label.setText("")
    
    def set_error(self, message: str):
        """Set error message."""
        self.step_info.error_message = message
        self.error_label.setText(message)
    
    def _update_elapsed(self):
        """Update elapsed time."""
        if self.step_info.started_at:
            elapsed = (datetime.now() - self.step_info.started_at).total_seconds()
            self.step_info.elapsed_seconds = elapsed
            self._update_time_display()
    
    def _update_time_display(self):
        """Update the time display."""
        elapsed = self.step_info.elapsed_seconds
        if elapsed < 60:
            self.time_label.setText(f"{elapsed:.1f}s")
        else:
            mins = int(elapsed / 60)
            secs = int(elapsed % 60)
            self.time_label.setText(f"{mins}m {secs}s")
    
    def _update_appearance(self):
        """Update visual appearance based on state."""
        state = self.step_info.state
        
        # Border color based on state
        if state == StepState.RUNNING:
            border_color = "#3b82f6"
            bg_color = "#1e3a5f33"
        elif state == StepState.COMPLETE:
            border_color = "#22c55e"
            bg_color = "#16653422"
        elif state == StepState.ERROR:
            border_color = "#ef4444"
            bg_color = "#7f1d1d22"
        elif state == StepState.SKIPPED:
            border_color = "#6b7280"
            bg_color = "#37415122"
        elif state == StepState.QUEUED:
            border_color = "#f59e0b"
            bg_color = "#713f1222"
        else:
            border_color = "transparent"
            bg_color = "transparent"
        
        self.setStyleSheet(f"""
            QFrame#step-list-item {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#step-list-item:hover {{
                background-color: #16213e;
            }}
        """)
    
    def reset(self):
        """Reset the step item."""
        self.step_info.state = StepState.PENDING
        self.step_info.progress = 0.0
        self.step_info.current_item = ""
        self.step_info.items_processed = 0
        self.step_info.items_total = 0
        self.step_info.elapsed_seconds = 0.0
        self.step_info.error_message = ""
        self.step_info.started_at = None
        self.step_info.completed_at = None
        
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.current_item_label.setVisible(False)
        self.current_item_label.setText("")
        self.count_label.setText("")
        self.time_label.setText("")
        self.error_label.setVisible(False)
        self.error_label.setText("")
        self.cancel_btn.setVisible(False)
        
        if self._timer:
            self._timer.stop()
            self._timer = None
        
        self.update_state(StepState.PENDING)


class EnhancedWorkflowStepsPanel(QWidget):
    """
    Enhanced workflow steps panel with real pipeline status.
    
    Shows percent/item count, current file, elapsed time, and statuses including Skipped.
    """
    
    stepClicked = Signal(str)  # step_id
    stepCancelRequested = Signal(str)  # step_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps: Dict[str, StepListItem] = {}
        self._step_order: List[str] = []
        self._overall_progress: float = 0.0
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the panel UI."""
        self.setObjectName("enhanced-workflow-steps-panel")
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QLabel("PIPELINE STEPS")
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
        
        # Overall progress
        self.overall_frame = QFrame()
        overall_layout = QVBoxLayout(self.overall_frame)
        overall_layout.setContentsMargins(16, 12, 16, 12)
        overall_layout.setSpacing(8)
        
        overall_header = QHBoxLayout()
        overall_title = QLabel("Overall Progress")
        overall_title.setStyleSheet("font-size: 12px; color: #888;")
        overall_header.addWidget(overall_title)
        
        self.overall_percent = QLabel("0%")
        self.overall_percent.setStyleSheet("font-size: 12px; font-weight: bold; color: #3b82f6;")
        overall_header.addWidget(self.overall_percent)
        overall_layout.addLayout(overall_header)
        
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(False)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #1e293b;
                height: 8px;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #3b82f6;
            }
        """)
        overall_layout.addWidget(self.overall_progress)
        
        layout.addWidget(self.overall_frame)
        
        # Scroll area for steps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        
        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(12, 8, 12, 8)
        self.steps_layout.setSpacing(8)
        self.steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll.setWidget(self.steps_container)
        layout.addWidget(scroll, stretch=1)
        
        # Stats footer
        self.stats_frame = QFrame()
        self.stats_frame.setStyleSheet("""
            background-color: #0f172a;
            border-top: 1px solid #1e293b;
        """)
        stats_layout = QVBoxLayout(self.stats_frame)
        stats_layout.setContentsMargins(16, 12, 16, 12)
        stats_layout.setSpacing(4)
        
        self.stats_label = QLabel("Ready")
        self.stats_label.setStyleSheet("font-size: 11px; color: #666;")
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(self.stats_frame)
    
    def add_step(self, step_id: str, name: str, description: str, 
                 can_cancel: bool = True) -> StepListItem:
        """Add a step to the panel."""
        step_info = StepInfo(
            step_id=step_id,
            name=name,
            description=description,
            can_cancel=can_cancel
        )
        item = StepListItem(step_info)
        item.clicked.connect(self.stepClicked.emit)
        item.cancelRequested.connect(self.stepCancelRequested.emit)
        
        self._steps[step_id] = item
        self._step_order.append(step_id)
        self.steps_layout.addWidget(item)
        
        self._update_overall_progress()
        return item
    
    def remove_step(self, step_id: str):
        """Remove a step from the panel."""
        if step_id in self._steps:
            item = self._steps.pop(step_id)
            self._step_order.remove(step_id)
            self.steps_layout.removeWidget(item)
            item.deleteLater()
            self._update_overall_progress()
    
    def set_step_state(self, step_id: str, state: StepState):
        """Set the state of a step."""
        if step_id in self._steps:
            self._steps[step_id].update_state(state)
            self._update_overall_progress()
            self._update_stats()
    
    def set_step_progress(self, step_id: str, percent: float, 
                         current_item: str = "", items_processed: int = 0,
                         items_total: int = 0):
        """Set the progress of a step."""
        if step_id in self._steps:
            self._steps[step_id].set_progress(percent, current_item, items_processed, items_total)
            self._update_overall_progress()
    
    def set_step_error(self, step_id: str, message: str):
        """Set an error on a step."""
        if step_id in self._steps:
            self._steps[step_id].set_error(message)
            self._steps[step_id].update_state(StepState.ERROR)
            self._update_stats()
    
    def skip_step(self, step_id: str):
        """Mark a step as skipped."""
        self.set_step_state(step_id, StepState.SKIPPED)
    
    def get_step(self, step_id: str) -> Optional[StepListItem]:
        """Get a step item by ID."""
        return self._steps.get(step_id)
    
    def reset_all(self):
        """Reset all steps."""
        for step in self._steps.values():
            step.reset()
        self._update_overall_progress()
        self._update_stats()
    
    def _update_overall_progress(self):
        """Update the overall progress bar."""
        if not self._steps:
            self._overall_progress = 0.0
        else:
            total_progress = 0.0
            for step in self._steps.values():
                if step.step_info.state == StepState.COMPLETE:
                    total_progress += 100.0
                elif step.step_info.state == StepState.SKIPPED:
                    total_progress += 100.0  # Skipped counts as done
                else:
                    total_progress += step.step_info.progress
            self._overall_progress = total_progress / len(self._steps)
        
        self.overall_progress.setValue(int(self._overall_progress))
        self.overall_percent.setText(f"{int(self._overall_progress)}%")
    
    def _update_stats(self):
        """Update the stats label."""
        if not self._steps:
            self.stats_label.setText("No steps")
            return
        
        total = len(self._steps)
        pending = sum(1 for s in self._steps.values() if s.step_info.state == StepState.PENDING)
        queued = sum(1 for s in self._steps.values() if s.step_info.state == StepState.QUEUED)
        running = sum(1 for s in self._steps.values() if s.step_info.state == StepState.RUNNING)
        complete = sum(1 for s in self._steps.values() if s.step_info.state == StepState.COMPLETE)
        error = sum(1 for s in self._steps.values() if s.step_info.state == StepState.ERROR)
        skipped = sum(1 for s in self._steps.values() if s.step_info.state == StepState.SKIPPED)
        
        parts = []
        if running > 0:
            parts.append(f"{running} running")
        if complete > 0:
            parts.append(f"{complete} complete")
        if error > 0:
            parts.append(f"{error} error")
        if skipped > 0:
            parts.append(f"{skipped} skipped")
        if queued > 0:
            parts.append(f"{queued} queued")
        if pending > 0:
            parts.append(f"{pending} pending")
        
        if parts:
            self.stats_label.setText(" | ".join(parts))
        else:
            self.stats_label.setText("Ready")
    
    def get_all_states(self) -> Dict[str, StepState]:
        """Get all step states."""
        return {sid: item.step_info.state for sid, item in self._steps.items()}


# Default workflow steps
DEFAULT_STEPS = [
    ("copy", "Copy", "Copy media files to destinations"),
    ("verify", "Verify", "Verify file integrity after copy"),
    ("reports", "Reports", "Generate PDF and CSV reports"),
    ("sync", "Sync", "Synchronize audio and video"),
    ("frame_analysis", "Frame Analysis", "Analyze frames for visual content"),
    ("transcription", "Transcription", "Transcribe audio using local AI"),
]
