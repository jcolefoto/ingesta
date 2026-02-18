"""Dark mode styles for ingesta UI."""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #1a1a2e;
    color: #eee;
}

QWidget {
    background-color: #1a1a2e;
    color: #eee;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

QLabel {
    color: #eee;
}

QLabel#title {
    font-size: 24px;
    font-weight: bold;
    color: #fff;
    padding: 10px;
}

QLabel#section-title {
    font-size: 14px;
    font-weight: bold;
    color: #aaa;
    margin-top: 15px;
    margin-bottom: 5px;
}

QLabel#badge {
    padding: 6px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: bold;
}

QLabel#badge-valid {
    background-color: #2d5a3d;
    color: #4ade80;
}

QLabel#badge-warning {
    background-color: #5a4d2d;
    color: #fbbf24;
}

QLabel#badge-error {
    background-color: #5a2d2d;
    color: #f87171;
}

QLabel#badge-info {
    background-color: #2d3a5a;
    color: #60a5fa;
}

QPushButton {
    background-color: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
    min-width: 100px;
}

QPushButton:hover {
    background-color: #2563eb;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #374151;
    color: #6b7280;
}

QPushButton#secondary {
    background-color: #374151;
    color: #eee;
}

QPushButton#secondary:hover {
    background-color: #4b5563;
}

QPushButton#danger {
    background-color: #dc2626;
}

QPushButton#danger:hover {
    background-color: #b91c1c;
}

QPushButton#success {
    background-color: #16a34a;
}

QPushButton#success:hover {
    background-color: #15803d;
}

DropZone {
    background-color: #16213e;
    border: 2px dashed #3b82f6;
    border-radius: 12px;
    padding: 30px;
    min-height: 120px;
}

DropZone[active="true"] {
    background-color: #1e3a5f;
    border-color: #60a5fa;
}

DropZone[valid="true"] {
    border-color: #4ade80;
    background-color: #1a3a2e;
}

DropZone[valid="false"] {
    border-color: #f87171;
    background-color: #3a1a2e;
}

QProgressBar {
    border: none;
    border-radius: 6px;
    background-color: #16213e;
    height: 24px;
    text-align: center;
    font-size: 11px;
    font-weight: bold;
}

QProgressBar::chunk {
    border-radius: 6px;
    background-color: #3b82f6;
}

QProgressBar[phase="copying"]::chunk {
    background-color: #3b82f6;
}

QProgressBar[phase="verifying"]::chunk {
    background-color: #10b981;
}

QProgressBar[phase="error"]::chunk {
    background-color: #ef4444;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: #16213e;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #3b82f6;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #60a5fa;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QListWidget {
    background-color: #16213e;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 8px;
    color: #eee;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
    margin: 2px 0;
}

QListWidget::item:selected {
    background-color: #3b82f6;
}

QListWidget::item:hover {
    background-color: #2d3748;
}

QGroupBox {
    border: 1px solid #2d3748;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: bold;
    color: #aaa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QFrame#card {
    background-color: #16213e;
    border-radius: 12px;
    padding: 16px;
}

QLabel#stats-value {
    font-size: 28px;
    font-weight: bold;
    color: #fff;
}

QLabel#stats-label {
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QLabel#status-text {
    font-size: 12px;
    color: #aaa;
    padding: 4px 0;
}

QLabel#file-path {
    font-size: 11px;
    color: #888;
    font-family: 'SF Mono', Monaco, monospace;
}

QFrame#separator {
    background-color: #2d3748;
    max-height: 1px;
}

HistoryPanel {
    background-color: #0f172a;
    border-left: 1px solid #1e293b;
    min-width: 250px;
}

HistoryPanel QLabel#panel-title {
    font-size: 14px;
    font-weight: bold;
    color: #fff;
    padding: 16px;
    border-bottom: 1px solid #1e293b;
}

HistoryPanel QListWidget {
    background-color: transparent;
    border: none;
}

HistoryPanel QListWidget::item {
    border-bottom: 1px solid #1e293b;
    padding: 12px;
}
"""

SAFE_BADGE_STYLE = """
    background-color: #166534;
    color: #86efac;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: bold;
"""

FAIL_BADGE_STYLE = """
    background-color: #7f1d1d;
    color: #fca5a5;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: bold;
"""

WARNING_BADGE_STYLE = """
    background-color: #713f12;
    color: #fde047;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: bold;
"""

# Workflow step styles
WORKFLOW_STEP_ACTIVE = """
    background-color: #1e3a5f;
    border-left: 3px solid #3b82f6;
"""

WORKFLOW_STEP_COMPLETE = """
    background-color: transparent;
    border-left: 3px solid #22c55e;
"""

WORKFLOW_STEP_INACTIVE = """
    background-color: transparent;
    border-left: 3px solid transparent;
"""

# Feature badge styles
FEATURE_BADGE_STABLE = """
    background-color: #166534;
    color: #86efac;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: bold;
"""

FEATURE_BADGE_BETA = """
    background-color: #713f12;
    color: #fde047;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: bold;
"""

FEATURE_BADGE_ALPHA = """
    background-color: #7f1d1d;
    color: #fca5a5;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: bold;
"""

# Footer styles
FOOTER_STYLE = """
    background-color: #0f172a;
    border-top: 1px solid #1e293b;
    padding: 8px 16px;
"""

# Next steps panel styles
NEXT_STEPS_CARD_STYLE = """
    background-color: #16213e;
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 16px;
"""

NEXT_STEPS_CARD_HOVER = """
    background-color: #16213e;
    border: 1px solid #3b82f6;
    border-radius: 10px;
    padding: 16px;
"""
