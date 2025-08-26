"""CLI interface for Princer."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from princer.models.audio import AudioFile, AudioFileInfo

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
def tag(
    file_path: str = typer.Argument(..., help="Audio file to tag"),
    tag_only: bool = typer.Option(True, "--tag-only", help="Write tags in place (default)"),
    copy_place: bool = typer.Option(False, "--copy-place", help="Copy to destination and tag"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Configuration file path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposed changes without applying")
) -> None:
    """Tag an audio file with normalized metadata."""
    
    console.print("[yellow]Tagging functionality coming in Phase 2![/yellow]")
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