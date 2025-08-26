# Changelog

## [0.1.0] - 2025-08-26 - Phase 1 Complete

### Added
- **CLI Interface**: `tagger` command with `info` subcommand
- **Audio File Support**: MP3, FLAC, M4A, WAV, OGG formats
- **Metadata Extraction**: Complete tag reading from ID3 and Vorbis formats
- **File Analysis**: Duration, bitrate, sample rate, channel count
- **Rich Output**: Beautiful formatted tables for file information
- **Configuration System**: YAML-based configuration with environment variable support
- **Naming Rules**: Human-readable naming rules file for future LLM processing

### Architecture Decisions
- **Simplified Approach**: Removed complex filename parsing in favor of LLM processing
- **Virtual Environment**: Required for clean dependency management
- **Incremental Development**: Working functionality at each phase
- **Non-Destructive**: Copy-first approach, preserve originals

### Dependencies
- `typer` + `rich` for CLI and output formatting
- `mutagen` for audio file metadata reading  
- `pyyaml` for configuration management
- Future: `pyacoustid`, `musicbrainzngs`, `openai` for upcoming phases

### Test Results
- ✅ MP3 files with ID3 tags
- ✅ FLAC files with Vorbis comments
- ✅ Proper bitrate display (fixed conversion from bps to kbps)
- ✅ Error handling for missing files and unsupported formats

### Next Phase
Phase 2: Audio fingerprinting with AcoustID integration