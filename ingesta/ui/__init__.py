"""PySide6 Desktop UI for ingesta media ingestion tool.

Install with UI support: pip install ingesta[ui]
"""

# Only import if PySide6 is available
try:
    from .app import main
    from .main_window import IngestaMainWindow
    from .sync_dialog import SyncSourceDialog
    __all__ = ['main', 'IngestaMainWindow', 'SyncSourceDialog']
except ImportError:
    # PySide6 not installed, UI unavailable
    def main():
        """Placeholder main function when PySide6 is not installed."""
        import sys
        print("Error: PySide6 is not installed.")
        print("Install UI support with: pip install ingesta[ui]")
        sys.exit(1)
    
    IngestaMainWindow = None
    SyncSourceDialog = None
    __all__ = ['main', 'IngestaMainWindow', 'SyncSourceDialog']
