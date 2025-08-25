# Princer - Prince Song Tagger

A CLI tool for tagging and organizing Prince audio files using fingerprinting, metadata fusion, and AI normalization.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Tag a single file
tagger audio.mp3

# Tag in batch mode
tagger /path/to/music --batch

# Show file info only
tagger info audio.mp3
```

## Features

- Audio fingerprinting via AcoustID
- MusicBrainz integration
- PrinceVault database matching
- AI-powered metadata normalization
- Tag-only or Copy+Place modes
- Interactive approval flow

## Configuration

Copy `config/default.yaml` and customize for your setup.

## Development

```bash
pip install -e ".[dev]"
pytest
```

See [docs/](docs/) for detailed documentation.