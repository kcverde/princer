"""LLM service for metadata normalization using OpenRouter or OpenAI."""

import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from openai import OpenAI
from princer.core.config import Config


@dataclass
class MetadataNormalizationRequest:
    """Request for LLM metadata normalization."""
    
    # Source data
    filename: str
    acoustid_data: Dict[str, Any]
    musicbrainz_data: Optional[Dict[str, Any]] = None
    princevault_data: Optional[Dict[str, Any]] = None
    
    # Additional context
    file_tags: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    format_info: Optional[str] = None
    bitrate: Optional[str] = None


@dataclass  
class NormalizedMetadata:
    """Normalized metadata output from LLM."""
    
    # Core metadata
    title: str
    artist: str
    album: Optional[str] = None
    track_number: Optional[int] = None
    year: Optional[int] = None
    date: Optional[str] = None
    
    # Prince-specific
    category: Optional[str] = None  # official, live, outtakes, unofficial
    recording_date: Optional[str] = None
    venue: Optional[str] = None
    session_info: Optional[str] = None
    
    # Additional
    genre: Optional[str] = None
    comments: Optional[str] = None
    confidence: float = 0.0
    
    # Raw LLM response for debugging
    llm_response: Optional[str] = None


class LLMService:
    """Service for LLM-based metadata normalization."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize OpenAI client
        if config.llm.provider.lower() == "openrouter":
            api_key = self._get_api_key("OPENROUTER_API_KEY")
            base_url = "https://openrouter.ai/api/v1"
            self.model = self._get_model("OPENROUTER_MODEL", config.llm.model)
            
            # Add OpenRouter-specific headers
            self.extra_headers = {
                "HTTP-Referer": "https://github.com/kcverde/princer",
                "X-Title": "Prince Song Tagger"
            }
        else:
            # Default to OpenAI
            api_key = self._get_api_key("OPENAI_API_KEY") 
            base_url = None  # Use default OpenAI base URL
            self.model = config.llm.model
            self.extra_headers = {}
        
        if not api_key:
            self.logger.warning(f"No API key found for {config.llm.provider}")
            self.client = None
        else:
            self.logger.debug(f"Using API key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )
    
    def _get_api_key(self, env_var: str) -> Optional[str]:
        """Get API key from environment."""
        import os
        return os.getenv(env_var)
    
    def _get_model(self, env_var: str, default: str) -> str:
        """Get model from environment or use default."""
        import os
        return os.getenv(env_var, default)
    
    def test_connection(self) -> Dict[str, Any]:
        """Test LLM connectivity with a simple query."""
        
        if not self.client:
            return {
                "success": False,
                "error": "No API key configured"
            }
        
        try:
            self.logger.info(f"Testing LLM connection with provider: {self.config.llm.provider}")
            self.logger.info(f"Testing LLM connection with model: {self.model}")
            self.logger.info(f"Base URL: {self.client.base_url}")
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": "Hello! Please respond with exactly: 'LLM connection test successful'"
                    }
                ],
                temperature=0.0,
                max_tokens=50,
                extra_headers=self.extra_headers
            )
            
            response = completion.choices[0].message.content.strip()
            
            return {
                "success": True,
                "model": self.model,
                "response": response,
                "usage": {
                    "prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
                    "completion_tokens": completion.usage.completion_tokens if completion.usage else 0,
                    "total_tokens": completion.usage.total_tokens if completion.usage else 0
                } if completion.usage else None
            }
            
        except Exception as e:
            self.logger.error(f"LLM connection test failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def normalize_metadata(self, request: MetadataNormalizationRequest) -> NormalizedMetadata:
        """Normalize metadata using LLM."""
        
        if not self.client:
            return NormalizedMetadata(
                title="Unknown",
                artist="Unknown", 
                llm_response="No LLM client available"
            )
        
        try:
            # Build comprehensive prompt with all available data
            prompt = self._build_normalization_prompt(request)
            
            self.logger.info(f"Normalizing metadata for: {request.filename}")
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self.config.llm.system_prompt
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                extra_headers=self.extra_headers
            )
            
            response = completion.choices[0].message.content.strip()
            
            # Parse JSON response - handle markdown code blocks
            try:
                # Remove markdown code block markers if present
                json_text = response
                if json_text.startswith('```json'):
                    json_text = json_text[7:]  # Remove ```json
                if json_text.endswith('```'):
                    json_text = json_text[:-3]  # Remove ```
                json_text = json_text.strip()
                
                data = json.loads(json_text)
                return NormalizedMetadata(
                    title=data.get("title", "Unknown"),
                    artist=data.get("artist", "Unknown"),
                    album=data.get("album"),
                    track_number=data.get("track_number"),
                    year=data.get("year"),
                    date=data.get("date"),
                    category=data.get("category"),
                    recording_date=data.get("recording_date"),
                    venue=data.get("venue"),
                    session_info=data.get("session_info"),
                    genre=data.get("genre"),
                    comments=data.get("comments"),
                    confidence=data.get("confidence", 0.0),
                    llm_response=response
                )
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return NormalizedMetadata(
                    title="Unknown",
                    artist="Unknown",
                    llm_response=response,
                    comments="Failed to parse LLM JSON response"
                )
                
        except Exception as e:
            self.logger.error(f"LLM normalization failed: {e}")
            return NormalizedMetadata(
                title="Unknown", 
                artist="Unknown",
                llm_response=f"Error: {str(e)}"
            )
    
    def _build_normalization_prompt(self, request: MetadataNormalizationRequest) -> str:
        """Build comprehensive prompt for metadata normalization using template."""
        
        # Format file info
        duration = f"{request.duration_seconds:.1f}" if request.duration_seconds else "Unknown"
        format_info = request.format_info or "Unknown"
        bitrate = request.bitrate or "Unknown"
        
        # Format current tags
        if request.file_tags:
            current_tags = []
            for key, value in request.file_tags.items():
                current_tags.append(f"  {key.title()}: {value}")
            current_tags_str = "\n".join(current_tags)
        else:
            current_tags_str = "  No tags found"
        
        # Format AcoustID data
        acoustid_str = ""
        if request.acoustid_data:
            acoustid_lines = ["AcoustID matches:"]
            for i, match in enumerate(request.acoustid_data.get('matches', [])[:3], 1):
                acoustid_lines.append(f"  {i}. Title: {match.get('title', 'Unknown')} | Artist: {match.get('artist', 'Unknown')} | Score: {match.get('score', 0):.3f}")
            acoustid_str = "\n".join(acoustid_lines)
        else:
            acoustid_str = "No AcoustID matches"
        
        # Format MusicBrainz data
        musicbrainz_str = ""
        if request.musicbrainz_data:
            mb_lines = [
                "MusicBrainz details:",
                f"  Recording ID: {request.musicbrainz_data.get('id', 'N/A')}",
                f"  Title: {request.musicbrainz_data.get('title', 'Unknown')}",
                f"  Artist: {request.musicbrainz_data.get('artist_name', 'Unknown')}",
                f"  Date: {request.musicbrainz_data.get('date', 'Unknown')}",
                f"  Duration: {request.musicbrainz_data.get('length', 'Unknown')}",
            ]
            
            if request.musicbrainz_data.get('disambiguation'):
                mb_lines.append(f"  Context: {request.musicbrainz_data['disambiguation']}")
            
            if request.musicbrainz_data.get('releases'):
                mb_lines.append("  Releases:")
                for release in request.musicbrainz_data['releases'][:2]:
                    mb_lines.append(f"    - {release.get('title', 'Unknown')} ({release.get('date', 'Unknown')})")
            
            musicbrainz_str = "\n".join(mb_lines)
        else:
            musicbrainz_str = "No MusicBrainz data"
        
        # Format PrinceVault data
        princevault_str = ""
        if request.princevault_data:
            pv_lines = [
                "PrinceVault details:",
                f"  Title: {request.princevault_data.get('title', 'Unknown')}",
                f"  Recording Date: {request.princevault_data.get('recording_date', 'Unknown')}",
                f"  Performer: {request.princevault_data.get('performer', 'Unknown')}",
                f"  Confidence: {request.princevault_data.get('confidence', 0):.2f}",
            ]
            
            if request.princevault_data.get('session_info'):
                pv_lines.append(f"  Session: {request.princevault_data['session_info']}")
            
            if request.princevault_data.get('written_by'):
                pv_lines.append(f"  Written By: {request.princevault_data['written_by']}")
                
            if request.princevault_data.get('produced_by'):
                pv_lines.append(f"  Produced By: {request.princevault_data['produced_by']}")
            
            if request.princevault_data.get('personnel'):
                personnel = request.princevault_data['personnel']
                if isinstance(personnel, list):
                    pv_lines.append(f"  Personnel: {'; '.join(personnel[:3])}")
                else:
                    pv_lines.append(f"  Personnel: {personnel}")
            
            if request.princevault_data.get('album_appearances'):
                pv_lines.append(f"  Albums: {'; '.join(request.princevault_data['album_appearances'][:2])}")
                
            if request.princevault_data.get('related_versions'):
                pv_lines.append(f"  Related Versions: {'; '.join(request.princevault_data['related_versions'][:2])}")
                
            if request.princevault_data.get('categories'):
                pv_lines.append(f"  Categories: {', '.join(request.princevault_data['categories'][:5])}")
                
            # Include raw content snippet if available for additional context
            if request.princevault_data.get('raw_content'):
                content = request.princevault_data['raw_content'][:200] + "..." if len(request.princevault_data['raw_content']) > 200 else request.princevault_data['raw_content']
                pv_lines.append(f"  Raw Content Snippet: {content}")
            
            princevault_str = "\n".join(pv_lines)
        else:
            princevault_str = "No PrinceVault data"
        
        # Use the template from config
        return self.config.llm.user_prompt_template.format(
            filename=request.filename,
            duration=duration,
            format=format_info,
            bitrate=bitrate,
            current_tags=current_tags_str,
            acoustid_data=acoustid_str,
            musicbrainz_data=musicbrainz_str,
            princevault_data=princevault_str
        )