"""MusicBrainz service for metadata lookup."""

import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import musicbrainzngs as mb
from princer.core.config import Config


@dataclass
class MBRecording:
    """MusicBrainz recording data."""
    
    id: str
    title: str
    artist_name: str
    artist_id: str
    length: Optional[int] = None  # Duration in milliseconds
    disambiguation: Optional[str] = None
    date: Optional[str] = None
    releases: List[Dict[str, Any]] = None


@dataclass 
class MBLookupResult:
    """Result of MusicBrainz lookup."""
    
    recordings: List[MBRecording]
    error: Optional[str] = None


class MusicBrainzService:
    """Service for MusicBrainz metadata lookup."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Configure musicbrainzngs
        mb.set_useragent(
            app=config.api.musicbrainz_user_agent.split('/')[0],
            version=config.api.musicbrainz_user_agent.split('/')[1].split(' ')[0],
            contact=config.api.musicbrainz_user_agent.split('(')[1].split(')')[0]
        )
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # MusicBrainz allows 1 req/sec for open data
        
    def _rate_limit(self):
        """Ensure we don't exceed MusicBrainz rate limits."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def lookup_recordings(self, recording_ids: List[str]) -> MBLookupResult:
        """Look up MusicBrainz recordings by ID."""
        
        recordings = []
        errors = []
        
        for recording_id in recording_ids:
            try:
                self._rate_limit()
                self.logger.info(f"Looking up MusicBrainz recording: {recording_id}")
                
                result = mb.get_recording_by_id(
                    recording_id,
                    includes=['artists', 'releases', 'artist-credits']
                )
                
                recording_data = result['recording']
                recording = self._parse_recording(recording_data)
                recordings.append(recording)
                
            except mb.WebServiceError as e:
                self.logger.warning(f"MusicBrainz API error for {recording_id}: {e}")
                errors.append(f"API error for {recording_id}: {str(e)}")
                
            except Exception as e:
                self.logger.error(f"Unexpected error looking up {recording_id}: {e}")
                errors.append(f"Error for {recording_id}: {str(e)}")
        
        error_msg = "; ".join(errors) if errors else None
        return MBLookupResult(recordings=recordings, error=error_msg)
    
    def _parse_recording(self, recording_data: Dict[str, Any]) -> MBRecording:
        """Parse MusicBrainz recording data into our format."""
        
        # Extract basic info
        recording_id = recording_data['id']
        title = recording_data.get('title', 'Unknown Title')
        length = recording_data.get('length')  # in milliseconds
        disambiguation = recording_data.get('disambiguation')
        
        # Extract artist info (may be multiple artists)
        artist_name = "Unknown Artist"
        artist_id = ""
        
        if 'artist-credit' in recording_data:
            artist_credits = recording_data['artist-credit']
            if artist_credits and len(artist_credits) > 0:
                first_artist = artist_credits[0]
                if isinstance(first_artist, dict) and 'artist' in first_artist:
                    artist_name = first_artist['artist'].get('name', artist_name)
                    artist_id = first_artist['artist'].get('id', '')
        
        # Extract release info
        releases = []
        if 'release-list' in recording_data:
            for release in recording_data['release-list'][:3]:  # Limit to first 3 releases
                release_info = {
                    'id': release.get('id'),
                    'title': release.get('title'),
                    'date': release.get('date'),
                    'status': release.get('status'),
                }
                releases.append(release_info)
        
        # Try to extract a date from releases
        date = None
        for release in releases:
            if release.get('date'):
                date = release['date']
                break
        
        return MBRecording(
            id=recording_id,
            title=title,
            artist_name=artist_name,
            artist_id=artist_id,
            length=length,
            disambiguation=disambiguation,
            date=date,
            releases=releases
        )
    
    def find_prince_recordings(self, title: str, limit: int = 5) -> MBLookupResult:
        """Search for Prince recordings by title."""
        
        try:
            self._rate_limit()
            self.logger.info(f"Searching MusicBrainz for Prince recording: '{title}'")
            
            # Search for recordings by Prince
            result = mb.search_recordings(
                query=f'recording:"{title}" AND artist:"Prince"',
                limit=limit
            )
            
            recordings = []
            for recording_data in result['recording-list']:
                recording = self._parse_recording(recording_data)
                recordings.append(recording)
            
            return MBLookupResult(recordings=recordings)
            
        except Exception as e:
            self.logger.error(f"Error searching MusicBrainz for '{title}': {e}")
            return MBLookupResult(recordings=[], error=str(e))
    
    def format_recording_summary(self, recording: MBRecording) -> str:
        """Format a recording for display."""
        
        parts = [f"'{recording.title}' by {recording.artist_name}"]
        
        if recording.date:
            parts.append(f"({recording.date})")
        
        if recording.disambiguation:
            parts.append(f"[{recording.disambiguation}]")
        
        if recording.length:
            duration_sec = recording.length // 1000
            minutes = duration_sec // 60
            seconds = duration_sec % 60
            parts.append(f"{minutes}:{seconds:02d}")
        
        return " ".join(parts)