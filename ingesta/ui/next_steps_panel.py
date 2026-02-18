"""Next recommended steps panel - shown after ingestion completion."""

from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal


@dataclass
class NextStep:
    """Represents a recommended next step."""
    id: str
    title: str
    description: str
    icon: str
    action_text: str
    enabled: bool = True


class NextStepCard(QFrame):
    """Individual next step card."""
    
    actionClicked = Signal(str)  # Emits step id
    
    def __init__(self, step: NextStep, parent=None):
        super().__init__(parent)
        self.step = step
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the card UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            NextStepCard {
                background-color: #16213e;
                border: 1px solid #2d3748;
                border-radius: 10px;
                padding: 16px;
            }
            NextStepCard:hover {
                border-color: #3b82f6;
                background-color: #1e293b;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header row with icon and title
        header = QHBoxLayout()
        
        icon_label = QLabel(self.step.icon)
        icon_label.setStyleSheet("font-size: 24px;")
        header.addWidget(icon_label)
        
        title = QLabel(self.step.title)
        title.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #fff;
        """)
        header.addWidget(title, stretch=1)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel(self.step.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            font-size: 12px;
            color: #aaa;
            line-height: 1.4;
        """)
        layout.addWidget(desc)
        
        # Action button
        self.action_btn = QPushButton(self.step.action_text)
        self.action_btn.setEnabled(self.step.enabled)
        if self.step.enabled:
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3b82f6;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #2563eb;
                }
            """)
        else:
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #374151;
                    color: #6b7280;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 12px;
                }
            """)
        self.action_btn.clicked.connect(lambda: self.actionClicked.emit(self.step.id))
        layout.addWidget(self.action_btn)


class NextStepsPanel(QWidget):
    """Panel showing recommended next steps after ingestion."""
    
    stepActionClicked = Signal(str)  # Emits step id
    dismissed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps: List[NextStep] = []
        self._is_visible = False
        self._setup_ui()
        self.hide()
    
    def _setup_ui(self):
        """Setup the panel UI."""
        self.setStyleSheet("""
            NextStepsPanel {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("Next Recommended Steps")
        title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #fff;
        """)
        header.addWidget(title)
        
        header.addStretch()
        
        # Dismiss button
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setFixedSize(28, 28)
        dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666;
                border: none;
                border-radius: 14px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #374151;
                color: #fff;
            }
        """)
        dismiss_btn.clicked.connect(self._on_dismiss)
        header.addWidget(dismiss_btn)
        
        layout.addLayout(header)
        
        # Success message
        self.success_label = QLabel("✓ Ingestion Complete - Media is safely backed up")
        self.success_label.setStyleSheet("""
            font-size: 13px;
            color: #4ade80;
            padding: 12px;
            background-color: #166534;
            border-radius: 8px;
        """)
        layout.addWidget(self.success_label)
        
        # Scroll area for steps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        
        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(12)
        
        scroll.setWidget(self.steps_container)
        layout.addWidget(scroll)
        
        # Initialize default steps
        self._init_default_steps()
    
    def _init_default_steps(self):
        """Initialize the default set of next steps."""
        default_steps = [
            NextStep(
                id="verify",
                title="Verify Backups",
                description="Double-check that all files were copied correctly to all destinations before formatting the source.",
                icon="🔍",
                action_text="Open Destinations",
                enabled=True
            ),
            NextStep(
                id="report",
                title="Generate Report",
                description="Create a detailed report of all ingested media including metadata, checksums, and technical specs.",
                icon="📊",
                action_text="Generate Report",
                enabled=True
            ),
            NextStep(
                id="transcribe",
                title="Transcribe Audio",
                description="Generate transcripts from audio files for easier searching and documentation.",
                icon="📝",
                action_text="Start Transcription",
                enabled=False  # Placeholder - not yet implemented
            ),
            NextStep(
                id="format",
                title="Format Source Media",
                description="Safely format the source card/drive after confirming all backups are verified. ⚠️ Destructive action.",
                icon="🗑️",
                action_text="Format Media",
                enabled=True
            ),
            NextStep(
                id="editor",
                title="Send to Editor",
                description="Import the ingested media directly into your editing software with organized bins.",
                icon="🎬",
                action_text="Export to Editor",
                enabled=False  # Placeholder
            ),
        ]
        
        self.set_steps(default_steps)
    
    def set_steps(self, steps: List[NextStep]):
        """Set the list of next steps to display."""
        self._steps = steps
        self._refresh_steps()
    
    def _refresh_steps(self):
        """Refresh the steps display."""
        # Clear existing
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Add step cards
        for step in self._steps:
            card = NextStepCard(step)
            card.actionClicked.connect(self.stepActionClicked.emit)
            self.steps_layout.addWidget(card)
        
        self.steps_layout.addStretch()
    
    def show_panel(self, source_path: Optional[Path] = None, 
                   destinations: Optional[List[Path]] = None):
        """Show the next steps panel."""
        # Update success message with details
        if source_path:
            source_name = source_path.name
            self.success_label.setText(f"✓ Ingestion Complete - {source_name} safely backed up")
        else:
            self.success_label.setText("✓ Ingestion Complete - Media is safely backed up")
        
        self.show()
        self._is_visible = True
    
    def hide_panel(self):
        """Hide the next steps panel."""
        self.hide()
        self._is_visible = False
    
    def _on_dismiss(self):
        """Handle dismiss button click."""
        self.hide_panel()
        self.dismissed.emit()
    
    def is_visible(self) -> bool:
        """Check if panel is currently visible."""
        return self._is_visible
