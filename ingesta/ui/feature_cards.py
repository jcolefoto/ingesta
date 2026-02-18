"""
Feature cards module for ingesta UI.

Provides actionable feature cards with Run/Enable toggle, status pills,
progress indicators, and action buttons for Complete/Error states.
"""

from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QProgressBar, QCheckBox, QToolButton,
    QSizePolicy, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction


class FeatureStatus(Enum):
    """Feature execution status."""
    IDLE = ("Idle", "#6b7280", "#374151")
    QUEUED = ("Queued", "#f59e0b", "#713f12")
    RUNNING = ("Running", "#3b82f6", "#1e3a5f")
    COMPLETE = ("Complete", "#22c55e", "#166534")
    ERROR = ("Error", "#ef4444", "#7f1d1d")
    SKIPPED = ("Skipped", "#6b7280", "#374151")
    
    def __init__(self, label: str, text_color: str, bg_color: str):
        self.label = label
        self.text_color = text_color
        self.bg_color = bg_color


@dataclass
class FeatureState:
    """State container for a feature card."""
    enabled: bool = True
    running: bool = False
    status: FeatureStatus = FeatureStatus.IDLE
    progress: float = 0.0
    current_item: str = ""
    items_processed: int = 0
    items_total: int = 0
    elapsed_seconds: float = 0.0
    error_message: str = ""
    result_data: Dict[str, Any] = field(default_factory=dict)


