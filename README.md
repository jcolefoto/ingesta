# Media Ingestion Tool

A Python-based media ingestion tool that combines Shotput Pro-style offloading with verification and Pluralize-style audio sync capabilities.

## Features

### 1. Media Offloading & Verification (Shotput Pro-style)
- Copy media from memory cards/storage devices to destination drives
- Generate MD5/SHA256 checksums during copy
- Verify file integrity after transfer
- Support multiple source/destination pairs
- Progress tracking and detailed logging

### 2. Audio Sync & Premiere Integration (Pluralize-style)
- Sync external audio to video via waveform matching
- Create Adobe Premiere Pro project files (.prproj)
- Auto-align audio tracks based on waveform analysis
- Support common formats:
  - Audio: WAV, MP3, BWF
  - Video: MP4, MOV, MXF

### 3. Comprehensive Reporting
- Generate professional PDF reports with thumbnails and metadata
- Export CSV files for spreadsheet analysis
- Extract evenly-distributed thumbnails from each clip
- Parse camera XML sidecar files (Sony, Canon, Blackmagic)
- Content classification (B-roll, interview, establishing shots, etc.)
- Summary statistics and breakdown by clip type

## Installation

```bash
# Clone the repository
git clone https://github.com/jcolefoto/ingesta.git
cd ingesta

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Prerequisites

- Python 3.8+
- FFmpeg installed on your system

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

## Usage

### Basic Ingestion

Copy media from a source to destination with verification:

```bash
ingesta ingest --source /Volumes/CARD001 --dest /Volumes/BackupDrive/Project001
```

With specific checksum algorithm and logging:

```bash
ingesta ingest \
  --source /Volumes/CARD001 \
  --dest /Volumes/BackupDrive/Project001 \
  --checksum sha256 \
  --log-file ingestion.log
```

### Multiple Destinations

Copy to multiple destinations simultaneously:

```bash
ingesta ingest \
  --source /Volumes/CARD001 \
  --dest /Volumes/BackupDrive1 \
  --dest /Volumes/BackupDrive2 \
  --dest /Volumes/BackupDrive3
```

### Audio Sync

Sync external audio files to video clips:

```bash
ingesta sync \
  --video-dir /path/to/video/files \
  --audio-dir /path/to/audio/files \
  --output-dir /path/to/synced/output
```

With options:

```bash
ingesta sync \
  --video-dir ./video \
  --audio-dir ./audio \
  --output-dir ./synced \
  --tolerance 0.5 \
  --prefix "synced_"
```

### Create Premiere Project

Create a Premiere Pro project with synced media:

```bash
ingesta premiere \
  --media-dir /path/to/synced/media \
  --output project.prproj \
  --name "MyProject"
```

With bins/sequences:

```bash
ingesta premiere \
  --media-dir ./synced \
  --output project.prproj \
  --name "Documentary_001" \
  --fps 24 \
  --resolution 1920x1080
```

### Complete Workflow

Full workflow: ingest, sync, and create Premiere project:

```bash
# Step 1: Ingest with verification
ingesta ingest \
  --source /Volumes/CARD001 \
  --dest ./ingested \
  --checksum sha256

# Step 2: Sync audio
ingesta sync \
  --video-dir ./ingested/video \
  --audio-dir ./ingested/audio \
  --output-dir ./synced

# Step 3: Create Premiere project
ingesta premiere \
  --media-dir ./synced \
  --output ./project.prproj
```

### Generate Reports

Generate comprehensive PDF and CSV reports with thumbnails and metadata:

```bash
# Generate both PDF and CSV reports
ingesta report -m ./ingested -o ./reports

# PDF only
ingesta report -m ./media --format pdf -o ./reports

# CSV only, no thumbnails
ingesta report -m ./media --format csv --no-thumbnails

# With project metadata
ingesta report \
  -m ./ingested \
  -o ./reports \
  -n "Documentary Project" \
  -s /Volumes/CARD001 \
  -d /Backup/Project001 \
  -d /Archive/Project001
