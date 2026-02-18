"""Entry point for ingesta PySide6 desktop UI."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .main_window import IngestaMainWindow
from .styles import DARK_STYLESHEET


def main():
    """Main entry point for the desktop UI."""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("Ingesta")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("jcolefoto")
    
    # Apply dark stylesheet
    app.setStyleSheet(DARK_STYLESHEET)
    
    # Create and show main window
    window = IngestaMainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
