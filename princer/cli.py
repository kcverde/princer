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

app = typer.Typer(
    name="tagger",
    help="Prince song tagger and metadata normalizer",
    no_args_is_help=True
)

console = Console()


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
    lookup_mb: bool = typer.Option(True, "--lookup-mb", help="Look up matches in MusicBrainz")
) -> None:
    """Generate audio fingerprint and find matches via AcoustID + MusicBrainz."""
    
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
    
    # Generate fingerprint and get AcoustID matches
    with console.status("[bold green]Generating fingerprint..."):
        result = acoustid_service.fingerprint_file(path)
    
    if result.error:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(1)
    
    # Display fingerprint info
    console.print()
    fp_table = Table(title="Audio Fingerprint", box=box.ROUNDED)
    fp_table.add_column("Property", style="cyan")
    fp_table.add_column("Value", style="white")
    
    fp_table.add_row("Duration", f"{result.duration:.1f} seconds")
    fp_table.add_row("Fingerprint ID", result.fingerprint[:16] + "...")
    fp_table.add_row("AcoustID Matches", str(len(result.acoustid_matches)))
    
    console.print(fp_table)
    
    # Display AcoustID matches
    if result.acoustid_matches:
        console.print()
        matches_table = Table(title="AcoustID Matches", box=box.ROUNDED)
        matches_table.add_column("Score", style="yellow")
        matches_table.add_column("Recording ID", style="green") 
        matches_table.add_column("Title", style="white")
        matches_table.add_column("Artist", style="blue")
        
        for match in result.acoustid_matches[:5]:  # Show top 5
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
        
        # Look up detailed MusicBrainz info for best matches
        if lookup_mb and mb_service:
            best_matches = acoustid_service.get_best_matches(result, min_score=0.8)
            if best_matches:
                console.print()
                console.print("[bold]Looking up MusicBrainz details for best matches...[/bold]")
                
                recording_ids = []
                for match in best_matches[:3]:  # Top 3 matches only
                    recording_ids.extend(match.recording_ids)
                
                if recording_ids:
                    with console.status("[bold green]Querying MusicBrainz..."):
                        mb_result = mb_service.lookup_recordings(recording_ids)
                    
                    if mb_result.recordings:
                        for i, recording in enumerate(mb_result.recordings, 1):
                            console.print()
                            console.print(f"[bold cyan]Match {i}: {recording.title} by {recording.artist_name}[/bold cyan]")
                            
                            # Basic info table
                            basic_table = Table(box=box.ROUNDED)
                            basic_table.add_column("Property", style="cyan")
                            basic_table.add_column("Value", style="white")
                            
                            # Duration
                            duration = "Unknown"
                            if recording.length:
                                try:
                                    length_ms = int(recording.length)
                                    duration_sec = length_ms // 1000
                                    minutes = duration_sec // 60
                                    seconds = duration_sec % 60
                                    duration = f"{minutes}:{seconds:02d}"
                                except (ValueError, TypeError):
                                    duration = "Unknown"
                            
                            basic_table.add_row("Date", recording.date or "Unknown")
                            basic_table.add_row("Duration", duration)
                            if recording.disambiguation:
                                basic_table.add_row("Notes", recording.disambiguation)
                            if recording.release_status:
                                basic_table.add_row("Status", recording.release_status)
                            
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
                            
                    
                    if mb_result.error:
                        console.print(f"[yellow]Warning:[/yellow] MusicBrainz errors: {mb_result.error}")
    
    else:
        console.print("\n[yellow]No AcoustID matches found for this file.[/yellow]")


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