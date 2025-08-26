# Princer - Prince Song Tagger

A CLI tool for tagging and organizing Prince audio files using fingerprinting, metadata fusion, and AI normalization.

## Current Status: Phase 1 Complete ✅

**Working now:**
- Audio file metadata extraction (MP3, FLAC, M4A, WAV, OGG)
- CLI with `info` command to display file details
- Tag reading from ID3 and Vorbis formats
- Clean, formatted output using Rich tables

**Coming next:**
- AcoustID fingerprinting
- MusicBrainz integration
- AI-powered metadata normalization

## Quick Start

```bash
# Set up virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Analyze an audio file
tagger info "your-prince-file.mp3"
```

## Current Features

- ✅ **Audio file reading** - Supports MP3, FLAC, M4A, WAV, OGG
- ✅ **Metadata extraction** - Tags, duration, bitrate, sample rate, channels
- ✅ **Smart approach** - LLM will handle complex filename parsing (no brittle regex)
- ✅ **Clean CLI** - Rich-formatted tables for easy reading
- 🚧 **AcoustID fingerprinting** - Coming in Phase 2
- 🚧 **MusicBrainz integration** - Coming in Phase 2
- 🚧 **PrinceVault database** - Coming in Phase 3
- 🚧 **AI normalization** - Coming in Phase 4

## Example Output

```
tagger info "testfiles/Purple Rain.mp3"

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

                Tags                
┌──────────────┬─────────────────────┐
│ Tag          │ Value               │
├──────────────┼─────────────────────┤
│ artist       │ Prince              │
│ title        │ Purple Rain         │
│ album        │ Purple Rain         │
│ date         │ 1984                │
└──────────────┴─────────────────────┘
```

## Configuration

Configuration files in `config/`:
- `default.yaml` - Main configuration 
- `naming_rules.md` - Human-readable naming rules for the LLM
- `.env.example` - Template for API keys

## Development

This project uses incremental development with frequent testing:

```bash
# Set up development environment
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests (when we add them)
pytest

# Format code
black princer/
```

## Architecture Philosophy

**Simple and LLM-first:**
- Let AI handle complex pattern matching instead of brittle regex
- Incremental development with working pieces at each phase  
- User approval required - never auto-apply changes
- Non-destructive by default (copy, don't move originals)

See the [PRD.md](PRD.md) for complete requirements and [planning docs](docs/) for detailed phase breakdown.