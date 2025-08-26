"""CLI interface for Princer."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from princer.models.audio import AudioFile, AudioFileInfo
from princer.core.config import ConfigLoader
from princer.services.acoustid import AcoustIDService
from princer.services.musicbrainz import MusicBrainzService
from princer.services.princevault import PrinceVaultService
from princer.services.llm import LLMService

app = typer.Typer(
    name="tagger",
    help="Prince song tagger and metadata normalizer",
    no_args_is_help=True
)

console = Console()


def _collect_metadata(
    path: Path, 
    acoustid_service: AcoustIDService,
    mb_service: Optional[MusicBrainzService] = None,
    pv_service: Optional[PrinceVaultService] = None
) -> dict:
    """
    Collect comprehensive metadata from all sources for a given audio file.
    
    Returns a dict with file_info, acoustid, musicbrainz, and princevault data.
    """
    # Get audio file info first
    audio_file = AudioFile(path)
    info_result = audio_file.extract_info()
    
    # Generate fingerprint and get AcoustID matches
    acoustid_result = acoustid_service.fingerprint_file(path)
    
    if acoustid_result.error:
        raise ValueError(f"Fingerprinting failed: {acoustid_result.error}")
    
    # Collect MusicBrainz data if service available
    mb_recordings = []
    if acoustid_result.acoustid_matches and mb_service:
        best_matches = acoustid_service.get_best_matches(acoustid_result, min_score=0.8)
        if best_matches:
            recording_ids = []
            for match in best_matches[:3]:  # Top 3 matches
                recording_ids.extend(match.recording_ids)
            
            if recording_ids:
                mb_result = mb_service.lookup_recordings(recording_ids)
                if mb_result.recordings:
                    mb_recordings = mb_result.recordings
    
    # Collect PrinceVault data if service available
    pv_matches = []
    pv_raw_content = ""
    if pv_service:
        search_terms = set()
        
        # Get search terms from AcoustID matches
        if acoustid_result.acoustid_matches:
            for match in acoustid_result.acoustid_matches[:2]:
                title = match.get('title', '').strip()
                if title and title.lower() != 'unknown':
                    search_terms.add(title)
        
        # Fall back to filename if no good titles found
        if not search_terms:
            search_terms.add(info_result.filename)
        
        # Search PrinceVault with each term
        for search_title in list(search_terms)[:2]:  # Limit to 2 searches
            pv_results = pv_service.search_by_title(search_title, limit=3, min_confidence=0.7)
            if pv_results:
                pv_matches.extend(pv_results)
                # Get raw content from best match for additional context
                if not pv_raw_content and pv_results[0].confidence >= 0.7:
                    best_song = pv_results[0].song
                    pv_raw_content = best_song.content[:500] + "..." if len(best_song.content) > 500 else best_song.content
        
        # Remove duplicates and sort by confidence
        seen_ids = set()
        unique_matches = []
        for match in pv_matches:
            if match.song.id not in seen_ids:
                unique_matches.append(match)
                seen_ids.add(match.song.id)
        pv_matches = sorted(unique_matches, key=lambda x: x.confidence, reverse=True)[:3]
    
    return {
        'file_info': {
            'path': path,
            'filename': info_result.filename,
            'duration_seconds': info_result.duration_seconds,
            'format': getattr(info_result, 'format', 'Unknown'),
            'bitrate': getattr(info_result, 'bitrate', None),
            'tags': info_result.tags or {}
        },
        'acoustid': {
            'fingerprint': acoustid_result.fingerprint,
            'duration': acoustid_result.duration,
            'matches': acoustid_result.acoustid_matches
        },
        'musicbrainz': {
            'recordings': mb_recordings
        },
        'princevault': {
            'matches': pv_matches,
            'raw_content': pv_raw_content
        }
    }


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def display_audio_info(info: AudioFileInfo) -> None:
    """Display audio file information in a formatted table."""
    
    if info.error:
        console.print(f"[red]Error:[/red] {info.error}")
        return
    
    # Main file info table
    table = Table(title=f"Audio File: {info.filename}{info.extension}", box=box.ROUNDED)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="white")
    
    # Basic file info
    table.add_row("File Size", format_file_size(info.file_size))
    
    if info.duration_seconds:
        audio_file = AudioFile(info.path)
        duration_str = audio_file.format_duration(info.duration_seconds)
        table.add_row("Duration", duration_str)
    
    if info.bitrate:
        # Convert from bps to kbps
        bitrate_kbps = info.bitrate // 1000 if info.bitrate >= 1000 else info.bitrate
        table.add_row("Bitrate", f"{bitrate_kbps} kbps")
    
    if info.sample_rate:
        table.add_row("Sample Rate", f"{info.sample_rate} Hz")
        
    if info.channels:
        table.add_row("Channels", str(info.channels))
    
    console.print(table)
    
    # Tags table
    if info.tags:
        tags_table = Table(title="Tags", box=box.ROUNDED)
        tags_table.add_column("Tag", style="yellow", width=20)
        tags_table.add_column("Value", style="white")
        
        # Sort tags for consistent display
        for key, value in sorted(info.tags.items()):
            # Truncate very long values
            str_value = str(value)
            if len(str_value) > 60:
                str_value = str_value[:57] + "..."
            tags_table.add_row(key, str_value)
            
        console.print(tags_table)
    
    # Show raw filename for reference (LLM will parse this later)
    console.print(f"[dim]Raw filename: {info.filename}{info.extension}[/dim]")


@app.command()
def info(
    file_path: str = typer.Argument(..., help="Audio file to analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show verbose output")
) -> None:
    """Display detailed information about an audio file."""
    
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)
    
    if not AudioFile.is_supported(path):
        console.print(f"[red]Error:[/red] Unsupported file format: {path.suffix}")
        console.print(f"Supported formats: {', '.join(AudioFile.SUPPORTED_EXTENSIONS)}")
        raise typer.Exit(1)
    
    console.print(f"[dim]Analyzing file: {path}[/dim]")
    console.print()
    
    audio_file = AudioFile(path)
    info_result = audio_file.extract_info()
    
    display_audio_info(info_result)


@app.command()
def fingerprint(
    file_path: str = typer.Argument(..., help="Audio file to fingerprint"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    lookup_mb: bool = typer.Option(True, "--lookup-mb", help="Look up matches in MusicBrainz"),
    lookup_pv: bool = typer.Option(True, "--lookup-pv", help="Look up matches in PrinceVault")
) -> None:
    """Generate audio fingerprint and find matches via AcoustID + MusicBrainz + PrinceVault."""
    
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)
    
    if not AudioFile.is_supported(path):
        console.print(f"[red]Error:[/red] Unsupported file format: {path.suffix}")
        raise typer.Exit(1)
    
    console.print(f"[dim]Fingerprinting file: {path}[/dim]")
    
    # Load configuration
    cfg = ConfigLoader.load(config)
    
    # Check for API key
    if not cfg.api.acoustid_key:
        console.print("[red]Error:[/red] No AcoustID API key found.")
        console.print("Set your API key in the ACOUSTID_KEY environment variable.")
        console.print("Get a free key at: https://acoustid.org/api-key")
        raise typer.Exit(1)
    
    # Initialize services
    acoustid_service = AcoustIDService(cfg)
    mb_service = MusicBrainzService(cfg) if lookup_mb else None
    pv_service = PrinceVaultService(cfg) if lookup_pv else None
    
    # Collect all metadata using shared function
    with console.status("[bold green]Collecting metadata from all sources..."):
        try:
            metadata = _collect_metadata(path, acoustid_service, mb_service, pv_service)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    # Display file info first
    console.print()
    file_info = metadata['file_info']
    file_table = Table(title=f"File: {file_info['filename']}", box=box.ROUNDED)
    file_table.add_column("Property", style="cyan", width=20)
    file_table.add_column("Value", style="white")
    
    file_table.add_row("Duration", f"{file_info['duration_seconds']:.1f}s")
    if file_info['format'] != 'Unknown':
        file_table.add_row("Format", file_info['format'])
    if file_info['bitrate']:
        bitrate_kbps = file_info['bitrate'] // 1000 if file_info['bitrate'] >= 1000 else file_info['bitrate']
        file_table.add_row("Bitrate", f"{bitrate_kbps} kbps")
    
    console.print(file_table)
    
    # Display existing tags
    console.print()
    tags_table = Table(title="Current Tags", box=box.ROUNDED)
    tags_table.add_column("Tag", style="cyan")
    tags_table.add_column("Value", style="white")
    
    if file_info['tags']:
        for key, value in file_info['tags'].items():
            tags_table.add_row(key.title(), str(value))
    else:
        tags_table.add_row("Status", "[dim]No tags found[/dim]")
    
    console.print(tags_table)
    
    # Display fingerprint info
    console.print()
    fp_table = Table(title="Audio Fingerprint", box=box.ROUNDED)
    fp_table.add_column("Property", style="cyan")
    fp_table.add_column("Value", style="white")
    
    fp_table.add_row("Duration", f"{metadata['acoustid']['duration']:.1f} seconds")
    fp_table.add_row("Fingerprint ID", metadata['acoustid']['fingerprint'][:16] + "...")
    fp_table.add_row("AcoustID Matches", str(len(metadata['acoustid']['matches'])))
    
    console.print(fp_table)
    
    # Display AcoustID matches
    if metadata['acoustid']['matches']:
        console.print()
        matches_table = Table(title="AcoustID Matches", box=box.ROUNDED)
        matches_table.add_column("Score", style="yellow")
        matches_table.add_column("Recording ID", style="green") 
        matches_table.add_column("Title", style="white")
        matches_table.add_column("Artist", style="blue")
        
        for match in metadata['acoustid']['matches'][:5]:  # Show top 5
            score = match.get('score', 0)
            recording_id = match.get('recording_id', 'N/A')
            title = match.get('title', 'Unknown')
            artist = match.get('artist', 'Unknown')
            
            matches_table.add_row(
                f"{score:.3f}",
                recording_id[:8] + "..." if len(recording_id) > 8 else recording_id,
                title,
                artist
            )
        
        console.print(matches_table)
        
        # Display MusicBrainz details
        if lookup_mb and metadata['musicbrainz']['recordings']:
            console.print()
            console.print("[bold]MusicBrainz Details:[/bold]")
            
            for i, recording in enumerate(metadata['musicbrainz']['recordings'], 1):
                console.print()
                console.print(f"[bold cyan]Match {i}: {recording.title} by {recording.artist_name}[/bold cyan]")
                
                # Comprehensive MusicBrainz info table
                basic_table = Table(title="MusicBrainz Details", box=box.ROUNDED)
                basic_table.add_column("Property", style="cyan")
                basic_table.add_column("Value", style="white")
                
                # Core info
                basic_table.add_row("Recording ID", recording.id)
                basic_table.add_row("Artist ID", recording.artist_id or "Unknown")
                basic_table.add_row("Date", recording.date or "Unknown")
                
                # Duration
                duration = "Unknown"
                if recording.length:
                    try:
                        length_ms = int(recording.length)
                        duration_sec = length_ms // 1000
                        minutes = duration_sec // 60
                        seconds = duration_sec % 60
                        duration = f"{minutes}:{seconds:02d} ({recording.length}ms)"
                    except (ValueError, TypeError):
                        duration = f"{recording.length} (raw)"
                basic_table.add_row("Duration", duration)
                
                if recording.disambiguation:
                    basic_table.add_row("Disambiguation", recording.disambiguation)
                if recording.release_status:
                    basic_table.add_row("Release Status", recording.release_status)
                
                # Show all releases
                if recording.releases:
                    for idx, release in enumerate(recording.releases[:3]):
                        release_info = f"{release.get('title', 'Unknown')}"
                        if release.get('date'):
                            release_info += f" ({release['date']})"
                        if release.get('country'):
                            release_info += f" [{release['country']}]"
                        if release.get('status'):
                            release_info += f" - {release['status']}"
                        basic_table.add_row(f"Release {idx+1}", release_info)
                
                # Artist credits (full details)
                if recording.artist_credits:
                    for idx, credit in enumerate(recording.artist_credits[:3]):
                        credit_info = f"{credit.get('artist_name', 'Unknown')}"
                        if credit.get('name') != credit.get('artist_name'):
                            credit_info += f" (as {credit.get('name')})"
                        if credit.get('joinphrase'):
                            credit_info += f" {credit['joinphrase']}"
                        basic_table.add_row(f"Credit {idx+1}", credit_info)
                
                console.print(basic_table)
                
                # Recording venue/place
                if recording.recording_place:
                    place = recording.recording_place
                    venue_info = place.name
                    if place.area:
                        venue_info += f", {place.area}"
                    if place.type:
                        venue_info += f" ({place.type})"
                        
                    venue_table = Table(title="Recording Location", box=box.ROUNDED)
                    venue_table.add_column("Venue", style="green")
                    venue_table.add_row(venue_info)
                    console.print(venue_table)
                
                # Works (compositions)
                if recording.works:
                    works_table = Table(title="Original Compositions", box=box.ROUNDED)
                    works_table.add_column("Work", style="magenta")
                    works_table.add_column("Type", style="dim")
                    
                    for work in recording.works[:3]:  # Limit display
                        works_table.add_row(
                            work.title,
                            work.type or "Song"
                        )
                    console.print(works_table)
                
                # Tags
                if recording.tags:
                    popular_tags = []
                    for tag in recording.tags:
                        count = tag.get('count', 0)
                        # Convert count to int if it's a string
                        try:
                            count_int = int(count) if isinstance(count, str) else count
                            if count_int > 1:
                                popular_tags.append(tag)
                        except ValueError:
                            continue
                    popular_tags = popular_tags[:5]
                    if popular_tags:
                        tags_text = ", ".join([tag['name'] for tag in popular_tags])
                        console.print(f"[dim]Tags: {tags_text}[/dim]")
                
                # URLs
                if recording.urls:
                    url_types = {}
                    for url in recording.urls:
                        url_type = url.get('type', 'link')
                        if url_type not in url_types:
                            url_types[url_type] = url.get('url', '')
                    
                    if url_types:
                        console.print("[dim]External links: " + 
                                    ", ".join([f"{k}" for k in url_types.keys()]) + "[/dim]")
                
                # Related recordings
                if recording.related_recordings:
                    console.print(f"[dim]Related recordings: {len(recording.related_recordings)} other versions[/dim]")
                
                # ISRCs
                if recording.isrcs:
                    console.print(f"[dim]ISRCs: {', '.join(recording.isrcs[:2])}[/dim]")
        
        # Display PrinceVault matches
        if lookup_pv and metadata['princevault']['matches']:
            console.print()
            console.print("[bold]PrinceVault Matches:[/bold]")
            
            pv_table = Table(title="PrinceVault Matches", box=box.ROUNDED)
            pv_table.add_column("Confidence", style="yellow")
            pv_table.add_column("Title", style="cyan")
            pv_table.add_column("Details", style="white")
            
            for pv_match in metadata['princevault']['matches']:
                song = pv_match.song
                details = []
                
                if song.performer and song.performer.lower() != 'prince':
                    details.append(f"by {song.performer}")
                
                if song.recording_date:
                    details.append(f"recorded {song.recording_date}")
                
                if song.album_appearances:
                    details.append(f"from {song.album_appearances[0]}")
                
                details_str = ", ".join(details) if details else "Prince recording"
                
                pv_table.add_row(
                    f"{pv_match.confidence:.2f}",
                    song.title,
                    details_str
                )
            
            console.print(pv_table)
            
            # Show detailed info for best match
            best_match = metadata['princevault']['matches'][0]
            if best_match.confidence >= 0.70:
                console.print()
                console.print(f"[bold cyan]Best PrinceVault Match: {best_match.song.title}[/bold cyan]")
                
                song = best_match.song
                pv_metadata = pv_service.parse_comprehensive_metadata(song)
                
                # Show comprehensive PrinceVault table
                pv_table = Table(title="PrinceVault Details", box=box.ROUNDED)
                pv_table.add_column("Property", style="cyan")
                pv_table.add_column("Value", style="white")
                
                # Show database IDs and raw info
                pv_table.add_row("Database ID", str(song.id))
                pv_table.add_row("Page ID", str(song.page_id))
                pv_table.add_row("Revision ID", str(song.revision_id))
                pv_table.add_row("Last Updated", song.timestamp or "Unknown")
                pv_table.add_row("Contributor", song.contributor or "Unknown")
                
                # Core metadata - show raw values
                if song.performer:
                    pv_table.add_row("Performer", song.performer)
                if song.recording_date:
                    pv_table.add_row("Recording Date", song.recording_date)
                if song.written_by:
                    pv_table.add_row("Written By", song.written_by)
                if song.produced_by:
                    pv_table.add_row("Produced By", song.produced_by)
                if song.session_info:
                    pv_table.add_row("Session", song.session_info)
                if song.personnel:
                    pv_table.add_row("Personnel", "; ".join(song.personnel))
                if song.album_appearances:
                    pv_table.add_row("Album Appearances", "; ".join(song.album_appearances))
                if song.related_versions:
                    pv_table.add_row("Related Versions", "; ".join(song.related_versions))
                
                # Additional parsed metadata - show all available
                for key, value in pv_metadata.items():
                    if value and key not in ['categories']:  # Handle categories separately
                        if isinstance(value, list):
                            pv_table.add_row(key.title(), "; ".join(str(v) for v in value))
                        else:
                            pv_table.add_row(key.title(), str(value))
                
                console.print(pv_table)
                
                # Show categories separately
                categories = pv_metadata.get('categories')
                if categories:
                    console.print(f"[dim]Categories: {', '.join(categories)}[/dim]")
        
        elif lookup_pv and not metadata['princevault']['matches']:
            console.print()
            console.print("[dim]No PrinceVault matches found[/dim]")
    
    else:
        console.print("\n[yellow]No AcoustID matches found for this file.[/yellow]")
        
        # Show PrinceVault matches even without AcoustID matches
        if lookup_pv and metadata['princevault']['matches']:
            console.print()
            console.print("[bold]PrinceVault Filename Matches:[/bold]")
            
            pv_table = Table(title="PrinceVault Filename Matches", box=box.ROUNDED)
            pv_table.add_column("Confidence", style="yellow")
            pv_table.add_column("Title", style="cyan")
            pv_table.add_column("Details", style="white")
            
            for pv_match in metadata['princevault']['matches']:
                song = pv_match.song
                details = pv_service.format_song_summary(song).replace(f"'{song.title}' ", "")
                
                pv_table.add_row(
                    f"{pv_match.confidence:.2f}",
                    song.title,
                    details
                )
            
            console.print(pv_table)
        elif lookup_pv:
            console.print()
            console.print("[dim]No PrinceVault matches found for filename[/dim]")


@app.command()
def test_llm(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path")
) -> None:
    """Test LLM connectivity and basic functionality."""
    
    console.print("[dim]Testing LLM connectivity...[/dim]")
    
    # Load configuration
    cfg = ConfigLoader.load(config)
    
    # Initialize LLM service
    llm_service = LLMService(cfg)
    
    # Test connection
    result = llm_service.test_connection()
    
    console.print()
    
    if result["success"]:
        console.print("✅ [green]LLM Connection Successful![/green]")
        
        # Create results table
        table = Table(title="LLM Test Results", box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Provider", cfg.llm.provider)
        table.add_row("Model", result["model"])
        table.add_row("Response", result["response"])
        
        if result.get("usage"):
            usage = result["usage"]
            if usage.get("total_tokens"):
                table.add_row("Tokens Used", str(usage["total_tokens"]))
        
        console.print(table)
        
    else:
        console.print("❌ [red]LLM Connection Failed![/red]")
        console.print(f"[red]Error:[/red] {result['error']}")
        
        console.print()
        console.print("[yellow]Troubleshooting tips:[/yellow]")
        console.print("1. Check your API key in .env file")
        console.print("2. Verify the model name is correct")  
        console.print("3. Ensure you have API credits/quota")
        
        if cfg.llm.provider == "openrouter":
            console.print("4. Visit https://openrouter.ai/ to check your account")
        else:
            console.print("4. Visit https://platform.openai.com/ to check your account")
        
        raise typer.Exit(1)


@app.command()
def normalize(
    file_path: str = typer.Argument(..., help="Audio file to normalize metadata"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    dry_run: bool = typer.Option(True, "--dry-run", help="Show proposed metadata without applying"),
    debug: bool = typer.Option(False, "--debug", help="Show LLM prompts and debug info"),
    show_fingerprint: bool = typer.Option(False, "--show-fingerprint", help="Show full fingerprint analysis before LLM")
) -> None:
    """Normalize metadata using LLM with comprehensive data from all sources."""
    
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)
    
    if not AudioFile.is_supported(path):
        console.print(f"[red]Error:[/red] Unsupported file format: {path.suffix}")
        raise typer.Exit(1)
    
    console.print(f"[dim]Normalizing metadata for: {path}[/dim]")
    
    # Load configuration
    cfg = ConfigLoader.load(config)
    
    # Check for API key
    if not cfg.api.acoustid_key:
        console.print("[red]Error:[/red] No AcoustID API key found.")
        console.print("Set your API key in the ACOUSTID_KEY environment variable.")
        console.print("Get a free key at: https://acoustid.org/api-key")
        raise typer.Exit(1)
    
    # Initialize services
    acoustid_service = AcoustIDService(cfg)
    mb_service = MusicBrainzService(cfg)
    pv_service = PrinceVaultService(cfg)
    llm_service = LLMService(cfg)
    
    # Collect all metadata using shared function
    with console.status("[bold green]Collecting metadata from all sources..."):
        try:
            metadata = _collect_metadata(path, acoustid_service, mb_service, pv_service)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    
    # Show fingerprint analysis if requested
    if show_fingerprint:
        console.print()
        console.print("[bold]📄 FINGERPRINT ANALYSIS[/bold]")
        console.print("─" * 80)
        
        # Display brief fingerprint info
        fp_table = Table(title="Audio Fingerprint", box=box.ROUNDED)
        fp_table.add_column("Property", style="cyan")
        fp_table.add_column("Value", style="white")
        
        fp_table.add_row("Duration", f"{metadata['acoustid']['duration']:.1f} seconds")
        fp_table.add_row("AcoustID Matches", str(len(metadata['acoustid']['matches'])))
        fp_table.add_row("MusicBrainz Recordings", str(len(metadata['musicbrainz']['recordings'])))
        fp_table.add_row("PrinceVault Matches", str(len(metadata['princevault']['matches'])))
        
        console.print(fp_table)
        console.print("─" * 80)
    
    # Show debug info if requested
    if debug:
        console.print()
        console.print("[bold yellow]🐛 DEBUG INFO[/bold yellow]")
        console.print("─" * 80)
        
        # File info section
        console.print("[bold cyan]📁 FILE INFO[/bold cyan]")
        file_info = metadata['file_info']
        console.print(f"Filename: {file_info['filename']}")
        console.print(f"Duration: {file_info['duration_seconds']:.1f}s")
        console.print(f"Format: {file_info['format']}")
        if file_info['bitrate']:
            console.print(f"Bitrate: {file_info['bitrate']} bps")
        console.print()
        
        # Current file tags section
        console.print("[bold cyan]🏷️ CURRENT FILE TAGS[/bold cyan]")
        if file_info['tags']:
            for key, value in file_info['tags'].items():
                console.print(f"{key}: {value}")
        else:
            console.print("No tags found")
        console.print()
        
        # MusicBrainz section
        console.print("[bold cyan]🎵 MUSICBRAINZ DATA[/bold cyan]")
        if metadata['musicbrainz']['recordings']:
            recording = metadata['musicbrainz']['recordings'][0]  # Show first match
            console.print(f"Title: {recording.title}")
            console.print(f"Artist: {recording.artist_name}")
            console.print(f"Date: {recording.date or 'N/A'}")
            console.print(f"Length: {recording.length or 'N/A'}")
            if recording.releases:
                console.print(f"Releases: {len(recording.releases)} found")
                console.print(f"Release Status: {recording.release_status or 'N/A'}")
            if recording.disambiguation:
                console.print(f"Disambiguation: {recording.disambiguation}")
        else:
            console.print("No MusicBrainz matches found")
        console.print()
        
        # PrinceVault section  
        console.print("[bold cyan]👑 PRINCEVAULT DATA[/bold cyan]")
        if metadata['princevault']['matches']:
            match = metadata['princevault']['matches'][0]  # Show best match
            song = match.song
            console.print(f"Title: {song.title}")
            console.print(f"Performer: {song.performer or 'N/A'}")
            console.print(f"Recording Date: {song.recording_date or 'N/A'}")
            console.print(f"Session Info: {song.session_info or 'N/A'}")
            console.print(f"Written By: {song.written_by or 'N/A'}")
            console.print(f"Produced By: {song.produced_by or 'N/A'}")
            console.print(f"Confidence: {match.confidence:.2f}")
            
            # Show parsed categories
            pv_metadata = pv_service.parse_comprehensive_metadata(song)
            categories = pv_metadata.get('categories', [])
            if categories:
                console.print(f"Categories: {', '.join(categories)}")
        else:
            console.print("No PrinceVault matches found")
        console.print()
        
        # LLM prompt section
        console.print("[bold cyan]🤖 LLM PROMPT[/bold cyan]")
        console.print("[dim]System prompt:[/dim]")
        console.print(llm_service.config.llm.system_prompt)
        console.print("─" * 80)
        console.print()
    
    # Prepare LLM request with ALL the collected data
    from princer.services.llm import MetadataNormalizationRequest
    
    # Convert to format expected by current LLM service
    mb_data = None
    if metadata['musicbrainz']['recordings']:
        recording = metadata['musicbrainz']['recordings'][0]
        mb_data = {
            'id': recording.id,
            'title': recording.title,
            'artist_name': recording.artist_name,
            'artist_id': recording.artist_id,
            'date': recording.date,
            'length': recording.length,
            'disambiguation': recording.disambiguation,
            'releases': recording.releases,
            'release_status': recording.release_status,
            'artist_credits': recording.artist_credits,
            'recording_place': recording.recording_place,
            'works': recording.works,
            'tags': recording.tags,
            'urls': recording.urls,
            'related_recordings': recording.related_recordings,
            'isrcs': recording.isrcs
        }
    
    pv_data = None
    if metadata['princevault']['matches']:
        best_match = metadata['princevault']['matches'][0]
        song = best_match.song
        pv_metadata = pv_service.parse_comprehensive_metadata(song)
        pv_data = {
            'title': song.title,
            'performer': song.performer,
            'recording_date': song.recording_date,
            'written_by': song.written_by,
            'produced_by': song.produced_by,
            'session_info': song.session_info,
            'personnel': song.personnel,
            'album_appearances': song.album_appearances,
            'related_versions': song.related_versions,
            'categories': pv_metadata.get('categories', []),
            'confidence': best_match.confidence,
            'raw_content': metadata['princevault']['raw_content']
        }
        # Include all parsed metadata fields
        for key, value in pv_metadata.items():
            if key not in pv_data and value:
                pv_data[key] = value
    
    llm_request = MetadataNormalizationRequest(
        filename=metadata['file_info']['filename'],
        acoustid_data={'matches': metadata['acoustid']['matches'][:3]},
        musicbrainz_data=mb_data,
        princevault_data=pv_data,
        file_tags=metadata['file_info']['tags'],
        duration_seconds=metadata['file_info']['duration_seconds']
    )
    
    # Get LLM normalization
    console.print()
    console.print("[bold]🤖 LLM Processing...[/bold]")
    with console.status("[bold green]Processing with LLM..."):
        normalized = llm_service.normalize_metadata(llm_request)
    
    # Display results
    console.print()
    console.print("[bold green]✅ Normalized Metadata:[/bold green]")
    
    result_table = Table(title="LLM Normalized Metadata", box=box.ROUNDED)
    result_table.add_column("Field", style="cyan")
    result_table.add_column("Value", style="white")
    
    result_table.add_row("Title", normalized.title or "Unknown")
    result_table.add_row("Artist", normalized.artist or "Unknown")
    if normalized.album:
        result_table.add_row("Album", normalized.album)
    if normalized.track_number:
        result_table.add_row("Track Number", str(normalized.track_number))
    if normalized.year:
        result_table.add_row("Year", str(normalized.year))
    if normalized.date:
        result_table.add_row("Date", normalized.date)
    if normalized.category:
        result_table.add_row("Category", normalized.category)
    if normalized.recording_date:
        result_table.add_row("Recording Date", normalized.recording_date)
    if normalized.venue:
        result_table.add_row("Venue", normalized.venue)
    if normalized.session_info:
        result_table.add_row("Session Info", normalized.session_info)
    if normalized.genre:
        result_table.add_row("Genre", normalized.genre)
    if normalized.comments:
        result_table.add_row("Comments", normalized.comments)
    
    result_table.add_row("Confidence", f"{normalized.confidence:.2f}")
    
    console.print(result_table)
    
    # Show raw LLM response if in debug mode
    if debug and normalized.llm_response:
        console.print()
        console.print("[bold]Raw LLM Response:[/bold]")
        console.print(f"[dim]{normalized.llm_response}[/dim]")
    
    if dry_run:
        console.print()
        console.print("[yellow]This was a dry run. No metadata was applied to the file.[/yellow]")


@app.command()
def tag(
    file_path: str = typer.Argument(..., help="Audio file to tag"),
    tag_only: bool = typer.Option(True, "--tag-only", help="Write tags in place (default)"),
    copy_place: bool = typer.Option(False, "--copy-place", help="Copy to destination and tag"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposed changes without applying")
) -> None:
    """Tag an audio file with normalized metadata."""
    
    console.print("[yellow]Tagging functionality coming in Phase 4![/yellow]")
    console.print(f"Would process: {file_path}")
    console.print(f"Mode: {'Tag-only' if tag_only else 'Copy+Place'}")
    if dry_run:
        console.print("[dim]Dry-run mode - no changes will be made[/dim]")


@app.command() 
def batch(
    directory: str = typer.Argument(..., help="Directory to process"),
    tag_only: bool = typer.Option(True, "--tag-only", help="Write tags in place (default)"),
    copy_place: bool = typer.Option(False, "--copy-place", help="Copy to destination and tag"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposed changes without applying")
) -> None:
    """Process multiple files in batch mode."""
    
    console.print("[yellow]Batch processing functionality coming in Phase 7![/yellow]")
    console.print(f"Would process directory: {directory}")


@app.callback()
def callback(
    version: Optional[bool] = typer.Option(None, "--version", help="Show version and exit")
) -> None:
    """Prince song tagger and metadata normalizer."""
    
    if version:
        from princer import __version__
        console.print(f"Princer v{__version__}")
        raise typer.Exit()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()