"""Workflow steps sidebar for ingesta UI."""

from enum import Enum
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal


class WorkflowStep(Enum):
    """Workflow step identifiers."""
    SOURCE = 0
    DESTINATIONS = 1
    INGEST = 2
    COMPLETE = 3


class StepItem(QFrame):
    """Individual workflow step item."""
    
    def __init__(self, step: WorkflowStep, title: str, description: str, parent=None):
        super().__init__(parent)
        self.step = step
        self.title = title
        self.description = description
        self._is_active = False
        self._is_complete = False
        
        self._setup_ui()
        self._update_style()
    
    def _setup_ui(self):
        """Setup the step item UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Step number indicator
        self.number_label = QLabel(str(self.step.value + 1))
        self.number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.number_label.setFixedSize(32, 32)
        layout.addWidget(self.number_label)
        
        # Text content
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("step-title")
        text_layout.addWidget(self.title_label)
        
        self.desc_label = QLabel(self.description)
        self.desc_label.setObjectName("step-desc")
        text_layout.addWidget(self.desc_label)
        
        layout.addLayout(text_layout, stretch=1)
        layout.addStretch()
    
    def set_active(self, active: bool):
        """Set whether this step is currently active."""
        self._is_active = active
        self._update_style()
    
    def set_complete(self, complete: bool):
        """Set whether this step is complete."""
        self._is_complete = complete
        self._update_style()
    
    def _update_style(self):
        """Update visual style based on state."""
        if self._is_active:
            # Active step - highlighted
            self.setStyleSheet("""
                StepItem {
                    background-color: #1e3a5f;
                    border-left: 3px solid #3b82f6;
                }
                QLabel#step-title {
                    color: #fff;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLabel#step-desc {
                    color: #93c5fd;
                    font-size: 11px;
                }
            """)
            self.number_label.setStyleSheet("""
                background-color: #3b82f6;
                color: #fff;
                border-radius: 16px;
                font-weight: bold;
                font-size: 13px;
            """)
        elif self._is_complete:
            # Complete step - green accent
            self.setStyleSheet("""
                StepItem {
                    background-color: transparent;
                    border-left: 3px solid #22c55e;
                }
                QLabel#step-title {
                    color: #86efac;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLabel#step-desc {
                    color: #4ade80;
                    font-size: 11px;
                }
            """)
            self.number_label.setText("✓")
            self.number_label.setStyleSheet("""
                background-color: #22c55e;
                color: #fff;
                border-radius: 16px;
                font-weight: bold;
                font-size: 14px;
            """)
        else:
            # Inactive step - muted
            self.setStyleSheet("""
                StepItem {
                    background-color: transparent;
                    border-left: 3px solid transparent;
                }
                StepItem:hover {
                    background-color: #16213e;
                }
                QLabel#step-title {
                    color: #888;
                    font-size: 13px;
                    font-weight: bold;
                }
                QLabel#step-desc {
                    color: #666;
                    font-size: 11px;
                }
            """)
            self.number_label.setStyleSheet("""
                background-color: #2d3748;
                color: #888;
                border-radius: 16px;
                font-weight: bold;
                font-size: 13px;
            """)


class WorkflowStepsPanel(QWidget):
    """Left sidebar showing workflow steps."""
    
    stepClicked = Signal(WorkflowStep)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_step = WorkflowStep.SOURCE
        self._completed_steps: set = set()
        self._step_items: dict = {}
        
        self._setup_ui()
        self.set_current_step(WorkflowStep.SOURCE)
    
    def _setup_ui(self):
        """Setup the workflow steps panel."""
        self.setObjectName("workflow-steps-panel")
        self.setMinimumWidth(220)
        self.setMaximumWidth(280)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QLabel("WORKFLOW")
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
        
        # Step items
        steps = [
            (WorkflowStep.SOURCE, "Select Source", "Choose media to ingest"),
            (WorkflowStep.DESTINATIONS, "Select Destinations", "Choose where to copy"),
            (WorkflowStep.INGEST, "Ingest Media", "Copy and verify files"),
            (WorkflowStep.COMPLETE, "Complete", "Review and next steps"),
        ]
        
        for step, title, desc in steps:
            item = StepItem(step, title, desc)
            item.mousePressEvent = lambda e, s=step: self._on_step_clicked(s)
            self._step_items[step] = item
            layout.addWidget(item)
        
        layout.addStretch()
        
        # App info at bottom
        info_frame = QFrame()
        info_frame.setStyleSheet("background-color: #0f172a; border-top: 1px solid #1e293b;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 12, 16, 12)
        
        version_label = QLabel("Ingesta v1.0")
        version_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(version_label)
        
        layout.addWidget(info_frame)
    
    def _on_step_clicked(self, step: WorkflowStep):
        """Handle step click."""
        self.stepClicked.emit(step)
    
    def set_current_step(self, step: WorkflowStep):
        """Set the current active step."""
        self._current_step = step
        for s, item in self._step_items.items():
            item.set_active(s == step)
            item.set_complete(s in self._completed_steps)
    
    def mark_step_complete(self, step: WorkflowStep, complete: bool = True):
        """Mark a step as complete or incomplete."""
        if complete:
            self._completed_steps.add(step)
        else:
            self._completed_steps.discard(step)
        
        # Update the item
        if step in self._step_items:
            self._step_items[step].set_complete(complete)
            # Re-apply current step styling
            if step == self._current_step:
                self._step_items[step].set_active(True)
    
    def reset_progress(self):
        """Reset all progress markers."""
        self._completed_steps.clear()
        self.set_current_step(WorkflowStep.SOURCE)
    
    def get_current_step(self) -> WorkflowStep:
        """Get the current active step."""
        return self._current_step
