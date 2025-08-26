# Quick Start Guide

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd princer

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .
```

## Test the Current Functionality

```bash
# Analyze an audio file
tagger info "path/to/your/prince-file.mp3"

# Test with the included samples
tagger info "testfiles/84_024 Prince & The Revolution - Purple Rain.mp3"
tagger info "testfiles/Always in My Hair (Soundboard).mp3"
tagger info "testfiles/[1988] - By Alien Means {Outtake}.flac"
```

## What Works Now (Phase 1)

- ✅ Audio file reading (MP3, FLAC, M4A, WAV, OGG)
- ✅ Metadata extraction (tags, duration, bitrate, etc.)
- ✅ Clean CLI output with Rich formatting
- ✅ Configuration system (YAML + naming rules)

## Example Output

```
$ tagger info "Purple Rain.mp3"

  Audio File: Purple Rain.mp3    
┌──────────────────────┬──────────┐
│ Property             │ Value    │
├──────────────────────┼──────────┤
│ File Size            │ 4.6 MB   │
│ Duration             │ 4:01     │
│ Bitrate              │ 160 kbps │
│ Sample Rate          │ 44100 Hz │
│ Channels             │ 2        │
└──────────────────────┴──────────┘

Raw filename: Purple Rain.mp3
```

## Configuration

The tool loads configuration from these locations (in order):
1. `config/default.yaml` (included)
2. `princer.yaml` (in current directory)
3. `~/.princer/config.yaml`
4. `~/.config/princer/config.yaml`

API keys go in a `.env` file (see `.env.example`).

## Next Steps

Phase 2 will add:
- Audio fingerprinting via AcoustID
- MusicBrainz integration
- Basic matching and proposal system

See the [CHANGELOG.md](../CHANGELOG.md) for development progress.