class FeatureCard(QFrame):
    """
    Actionable feature card with Run/Enable toggle, status pill,
    progress indicator, and action buttons.
    """
    
    runRequested = Signal(str)  # feature_id
    cancelRequested = Signal(str)  # feature_id
    enabledChanged = Signal(str, bool)  # feature_id, enabled
    actionTriggered = Signal(str, str)  # feature_id, action
    
    def __init__(self, feature_id: str, title: str, description: str, 
                 icon: str = "", parent=None):
        super().__init__(parent)
        self.feature_id = feature_id
        self.title = title
        self.description = description
        self.icon = icon
        self.state = FeatureState()
        self._cancel_callback: Optional[Callable] = None
        self._timer: Optional[QTimer] = None
        
        self._setup_ui()
        self._update_appearance()
    
    def _setup_ui(self):
        """Setup the feature card UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("feature-card")
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header row: Icon + Title + Status + Enable toggle
        header = QHBoxLayout()
        header.setSpacing(12)
        
        # Icon
        if self.icon:
            icon_label = QLabel(self.icon)
            icon_label.setStyleSheet("font-size: 20px;")
            header.addWidget(icon_label)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("feature-title")
        self.title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #fff;
        """)
        header.addWidget(self.title_label, stretch=1)
        
        # Status pill
        self.status_pill = QLabel(FeatureStatus.IDLE.label)
        self.status_pill.setObjectName("status-pill")
        self.status_pill.setStyleSheet(self._get_status_pill_style(FeatureStatus.IDLE))
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_pill.setMinimumWidth(70)
        header.addWidget(self.status_pill)
        
        # Enable toggle
        self.enable_toggle = QCheckBox()
        self.enable_toggle.setChecked(True)
        self.enable_toggle.setToolTip("Enable/disable this feature")
        self.enable_toggle.stateChanged.connect(self._on_enable_changed)
        header.addWidget(self.enable_toggle)
        
        layout.addLayout(header)
        
        # Description
        self.desc_label = QLabel(self.description)
        self.desc_label.setObjectName("feature-desc")
        self.desc_label.setStyleSheet("""
            font-size: 11px;
            color: #888;
            line-height: 1.4;
        """)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)
        
        # Progress section
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)
        
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
                height: 8px;
                text-align: center;
                font-size: 10px;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #3b82f6;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        # Progress details row
        details_layout = QHBoxLayout()
        details_layout.setSpacing(8)
        
        self.current_item_label = QLabel("")
        self.current_item_label.setStyleSheet("font-size: 10px; color: #aaa;")
        self.current_item_label.setElideMode(Qt.TextElideMode.ElideMiddle)
        details_layout.addWidget(self.current_item_label, stretch=1)
        
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("font-size: 10px; color: #666;")
        details_layout.addWidget(self.count_label)
        
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("font-size: 10px; color: #666;")
        details_layout.addWidget(self.time_label)
        
        progress_layout.addLayout(details_layout)
        layout.addWidget(self.progress_frame)
        
        # Error message (hidden by default)
        self.error_frame = QFrame()
        self.error_frame.setVisible(False)
        error_layout = QVBoxLayout(self.error_frame)
        error_layout.setContentsMargins(8, 8, 8, 8)
        error_layout.setSpacing(4)
        
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("""
            font-size: 11px;
            color: #fca5a5;
            padding: 4px;
        """)
        self.error_label.setWordWrap(True)
        error_layout.addWidget(self.error_label)
        
        self.error_frame.setStyleSheet("""
            background-color: #3a1a1a;
            border-radius: 6px;
        """)
        layout.addWidget(self.error_frame)
        
        # Action buttons row
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(8)
        
        # Run button
        self.run_btn = QPushButton("Run")
        self.run_btn.setObjectName("run-btn")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 500;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #374151;
                color: #6b7280;
            }
        """)
        self.run_btn.clicked.connect(self._on_run_clicked)
        self.action_layout.addWidget(self.run_btn)
        
        # Cancel button (hidden by default)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancel-btn")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #b91c1c;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.cancel_btn.setVisible(False)
        self.action_layout.addWidget(self.cancel_btn)
        
        self.action_layout.addStretch()
        
        # More actions menu button
        self.more_btn = QToolButton()
        self.more_btn.setText("⋯")
        self.more_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #888;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #374151;
                color: #fff;
            }
        """)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_action_menu()
        self.action_layout.addWidget(self.more_btn)
        
        layout.addLayout(self.action_layout)
        
        # Set card style
        self._update_appearance()
    
    def _setup_action_menu(self):
        """Setup the action menu for the card."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                color: #eee;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
            }
            QMenu::separator {
                height: 1px;
                background-color: #374151;
                margin: 4px 8px;
            }
        """)
        
        # View logs action
        self.view_logs_action = QAction("View Logs", self)
        self.view_logs_action.triggered.connect(lambda: self.actionTriggered.emit(self.feature_id, "view_logs"))
        menu.addAction(self.view_logs_action)
        
        # View results action (only available when complete)
        self.view_results_action = QAction("View Results", self)
        self.view_results_action.setEnabled(False)
        self.view_results_action.triggered.connect(lambda: self.actionTriggered.emit(self.feature_id, "view_results"))
        menu.addAction(self.view_results_action)
        
        menu.addSeparator()
        
        # Reset action
        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self.reset)
        menu.addAction(reset_action)
        
        self.more_btn.setMenu(menu)
    
    def _get_status_pill_style(self, status: FeatureStatus) -> str:
        """Get the stylesheet for a status pill."""
        return f"""
            background-color: {status.bg_color};
            color: {status.text_color};
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: bold;
        """
    
    def _update_appearance(self):
        """Update the card appearance based on state."""
        # Update status pill
        self.status_pill.setText(self.state.status.label)
        self.status_pill.setStyleSheet(self._get_status_pill_style(self.state.status))
        
        # Update progress visibility
        is_running = self.state.status == FeatureStatus.RUNNING
        self.progress_frame.setVisible(is_running)
        
        # Update buttons
        can_run = (self.state.status in [FeatureStatus.IDLE, FeatureStatus.ERROR, FeatureStatus.COMPLETE] 
                   and self.state.enabled)
        self.run_btn.setVisible(not is_running)
        self.run_btn.setEnabled(can_run)
        self.cancel_btn.setVisible(is_running)
        
        # Update error display
        has_error = self.state.status == FeatureStatus.ERROR and self.state.error_message
        self.error_frame.setVisible(has_error)
        if has_error:
            self.error_label.setText(self.state.error_message)
        
        # Update enable toggle
        self.enable_toggle.setChecked(self.state.enabled)
        self.enable_toggle.setEnabled(not is_running)
        
        # Update card border based on status
        if self.state.status == FeatureStatus.RUNNING:
            border_color = "#3b82f6"
        elif self.state.status == FeatureStatus.COMPLETE:
            border_color = "#22c55e"
        elif self.state.status == FeatureStatus.ERROR:
            border_color = "#ef4444"
        elif self.state.status == FeatureStatus.QUEUED:
            border_color = "#f59e0b"
        else:
            border_color = "#2d3748"
        
        self.setStyleSheet(f"""
            QFrame#feature-card {{
                background-color: #16213e;
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
            QFrame#feature-card:hover {{
                border-color: #3b82f6;
            }}
        """)
        
        # Update results action availability
        self.view_results_action.setEnabled(self.state.status == FeatureStatus.COMPLETE)
    
    def _on_enable_changed(self, state):
        """Handle enable toggle change."""
        self.state.enabled = bool(state)
        self.enabledChanged.emit(self.feature_id, self.state.enabled)
        self._update_appearance()
    
    def _on_run_clicked(self):
        """Handle run button click."""
        if self.state.enabled and not self.state.running:
            self.runRequested.emit(self.feature_id)
    
    def _on_cancel_clicked(self):
        """Handle cancel button click."""
        if self.state.running:
            self.cancelRequested.emit(self.feature_id)
            if self._cancel_callback:
                self._cancel_callback()
    
    def _update_timer(self):
        """Update elapsed time display."""
        if self.state.running and self.state.status == FeatureStatus.RUNNING:
            self.state.elapsed_seconds += 0.1
            self._update_time_label()
    
    def _update_time_label(self):
        """Update the time label display."""
        elapsed = self.state.elapsed_seconds
        if elapsed < 60:
            self.time_label.setText(f"{elapsed:.1f}s")
        else:
            mins = int(elapsed / 60)
            secs = int(elapsed % 60)
            self.time_label.setText(f"{mins}m {secs}s")
    
    # Public API
    
    def set_status(self, status: FeatureStatus):
        """Set the feature status."""
        self.state.status = status
        
        if status == FeatureStatus.RUNNING and not self.state.running:
            self.state.running = True
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update_timer)
            self._timer.start(100)  # Update every 100ms
        elif status != FeatureStatus.RUNNING and self.state.running:
            self.state.running = False
            if self._timer:
                self._timer.stop()
                self._timer = None
        
        self._update_appearance()
    
    def set_progress(self, percent: float, current_item: str = "", 
                     items_processed: int = 0, items_total: int = 0):
        """Update progress information."""
        self.state.progress = max(0.0, min(100.0, percent))
        self.state.current_item = current_item
        self.state.items_processed = items_processed
        self.state.items_total = items_total
        
        self.progress_bar.setValue(int(self.state.progress))
        
        if current_item:
            self.current_item_label.setText(current_item)
        
        if items_total > 0:
            self.count_label.setText(f"{items_processed}/{items_total}")
        else:
            self.count_label.setText("")
        
        self._update_time_label()
    
    def set_error(self, message: str):
        """Set error message."""
        self.state.error_message = message
        self.set_status(FeatureStatus.ERROR)
    
    def set_result(self, data: Dict[str, Any]):
        """Set result data after completion."""
        self.state.result_data = data
    
    def reset(self):
        """Reset the card to initial state."""
        self.state = FeatureState(enabled=self.state.enabled)
        self.state.status = FeatureStatus.IDLE
        self.progress_bar.setValue(0)
        self.current_item_label.setText("")
        self.count_label.setText("")
        self.time_label.setText("")
        if self._timer:
            self._timer.stop()
            self._timer = None
        self._update_appearance()
    
    def set_cancel_callback(self, callback: Callable):
        """Set a callback for when cancel is requested."""
        self._cancel_callback = callback
    
    def get_state(self) -> FeatureState:
        """Get the current feature state."""
        return self.state


