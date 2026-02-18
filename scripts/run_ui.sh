#!/bin/bash
set -euo pipefail

# Ingesta PySide6 UI Launcher Script
# Creates venv if missing, installs dependencies, and launches the UI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Ingesta UI Launcher ===${NC}"
echo ""

# Check Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed or not in PATH${NC}"
    echo "Please install Python 3.8 or higher: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating virtual environment at $VENV_DIR...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}Virtual environment created${NC}"
else
    echo -e "${GREEN}Using existing virtual environment${NC}"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Check if ingesta is installed with UI extras
if ! python3 -c "import ingesta" 2>/dev/null || ! python3 -c "from PySide6 import QtWidgets" 2>/dev/null; then
    echo -e "${YELLOW}Installing ingesta with UI dependencies...${NC}"
    pip install --upgrade pip
    pip install -e "$PROJECT_DIR[ui]"
    echo -e "${GREEN}Installation complete${NC}"
else
    echo -e "${GREEN}Dependencies already installed${NC}"
fi

# Check for FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}Warning: FFmpeg not found in PATH${NC}"
    echo "Media processing will not work without FFmpeg."
    echo "Install FFmpeg:"
    echo "  macOS: brew install ffmpeg"
    echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
    echo ""
fi

echo ""
echo -e "${BLUE}=== Launching Ingesta UI ===${NC}"
echo ""

# Launch the UI
ingesta-ui "$@"
