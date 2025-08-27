"""Configuration management using Pydantic Settings."""

import os
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class PathConfig(BaseSettings):
    """Path-related configuration."""
    
    root: str = "/Volumes/Music/Prince"
    category_roots: Dict[str, str] = {
        "official": "Official",
        "unofficial": "Unofficial", 
        "live": "Live",
        "outtakes": "Outtakes"
    }
    logs: Optional[str] = None
    pv_sqlite: str = "/Users/kverde/dev/Projects/princer/princevault.db"
    pv_xml_dir: str = "~/data/princevault/xml"

    class Config:
        env_prefix = "PRINCER_PATHS_"


class BehaviorConfig(BaseSettings):
    """Behavior and mode configuration."""
    
    tag_only: bool = False
    copy_files: bool = True
    move_files: bool = False
    write_tags: bool = True
    ask_confirmation: bool = True
    llm_always: bool = True
    min_auto_score: Optional[float] = None

    class Config:
        env_prefix = "PRINCER_BEHAVIOR_"


class NamingConfig(BaseSettings):
    """Naming and template configuration."""
    
    rules_file: str = "config/naming_rules.md"
    rules_format: str = "text"
    templates_default: Dict[str, str] = {
        "live": "{date} - {city} - {venue} - {tracknum} {title} [{source}]{lineage_short}",
        "outtake": "{era}/{session_date} - {title}",
        "official": "{album}/{tracknum} {title}",
        "unofficial": "{setname}/{tracknum} {title}"
    }

    class Config:
        env_prefix = "PRINCER_NAMING_"


class FieldsConfig(BaseSettings):
    """Field handling configuration."""
    
    keep_custom_tags: List[str] = ["LINEAGE", "TAPER", "TRANSFER"]
    prefer_dates_from: List[str] = ["PrinceVault", "MusicBrainz", "FileTags"]

    class Config:
        env_prefix = "PRINCER_FIELDS_"


class ApiConfig(BaseSettings):
    """API configuration."""
    
    acoustid_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    musicbrainz_user_agent: str = "PrinceTagger/0.1 (you@example.com)"

    class Config:
        env_prefix = ""
        env_file = [".env", "../.env", "~/.princer/.env"]
        env_file_encoding = 'utf-8'
        extra = 'ignore'


class LlmConfig(BaseSettings):
    """LLM configuration."""
    
    provider: str = "openrouter"
    model: str = "google/gemini-2.5-flash"
    temperature: float = 0.2
    max_tokens: int = 800
    approval_required: bool = True
    system_prompt: str = (
        "You are a Prince music metadata expert. Analyze the provided data sources "
        "(AcoustID, MusicBrainz, PrinceVault) and return normalized metadata in strict JSON format. "
        "Prioritize accuracy over guessing. Use Prince-specific knowledge for categories and context. "
        "Categories: official (commercial releases), live (concerts), outtakes (studio outtakes/demos), "
        "unofficial (bootleg compilations). Never invent information not supported by the sources."
    )
    user_prompt_template: str = (
        "Normalize metadata for audio file: {filename}\n"
        "Duration: {duration} seconds\n"
        "Format: {format}\n"
        "Bitrate: {bitrate}\n\n"
        "CURRENT FILE TAGS:\n{current_tags}\n\n"
        "AVAILABLE DATA SOURCES:\n{acoustid_data}\n{musicbrainz_data}\n{princevault_data}\n\n"
        "Please return normalized metadata in JSON format with these fields:\n"
        "{{\n"
        '  "title": "song title",\n'
        '  "artist": "artist name",\n'
        '  "album": "album name or null",\n'
        '  "track_number": number or null,\n'
        '  "year": 4-digit year or null,\n'
        '  "date": "YYYY-MM-DD or YYYY or null",\n'
        '  "category": "official/live/outtakes/unofficial",\n'
        '  "recording_date": "YYYY-MM-DD or descriptive date",\n'
        '  "venue": "recording location or null",\n'
        '  "session_info": "session details or null",\n'
        '  "genre": "music genre or null",\n'
        '  "comments": "additional context or null",\n'
        '  "confidence": 0.0-1.0 score\n'
        "}}\n\n"
        "Return ONLY valid JSON, no other text."
    )

    class Config:
        env_prefix = "PRINCER_LLM_"


class Config(BaseSettings):
    """Main configuration object."""
    
    paths: PathConfig = Field(default_factory=PathConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    naming: NamingConfig = Field(default_factory=NamingConfig)
    fields: FieldsConfig = Field(default_factory=FieldsConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)

    class Config:
        env_file = [".env", "../.env", "~/.princer/.env"]
        env_file_encoding = 'utf-8'
        case_sensitive = False
        extra = 'ignore'
        env_nested_delimiter = '__'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._expand_paths()

    def _expand_paths(self):
        """Expand user paths and resolve environment variables."""
        self.paths.pv_sqlite = os.path.expanduser(self.paths.pv_sqlite)
        self.paths.pv_xml_dir = os.path.expanduser(self.paths.pv_xml_dir)

    def get_naming_rules_path(self) -> Path:
        """Get the full path to the naming rules file."""
        return Path(self.naming.rules_file)
        
    def load_naming_rules(self) -> str:
        """Load the naming rules text for the LLM."""
        rules_path = self.get_naming_rules_path()
        if rules_path.exists():
            return rules_path.read_text(encoding='utf-8')
        else:
            return self._get_default_naming_rules()
            
    def _get_default_naming_rules(self) -> str:
        """Get default naming rules if file doesn't exist."""
        return """# Default Naming Rules

## Categories
- Official: Commercial releases
- Live: Concert recordings 
- Outtakes: Studio outtakes and demos
- Unofficial: Bootleg compilations

## Templates
- Live: {date} - {city} - {venue} - {tracknum:02d} {title} [{source}]{lineage_short}
- Outtakes: {era}/{session_date} - {title}  
- Official: {album}/{tracknum:02d} {title}
- Unofficial: {setname}/{tracknum:02d} {title}

## Source Types
- SBD: Soundboard
- AUD: Audience recording
- FM: Radio broadcast
- TV: Television broadcast
- PRO: Professional recording

## Filename Rules
- Use only ASCII letters, numbers, spaces, hyphens, underscores, parentheses, and brackets
- Replace invalid characters with underscore
- Collapse multiple spaces
- Trim whitespace from ends
"""


class ConfigLoader:
    """Simple config loader."""
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> Config:
        """Load configuration."""
        if config_path:
            # For custom config files, we'd need to implement YAML loading
            # For now, just load with environment variables
            pass
        
        return Config()