class FeatureCardsPanel(QWidget):
    """
    Panel containing multiple feature cards arranged in a grid.
    """
    
    featureRunRequested = Signal(str)  # feature_id
    featureCancelRequested = Signal(str)  # feature_id
    featureEnabledChanged = Signal(str, bool)  # feature_id, enabled
    featureActionTriggered = Signal(str, str)  # feature_id, action
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: Dict[str, FeatureCard] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # Header
        header = QLabel("FEATURES")
        header.setObjectName("panel-header")
        header.setStyleSheet("""
            color: #666;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 0 0 8px 0;
        """)
        layout.addWidget(header)
        
        # Cards container
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        layout.addWidget(self.cards_container)
        layout.addStretch()
    
    def add_card(self, feature_id: str, title: str, description: str, 
                 icon: str = "") -> FeatureCard:
        """Add a feature card to the panel."""
        card = FeatureCard(feature_id, title, description, icon)
        card.runRequested.connect(self.featureRunRequested.emit)
        card.cancelRequested.connect(self.featureCancelRequested.emit)
        card.enabledChanged.connect(self.featureEnabledChanged.emit)
        card.actionTriggered.connect(self.featureActionTriggered.emit)
        
        self._cards[feature_id] = card
        self.cards_layout.addWidget(card)
        return card
    
    def get_card(self, feature_id: str) -> Optional[FeatureCard]:
        """Get a feature card by ID."""
        return self._cards.get(feature_id)
    
    def remove_card(self, feature_id: str):
        """Remove a feature card."""
        if feature_id in self._cards:
            card = self._cards.pop(feature_id)
            self.cards_layout.removeWidget(card)
            card.deleteLater()
    
    def set_feature_status(self, feature_id: str, status: FeatureStatus):
        """Set the status of a feature."""
        card = self._cards.get(feature_id)
        if card:
            card.set_status(status)
    
    def set_feature_progress(self, feature_id: str, percent: float, 
                            current_item: str = "", items_processed: int = 0,
                            items_total: int = 0):
        """Set the progress of a feature."""
        card = self._cards.get(feature_id)
        if card:
            card.set_progress(percent, current_item, items_processed, items_total)
    
    def reset_all(self):
        """Reset all feature cards."""
        for card in self._cards.values():
            card.reset()
    
    def get_all_states(self) -> Dict[str, FeatureState]:
        """Get all feature states."""
        return {fid: card.get_state() for fid, card in self._cards.items()}


# Predefined feature configurations
FEATURE_COPY = ("copy", "Copy", "Copy media files with verification", "📁")
FEATURE_VERIFY = ("verify", "Verify", "Verify file integrity after copy", "✓")
FEATURE_REPORTS = ("reports", "Reports", "Generate PDF/CSV reports with metadata", "📊")
FEATURE_SYNC = ("sync", "Sync", "Synchronize audio and video files", "🔄")
FEATURE_FRAME_ANALYSIS = ("frame_analysis", "Frame Analysis", "Analyze frames for visual content", "🎬")
FEATURE_TRANSCRIPTION = ("transcription", "Transcription", "Transcribe audio using local AI", "🎤")

ALL_FEATURES = [
    FEATURE_COPY,
    FEATURE_VERIFY,
    FEATURE_REPORTS,
    FEATURE_SYNC,
    FEATURE_FRAME_ANALYSIS,
    FEATURE_TRANSCRIPTION,
]