```

The report command:
- Analyzes all clips in the media directory
- Extracts 5-6 thumbnails evenly distributed throughout each clip
- Parses XML sidecar files from professional cameras (Sony, Canon, Blackmagic)
- Generates a professional PDF report with cover page, statistics, and clip details
- Generates CSV files for spreadsheet analysis
- Creates a summary CSV with aggregate statistics

## CLI Reference

### Global Options

```
--help          Show help message and exit
--version       Show version number and exit
-v, --verbose   Enable verbose output
```

### Ingest Command

```
ingesta ingest [OPTIONS]

Options:
  --source PATH       Source directory/memory card (required)
  --dest PATH         Destination directory (can be used multiple times)
  --checksum TEXT     Checksum algorithm: md5, sha256 (default: md5)
  --verify            Verify after copy (default: True)
  --log-file PATH     Path to log file
  --include TEXT      File patterns to include (e.g., *.mov,*.mp4)
  --exclude TEXT      File patterns to exclude
```

### Sync Command

```
ingesta sync [OPTIONS]

Options:
  --video-dir PATH    Directory containing video files (required)
  --audio-dir PATH    Directory containing audio files (required)
  --output-dir PATH   Output directory for synced files (required)
  --tolerance FLOAT   Sync tolerance in seconds (default: 0.3)
  --prefix TEXT       Prefix for output filenames
  --method TEXT       Sync method: waveform, timecode (default: waveform)
```

### Premiere Command

```
ingesta premiere [OPTIONS]

Options:
  --media-dir PATH    Directory containing media files (required)
  --output PATH       Output path for .prproj file (required)
  --name TEXT         Project name
  --fps FLOAT         Frame rate (default: 24)
  --resolution TEXT   Resolution as WIDTHxHEIGHT (default: 1920x1080)
  --create-bins       Automatically create bins for organization
```

### Report Command

```
ingesta report [OPTIONS]

Options:
  --media-dir PATH    Directory containing media files (required)
  --output-dir PATH   Output directory for reports (default: ./reports)
  --format TEXT       Report format: pdf, csv, both (default: both)
  --thumbnails        Generate thumbnails (default: enabled)
  --no-thumbnails     Skip thumbnail generation
  --project-name TEXT Project name for report
  --source-path TEXT  Source media path for report metadata
  --dest-path PATH    Destination/archive path (can use multiple times)
```

## Project Structure

```
ingesta/
├── ingesta/
│   ├── __init__.py
│   ├── checksum.py      # MD5/SHA256 utilities
│   ├── ingestion.py     # File copying & verification
│   ├── sync.py          # Waveform matching & audio sync
│   ├── premiere.py      # Premiere project generation
│   ├── analysis.py      # Content analysis & classification
│   ├── cli.py           # Command-line interface
│   └── reports/         # Report generation
│       ├── __init__.py
│       ├── xml_parser.py    # Camera XML sidecar parser
│       ├── thumbnails.py    # Thumbnail extraction
│       ├── csv_report.py    # CSV report generator
│       └── pdf_report.py    # PDF report generator
├── tests/
│   └── test_*.py
├── README.md
├── requirements.txt
└── setup.py
```

## How It Works

### Checksum Verification

During ingestion, files are copied with concurrent checksum calculation:

1. Read file in chunks
2. Update checksum hash incrementally
3. Write chunks to destination
4. Compare source and destination checksums
5. Generate verification report

### Waveform Sync

Audio synchronization uses cross-correlation of audio waveforms:

1. Extract audio from video file
2. Load external audio file
3. Normalize and preprocess both signals
4. Compute cross-correlation
5. Find peak correlation (offset)
6. Shift external audio to match
7. Merge into output file

### Premiere Project Generation

Projects are generated as XML (.prproj) files:

1. Scan media directory for supported formats
2. Create project structure with bins
3. Generate clip metadata (duration, resolution, etc.)
4. Build sequence with tracks
5. Write Premiere-compatible XML

## License

MIT License

## Contributing

Contributions welcome! Please submit pull requests or open issues on GitHub.

## Acknowledgments

- Inspired by Shotput Pro and Pluralize workflows
- Uses FFmpeg, librosa, and other open-source libraries
