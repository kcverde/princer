"""MusicBrainz service for metadata lookup."""

import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import musicbrainzngs as mb
from princer.core.config import Config


@dataclass
class MBWork:
    """MusicBrainz work (composition) data."""
    id: str
    title: str
    type: Optional[str] = None


@dataclass
class MBPlace:
    """MusicBrainz place data."""
    id: str
    name: str
    type: Optional[str] = None
    area: Optional[str] = None


@dataclass
class MBRelationship:
    """MusicBrainz relationship data."""
    type: str
    target_type: str
    target_id: str
    target_name: str
    direction: str
    attributes: List[str] = None


@dataclass
class MBRecording:
    """Enhanced MusicBrainz recording data."""
    
    # Core identification
    id: str
    title: str
    artist_name: str
    artist_id: str
    
    # Basic metadata  
    length: Optional[int] = None  # Duration in milliseconds
    disambiguation: Optional[str] = None
    date: Optional[str] = None
    
    # Release information
    releases: List[Dict[str, Any]] = None
    release_status: Optional[str] = None  # Official, Bootleg, etc.
    
    # Identifiers
    isrcs: List[str] = None
    acoustid: Optional[str] = None
    
    # Relationships
    works: List[MBWork] = None  # Original compositions
    recording_place: Optional[MBPlace] = None  # Recording venue/studio
    related_recordings: List[Dict[str, Any]] = None  # Other versions
    
    # Credits and personnel
    artist_credits: List[Dict[str, Any]] = None  # Detailed credits
    relationships: List[MBRelationship] = None  # All relationships
    
    # User-generated content
    tags: List[Dict[str, Any]] = None  # Genre tags, descriptive tags
    rating: Optional[float] = None
    
    # URLs and external links
    urls: List[Dict[str, str]] = None  # YouTube, Spotify, etc.


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
                    includes=[
                        'artists', 'releases', 'artist-credits', 
                        'work-rels', 'place-rels', 'recording-rels',
                        'tags', 'isrcs', 'url-rels'
                    ]
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
        """Parse enhanced MusicBrainz recording data into our format."""
        
        # Extract basic info
        recording_id = recording_data['id']
        title = recording_data.get('title', 'Unknown Title')
        length = recording_data.get('length')  # in milliseconds
        disambiguation = recording_data.get('disambiguation')
        
        # Extract artist info (may be multiple artists)
        artist_name = "Unknown Artist"
        artist_id = ""
        artist_credits = None
        
        if 'artist-credit' in recording_data:
            artist_credits_raw = recording_data['artist-credit']
            if artist_credits_raw and len(artist_credits_raw) > 0:
                first_artist = artist_credits_raw[0]
                if isinstance(first_artist, dict) and 'artist' in first_artist:
                    artist_name = first_artist['artist'].get('name', artist_name)
                    artist_id = first_artist['artist'].get('id', '')
                
                # Store full artist credits
                artist_credits = []
                for credit in artist_credits_raw:
                    if isinstance(credit, dict):
                        artist_data = credit.get('artist', {})
                        if isinstance(artist_data, dict):
                            artist_credits.append({
                                'name': credit.get('name', ''),
                                'artist_name': artist_data.get('name', ''),
                                'artist_id': artist_data.get('id', ''),
                                'joinphrase': credit.get('joinphrase', '')
                            })
                    elif isinstance(credit, str):
                        # Sometimes credits are just strings
                        artist_credits.append({
                            'name': credit,
                            'artist_name': credit,
                            'artist_id': '',
                            'joinphrase': ''
                        })
        
        # Extract release info with enhanced details
        releases = []
        release_status = None
        if 'release-list' in recording_data:
            for release in recording_data['release-list'][:5]:  # More releases for bootlegs
                release_info = {
                    'id': release.get('id'),
                    'title': release.get('title'),
                    'date': release.get('date'),
                    'status': release.get('status'),
                    'packaging': release.get('packaging'),
                    'country': release.get('country'),
                    'barcode': release.get('barcode'),
                }
                releases.append(release_info)
                
                # Set overall status (prefer Official, then Bootleg)
                status = release.get('status')
                if not release_status or (status == 'Official' and release_status != 'Official'):
                    release_status = status
        
        # Extract ISRCs
        isrcs = []
        if 'isrc-list' in recording_data:
            for isrc_item in recording_data['isrc-list']:
                if isinstance(isrc_item, dict):
                    isrc_code = isrc_item.get('isrc')
                    if isrc_code:
                        isrcs.append(isrc_code)
                elif isinstance(isrc_item, str):
                    isrcs.append(isrc_item)
        
        # Extract tags
        tags = []
        if 'tag-list' in recording_data:
            for tag in recording_data['tag-list']:
                if isinstance(tag, dict):
                    tags.append({
                        'name': tag.get('name'),
                        'count': tag.get('count', 0)
                    })
                elif isinstance(tag, str):
                    tags.append({
                        'name': tag,
                        'count': 1
                    })
        
        # Parse relationships
        works = []
        recording_place = None
        related_recordings = []
        relationships = []
        urls = []
        
        if 'relation-list' in recording_data:
            for relation in recording_data['relation-list']:
                rel_type = relation.get('type', '')
                target_type = relation.get('target-type', '')
                direction = relation.get('direction', 'forward')
                attributes = [attr.get('type') for attr in relation.get('attribute-list', [])]
                
                # Extract work relationships (original compositions)
                if target_type == 'work' and 'work' in relation:
                    work = relation['work']
                    works.append(MBWork(
                        id=work.get('id', ''),
                        title=work.get('title', ''),
                        type=work.get('type')
                    ))
                
                # Extract place relationships (recording venues/studios)
                elif target_type == 'place' and 'place' in relation and rel_type in ['recorded at', 'performance']:
                    place = relation['place']
                    area_name = ''
                    if 'area' in place:
                        area_name = place['area'].get('name', '')
                    
                    recording_place = MBPlace(
                        id=place.get('id', ''),
                        name=place.get('name', ''),
                        type=place.get('type'),
                        area=area_name
                    )
                
                # Extract recording relationships (other versions)
                elif target_type == 'recording' and 'recording' in relation:
                    related_rec = relation['recording']
                    related_recordings.append({
                        'id': related_rec.get('id'),
                        'title': related_rec.get('title'),
                        'relationship_type': rel_type,
                        'attributes': attributes
                    })
                
                # Extract URL relationships
                elif target_type == 'url' and 'url' in relation:
                    url_data = relation['url']
                    urls.append({
                        'type': rel_type,
                        'url': url_data.get('resource', ''),
                        'resource': url_data.get('resource', '')
                    })
                
                # Store all relationships for comprehensive data
                relationships.append(MBRelationship(
                    type=rel_type,
                    target_type=target_type,
                    target_id=relation.get('target', ''),
                    target_name=self._extract_target_name(relation),
                    direction=direction,
                    attributes=attributes
                ))
        
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
            releases=releases,
            release_status=release_status,
            isrcs=isrcs,
            works=works,
            recording_place=recording_place,
            related_recordings=related_recordings,
            artist_credits=artist_credits,
            relationships=relationships,
            tags=tags,
            urls=urls
        )
    
    def _extract_target_name(self, relation: Dict[str, Any]) -> str:
        """Extract the name of the relationship target."""
        target_type = relation.get('target-type', '')
        
        if target_type == 'work' and 'work' in relation:
            return relation['work'].get('title', '')
        elif target_type == 'place' and 'place' in relation:
            return relation['place'].get('name', '')
        elif target_type == 'recording' and 'recording' in relation:
            return relation['recording'].get('title', '')
        elif target_type == 'artist' and 'artist' in relation:
            return relation['artist'].get('name', '')
        elif target_type == 'url' and 'url' in relation:
            return relation['url'].get('resource', '')
        else:
            return relation.get('target', '')
    
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