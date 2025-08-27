"""CLI interface for Princer."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box
from tabulate import tabulate

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


# Constants for readability
MAX_ACOUSTID_MATCHES = 3
MAX_SEARCH_TERMS = 2  
MAX_PV_MATCHES = 3
MIN_ACOUSTID_SCORE = 0.8
MIN_PV_CONFIDENCE = 0.7
MAX_CONTENT_LENGTH = 500


def _validate_audio_file(file_path: str) -> Path:
    """Validate that an audio file exists and is supported."""
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(1)
    
    if not AudioFile.is_supported(path):
        console.print(f"[red]Error:[/red] Unsupported file format: {path.suffix}")
        console.print(f"Supported formats: {', '.join(AudioFile.SUPPORTED_EXTENSIONS)}")
        raise typer.Exit(1)
    
    return path


def _check_api_key(cfg) -> None:
    """Check that required API key is available."""
    if not cfg.api.acoustid_key:
        console.print("[red]Error:[/red] No AcoustID API key found.")
        console.print("Set your API key in the ACOUSTID_KEY environment variable.")
        console.print("Get a free key at: https://acoustid.org/api-key")
        raise typer.Exit(1)


def _get_file_info(path: Path) -> dict:
    """Extract basic file information."""
    audio_file = AudioFile(path)
    info_result = audio_file.extract_info()
    
    return {
        'path': path,
        'filename': info_result.filename,
        'duration_seconds': info_result.duration_seconds,
        'format': getattr(info_result, 'format', 'Unknown'),
        'bitrate': getattr(info_result, 'bitrate', None),
        'tags': info_result.tags or {}
    }


def _get_acoustid_data(path: Path, acoustid_service: AcoustIDService) -> dict:
    """Generate fingerprint and get AcoustID matches."""
    acoustid_result = acoustid_service.fingerprint_file(path)
    
    if acoustid_result.error:
        raise ValueError(f"Fingerprinting failed: {acoustid_result.error}")
    
    return {
        'fingerprint': acoustid_result.fingerprint,
        'duration': acoustid_result.duration,
        'matches': acoustid_result.acoustid_matches
    }


def _get_musicbrainz_data(acoustid_data: dict, acoustid_service: AcoustIDService, mb_service: Optional[MusicBrainzService]) -> dict:
    """Collect MusicBrainz recordings from AcoustID matches."""
    recordings = []
    raw_recordings = []
    
    if acoustid_data['matches'] and mb_service:
        # Use a mock FingerprintResult to leverage existing logic
        from princer.services.acoustid import FingerprintResult
        acoustid_result = FingerprintResult(
            fingerprint=acoustid_data['fingerprint'],
            duration=acoustid_data['duration'],
            acoustid_matches=acoustid_data['matches']
        )
        
        best_matches = acoustid_service.get_best_matches(acoustid_result, min_score=MIN_ACOUSTID_SCORE)
        if best_matches:
            recording_ids = []
            for match in best_matches[:MAX_ACOUSTID_MATCHES]:
                recording_ids.extend(match.recording_ids)
            
            if recording_ids:
                mb_result = mb_service.lookup_recordings(recording_ids)
                if mb_result.recordings:
                    recordings = mb_result.recordings
                raw_recordings = mb_result.raw_recordings or []
    
    return {'recordings': recordings, 'raw_recordings': raw_recordings}


def _get_search_terms(acoustid_matches: list, filename: str) -> set:
    """Extract search terms from AcoustID matches or fallback to filename."""
    search_terms = set()
    
    if acoustid_matches:
        for match in acoustid_matches[:MAX_SEARCH_TERMS]:
            title = match.get('title', '').strip()
            if title and title.lower() != 'unknown':
                search_terms.add(title)
    
    # Fallback to filename if no good titles found
    if not search_terms:
        search_terms.add(filename)
    
    return search_terms


def _deduplicate_pv_matches(pv_matches: list) -> list:
    """Remove duplicate PrinceVault matches and sort by confidence."""
    seen_ids = set()
    unique_matches = []
    
    for match in pv_matches:
        if match.song.id not in seen_ids:
            unique_matches.append(match)
            seen_ids.add(match.song.id)
    
    return sorted(unique_matches, key=lambda x: x.confidence, reverse=True)[:MAX_PV_MATCHES]


def _get_princevault_data(acoustid_data: dict, filename: str, pv_service: Optional[PrinceVaultService]) -> dict:
    """Collect PrinceVault matches based on AcoustID data or filename."""
    matches = []
    raw_content = ""
    
    if not pv_service:
        return {'matches': matches, 'raw_content': raw_content}
    
    search_terms = _get_search_terms(acoustid_data['matches'], filename)
    
    # Search PrinceVault with each term
    for search_title in list(search_terms)[:MAX_SEARCH_TERMS]:
        pv_results = pv_service.search_by_title(search_title, limit=MAX_PV_MATCHES, min_confidence=MIN_PV_CONFIDENCE)
        if pv_results:
            matches.extend(pv_results)
            # Get raw content from best match for additional context
            if not raw_content and pv_results[0].confidence >= MIN_PV_CONFIDENCE:
                best_song = pv_results[0].song
                content = best_song.content
                raw_content = content[:MAX_CONTENT_LENGTH] + "..." if len(content) > MAX_CONTENT_LENGTH else content
    
    matches = _deduplicate_pv_matches(matches)
    return {'matches': matches, 'raw_content': raw_content}


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
    file_info = _get_file_info(path)
    acoustid_data = _get_acoustid_data(path, acoustid_service)
    musicbrainz_data = _get_musicbrainz_data(acoustid_data, acoustid_service, mb_service)
    princevault_data = _get_princevault_data(acoustid_data, file_info['filename'], pv_service)
    
    return {
        'file_info': file_info,
        'acoustid': acoustid_data,
        'musicbrainz': musicbrainz_data,
        'princevault': princevault_data
    }


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def _display_file_summary(metadata: dict) -> None:
    """Display basic file information table."""
    file_info = metadata['file_info']
    
    data = [["Duration", f"{file_info['duration_seconds']:.1f}s"]]
    if file_info['format'] != 'Unknown':
        data.append(["Format", file_info['format']])
    if file_info['bitrate']:
        bitrate_kbps = file_info['bitrate'] // 1000 if file_info['bitrate'] >= 1000 else file_info['bitrate']
        data.append(["Bitrate", f"{bitrate_kbps} kbps"])
    
    console.print(f"\n[bold]File: {file_info['filename']}[/bold]")
    console.print(tabulate(data, headers=["Property", "Value"], tablefmt="rounded_grid"))


def _display_current_tags(metadata: dict) -> None:
    """Display current file tags table."""
    file_tags = metadata['file_info']['tags']
    
    console.print(f"\n[bold]Current Tags[/bold]")
    if file_tags:
        data = [[key.title(), str(value)] for key, value in file_tags.items()]
        console.print(tabulate(data, headers=["Tag", "Value"], tablefmt="rounded_grid"))
    else:
        console.print("[dim]No tags found[/dim]")


def _display_fingerprint_info(metadata: dict) -> None:
    """Display audio fingerprint information table."""
    acoustid_data = metadata['acoustid']
    
    data = [
        ["Duration", f"{acoustid_data['duration']:.1f} seconds"],
        ["Fingerprint ID", acoustid_data['fingerprint'][:16] + "..."],
        ["AcoustID Matches", str(len(acoustid_data['matches']))]
    ]
    
    console.print(f"\n[bold]Audio Fingerprint[/bold]")
    console.print(tabulate(data, headers=["Property", "Value"], tablefmt="rounded_grid"))


def _display_musicbrainz_matches(raw_data: list) -> None:
    """Display raw MusicBrainz data for debug."""
    if not raw_data:
        return
        
    console.print()
    console.print("[bold]MusicBrainz Raw Data:[/bold]")
    console.print(json.dumps(raw_data, indent=2))


def _display_princevault_matches(matches: list) -> None:
    """Display raw PrinceVault data for debug."""
    if not matches:
        return
        
    console.print()
    console.print("[bold]PrinceVault Raw Data:[/bold]")
    # Convert to dict for JSON serialization
    raw_data = []
    for match in matches:
        raw_data.append({
            'confidence': match.confidence,
            'song': match.song.__dict__
        })
    console.print(json.dumps(raw_data, indent=2))


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
    
    path = _validate_audio_file(file_path)
    
    console.print(f"[dim]Analyzing file: {path}[/dim]")
    if verbose:
        console.print(f"[dim]Verbose mode enabled[/dim]")
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
    
    path = _validate_audio_file(file_path)
    console.print(f"[dim]Fingerprinting file: {path}[/dim]")
    
    # Load configuration and check API key
    cfg = ConfigLoader.load(config)
    _check_api_key(cfg)
    
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
    _display_file_summary(metadata)
    
    # Display existing tags
    console.print()
    _display_current_tags(metadata)
    
    # Display fingerprint info
    console.print()
    _display_fingerprint_info(metadata)
    
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
        if lookup_mb:
            _display_musicbrainz_matches(metadata['musicbrainz'].get('raw_recordings', []))
            
        # Display PrinceVault matches
        if lookup_pv:
            _display_princevault_matches(metadata['princevault']['matches'])
    
    else:
        console.print("\n[yellow]No AcoustID matches found for this file.[/yellow]")
        
        # Show PrinceVault matches even without AcoustID matches
        if lookup_pv:
            _display_princevault_matches(metadata['princevault']['matches'])


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
    
    path = _validate_audio_file(file_path)
    console.print(f"[dim]Normalizing metadata for: {path}[/dim]")
    
    # Load configuration and check API key
    cfg = ConfigLoader.load(config)
    _check_api_key(cfg)
    
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
        
        # MusicBrainz section - show raw JSON for debug
        console.print("[bold cyan]🎵 MUSICBRAINZ DATA[/bold cyan]")
        if metadata['musicbrainz'].get('raw_recordings'):
            import json
            console.print("[dim]Raw JSON (as sent to LLM):[/dim]")
            console.print(json.dumps(metadata['musicbrainz']['raw_recordings'][0], indent=2))
        else:
            console.print("No MusicBrainz matches found")
        console.print()
        
        # PrinceVault section  
        console.print("[bold cyan]👑 PRINCEVAULT DATA[/bold cyan]")
        
        # Show what search terms were used
        search_terms = _get_search_terms(metadata['acoustid']['matches'], metadata['file_info']['filename'])
        console.print(f"Search terms used: {', '.join(search_terms)}")
        
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
            
            # Show raw content length for debug
            if song.content:
                console.print(f"Raw Content Length: {len(song.content)} chars")
        else:
            console.print("No PrinceVault matches found")
        console.print()
        
        # LLM prompt section - will show complete prompts after request is built
        console.print("[bold cyan]🤖 LLM PROMPT PREVIEW[/bold cyan]")
        console.print("[dim]Complete prompts will be shown below after request is built...[/dim]")
        console.print("─" * 80)
        console.print()
    
    # Prepare LLM request with ALL the collected data
    from princer.services.llm import MetadataNormalizationRequest
    
    # Convert to format expected by current LLM service
    mb_data = None
    if metadata['musicbrainz'].get('raw_recordings'):
        # Use raw JSON data instead of parsed objects
        mb_data = metadata['musicbrainz']['raw_recordings'][0]
    
    pv_data = None
    if metadata['princevault']['matches']:
        best_match = metadata['princevault']['matches'][0]
        song = best_match.song
        # Use raw song data instead of complex parsing
        song_dict = {
            'id': song.id,
            'title': song.title,
            'content': song.content,
            'page_id': song.page_id,
            'revision_id': song.revision_id,
            'timestamp': song.timestamp,
            'contributor': song.contributor,
            'recording_date': song.recording_date,
            'session_info': song.session_info,
            'personnel': song.personnel,
            'album_appearances': song.album_appearances,
            'related_versions': song.related_versions,
            'performer': song.performer,
            'written_by': song.written_by,
            'produced_by': song.produced_by
        }
        pv_data = {
            'confidence': best_match.confidence,
            'song': song_dict,  # JSON-serializable song data
            'raw_content': metadata['princevault']['raw_content']
        }
    
    # Format file info for LLM
    file_info = metadata['file_info']
    format_str = file_info['format'] if file_info['format'] != 'Unknown' else "Unknown"
    bitrate_str = f"{file_info['bitrate'] // 1000} kbps" if file_info['bitrate'] else "Unknown"
    
    llm_request = MetadataNormalizationRequest(
        filename=file_info['filename'],
        acoustid_data={'matches': metadata['acoustid']['matches'][:3]},
        musicbrainz_data=mb_data,
        princevault_data=pv_data,
        file_tags=file_info['tags'],
        duration_seconds=file_info['duration_seconds'],
        format_info=format_str,
        bitrate=bitrate_str
    )
    
    # Show complete LLM prompts if in debug mode
    if debug:
        console.print()
        console.print("[bold yellow]🤖 COMPLETE LLM PROMPTS[/bold yellow]")
        console.print("=" * 80)
        console.print("[bold]SYSTEM PROMPT:[/bold]")
        console.print(llm_service.config.llm.system_prompt)
        console.print()
        console.print("[bold]USER PROMPT:[/bold]")
        user_prompt = llm_service._build_normalization_prompt(llm_request)
        console.print(user_prompt)
        console.print("=" * 80)
        console.print()
    
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
    console.print(f"Config: {config or 'default'}")
    console.print(f"Copy+Place: {copy_place}")
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
    console.print(f"Mode: {'Tag-only' if tag_only else 'Copy+Place'}")
    console.print(f"Config: {config or 'default'}")
    console.print(f"Copy+Place: {copy_place}")
    if dry_run:
        console.print("[dim]Dry-run mode - no changes will be made[/dim]")


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