"""Workflow status panel showing features and their stability."""

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt


class FeatureStatus(Enum):
    """Feature stability status."""
    STABLE = ("Stable", "#22c55e", "#166534")
    BETA = ("Beta", "#f59e0b", "#713f12")
    ALPHA = ("Alpha", "#ef4444", "#7f1d1d")
    PLANNED = ("Planned", "#6b7280", "#374151")
    
    def __init__(self, label: str, text_color: str, bg_color: str):
        self.label = label
        self.text_color = text_color
        self.bg_color = bg_color


@dataclass
class WorkflowFeature:
    """Represents a workflow feature."""
    name: str
    description: str
    status: FeatureStatus
    category: str


class FeatureItem(QFrame):
    """Individual feature item with status badge."""
    
    def __init__(self, feature: WorkflowFeature, parent=None):
        super().__init__(parent)
        self.feature = feature
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the feature item UI."""
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("""
            FeatureItem {
                background-color: transparent;
                border-bottom: 1px solid #1e293b;
                padding: 12px 0;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)
        
        # Header row with name and badge
        header = QHBoxLayout()
        header.setSpacing(8)
        
        name = QLabel(self.feature.name)
        name.setStyleSheet("""
            font-size: 13px;
            font-weight: 500;
            color: #fff;
        """)
        header.addWidget(name)
        
        header.addStretch()
        
        # Status badge
        badge = QLabel(self.feature.status.label)
        badge.setStyleSheet(f"""
            background-color: {self.feature.status.bg_color};
            color: {self.feature.status.text_color};
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: bold;
        """)
        header.addWidget(badge)
        
        layout.addLayout(header)
        
        # Description
        desc = QLabel(self.feature.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            font-size: 11px;
            color: #888;
            line-height: 1.3;
        """)
        layout.addWidget(desc)


class WorkflowStatusPanel(QWidget):
    """Right panel showing workflow status and feature stability."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._features: List[WorkflowFeature] = []
        self._setup_ui()
        self._init_default_features()
    
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
        
        layout.addWidget(self.status_card)
        
        # Features section header
        features_header = QLabel("FEATURES")
        features_header.setStyleSheet("""
            color: #666;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 8px 16px;
        """)
        layout.addWidget(features_header)
        
        # Scroll area for features
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)
        
        self.features_container = QWidget()
        self.features_layout = QVBoxLayout(self.features_container)
        self.features_layout.setContentsMargins(12, 0, 12, 0)
        self.features_layout.setSpacing(0)
        
        scroll.setWidget(self.features_container)
        layout.addWidget(scroll, stretch=1)
        
        # Legend at bottom
        legend_frame = QFrame()
        legend_frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border-top: 1px solid #1e293b;
                padding: 12px;
            }
        """)
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(12, 8, 12, 8)
        legend_layout.setSpacing(12)
        
        # Add legend items
        for status in [FeatureStatus.STABLE, FeatureStatus.BETA, FeatureStatus.ALPHA]:
            badge = QLabel(status.label)
            badge.setStyleSheet(f"""
                background-color: {status.bg_color};
                color: {status.text_color};
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            """)
            legend_layout.addWidget(badge)
        
        legend_layout.addStretch()
        layout.addWidget(legend_frame)
    
    def _init_default_features(self):
        """Initialize default workflow features."""
        default_features = [
            WorkflowFeature(
                name="Media Ingestion",
                description="Copy and verify media files with checksums",
                status=FeatureStatus.STABLE,
                category="Core"
            ),
            WorkflowFeature(
                name="Multi-Destination",
                description="Copy to multiple destinations simultaneously",
                status=FeatureStatus.STABLE,
                category="Core"
            ),
            WorkflowFeature(
                name="Progress Tracking",
                description="Real-time progress with speed and ETA",
                status=FeatureStatus.STABLE,
                category="Core"
            ),
            WorkflowFeature(
                name="History & Resume",
                description="View past ingests and reload configurations",
                status=FeatureStatus.STABLE,
                category="Core"
            ),
            WorkflowFeature(
                name="Generate Reports",
                description="Create detailed media reports with metadata",
                status=FeatureStatus.BETA,
                category="Analysis"
            ),
            WorkflowFeature(
                name="Audio Sync",
                description="Synchronize separate audio and video files",
                status=FeatureStatus.BETA,
                category="Tools"
            ),
            WorkflowFeature(
                name="Local Transcription",
                description="Transcribe audio using local AI models",
                status=FeatureStatus.ALPHA,
                category="AI"
            ),
            WorkflowFeature(
                name="Proxy Generation",
                description="Generate lightweight editing proxies",
                status=FeatureStatus.BETA,
                category="Tools"
            ),
            WorkflowFeature(
                name="Editor Integration",
                description="Direct export to video editing software",
                status=FeatureStatus.PLANNED,
                category="Integration"
            ),
            WorkflowFeature(
                name="Cloud Backup",
                description="Automatic cloud backup options",
                status=FeatureStatus.PLANNED,
                category="Storage"
            ),
        ]
        
        self.set_features(default_features)
    
    def set_features(self, features: List[WorkflowFeature]):
        """Set the list of features to display."""
        self._features = features
        self._refresh_features()
    
    def _refresh_features(self):
        """Refresh the features display."""
        # Clear existing
        while self.features_layout.count():
            item = self.features_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Group by category
        categories = {}
        for feature in self._features:
            if feature.category not in categories:
                categories[feature.category] = []
            categories[feature.category].append(feature)
        
        # Add categorized features
        for category, features in sorted(categories.items()):
            # Category header
            cat_label = QLabel(category.upper())
            cat_label.setStyleSheet("""
                font-size: 10px;
                font-weight: bold;
                color: #3b82f6;
                padding: 16px 0 8px 0;
                letter-spacing: 0.5px;
            """)
            self.features_layout.addWidget(cat_label)
            
            # Feature items
            for feature in features:
                item = FeatureItem(feature)
                self.features_layout.addWidget(item)
        
        self.features_layout.addStretch()
    
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
        else:
            self.status_value.setStyleSheet("""
                font-size: 16px;
                font-weight: bold;
                color: #60a5fa;
            """)
