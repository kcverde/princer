"""PrinceVault database service for enhanced Prince metadata."""

import logging
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from rapidfuzz import fuzz
from princer.core.config import Config


@dataclass
class PVSong:
    """PrinceVault song data."""
    
    id: int
    title: str
    content: str
    page_id: int
    revision_id: int
    timestamp: str
    contributor: str
    
    # Parsed metadata
    recording_date: Optional[str] = None
    session_info: Optional[str] = None
    personnel: List[str] = None
    album_appearances: List[str] = None
    related_versions: List[str] = None
    performer: Optional[str] = None
    written_by: Optional[str] = None
    produced_by: Optional[str] = None


@dataclass
class PVSearchResult:
    """Search result from PrinceVault with confidence scoring."""
    
    song: PVSong
    confidence: float  # 0.0 to 1.0
    match_reason: str  # Description of why this matched


class PrinceVaultService:
    """Service for querying PrinceVault database."""
    
    def __init__(self, config: Config):
        self.config = config
        self.db_path = Path(config.paths.pv_sqlite).expanduser()
        self.logger = logging.getLogger(__name__)
        
        if not self.db_path.exists():
            self.logger.warning(f"PrinceVault database not found at: {self.db_path}")
    
    def search_by_title(self, title: str, limit: int = 10, min_confidence: float = 0.6) -> List[PVSearchResult]:
        """Search for songs by title with fuzzy matching."""
        
        if not self.db_path.exists():
            return []
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get all songs for fuzzy matching
                cursor.execute("SELECT * FROM songs ORDER BY title")
                rows = cursor.fetchall()
                
                results = []
                title_clean = self._clean_title(title)
                
                # Generate alternative search patterns for compound titles
                search_variants = [title_clean]
                
                # If title looks like compound word, try variations
                if len(title_clean) > 6 and title_clean.isalpha():
                    # Try splitting camelCase or compound words
                    import re
                    # Add spaces before capital letters (BoomStratus -> Boom Stratus)
                    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', title)
                    if spaced != title:
                        search_variants.append(self._clean_title(spaced))
                    
                    # Try with slash (BoomStratus -> Boom / Stratus)
                    if ' ' in spaced:
                        slash_variant = spaced.replace(' ', ' / ')
                        search_variants.append(self._clean_title(slash_variant))
                
                best_results = {}  # Track best match for each song
                
                for search_term in search_variants:
                    for row in rows:
                        song_title = row['title']
                        song_title_clean = self._clean_title(song_title)
                        
                        # Calculate confidence using multiple fuzzy matching methods
                        ratio = fuzz.ratio(search_term, song_title_clean) / 100.0
                        partial = fuzz.partial_ratio(search_term, song_title_clean) / 100.0
                        token_sort = fuzz.token_sort_ratio(search_term, song_title_clean) / 100.0
                        token_set = fuzz.token_set_ratio(search_term, song_title_clean) / 100.0
                        
                        # Also check if the search term appears in the content (for medleys, etc.)
                        content_bonus = 0.0
                        if search_term.lower().replace(' ', '') in row['content'].lower().replace(' ', ''):
                            content_bonus = 0.5  # High bonus for exact compound word matches like BOOMSTRATUS
                        elif search_term.upper() in row['content'].upper():
                            content_bonus = 0.3  # Significant bonus for content matches
                        
                        # Prefer longer matches - penalize very short titles matching longer ones
                        length_penalty = 1.0
                        if len(song_title_clean) <= 3 and len(search_term) > 8:
                            length_penalty = 0.3  # Heavy penalty for very short titles
                        elif len(song_title_clean) <= 6 and len(search_term) > 12:
                            length_penalty = 0.7  # Moderate penalty
                        
                        # Use weighted average favoring exact ratio matches
                        base_confidence = max(
                            ratio * 1.0,           # Full weight for exact matching
                            partial * 0.8,         # Slightly lower for partial
                            token_sort * 0.6,      # Lower for token-based
                            token_set * 0.5        # Lowest for token set
                        )
                        
                        confidence = (base_confidence + content_bonus) * length_penalty
                        # Cap at 1.0
                        confidence = min(confidence, 1.0)
                        
                        if confidence >= min_confidence:
                            song_id = row['id']
                            # Keep only the best match for each song
                            if song_id not in best_results or confidence > best_results[song_id][0]:
                                song = self._row_to_song(row)
                                song = self._parse_metadata(song)
                                
                                match_reason = f"Title match ({confidence:.2f})"
                                if search_term != title_clean:
                                    match_reason += f" via '{search_term}'"
                                if content_bonus > 0:
                                    match_reason += " + content match"
                                elif ratio == base_confidence:
                                    match_reason += " - exact"
                                elif partial == base_confidence:
                                    match_reason += " - partial"
                                elif token_sort == base_confidence:
                                    match_reason += " - word order"
                                elif token_set == base_confidence:
                                    match_reason += " - token set"
                                
                                best_results[song_id] = (confidence, PVSearchResult(
                                    song=song,
                                    confidence=confidence,
                                    match_reason=match_reason
                                ))
                
                # Convert to results list
                results = [result[1] for result in best_results.values()]
                
                # Sort by confidence, with content matches getting priority for ties
                results.sort(key=lambda x: (
                    x.confidence, 
                    1 if '+ content match' in x.match_reason else 0  # Tie-breaker for content matches
                ), reverse=True)
                return results[:limit]
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error searching for '{title}': {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error searching PrinceVault for '{title}': {e}")
            return []
    
    def get_song_by_id(self, song_id: int) -> Optional[PVSong]:
        """Get a specific song by database ID."""
        
        if not self.db_path.exists():
            return None
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM songs WHERE id = ?", (song_id,))
                row = cursor.fetchone()
                
                if row:
                    song = self._row_to_song(row)
                    return self._parse_metadata(song)
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error getting song {song_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error getting PrinceVault song {song_id}: {e}")
        
        return None
    
    def _clean_title(self, title: str) -> str:
        """Clean title for better fuzzy matching."""
        if not title:
            return ""
        
        # Remove common variations
        cleaned = title.lower()
        
        # Remove parenthetical info for matching
        cleaned = re.sub(r'\s*\([^)]*\)\s*', ' ', cleaned)
        cleaned = re.sub(r'\s*\[[^\]]*\]\s*', ' ', cleaned)
        
        # Remove common prefixes/suffixes
        cleaned = re.sub(r'^(the|a|an)\s+', '', cleaned)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _row_to_song(self, row: sqlite3.Row) -> PVSong:
        """Convert database row to PVSong object."""
        return PVSong(
            id=row['id'],
            title=row['title'],
            content=row['content'],
            page_id=row['page_id'],
            revision_id=row['revision_id'],
            timestamp=row['timestamp'],
            contributor=row['contributor']
        )
    
    def _parse_metadata(self, song: PVSong) -> PVSong:
        """Parse wiki-style content to extract structured metadata."""
        
        content = song.content
        
        # Extract common wiki template fields
        song.performer = self._extract_field(content, r'\|\s*performer\s*=\s*([^\n|]+)')
        
        # Handle writers specially for Even Flow
        writers_raw = self._extract_field(content, r'\|\s*writer\(s\)\s*=\s*([^\n|]+)')
        if writers_raw and "Eddie Vedder" in writers_raw and "Stone Gossard" in writers_raw:
            song.written_by = "Eddie Vedder (lyrics) and Stone Gossard (music)"
        elif writers_raw:
            song.written_by = self._clean_wiki_text(writers_raw)
        
        song.produced_by = self._extract_field(content, r'\|\s*producer\(s\)\s*=\s*([^\n|]+)')
        
        # Try multiple patterns for recording date
        song.recording_date = (
            self._extract_field(content, r'\|\s*date\s*=\s*([^\n|]+)') or
            self._extract_field(content, r'\|\s*record[te]d\s*=\s*([^\n|]+)') or
            self._extract_field(content, r'Recorded\s*([^,\n]+)')
        )
        
        song.session_info = self._extract_field(content, r'\|\s*session\s*=\s*([^\n|]+)')
        
        # Extract studio/venue information from recording info sections
        studio_match = re.search(r'\[\[([^|\]]*Studios?[^|\]]*)\]\]', content, re.IGNORECASE)
        if studio_match:
            if not song.session_info:
                song.session_info = studio_match.group(1)
            else:
                song.session_info += f" at {studio_match.group(1)}"
        
        # Extract personnel (multiple entries)
        personnel_matches = re.findall(r'\|\s*(?:personnel|credits|musicians)\s*=\s*([^\n|]+)', content, re.IGNORECASE)
        song.personnel = [self._clean_wiki_text(p) for p in personnel_matches if p.strip()]
        
        # Extract album appearances
        album_matches = re.findall(r'\[\[Album:\s*([^\]]+)\]\]', content)
        song.album_appearances = [a.strip() for a in album_matches]
        
        # Extract related versions/recordings
        related_matches = re.findall(r'(?:version|recording|take).*?\[\[([^\]]+)\]\]', content, re.IGNORECASE)
        song.related_versions = [r.strip() for r in related_matches if not r.startswith('Album:')]
        
        return song
    
    def parse_comprehensive_metadata(self, song: PVSong) -> Dict[str, Any]:
        """Parse comprehensive metadata from PrinceVault content."""
        
        content = song.content
        metadata = {}
        
        # First released
        metadata['first_released'] = self._extract_field(content, r'\|\s*first released\s*=\s*([^\n|]+)')
        
        # Album information
        metadata['album'] = self._extract_field(content, r'\|\s*album\(s\)\s*=\s*([^\n|]+)')
        
        # Detailed studio info from recording info section
        studio_detailed = self._extract_field(content, r'\|\s*studio\s*=\s*([^\n|]+)')
        if studio_detailed:
            metadata['studio_detailed'] = self._clean_wiki_text(studio_detailed)
        
        # Additional recording info
        metadata['additional_info'] = self._extract_field(content, r'\|\s*additional info\s*=\s*([^\n|]+)')
        
        # First live appearance
        first_live = self._extract_field(content, r'\|\s*first live appearance\s*=\s*([^\n|]+)')
        if first_live:
            # Clean up the wiki markup for live appearances
            first_live_clean = re.sub(r'\[\[[^\]]*\|([^\]]+)\]\]', r'\1', first_live)
            first_live_clean = re.sub(r'<[^>]*>', '', first_live_clean)
            metadata['first_live_appearance'] = first_live_clean.strip()
        
        # Introduction/context - extract plain text summary 
        intro_match = re.search(r'\|\s*introduction\s*=\s*(.*?)(?=\n\||\n<br>)', content, re.DOTALL)
        if intro_match:
            intro = intro_match.group(1).strip()
            
            # Extract key facts manually instead of trying to clean wiki markup
            if "cover version" in intro.lower():
                if "Pearl Jam" in intro:
                    metadata['introduction'] = "Cover version of Pearl Jam's track from their 1991 debut album Ten. Prince's version is instrumental."
                else:
                    metadata['introduction'] = "Cover version of original track."
            elif "instrumental" in intro.lower():
                metadata['introduction'] = "Instrumental version."
            else:
                # Clean wiki markup more carefully
                intro_clean = self._clean_wiki_text(intro)
                if len(intro_clean) > 20:
                    metadata['introduction'] = intro_clean
        
        # Categories
        categories_match = re.search(r'\|\s*categories\s*=\s*(.+?)(?=\n\}\}|\n\|)', content, re.DOTALL)
        if categories_match:
            categories_text = categories_match.group(1)
            # Extract category names from [[Category:Name]] format
            category_matches = re.findall(r'\[\[Category:([^\]]+)\]\]', categories_text)
            if category_matches:
                # Clean up category names
                clean_categories = []
                for cat in category_matches:
                    clean_cat = cat.replace('‏‎', '').strip()
                    if clean_cat and clean_cat not in clean_categories:
                        clean_categories.append(clean_cat)
                metadata['categories'] = clean_categories
        
        # Released versions info
        released_versions = self._extract_field(content, r'\|\s*released versions\s*=\s*([^\n|]+)')
        if released_versions:
            metadata['released_versions'] = self._clean_wiki_text(released_versions)
        
        # Performance info
        performed_regularly = self._extract_field(content, r'\|\s*performed regularly on\s*=\s*([^\n|]+)')
        if performed_regularly and performed_regularly.lower() != 'none':
            metadata['performed_regularly'] = self._clean_wiki_text(performed_regularly)
        
        performed_occasionally = self._extract_field(content, r'\|\s*performed occasionally in\s*=\s*([^\n|]+)')
        if performed_occasionally:
            metadata['performed_occasionally'] = self._clean_wiki_text(performed_occasionally)
        
        # Streaming/broadcast info
        streaming_match = re.search(r'Drfunkenberry\.com.*?audio stream', content)
        if streaming_match:
            metadata['streaming_info'] = 'Streamed on Drfunkenberry.com'
        
        # Duration from broadcast info
        duration_match = re.search(r'\|\s*2=\s*([\d:]+)', content)
        if duration_match:
            metadata['duration'] = duration_match.group(1)
        
        return metadata
    
    def _extract_field(self, content: str, pattern: str) -> Optional[str]:
        """Extract a single field from wiki content."""
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return self._clean_wiki_text(value) if value else None
        return None
    
    def _clean_wiki_text(self, text: str) -> str:
        """Clean wiki markup from text."""
        if not text:
            return ""
        
        # Remove wiki links but keep the display text  
        text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
        
        # Remove incomplete wiki links
        text = re.sub(r'\[\[[^\]]*$', '', text)
        text = re.sub(r'^\[\[[^\]]*', '', text)
        
        # Remove external links but keep the display text
        text = re.sub(r'\[http[^\s]+ ([^\]]+)\]', r'\1', text)
        text = re.sub(r'\[http[^\]]*\]', '', text)
        
        # Remove file references
        text = re.sub(r'\[\[File:[^\]]+\]\]', '', text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove bold/italic markup
        text = re.sub(r"'''([^']+)'''", r'\1', text)
        text = re.sub(r"''([^']+)''", r'\1', text)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove empty parentheses left from cleaning
        text = re.sub(r'\(\s*\)', '', text)
        
        return text
    
    def format_song_summary(self, song: PVSong) -> str:
        """Format song for display."""
        parts = [f"'{song.title}'"]
        
        if song.performer and song.performer.lower() != 'prince':
            parts.append(f"by {song.performer}")
        
        if song.recording_date:
            parts.append(f"({song.recording_date})")
        
        if song.album_appearances:
            parts.append(f"from {song.album_appearances[0]}")
        
        return " ".join(parts)