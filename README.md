# Media Ingestion Tool

A Python-based media ingestion tool that combines Shotput Pro-style offloading with verification and Pluralize-style audio sync capabilities.

## Security & Privacy

**All processing is done locally on your machine. No media files, transcriptions, or analysis data is ever sent to external services or cloud providers.**

- Local transcription using whisper.cpp - no audio leaves your machine
- Local frame analysis using FFmpeg - no frames uploaded
- Local checksum generation and verification
- No internet connection required for core functionality
- Your media stays on your system

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
- **ShotPut-style bin/clip organization** - Group clips by folder structure (A001, B002, Sound_001, etc.) for editor-ready workflows
- **Local transcription** - Transcribe audio using whisper.cpp (fully offline)
- **Frame analysis** - Generate visual descriptions and detect shot types (fully offline)
- **Slate detection** - Automatically detect scene/take slates and end marks in audio
- **Audio technical analysis** - Peak/RMS levels, clipping detection, channel/sample rate analysis
- **Timecode & metadata extraction** - Extract timecode, reel IDs, scene/shot/take, camera info
- **Duplicate detection** - Find exact and near-duplicate clips
- **Quality warnings** - Detect black frames, blur, long silence, corruption
- **Proxy generation** - Create editing proxies and hero stills
- **Keyword tagging** - Extract tags from transcription and visual content

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

# ShotPut-style bin organization (groups clips by folder: A001, B002, Sound_001, etc.)
ingesta report -m ./ingested -o ./reports --group-by-folder

# Organized structure example:
# ./ingested/
#   A001/           → Bin: A001 (Camera Reel)
#     A001_001.MOV
#     A001_002.MOV
#   B002/           → Bin: B002 (Camera Reel)
#     B002_001.MOV
#   Sound_001/      → Bin: Sound_001 (Sound Roll)
#     AUDIO_001.WAV

# With local transcription and frame analysis (fully offline)
ingesta report -m ./media -o ./reports --transcribe --analyze-frames

# Transcription with larger model for better accuracy (slower)
ingesta report -m ./media --transcribe --whisper-model medium

# Frame analysis only
ingesta report -m ./media -o ./reports --analyze-frames

# Full technical analysis with audio metrics and metadata
ingesta report -m ./media -o ./reports \
    --analyze-audio-tech \
    --extract-metadata \
    --transcribe

# Quality control check with proxy generation
ingesta report -m ./media -o ./reports \
    --check-quality \
    --detect-duplicates \
    --generate-proxies

# Comprehensive analysis with all features
ingesta report -m ./media -o ./reports \
    --transcribe \
    --analyze-frames \
    --analyze-audio-tech \
    --extract-metadata \
    --detect-duplicates \
    --check-quality \
    --generate-proxies \
    --extract-keywords \
    --group-by-folder
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
  --media-dir PATH              Directory containing media files (required)
  --output-dir PATH             Output directory for reports (default: ./reports)
  --format TEXT                 Report format: pdf, csv, both (default: both)
  --thumbnails                  Generate thumbnails (default: enabled)
  --no-thumbnails               Skip thumbnail generation
  --project-name TEXT           Project name for report
  --source-path TEXT            Source media path for report metadata
  --dest-path PATH              Destination/archive path (can use multiple times)

  # Organization
  --group-by-folder             Group clips by folder structure (ShotPut-style bins)
                                Organizes clips into bins based on top-level folder names
                                (e.g., A001, B002, Sound_001) with filename fallback

  # Transcription & Analysis
  --transcribe                  Transcribe audio locally using whisper.cpp (default: False)
                                All transcription happens locally - no data sent online
  --analyze-frames              Analyze frames for visual description (default: False)
                                Frame analysis happens locally - no data sent online
  --analyze-audio-tech          Analyze audio technical details (peak, RMS, clipping)
  --extract-metadata            Extract timecode, reel IDs, camera metadata
  --extract-keywords            Extract keyword tags from transcription and visuals
  --whisper-model               Whisper model size: base, small, medium, large (default: base)
                                Larger models are more accurate but slower

  # Quality & Duplicates
  --detect-duplicates           Detect duplicate and near-duplicate clips
  --check-quality               Check for quality issues (black frames, blur, silence)

  # Proxy Generation
  --generate-proxies            Generate proxy files and hero stills
  --proxy-resolution            Proxy resolution (default: 960x540)
                                Options: 640x360, 960x540, 1280x720, 1920x1080
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
│       ├── xml_parser.py          # Camera XML sidecar parser
│       ├── thumbnails.py          # Thumbnail extraction
│       ├── csv_report.py          # CSV report generator
│       ├── pdf_report.py          # PDF report generator
│       ├── bin_organizer.py       # ShotPut-style bin/clip organization
│       ├── local_transcription.py # Local audio transcription (whisper.cpp)
│       ├── frame_analysis.py      # Local frame analysis for visual descriptions
│       ├── audio_tech.py          # Audio technical analysis (peak, RMS, clipping)
│       ├── metadata_extractor.py  # Timecode and metadata extraction
│       ├── duplicate_detector.py  # Duplicate and near-duplicate detection
│       ├── bad_clip_detector.py   # Quality warnings (black frames, blur, etc.)
│       ├── proxy_generator.py     # Proxy and hero still generation
│       └── keyword_tagger.py      # Keyword extraction from content
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

