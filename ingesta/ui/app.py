"""Entry point for ingesta PySide6 desktop UI."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .main_window import IngestaMainWindow
from .styles import DARK_STYLESHEET


def print_ui_banner():
    """Print a banner explaining UI vs CLI entrypoints."""
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║                    INGESTA DESKTOP UI (PySide6)                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🎬 You are launching the VISUAL DESKTOP INTERFACE               ║
║                                                                  ║
║  This is a graphical application with:                           ║
║    • Drag-and-drop file selection                                ║
║    • Visual progress tracking                                    ║
║    • Guided workflow wizard                                      ║
║                                                                  ║
║  For command-line scripting and automation, use:                 ║
║    $ ingesta --help                                              ║
║    $ ingesta ingest --source /path --dest /path                  ║
║                                                                  ║
║  Both interfaces share the same core functionality.              ║
║  Choose CLI for automation, UI for visual interaction.           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def main():
    """Main entry point for the desktop UI."""
    # Print banner to console explaining UI vs CLI
    print_ui_banner()
    
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
