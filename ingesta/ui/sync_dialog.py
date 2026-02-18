"""Sync source selection dialog for ingesta UI."""

from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QRadioButton, QMessageBox
)
from PySide6.QtCore import Qt


class SyncSourceDialog(QDialog):
    """Dialog for selecting sync source before running sync operation."""
    
    # Sync source options
    AUTO = "auto"
    TIMECODE = "timecode"
    WAVEFORM = "waveform"
    
    def __init__(self, parent=None, video_dir: Optional[str] = None, audio_dir: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Select Sync Source")
        self.setMinimumWidth(400)
        self.selected_source: Optional[str] = None
        self.video_dir = video_dir
        self.audio_dir = audio_dir
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Sync Source Selection")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Description
        desc = QLabel(
            "Select the method to synchronize external audio with video clips. "
            "This selection will be used for all clips in this sync operation."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # Directories info
        if self.video_dir or self.audio_dir:
            info_layout = QVBoxLayout()
            if self.video_dir:
                video_label = QLabel(f"Video: {self.video_dir}")
                video_label.setStyleSheet("font-size: 11px; color: #666;")
                info_layout.addWidget(video_label)
            if self.audio_dir:
                audio_label = QLabel(f"Audio: {self.audio_dir}")
                audio_label.setStyleSheet("font-size: 11px; color: #666;")
                info_layout.addWidget(audio_label)
            layout.addLayout(info_layout)
        
        # Radio button group
        self.button_group = QButtonGroup(self)
        
        # Auto option (recommended)
        self.auto_radio = QRadioButton("Auto (recommended)")
        self.auto_radio.setChecked(True)
        self.auto_radio.setToolTip(
            "Automatically detect the best sync method based on available metadata"
        )
        self.button_group.addButton(self.auto_radio)
        layout.addWidget(self.auto_radio)
        
        auto_desc = QLabel("Automatically selects the best available sync method")
        auto_desc.setStyleSheet("color: #666; font-size: 11px; margin-left: 24px;")
        layout.addWidget(auto_desc)
        
        # Timecode option
        self.timecode_radio = QRadioButton("Timecode")
        self.timecode_radio.setToolTip(
            "Use embedded timecode metadata to synchronize audio and video"
        )
        self.button_group.addButton(self.timecode_radio)
        layout.addWidget(self.timecode_radio)
        
        timecode_desc = QLabel("Uses embedded timecode metadata for synchronization")
        timecode_desc.setStyleSheet("color: #666; font-size: 11px; margin-left: 24px;")
        layout.addWidget(timecode_desc)
        
        # Waveform option
        self.waveform_radio = QRadioButton("Waveform")
        self.waveform_radio.setToolTip(
            "Use audio waveform matching to align audio tracks"
        )
        self.button_group.addButton(self.waveform_radio)
        layout.addWidget(self.waveform_radio)
        
        waveform_desc = QLabel("Matches audio waveforms to find sync points")
        waveform_desc.setStyleSheet("color: #666; font-size: 11px; margin-left: 24px;")
        layout.addWidget(waveform_desc)
        
        layout.addSpacing(20)
        
        # Warning label
        warning = QLabel(
            "⚠️ You must confirm your selection before proceeding. "
            "The default is 'Auto' but you must explicitly confirm each run."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background-color: #2d3a5a; color: #fbbf24; padding: 10px; "
            "border-radius: 6px; font-size: 11px;"
        )
        layout.addWidget(warning)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        
        self.confirm_btn = QPushButton("Confirm & Start Sync")
        self.confirm_btn.setObjectName("success")
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self._on_confirm)
        button_layout.addWidget(self.confirm_btn)
        
        layout.addLayout(button_layout)
    
    def _on_confirm(self):
        """Handle confirm button click."""
        if self.auto_radio.isChecked():
            self.selected_source = self.AUTO
        elif self.timecode_radio.isChecked():
            self.selected_source = self.TIMECODE
        elif self.waveform_radio.isChecked():
            self.selected_source = self.WAVEFORM
        else:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a sync source method."
            )
            return
        
        self.accept()
    
    def get_selected_source(self) -> Optional[str]:
        """Get the selected sync source."""
        return self.selected_source
    
    @staticmethod
    def get_sync_source(parent=None, video_dir: Optional[str] = None, 
                        audio_dir: Optional[str] = None) -> Optional[str]:
        """
        Static method to show dialog and return selected sync source.
        
        Args:
            parent: Parent widget
            video_dir: Video directory path (for display)
            audio_dir: Audio directory path (for display)
            
        Returns:
            Selected sync source ('auto', 'timecode', or 'waveform') or None if cancelled
        """
        dialog = SyncSourceDialog(parent, video_dir, audio_dir)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            return dialog.get_selected_source()
        return None
