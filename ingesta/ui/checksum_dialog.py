"""Checksum selection dialog for ingesta UI."""

from typing import Optional, Callable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QRadioButton, QWidget, QFrame
)
from PySide6.QtCore import Qt


# Checksum algorithm options with metadata
CHECKSUM_ALGORITHMS = {
    "xxhash64": {
        "name": "xxHash64",
        "description": "Fastest - optimized for large files (recommended)",
        "speed": "Fast",
        "security": "Non-cryptographic",
        "use_case": "Large media files"
    },
    "xxhash32": {
        "name": "xxHash32",
        "description": "Very fast - smaller hash size",
        "speed": "Very Fast",
        "security": "Non-cryptographic",
        "use_case": "Quick verification"
    },
    "md5": {
        "name": "MD5",
        "description": "Widely compatible - older standard",
        "speed": "Medium",
        "security": "Cryptographic (broken)",
        "use_case": "Legacy compatibility"
    },
    "sha256": {
        "name": "SHA-256",
        "description": "Secure - cryptographic strength",
        "speed": "Slow",
        "security": "Cryptographic",
        "use_case": "Maximum security"
    }
}


class AlgorithmCard(QFrame):
    """Selectable card for a checksum algorithm."""
    
    def __init__(self, algorithm_id: str, info: dict, parent=None):
        super().__init__(parent)
        self.algorithm_id = algorithm_id
        self.info = info
        self._is_selected = False
        
        self._setup_ui()
        self.set_selected(False)
    
    def _setup_ui(self):
        """Setup the card UI."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        
        # Header row
        header = QHBoxLayout()
        
        # Name with recommended badge
        name_layout = QHBoxLayout()
        name_label = QLabel(self.info["name"])
        name_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #fff;")
        name_layout.addWidget(name_label)
        
        if self.algorithm_id == "xxhash64":
            rec_badge = QLabel("RECOMMENDED")
            rec_badge.setStyleSheet("""
                background-color: #166534;
                color: #86efac;
                padding: 2px 8px;
                border-radius: 10px;
                font-size: 9px;
                font-weight: bold;
            """)
            name_layout.addWidget(rec_badge)
        
        name_layout.addStretch()
        header.addLayout(name_layout)
        layout.addLayout(header)
        
        # Description
        desc = QLabel(self.info["description"])
        desc.setStyleSheet("font-size: 12px; color: #aaa;")
        layout.addWidget(desc)
        
        # Specs row
        specs = QHBoxLayout()
        specs.setSpacing(12)
        
        speed_badge = QLabel(f"⚡ {self.info['speed']}")
        speed_badge.setStyleSheet("font-size: 11px; color: #60a5fa;")
        specs.addWidget(speed_badge)
        
        use_case = QLabel(f"📋 {self.info['use_case']}")
        use_case.setStyleSheet("font-size: 11px; color: #888;")
        specs.addWidget(use_case)
        
        specs.addStretch()
        layout.addLayout(specs)
    
    def set_selected(self, selected: bool):
        """Update visual selection state."""
        self._is_selected = selected
        
        if selected:
            self.setStyleSheet("""
                AlgorithmCard {
                    background-color: #1e3a5f;
                    border: 2px solid #3b82f6;
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                AlgorithmCard {
                    background-color: #16213e;
                    border: 1px solid #2d3748;
                    border-radius: 10px;
                }
                AlgorithmCard:hover {
                    background-color: #1e293b;
                    border-color: #3b82f6;
                }
            """)
    
    def is_selected(self) -> bool:
        """Get selection state."""
        return self._is_selected
    
    def mousePressEvent(self, event):
        """Handle click to select."""
        self.set_selected(True)
        # Find parent dialog and update selection
        parent = self.parent()
        while parent and not isinstance(parent, ChecksumSelectionDialog):
            parent = parent.parent()
        if parent:
            parent._on_card_selected(self.algorithm_id)


class ChecksumSelectionDialog(QDialog):
    """Dialog for selecting checksum verification algorithm."""
    
    def __init__(self, parent=None, default_algorithm: str = "xxhash64"):
        super().__init__(parent)
        self.selected_algorithm = default_algorithm
        self._cards: dict = {}
        
        self.setWindowTitle("Select Verification Method")
        self.setMinimumWidth(500)
        self.setMinimumHeight(450)
        
        self._setup_ui()
        self._select_algorithm(default_algorithm)
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a2e;
            }
            QLabel {
                color: #eee;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Header
        header = QLabel("Choose Verification Method")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #fff;")
        layout.addWidget(header)
        
        # Subtitle
        subtitle = QLabel(
            "Select a checksum algorithm for verifying file integrity during ingestion.\n"
            "This ensures your media is copied correctly and can be safely verified."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 13px; color: #888; line-height: 1.4;")
        layout.addWidget(subtitle)
        
        # Algorithm cards
        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(10)
        
        for algo_id, info in CHECKSUM_ALGORITHMS.items():
            card = AlgorithmCard(algo_id, info)
            self._cards[algo_id] = card
            cards_layout.addWidget(card)
        
        layout.addLayout(cards_layout)
        
        # Info note
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-left: 3px solid #3b82f6;
                border-radius: 4px;
                padding: 12px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(12, 8, 12, 8)
        
        info_label = QLabel(
            "💡 <b>Recommendation:</b> xxHash64 offers the best balance of speed and reliability "
            "for large media files. It's optimized for media workflows and widely used for verification."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 12px; color: #93c5fd;")
        info_layout.addWidget(info_label)
        
        layout.addWidget(info_frame)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        
        button_layout.addStretch()
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #374151;
                color: #eee;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #4b5563;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # Confirm button
        self.confirm_btn = QPushButton("Start Ingestion")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #16a34a;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #15803d;
            }
        """)
        self.confirm_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.confirm_btn)
        
        layout.addLayout(button_layout)
    
    def _on_card_selected(self, algorithm_id: str):
        """Handle card selection."""
        self.selected_algorithm = algorithm_id
        # Deselect other cards
        for algo_id, card in self._cards.items():
            if algo_id != algorithm_id:
                card.set_selected(False)
        # Update button text
        algo_name = CHECKSUM_ALGORITHMS[algorithm_id]["name"]
        self.confirm_btn.setText(f"Start with {algo_name}")
    
    def _select_algorithm(self, algorithm_id: str):
        """Programmatically select an algorithm."""
        if algorithm_id in self._cards:
            self._cards[algorithm_id].set_selected(True)
            self._on_card_selected(algorithm_id)
    
    def get_selected_algorithm(self) -> str:
        """Get the selected algorithm ID."""
        return self.selected_algorithm
    
    @staticmethod
    def get_algorithm(parent=None, default: str = "xxhash64") -> Optional[str]:
        """
        Static method to show dialog and return selected algorithm.
        
        Returns:
            Selected algorithm ID or None if cancelled
        """
        dialog = ChecksumSelectionDialog(parent, default)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            return dialog.get_selected_algorithm()
        return None
