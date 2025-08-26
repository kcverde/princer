"""Configuration management for Princer."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

import yaml
from dotenv import load_dotenv


@dataclass
class PathConfig:
    """Path-related configuration."""
    
    root: str = "/Volumes/Music/Prince"
    category_roots: Dict[str, str] = field(default_factory=lambda: {
        "official": "Official",
        "unofficial": "Unofficial", 
        "live": "Live",
        "outtakes": "Outtakes"
    })
    logs: Optional[str] = None
    pv_sqlite: str = "/Users/kverde/dev/Projects/princer/princevault.db"
    pv_xml_dir: str = "~/data/princevault/xml"


@dataclass
class BehaviorConfig:
    """Behavior and mode configuration."""
    
    tag_only: bool = False
    copy_files: bool = True
    move_files: bool = False
    write_tags: bool = True
    ask_confirmation: bool = True
    llm_always: bool = True
    min_auto_score: Optional[float] = None


@dataclass
class NamingConfig:
    """Naming and template configuration."""
    
    rules_file: str = "config/naming_rules.md"
    rules_format: str = "text"
    templates_default: Dict[str, str] = field(default_factory=lambda: {
        "live": "{date} - {city} - {venue} - {tracknum} {title} [{source}]{lineage_short}",
        "outtake": "{era}/{session_date} - {title}",
        "official": "{album}/{tracknum} {title}",
        "unofficial": "{setname}/{tracknum} {title}"
    })


@dataclass
class FieldsConfig:
    """Field handling configuration."""
    
    keep_custom_tags: List[str] = field(default_factory=lambda: [
        "LINEAGE", "TAPER", "TRANSFER"
    ])
    prefer_dates_from: List[str] = field(default_factory=lambda: [
        "PrinceVault", "MusicBrainz", "FileTags"
    ])


@dataclass
class ApiConfig:
    """API configuration."""
    
    acoustid_key: str = "env:ACOUSTID_KEY"
    musicbrainz_user_agent: str = "PrinceTagger/0.1 (you@example.com)"


@dataclass
class LlmConfig:
    """LLM configuration."""
    
    provider: str = "openrouter"  # openrouter or openai
    model: str = "google/gemini-2.5-flash"
    temperature: float = 0.2
    max_tokens: int = 800  # Increased for more detailed responses
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


@dataclass
class Config:
    """Main configuration object."""
    
    paths: PathConfig = field(default_factory=PathConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    fields: FieldsConfig = field(default_factory=FieldsConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    
    def resolve_env_vars(self) -> None:
        """Resolve environment variable references in config values."""
        # Resolve API key
        if self.api.acoustid_key.startswith("env:"):
            env_var = self.api.acoustid_key[4:]
            self.api.acoustid_key = os.getenv(env_var, "")
            
        # Resolve paths with ~ expansion
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
    """Handles loading and saving configuration files."""
    
    DEFAULT_CONFIG_PATHS = [
        "config/default.yaml",
        "princer.yaml", 
        "~/.princer/config.yaml",
        "~/.config/princer/config.yaml"
    ]
    
    @classmethod
    def load(cls, config_path: Optional[Union[str, Path]] = None) -> Config:
        """Load configuration from file or defaults."""
        
        # Load .env file first (look in current directory)
        cls._load_env_file()
        
        if config_path:
            return cls._load_from_path(Path(config_path))
            
        # Try default locations
        for default_path in cls.DEFAULT_CONFIG_PATHS:
            path = Path(default_path).expanduser()
            if path.exists():
                return cls._load_from_path(path)
                
        # Return default config
        config = Config()
        config.resolve_env_vars()
        return config
    
    @classmethod
    def _load_env_file(cls) -> None:
        """Load environment variables from .env file."""
        
        # Look for .env file in current directory and parent directories
        env_paths = [
            Path(".env"),
            Path("../.env"),
            Path.home() / ".princer" / ".env"
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                break
    
    @classmethod
    def _load_from_path(cls, config_path: Path) -> Config:
        """Load configuration from a specific path."""
        try:
            with config_path.open('r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                
            config = cls._dict_to_config(data)
            config.resolve_env_vars()
            return config
            
        except Exception as e:
            raise RuntimeError(f"Failed to load config from {config_path}: {e}")
    
    @classmethod
    def _dict_to_config(cls, data: Dict[str, Any]) -> Config:
        """Convert dictionary to Config object."""
        
        config = Config()
        
        # Update paths
        if 'paths' in data:
            paths_data = data['paths']
            config.paths = PathConfig(
                root=paths_data.get('root', config.paths.root),
                category_roots=paths_data.get('category_roots', config.paths.category_roots),
                logs=paths_data.get('logs', config.paths.logs),
                pv_sqlite=paths_data.get('pv_sqlite', config.paths.pv_sqlite),
                pv_xml_dir=paths_data.get('pv_xml_dir', config.paths.pv_xml_dir)
            )
        
        # Update behavior
        if 'behavior' in data:
            behavior_data = data['behavior']
            config.behavior = BehaviorConfig(
                tag_only=behavior_data.get('tag_only', config.behavior.tag_only),
                copy_files=behavior_data.get('copy_files', config.behavior.copy_files),
                move_files=behavior_data.get('move_files', config.behavior.move_files),
                write_tags=behavior_data.get('write_tags', config.behavior.write_tags),
                ask_confirmation=behavior_data.get('ask_confirmation', config.behavior.ask_confirmation),
                llm_always=behavior_data.get('llm_always', config.behavior.llm_always),
                min_auto_score=behavior_data.get('min_auto_score', config.behavior.min_auto_score)
            )
        
        # Update naming
        if 'naming' in data:
            naming_data = data['naming']
            config.naming = NamingConfig(
                rules_file=naming_data.get('rules_file', config.naming.rules_file),
                rules_format=naming_data.get('rules_format', config.naming.rules_format),
                templates_default=naming_data.get('templates_default', config.naming.templates_default)
            )
        
        # Update fields
        if 'fields' in data:
            fields_data = data['fields']
            config.fields = FieldsConfig(
                keep_custom_tags=fields_data.get('keep_custom_tags', config.fields.keep_custom_tags),
                prefer_dates_from=fields_data.get('prefer_dates_from', config.fields.prefer_dates_from)
            )
        
        # Update API
        if 'api' in data:
            api_data = data['api']
            config.api = ApiConfig(
                acoustid_key=api_data.get('acoustid_key', config.api.acoustid_key),
                musicbrainz_user_agent=api_data.get('musicbrainz_user_agent', config.api.musicbrainz_user_agent)
            )
        
        # Update LLM
        if 'llm' in data:
            llm_data = data['llm']
            config.llm = LlmConfig(
                provider=llm_data.get('provider', config.llm.provider),
                model=llm_data.get('model', config.llm.model),
                temperature=llm_data.get('temperature', config.llm.temperature),
                max_tokens=llm_data.get('max_tokens', config.llm.max_tokens),
                approval_required=llm_data.get('approval_required', config.llm.approval_required),
                system_prompt=llm_data.get('system_prompt', config.llm.system_prompt)
            )
        
        return config
    
    @classmethod
    def save_default(cls, config_path: Union[str, Path]) -> None:
        """Save a default configuration file."""
        
        config = Config()
        data = cls._config_to_dict(config)
        
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with path.open('w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
    
    @classmethod
    def _config_to_dict(cls, config: Config) -> Dict[str, Any]:
        """Convert Config object to dictionary."""
        
        return {
            'paths': {
                'root': config.paths.root,
                'category_roots': config.paths.category_roots,
                'logs': config.paths.logs,
                'pv_sqlite': config.paths.pv_sqlite,
                'pv_xml_dir': config.paths.pv_xml_dir
            },
            'behavior': {
                'tag_only': config.behavior.tag_only,
                'copy_files': config.behavior.copy_files,
                'move_files': config.behavior.move_files,
                'write_tags': config.behavior.write_tags,
                'ask_confirmation': config.behavior.ask_confirmation,
                'llm_always': config.behavior.llm_always,
                'min_auto_score': config.behavior.min_auto_score
            },
            'naming': {
                'rules_file': config.naming.rules_file,
                'rules_format': config.naming.rules_format,
                'templates_default': config.naming.templates_default
            },
            'fields': {
                'keep_custom_tags': config.fields.keep_custom_tags,
                'prefer_dates_from': config.fields.prefer_dates_from
            },
            'api': {
                'acoustid_key': config.api.acoustid_key,
                'musicbrainz_user_agent': config.api.musicbrainz_user_agent
            },
            'llm': {
                'provider': config.llm.provider,
                'model': config.llm.model,
                'temperature': config.llm.temperature,
                'max_tokens': config.llm.max_tokens,
                'approval_required': config.llm.approval_required,
                'system_prompt': config.llm.system_prompt
            }
        }