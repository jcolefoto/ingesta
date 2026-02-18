#!/usr/bin/env python3
"""
Command-line interface for ingesta media ingestion tool.
"""

import logging
import sys
from pathlib import Path
from typing import List, Optional

import click
from tqdm import tqdm

from .ingestion import ingest_media, IngestionJob
from .sync import sync_audio_video
from .premiere import create_premiere_project
from .analysis import ContentAnalyzer
from .checksum import get_supported_algorithms


# Setup logging
def setup_logging(verbose: bool, log_file: Optional[str] = None):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


@click.group()
@click.version_option(version="0.1.0")
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """
    ingesta - Media Ingestion Tool
    
    Combines Shotput Pro-style offloading with verification and
    Pluralize-style audio sync capabilities.
    
    Commands:
        ingest     Copy and verify media files
        sync       Sync external audio to video
        premiere   Create Adobe Premiere Pro project
        analyze    Analyze clips for content type
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)


@cli.command()
@click.option('--source', '-s', required=True, type=click.Path(exists=True),
              help='Source directory or file')
@click.option('--dest', '-d', required=True, multiple=True,
              help='Destination directory (can be used multiple times)')
@click.option('--checksum', '-c', default='xxhash64',
              type=click.Choice(get_supported_algorithms()),
              help='Checksum algorithm (default: xxhash64)')
@click.option('--verify/--no-verify', default=True,
              help='Verify files after copy (default: True)')
@click.option('--log-file', '-l', type=click.Path(),
              help='Path to log file')
@click.option('--include', multiple=True,
              help='File patterns to include (e.g., *.mov,*.mp4)')
@click.option('--exclude', multiple=True,
              help='File patterns to exclude')
@click.option('--report', '-r', type=click.Path(),
              help='Save JSON report to file')
@click.pass_context
def ingest(ctx, source, dest, checksum, verify, log_file, include, exclude, report):
    """
    Copy media from source to destination(s) with verification.
    
    Example:
        ingesta ingest -s /Volumes/CARD001 -d /Backup/Project001
        ingesta ingest -s ./video -d /Backup1 -d /Backup2 -c xxhash64
    """
    setup_logging(ctx.obj['verbose'], log_file)
    
    click.echo(f"Starting ingestion from: {source}")
    click.echo(f"Destinations: {', '.join(dest)}")
    click.echo(f"Checksum algorithm: {checksum}")
    
    # Progress bar callback
    pbar = tqdm(unit="files")
    
    def progress_callback(filename, total, current):
        pbar.total = total
        pbar.set_description(f"Copying {filename}")
        pbar.update(1)
    
    try:
        job = ingest_media(
            source=source,
            destinations=list(dest),
            checksum_algorithm=checksum,
            verify=verify,
            include_patterns=list(include) if include else None,
            exclude_patterns=list(exclude) if exclude else None,
            log_file=log_file,
            progress_callback=progress_callback
        )
        
        pbar.close()
        
        # Print summary
        click.echo(f"\n✓ Ingestion complete!")
        click.echo(f"  Files processed: {len(job.files_processed)}")
        click.echo(f"  Successful: {job.success_count}")
        click.echo(f"  Failed: {job.failure_count}")
        click.echo(f"  Total size: {job.total_bytes / (1024**3):.2f} GB")
        
        if report:
            job.save_report(report)
            click.echo(f"  Report saved: {report}")
        
        # Exit with error if any failures
        if job.failure_count > 0:
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--video-dir', '-v', required=True, type=click.Path(exists=True),
              help='Directory containing video files')
@click.option('--audio-dir', '-a', required=True, type=click.Path(exists=True),
              help='Directory containing audio files')
@click.option('--output-dir', '-o', required=True, type=click.Path(),
              help='Output directory for synced files')
@click.option('--tolerance', '-t', default=0.5, type=float,
              help='Sync tolerance in seconds (default: 0.5)')
@click.option('--prefix', '-p', default='synced_',
              help='Prefix for output filenames')
@click.option('--method', '-m', default='waveform',
              type=click.Choice(['waveform', 'timecode']),
              help='Sync method (default: waveform)')
@click.pass_context
def sync(ctx, video_dir, audio_dir, output_dir, tolerance, prefix, method):
    """
    Sync external audio files to video clips.
    
    Uses waveform matching to automatically align audio tracks.
    
    Example:
        ingesta sync -v ./video -a ./audio -o ./synced
        ingesta sync -v ./video -a ./audio -o ./synced -t 0.3
    """
    setup_logging(ctx.obj['verbose'])
    
    click.echo(f"Syncing audio to video...")
    click.echo(f"  Video directory: {video_dir}")
    click.echo(f"  Audio directory: {audio_dir}")
    click.echo(f"  Output directory: {output_dir}")
    click.echo(f"  Tolerance: {tolerance}s")
    
    try:
        results = sync_audio_video(
            video_dir=video_dir,
            audio_dir=audio_dir,
            output_dir=output_dir,
            tolerance=tolerance,
            prefix=prefix,
            progress_callback=lambda current, total: click.echo(
                f"  Progress: {current}/{total}", nl=False, err=True
            )
        )
        
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        
        click.echo(f"\n✓ Sync complete!")
        click.echo(f"  Successful: {successful}")
        click.echo(f"  Failed: {failed}")
        
        if successful > 0:
            click.echo(f"  Output directory: {output_dir}")
        
        if failed > 0:
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--media-dir', '-m', required=True, type=click.Path(exists=True),
              help='Directory containing media files')
@click.option('--output', '-o', required=True, type=click.Path(),
              help='Output path for .prproj file')
@click.option('--name', '-n', help='Project name (default: directory name)')
@click.option('--fps', default=24.0, type=float,
              help='Frame rate (default: 24)')
@click.option('--resolution', '-r', default='1920x1080',
              help='Resolution as WIDTHxHEIGHT (default: 1920x1080)')
@click.option('--analyze/--no-analyze', default=True,
              help='Analyze and classify clips (default: True)')
@click.pass_context
def premiere(ctx, media_dir, output, name, fps, resolution, analyze):
    """
    Create an Adobe Premiere Pro project file.
    
    Automatically organizes clips into bins based on content analysis.
    
    Example:
        ingesta premiere -m ./media -o project.prproj
        ingesta premiere -m ./media -o project.prproj --fps 30 --resolution 3840x2160
    """
    setup_logging(ctx.obj['verbose'])
    
    click.echo(f"Creating Premiere project...")
    click.echo(f"  Media directory: {media_dir}")
    click.echo(f"  Output: {output}")
    click.echo(f"  Resolution: {resolution}")
    click.echo(f"  FPS: {fps}")
    
    if analyze:
        click.echo("  Analyzing clips for organization...")
    
    try:
        report = create_premiere_project(
            media_dir=media_dir,
            output_path=output,
            name=name,
            fps=fps,
            resolution=resolution,
            analyze_content=analyze
        )
        
        click.echo(f"\n✓ Project created: {output}")
        click.echo(f"  Total clips: {report['total_clips']}")
        click.echo(f"  Total duration: {report['total_duration']:.1f}s")
        
        if analyze and report.get('bins'):
            click.echo("\n  Bins created:")
            for bin_name, bin_info in report['bins'].items():
                click.echo(f"    - {bin_name}: {bin_info['count']} clips")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--media-dir', '-m', required=True, type=click.Path(exists=True),
              help='Directory containing media files')
@click.option('--output', '-o', type=click.Path(),
              help='Save analysis report to JSON file')
@click.option('--syncable-only', is_flag=True,
              help='Only show syncable clips')
@click.pass_context
def analyze(ctx, media_dir, output, syncable_only):
    """
    Analyze video clips and classify them by content type.
    
    Identifies B-roll, establishing shots, interviews, and syncable clips.
    
    Example:
        ingesta analyze -m ./video
        ingesta analyze -m ./video -o report.json
        ingesta analyze -m ./video --syncable-only
    """
    setup_logging(ctx.obj['verbose'])
    
    click.echo(f"Analyzing clips in: {media_dir}")
    
    try:
        analyzer = ContentAnalyzer()
        analyses = analyzer.analyze_directory(media_dir)
        
        if syncable_only:
            analyses = analyzer.get_syncable_clips(analyses)
            click.echo(f"\nFound {len(analyses)} syncable clips:\n")
        else:
            click.echo(f"\nAnalyzed {len(analyses)} clips:\n")
        
        # Group by type
        organized = analyzer.organize_by_type(analyses)
        
        for clip_type, clips in organized.items():
            if not clips:
                continue
            
            click.echo(f"{clip_type.value.upper()} ({len(clips)} clips):")
            for clip in clips:
                sync_indicator = "✓" if clip.is_syncable else "✗"
                click.echo(f"  {sync_indicator} {clip.file_path.name}")
                click.echo(f"     Duration: {clip.duration:.1f}s | "
                          f"Audio: {clip.audio_type.value} | "
                          f"Motion: {clip.motion_score:.2f}")
            click.echo()
        
        # Summary
        report = analyzer.generate_report(analyses)
        click.echo("Summary:")
        click.echo(f"  Total clips: {report['total_clips']}")
        click.echo(f"  Total duration: {report['total_duration']:.1f}s")
        click.echo(f"  Syncable clips: {report['syncable_clips']}")
        
        if output:
            import json
            with open(output, 'w') as f:
                json.dump(report, f, indent=2)
            click.echo(f"\nReport saved: {output}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
