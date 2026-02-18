"""
Pytest configuration for ingesta tests.
"""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_media_dir(temp_dir):
    """Create a directory with sample media files."""
    media_dir = temp_dir / "media"
    media_dir.mkdir()
    
    # Create test files
    (media_dir / "test1.txt").write_text("test content 1")
    (media_dir / "test2.txt").write_text("test content 2")
    
    return media_dir