### ShotPut-Style Bin Organization

Bin organization provides editor-ready clip grouping based on production workflows:

**Folder-Based Grouping:**
Clips are organized by their top-level folder names:
- `A001/`, `B002/`, `C001/` → Camera reel bins
- `Sound_001/`, `Audio_A/` → Sound roll bins
- `Scene_01/`, `Shot_001/` → Scene-based bins

**Filename Fallback:**
If clips are not in organized folders, bin names are extracted from filenames:
- `A001_001.MOV` → Bin: A001
- `CAM01_clip001.MP4` → Bin: CAM01
- `SOUND_001.WAV` → Bin: SOUND_001

**Bin Types:**
- **Camera Reel**: Traditional A001, B002 naming
- **Sound Roll**: Audio/sound recordings
- **Scene**: Scene or shot-based organization
- **Generic**: Other folder structures

**Reports Generated:**
- **Binned CSV**: Detailed clip list with Bin, Bin Type, and Reel columns
- **Bin Summary CSV**: Overview of each bin with clip counts and durations
- **Binned PDF**: Organized by bin sections with bin-level summaries

### Local Transcription

Transcription uses whisper.cpp running entirely on your local machine:

**Security:**
- Audio is extracted temporarily and processed locally
- No audio data is uploaded to cloud services
- Transcription models run on your CPU/GPU
- No internet connection required

**Features:**
- Detects slate markers ("Scene 1", "Take 3", etc.)
- Detects end marks ("Cut", "And cut")
- Generates excerpt for quick reference
- Supports multiple languages (auto-detection)

**Models:**
- `base`: Fast, good accuracy (default)
- `small`: Better accuracy, moderate speed
- `medium`: High accuracy, slower
- `large`: Best accuracy, slowest

### Local Frame Analysis

Frame analysis extracts and analyzes key frames using FFmpeg:

**Security:**
- Frames are extracted temporarily and analyzed locally
- No images are uploaded to external services
- All analysis happens on your machine

**Features:**
- Estimates shot type (wide, medium, close-up)
- Detects scene type (interior/exterior)
- Measures brightness and contrast
- Detects camera movement
- Generates human-readable visual descriptions

**Output:**
- Visual description: "Medium shot interior - static camera"
- Shot type classification
- Brightness/contrast scores

### Audio Technical Analysis

Detailed audio metrics for quality control:

**Features:**
- **Peak Level**: Maximum audio level in dBFS
- **RMS Level**: Average audio level in dBFS
- **Clipping Detection**: Identifies audio clipping and counts instances
- **Channel Configuration**: Mono, stereo, multi-channel
- **Sample Rate**: 44.1kHz, 48kHz, 96kHz, etc.
- **Bit Depth**: 16-bit, 24-bit, etc.
- **Codec**: AAC, PCM, etc.
- **Warnings**: Alerts for clipping, low levels, long silence

**Security:**
- Audio extracted temporarily for analysis
- All processing done locally via FFmpeg
- No audio leaves your machine

### Metadata Extraction

Extract professional production metadata:

