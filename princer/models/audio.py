"""Audio file data models and utilities."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from mutagen import File as MutagenFile
from mutagen.id3 import ID3NoHeaderError


@dataclass
class FilenameParse:
    """Parsed components from filename."""
    
    date: Optional[str] = None
    city: Optional[str] = None
    venue: Optional[str] = None
    source_type: Optional[str] = None
    title: Optional[str] = None
    track_number: Optional[str] = None
    generation: Optional[str] = None
    extra_info: List[str] = field(default_factory=list)


@dataclass
class AudioFileInfo:
    """Complete audio file information."""
    
    path: Path
    filename: str
    extension: str
    duration_seconds: Optional[float] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    file_size: int = 0
    tags: Dict[str, Any] = field(default_factory=dict)
    filename_parse: Optional[FilenameParse] = None
    error: Optional[str] = None


class AudioFile:
    """Handles audio file metadata extraction and filename parsing."""
    
    SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.wav', '.ogg'}
    
    def __init__(self, file_path: str | Path):
        """Initialize with audio file path."""
        self.path = Path(file_path)
        self._mutagen_file: Optional[MutagenFile] = None
        
    def extract_info(self) -> AudioFileInfo:
        """Extract all available information from the audio file."""
        info = AudioFileInfo(
            path=self.path,
            filename=self.path.stem,
            extension=self.path.suffix.lower(),
            file_size=self.path.stat().st_size if self.path.exists() else 0
        )
        
        if not self.path.exists():
            info.error = "File not found"
            return info
            
        if info.extension not in self.SUPPORTED_EXTENSIONS:
            info.error = f"Unsupported file format: {info.extension}"
            return info
            
        try:
            # Load with mutagen
            self._mutagen_file = MutagenFile(self.path)
            if self._mutagen_file is None:
                info.error = "Could not read audio file"
                return info
                
            # Extract technical info
            info.duration_seconds = getattr(self._mutagen_file.info, 'length', None)
            info.bitrate = getattr(self._mutagen_file.info, 'bitrate', None)
            info.sample_rate = getattr(self._mutagen_file.info, 'sample_rate', None)
            info.channels = getattr(self._mutagen_file.info, 'channels', None)
            
            # Extract tags
            info.tags = self._extract_tags()
            
            # Store raw filename for LLM processing later
            info.filename_parse = FilenameParse()
            
        except Exception as e:
            info.error = f"Error reading file: {str(e)}"
            
        return info
    
    def _extract_tags(self) -> Dict[str, Any]:
        """Extract and normalize tags from the audio file."""
        if not self._mutagen_file:
            return {}
            
        tags = {}
        
        # Handle different tag formats
        if hasattr(self._mutagen_file, 'tags') and self._mutagen_file.tags:
            raw_tags = self._mutagen_file.tags
            
            # ID3 tags (MP3)
            if hasattr(raw_tags, 'getall'):
                # Common ID3 mappings
                tag_mappings = {
                    'TIT2': 'title',
                    'TPE1': 'artist', 
                    'TALB': 'album',
                    'TDRC': 'date',
                    'TRCK': 'track',
                    'TPOS': 'disc',
                    'TCON': 'genre',
                    'COMM::eng': 'comment',
                }
                
                for id3_key, common_key in tag_mappings.items():
                    values = raw_tags.getall(id3_key)
                    if values:
                        tags[common_key] = str(values[0])
                        
                # Handle custom TXXX tags
                for frame in raw_tags.getall('TXXX'):
                    if hasattr(frame, 'desc') and hasattr(frame, 'text'):
                        key = f"TXXX:{frame.desc}"
                        tags[key] = str(frame.text[0]) if frame.text else ""
                        
            # Vorbis comments (FLAC, OGG)
            else:
                for key, values in raw_tags.items():
                    if isinstance(values, list) and values:
                        tags[key.lower()] = values[0]
                    elif values:
                        tags[key.lower()] = str(values)
        
        return tags
    
        
    @classmethod
    def is_supported(cls, file_path: str | Path) -> bool:
        """Check if file extension is supported."""
        return Path(file_path).suffix.lower() in cls.SUPPORTED_EXTENSIONS
    
    def format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in MM:SS or HH:MM:SS format."""
        if not seconds:
            return "Unknown"
            
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"