**Timecode:**
- Start timecode (HH:MM:SS:FF)
- End timecode
- Duration in timecode
- Frame rate detection
- Drop-frame flag

**Production Info:**
- Reel ID (A001, B002, etc.)
- Scene number
- Shot number
- Take number
- Camera ID

**Camera Metadata:**
- Camera model
- Serial number
- Lens information
- ISO
- White balance

**Security:**
- Metadata extracted via FFmpeg ffprobe
- No data sent to external services

### Duplicate Detection

Find duplicate and near-duplicate clips:

**Exact Duplicates:**
- File hash comparison (xxhash/MD5)
- Identical file detection

**Near-Duplicates:**
- Similar duration (within 5%)
- Similar file size (within 5%)
- Filename pattern matching
- Similarity score (0-1)

**Use Cases:**
- Identify backup copies
- Find accidentally imported duplicates
- Detect multiple takes of same shot

**Output:**
- Duplicate flag
- List of duplicate filenames
- Duplicate type (exact/near)
- Similarity percentage

### Quality Warnings

Automated quality control checks:

**Black Frame Detection:**
- Detects completely black frames
- Counts instances
- Critical warning if >10 frames

**Blur Detection:**
- Estimates focus/blur using edge detection
- Blur score 0-1
- Warning if severely out of focus

**Silence Detection:**
- Measures silence ratio
- Warns if >50% silence
- Detects no audio stream

**Corruption Detection:**
- Checks for decode errors
- Identifies truncated files
- Detects missing frames

**Exposure Issues:**
- Overexposed highlights (>240)
- Underexposed shadows (<15)

**Security:**
- All analysis done locally via FFmpeg
- No frames sent to external services

### Proxy Generation

Create editing proxies and preview files:

**Proxy Video:**
- Lower resolution (default 960x540)
- H.264 or ProRes codec
- Smaller file sizes
- Suitable for editing

**Hero Still:**
- Best frame extraction (10% into clip)
- High resolution (1920px width)
- JPEG format
- Thumbnail/preview ready

**Web Proxy:**
- Web-optimized H.264
- Fast start for web playback
- 1280x720 max resolution
- Suitable for web review

**Usage:**
```bash
# Generate proxies with default settings
ingesta report -m ./media --generate-proxies

# Custom proxy resolution
ingesta report -m ./media --generate-proxies --proxy-resolution 1280x720
```

**Security:**
- All transcoding done locally via FFmpeg
- No uploads required

### Keyword Tagging

Extract searchable tags from content:

**From Transcription:**
- Dialogue keywords (most frequent words)
- Topic extraction
- Named entities
- Technical terms

**From Visual Analysis:**
- Shot type tags (wide, medium, close-up)
- Scene type (interior/exterior)
- Production type (interview, b-roll, etc.)

**From Metadata:**
- Scene/shot/take numbers
- Reel IDs
- Camera information

**Priority Tags:**
- Most relevant tags across all sources
- Up to 10 priority tags per clip
- Production keywords boosted

**Output:**
- All tags (up to 30)
- Priority tags (top 10)
- CSV-friendly comma-separated format

**Security:**
- All processing done locally
- No text sent to external NLP services

### Full Analysis Example

Run comprehensive analysis with all features:

```bash
ingesta report -m ./media -o ./reports \
    --transcribe \
    --analyze-frames \
    --analyze-audio-tech \
    --extract-metadata \
    --detect-duplicates \
    --check-quality \
    --generate-proxies \
    --extract-keywords \
    --group-by-folder \
    --whisper-model medium
```

This will generate:
- PDF and CSV reports with all metadata
- Transcription excerpts and slate detection
- Visual descriptions and shot types
- Audio technical details (peak, RMS, clipping)
- Timecode, reel IDs, scene/shot/take
- Quality warnings for problematic clips
- Duplicate flags
- Proxy files and hero stills
- Keyword tags
- ShotPut-style bin organization

**Security Note:** All processing is done locally. No media, audio, or data is sent to external services.

## License

MIT License

## Contributing

Contributions welcome! Please submit pull requests or open issues on GitHub.

## Acknowledgments

- Inspired by Shotput Pro and Pluralize workflows
- Uses FFmpeg, librosa, and other open-source libraries
