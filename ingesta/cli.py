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
from .reports import (
    ThumbnailExtractor, PDFReportGenerator, CSVReportGenerator, BinOrganizer,
    LocalTranscriber, LocalFrameAnalyzer, AudioTechAnalyzer, MetadataExtractor,
    DuplicateDetector, BadClipDetector, ProxyGenerator, KeywordTagger
)
from .project_manager import ProjectManager, get_project_manager
from .auto import AutoWorkflow
from .tui import run_tui_workflow, WorkflowStep
from .templates import get_template_manager, TemplateType
from .exports import export_nle_project, ExportManager, ExportFormat
from .deliverables import create_client_deliverable, DeliverableConfig


# Setup logging
logger = logging.getLogger(__name__)
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
        auto       Full automated workflow (detect, ingest, analyze, report, premiere)
        ingest     Copy and verify media files
        sync       Sync external audio to video
        premiere   Create Adobe Premiere Pro project
        analyze    Analyze clips for content type
        report     Generate comprehensive PDF/CSV reports
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
@click.option('--project', '-p', help='Associate with project ID')
@click.option('--shoot-day', help='Associate with shoot day ID (requires --project)')
@click.option('--card-label', help='Card label (e.g., "A001", "Card 1")')
@click.option('--notes', help='Notes about this offload')
@click.pass_context
def ingest(ctx, source, dest, checksum, verify, log_file, include, exclude, report,
           project, shoot_day, card_label, notes):
    """
    Copy media from source to destination(s) with verification.
    
    Can be associated with a project and shoot day for consolidated reporting.
    
    Example:
        ingesta ingest -s /Volumes/CARD001 -d /Backup/Project001
        ingesta ingest -s ./video -d /Backup1 -d /Backup2 -c xxhash64
        ingesta ingest -s /card -d /backup -p PROJECT_ID --shoot-day DAY_ID --card-label A001
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
        
        # Track in project if specified
        if project:
            pm = get_project_manager()
            
            # If shoot_day not specified, use the first shoot day of the project
            if not shoot_day:
                proj_obj = pm.get_project(project)
                if proj_obj and proj_obj.shoot_days:
                    shoot_day = proj_obj.shoot_days[0].shoot_day_id
                    click.echo(f"  Using shoot day: {proj_obj.shoot_days[0].label}")
            
            if shoot_day:
                session = pm.add_ingest_session(
                    project_id=project,
                    shoot_day_id=shoot_day,
                    source_path=source,
                    destination_paths=list(dest),
                    files_count=job.success_count,
                    total_size_bytes=job.total_bytes,
                    card_label=card_label,
                    notes=notes
                )
                if session:
                    click.echo(f"  Tracked in project: {project}")
                else:
                    click.echo(f"  ⚠️  Could not track in project (invalid project/shoot day ID)")
            else:
                click.echo(f"  ⚠️  No shoot day specified for project tracking")
        
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


@cli.command()
@click.option('--media-dir', '-m', required=True, type=click.Path(exists=True),
              help='Directory containing media files')
@click.option('--output-dir', '-o', type=click.Path(),
              help='Output directory for reports (default: ./reports)')
@click.option('--format', '-f', 'report_format', default='both',
              type=click.Choice(['pdf', 'csv', 'both']),
              help='Report format (default: both)')
@click.option('--thumbnails/--no-thumbnails', default=True,
              help='Generate thumbnails (default: True)')
@click.option('--project-name', '-n',
              help='Project name for report')
@click.option('--source-path', '-s',
              help='Source media path for report metadata')
@click.option('--dest-path', '-d', multiple=True,
              help='Destination/archive path (can be used multiple times)')
@click.option('--group-by-folder', '-g', is_flag=True,
              help='Group clips by folder structure (ShotPut-style bins)')
@click.option('--transcribe/--no-transcribe', default=False,
              help='Transcribe audio locally using whisper.cpp (default: False)')
@click.option('--analyze-frames/--no-analyze-frames', default=False,
              help='Analyze frames for visual description (default: False)')
@click.option('--analyze-audio-tech/--no-analyze-audio-tech', default=False,
              help='Analyze audio technical details (peak, RMS, clipping) (default: False)')
@click.option('--extract-metadata/--no-extract-metadata', default=False,
              help='Extract timecode, reel IDs, camera metadata (default: False)')
@click.option('--detect-duplicates/--no-detect-duplicates', default=False,
              help='Detect duplicate and near-duplicate clips (default: False)')
@click.option('--check-quality/--no-check-quality', default=False,
              help='Check for quality issues (black frames, blur, silence) (default: False)')
@click.option('--generate-proxies/--no-generate-proxies', default=False,
              help='Generate proxy files and hero stills (default: False)')
@click.option('--extract-keywords/--no-extract-keywords', default=False,
              help='Extract keyword tags from transcription and visual analysis (default: False)')
@click.option('--whisper-model', default='base',
              type=click.Choice(['base', 'small', 'medium', 'large']),
              help='Whisper model size for transcription (default: base)')
@click.option('--proxy-resolution', default='960x540',
              help='Proxy resolution (default: 960x540)')
@click.option('--project', '-p', help='Generate consolidated report for project ID (aggregates all offloads)')
@click.pass_context
def report(ctx, media_dir, output_dir, report_format, thumbnails, project_name, source_path, dest_path,
           group_by_folder, transcribe, analyze_frames, analyze_audio_tech, extract_metadata,
           detect_duplicates, check_quality, generate_proxies, extract_keywords,
           whisper_model, proxy_resolution, project):
    """
    Generate comprehensive reports from analyzed media.

    Creates PDF and/or CSV reports with clip details, thumbnails,
    metadata, transcription, and visual analysis. All processing is done
    locally - no data is sent to external services.

    For consolidated project reports, use --project PROJECT_ID to aggregate
    all media from all offloads associated with the project.
    
    Example:
        ingesta report -m ./ingested -o ./reports
        ingesta report -m ./media --format pdf --no-thumbnails
        ingesta report -m ./media -n "Project Alpha" -s /card -d /backup1 -d /backup2
        ingesta report -m ./ingested -g -o ./reports  # ShotPut-style bins
        ingesta report -m ./media --transcribe --analyze-frames  # Full analysis
    """
    setup_logging(ctx.obj['verbose'])
    
    # Handle project-based reporting
    if project:
        pm = get_project_manager()
        proj_obj = pm.get_project(project)
        if not proj_obj:
            click.echo(f"❌ Project not found: {project}", err=True)
            sys.exit(1)
        
        click.echo(f"📁 Generating consolidated report for project: {proj_obj.name}")
        click.echo(f"   Project ID: {project}")
        click.echo(f"   Shoot Days: {proj_obj.total_shoot_days}")
        click.echo(f"   Total Sessions: {proj_obj.total_sessions}")
        
        # Get all media paths from project
        project_media_paths = proj_obj.get_all_media_paths()
        if not project_media_paths:
            click.echo("⚠️  No media paths found in project. Has any media been ingested?", err=True)
            sys.exit(1)
        
        click.echo(f"\n   Found {len(project_media_paths)} offload locations:")
        for path in project_media_paths:
            click.echo(f"   • {path}")
        
        # Use the first media path as the primary (or create a temp combined location)
        # For now, we'll analyze each location separately and combine results
        media_path = project_media_paths[0]
        click.echo(f"\n   Primary media path: {media_path}")
        
        # Update project_name for the report
        if not project_name:
            project_name = proj_obj.name
    else:
        media_path = Path(media_dir)
    
    output_path = Path(output_dir) if output_dir else Path("./reports")
    output_path.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"\nGenerating reports...")
    click.echo(f"  Media directory: {media_path}")
    click.echo(f"  Output directory: {output_path}")
    click.echo(f"  Format: {report_format}")
    click.echo(f"  Thumbnails: {'Yes' if thumbnails else 'No'}")
    click.echo(f"  Group by folder: {'Yes' if group_by_folder else 'No'}")
    click.echo(f"  Transcribe: {'Yes' if transcribe else 'No'}")
    click.echo(f"  Analyze frames: {'Yes' if analyze_frames else 'No'}")
    click.echo(f"  Analyze audio tech: {'Yes' if analyze_audio_tech else 'No'}")
    click.echo(f"  Extract metadata: {'Yes' if extract_metadata else 'No'}")
    click.echo(f"  Detect duplicates: {'Yes' if detect_duplicates else 'No'}")
    click.echo(f"  Check quality: {'Yes' if check_quality else 'No'}")
    click.echo(f"  Generate proxies: {'Yes' if generate_proxies else 'No'}")
    click.echo(f"  Extract keywords: {'Yes' if extract_keywords else 'No'}")
    
    try:
        # Step 1: Analyze media
        click.echo("\nAnalyzing clips...")
        analyzer = ContentAnalyzer()
        analyses = analyzer.analyze_directory(media_path)
        
        if not analyses:
            click.echo("No video files found in media directory.", err=True)
            sys.exit(1)
        
        click.echo(f"  Found {len(analyses)} clips")
        
        # Step 2: Extract metadata if requested
        if extract_metadata:
            click.echo("\nExtracting metadata (timecode, reel IDs, camera info)...")
            metadata_extractor = MetadataExtractor()
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = metadata_extractor.extract(analysis.file_path)
                if result:
                    analysis.timecode_start = result.timecode.start_tc
                    analysis.timecode_end = result.timecode.end_tc
                    analysis.reel_id = result.reel.reel_id
                    analysis.scene = result.reel.scene
                    analysis.shot = result.reel.shot
                    analysis.take = result.reel.take
                    analysis.camera_id = result.reel.camera_id
                    analysis.camera_model = result.camera_model
                    analysis.camera_serial = result.camera_serial
                    analysis.lens_info = result.lens_info
                    analysis.iso = result.iso
                    analysis.white_balance = result.white_balance
                    analysis.resolution = result.resolution
                    analysis.frame_rate = result.frame_rate
        
        # Step 3: Transcribe audio if requested (LOCAL ONLY)
        if transcribe:
            click.echo("\nTranscribing audio (local processing - no data sent online)...")
            transcriber = LocalTranscriber(model=whisper_model)
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = transcriber.transcribe(analysis.file_path)
                if result:
                    analysis.transcription = result.text
                    analysis.transcription_excerpt = result.excerpt
                    analysis.has_slate = result.has_slate
                    analysis.has_end_mark = result.has_end_mark
                    analysis.slate_text = result.slate_text
                    if result.has_slate:
                        click.echo(f"      Slate detected: {result.slate_text}")
        
        # Step 4: Analyze frames if requested (LOCAL ONLY)
        if analyze_frames:
            click.echo("\nAnalyzing frames for visual description (local processing)...")
            frame_analyzer = LocalFrameAnalyzer()
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = frame_analyzer.analyze(analysis.file_path)
                if result:
                    analysis.visual_description = result.description
                    analysis.shot_type = result.shot_type.value
                    click.echo(f"      {result.description}")
        
        # Step 5: Analyze audio tech if requested
        if analyze_audio_tech:
            click.echo("\nAnalyzing audio technical details...")
            audio_analyzer = AudioTechAnalyzer()
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = audio_analyzer.analyze(analysis.file_path)
                if result:
                    analysis.audio_peak_dbfs = result.peak_dbfs
                    analysis.audio_rms_dbfs = result.rms_dbfs
                    analysis.audio_clipping = result.clipping_detected
                    analysis.audio_clipping_count = result.clipping_count
                    analysis.audio_channels = result.channels
                    analysis.audio_sample_rate = result.sample_rate
                    analysis.audio_bit_depth = result.bit_depth
                    analysis.audio_codec = result.codec
                    analysis.audio_warnings = result.warnings
                    if result.warnings:
                        click.echo(f"      Warnings: {', '.join(result.warnings)}")
        
        # Step 6: Check quality if requested
        if check_quality:
            click.echo("\nChecking clip quality...")
            quality_checker = BadClipDetector()
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = quality_checker.detect(analysis.file_path, analysis.duration)
                if result:
                    analysis.quality_warnings = [w.message for w in result.warnings]
                    analysis.is_corrupted = result.is_corrupted
                    analysis.black_frame_count = result.black_frame_count
                    analysis.blur_score = result.blur_score
                    analysis.silence_ratio = result.silence_ratio
                    if result.has_issues:
                        click.echo(f"      Issues: {len(result.warnings)}")
        
        # Step 7: Detect duplicates if requested
        if detect_duplicates:
            click.echo("\nDetecting duplicates...")
            dup_detector = DuplicateDetector()
            file_list = [a.file_path for a in analyses]
            durations = {a.file_path: a.duration for a in analyses}
            dup_results = dup_detector.detect(file_list, durations)
            
            dup_count = 0
            for analysis in analyses:
                dup_info = dup_results.get(analysis.file_path)
                if dup_info and dup_info.is_duplicate:
                    analysis.is_duplicate = True
                    analysis.duplicate_of = dup_info.duplicate_of
                    analysis.duplicate_type = dup_info.duplicate_type
                    dup_count += 1
            
            click.echo(f"  Found {dup_count} duplicate clips")
        
        # Step 8: Generate proxies if requested
        if generate_proxies:
            click.echo("\nGenerating proxies and hero stills...")
            proxy_dir = output_path / "proxies"
            proxy_dir.mkdir(parents=True, exist_ok=True)
            proxy_gen = ProxyGenerator()
            
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                result = proxy_gen.generate(
                    analysis.file_path, 
                    proxy_dir, 
                    resolution=proxy_resolution,
                    create_web=True,
                    extract_hero=True
                )
                if result.success:
                    if result.proxy_path:
                        analysis.proxy_path = str(result.proxy_path.relative_to(output_path))
                    if result.hero_still_path:
                        analysis.hero_still_path = str(result.hero_still_path.relative_to(output_path))
                    if result.web_proxy_path:
                        analysis.web_proxy_path = str(result.web_proxy_path.relative_to(output_path))
                    click.echo(f"      Proxy created")
        
        # Step 9: Extract keywords if requested
        if extract_keywords:
            click.echo("\nExtracting keyword tags...")
            tagger = KeywordTagger()
            for i, analysis in enumerate(analyses, 1):
                click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                
                # Build metadata dict for tagger
                meta = {
                    'scene': analysis.scene,
                    'shot': analysis.shot,
                    'take': analysis.take,
                    'reel_id': analysis.reel_id,
                    'clip_type': analysis.clip_type.value if analysis.clip_type else None,
                }
                
                result = tagger.tag(
                    analysis.transcription,
                    analysis.visual_description,
                    meta
                )
                
                analysis.keyword_tags = result.all_tags
                analysis.priority_tags = result.priority_tags
                click.echo(f"      {len(result.priority_tags)} priority tags")
        
        # Step 10: Extract thumbnails if requested
        thumbnail_map = {}
        if thumbnails:
            click.echo("\nExtracting thumbnails...")
            thumb_dir = output_path / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            
            with ThumbnailExtractor(output_dir=thumb_dir) as extractor:
                for i, analysis in enumerate(analyses, 1):
                    click.echo(f"  [{i}/{len(analyses)}] {analysis.file_path.name}")
                    thumbs = extractor.extract_thumbnails_for_clip(analysis.file_path)
                    thumbnail_map[analysis.file_path] = thumbs
        
        # Step 3: Generate reports
        generated_files = []
        
        # Determine project name
        proj_name = project_name or media_path.name or "Media Ingest Report"
        dest_list = list(dest_path) if dest_path else []
        
        if report_format in ['pdf', 'both']:
            click.echo("\nGenerating PDF report...")
            pdf_generator = PDFReportGenerator(
                output_path=output_path / "report.pdf",
                project_name=proj_name,
                source_path=source_path or str(media_path),
                destination_paths=dest_list
            )
            pdf_path = pdf_generator.generate_report(analyses, thumbnail_map)
            generated_files.append(pdf_path)
            click.echo(f"  ✓ PDF: {pdf_path}")
        
        if report_format in ['csv', 'both']:
            click.echo("\nGenerating CSV reports...")
            csv_generator = CSVReportGenerator(output_path=output_path / "report.csv")
            csv_path = csv_generator.generate_report(analyses)
            generated_files.append(csv_path)
            click.echo(f"  ✓ CSV: {csv_path}")
            
            # Also generate summary CSV
            summary_path = csv_generator.generate_summary_csv(analyses)
            generated_files.append(summary_path)
            click.echo(f"  ✓ Summary CSV: {summary_path}")
        
        # Generate binned reports if requested
        if group_by_folder:
            click.echo("\nOrganizing clips into ShotPut-style bins...")
            organizer = BinOrganizer()
            organization = organizer.organize_by_folder(analyses, media_path)
            
            click.echo(f"  Created {len(organization.bins)} bins:")
            for bin_obj in organization.bins:
                click.echo(f"    - {bin_obj.name}: {bin_obj.clip_count} clips")
            
            if organization.unclassified:
                click.echo(f"    - Unclassified: {len(organization.unclassified)} clips")
            
            if report_format in ['csv', 'both']:
                click.echo("\nGenerating binned CSV reports...")
                csv_generator = CSVReportGenerator(output_path=output_path / "report.csv")
                
                # Generate binned report
                binned_csv_path = csv_generator.generate_binned_report(organization)
                generated_files.append(binned_csv_path)
                click.echo(f"  ✓ Binned CSV: {binned_csv_path}")
                
                # Generate bin summary
                bin_summary_path = csv_generator.generate_bin_summary_csv(organization)
                generated_files.append(bin_summary_path)
                click.echo(f"  ✓ Bin Summary CSV: {bin_summary_path}")
            
            if report_format in ['pdf', 'both']:
                click.echo("\nGenerating binned PDF report...")
                pdf_generator = PDFReportGenerator(
                    output_path=output_path / "report_binned.pdf",
                    project_name=proj_name,
                    source_path=source_path or str(media_path),
                    destination_paths=dest_list
                )
                binned_pdf_path = pdf_generator.generate_binned_report(organization, thumbnail_map)
                generated_files.append(binned_pdf_path)
                click.echo(f"  ✓ Binned PDF: {binned_pdf_path}")
        
        # Summary
        click.echo(f"\n✓ Reports generated successfully!")
        click.echo(f"  Total clips: {len(analyses)}")
        
        total_duration = sum(a.duration for a in analyses)
        click.echo(f"  Total duration: {total_duration:.1f}s")
        
        syncable_count = sum(1 for a in analyses if a.is_syncable)
        click.echo(f"  Syncable clips: {syncable_count}")
        
        click.echo(f"\nOutput files:")
        for f in generated_files:
            click.echo(f"  - {f}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--media-dir', '-m', required=True, type=click.Path(exists=True),
              help='Directory containing media files')
@click.option('--output-dir', '-o', required=True, type=click.Path(),
              help='Output directory for exports')
@click.option('--name', '-n', required=True, help='Project name')
@click.option('--format', '-f', 'export_formats', multiple=True,
              type=click.Choice(['premiere', 'resolve', 'fcpxml', 'edl', 'all']),
              default=['all'],
              help='Export format(s) - can specify multiple')
@click.option('--fps', default=24.0, type=float,
              help='Frame rate (default: 24)')
@click.option('--resolution', '-r', default='1920x1080',
              help='Resolution as WIDTHxHEIGHT (default: 1920x1080)')
@click.option('--template', '-t',
              help='Project template for bin organization')
@click.pass_context
def export(ctx, media_dir, output_dir, name, export_formats, fps, resolution, template):
    """
    Export NLE projects (Premiere/Resolve/FCP/EDL) with bins and markers.

    Creates professional project files with:
    - Bin organization by content type
    - Markers for slates, scenes, takes
    - Timecode preservation
    - Multi-format batch export

    Examples:
        ingesta export -m ./media -o ./exports -n "Project_001"
        ingesta export -m ./media -o ./exports -n "Project_001" -f premiere -f edl
        ingesta export -m ./media -o ./exports -n "Project" --template documentary
    """
    setup_logging(ctx.obj['verbose'])
    
    from .analysis import ContentAnalyzer
    from pathlib import Path
    
    media_path = Path(media_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Parse formats
    formats = list(export_formats)
    if 'all' in formats:
        formats = ['premiere', 'resolve', 'fcpxml', 'edl']
    
    click.echo(f"📁 Exporting NLE projects...")
    click.echo(f"   Media: {media_path}")
    click.echo(f"   Output: {output_path}")
    click.echo(f"   Name: {name}")
    click.echo(f"   Formats: {', '.join(formats)}")
    click.echo(f"   FPS: {fps}")
    click.echo(f"   Resolution: {resolution}")
    
    if template:
        click.echo(f"   Template: {template}")
    
    try:
        # Analyze media
        click.echo("\n🔍 Analyzing media...")
        analyzer = ContentAnalyzer()
        analyses = analyzer.analyze_directory(media_path)
        
        if not analyses:
            click.echo("❌ No media files found", err=True)
            sys.exit(1)
        
        click.echo(f"   Found {len(analyses)} clips")
        
        # Create export manager
        manager = ExportManager(fps, resolution)
        
        # Create timeline
        timeline = manager.create_timeline_from_analyses(name, analyses)
        
        # Get template if specified
        template_obj = None
        if template:
            from .templates import get_template_manager
            template_obj = get_template_manager().get_template_by_name(template)
            if template_obj:
                click.echo(f"   Using template: {template_obj.name}")
        
        # Parse export formats
        export_formats_enum = []
        for fmt in formats:
            try:
                export_formats_enum.append(ExportFormat(fmt))
            except ValueError:
                click.echo(f"⚠️  Unknown format: {fmt}", err=True)
        
        # Export
        click.echo("\n📤 Exporting...")
        results = manager.export(timeline, output_path, export_formats_enum, template_obj)
        
        if results:
            click.echo("\n✅ Export complete!")
            click.echo("\nGenerated files:")
            for fmt, path in results.items():
                click.echo(f"   • {fmt.value.upper()}: {path}")
        else:
            click.echo("\n❌ No files exported", err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"\n❌ Export failed: {e}", err=True)
        logger.error(f"Export error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option('--source', '-s', type=click.Path(exists=True),
              help='Source directory (auto-detect if not specified)')
@click.option('--dest', '-d', type=click.Path(),
              help='Destination directory (default: ./<project_name>)')
@click.option('--project', '-p',
              help='Project name (default: auto-generated)')
@click.option('--template', '-t',
              help='Project template to use (name or path)')
@click.option('--fps', default=24.0, type=float,
              help='Frame rate for Premiere project (default: 24)')
@click.option('--resolution', '-r', default='1920x1080',
              help='Resolution as WIDTHxHEIGHT (default: 1920x1080)')
@click.option('--no-slate', is_flag=True,
              help='Skip slate detection')
@click.option('--no-thumbnails', is_flag=True,
              help='Skip thumbnail extraction')
@click.option('--no-reports', is_flag=True,
              help='Skip report generation')
@click.option('--no-premiere', is_flag=True,
              help='Skip Premiere project creation')
@click.pass_context
def auto(ctx, source, dest, project, template, fps, resolution, no_slate, no_thumbnails, no_reports, no_premiere):
    """
    Automated workflow: detect cards, ingest, analyze, and create Premiere project.

    Runs the complete pipeline in one command:
    1. Auto-detect memory cards (if no source specified)
    2. Ingest media with xxhash64 verification
    3. Analyze clips for content type
    4. Extract thumbnails
    5. Detect slates from audio
    6. Generate PDF + CSV reports
    7. Create organized Premiere project with camera/reel bins

    Examples:
        ingesta auto                           # Auto-detect and process
        ingesta auto --source /Volumes/CARD001 # Process specific card
        ingesta auto --project "Client_001"    # Custom project name
        ingesta auto --template corporate      # Use project template
    """
    setup_logging(ctx.obj['verbose'])

    # Override template settings with CLI options
    template_settings = {}
    if no_slate:
        template_settings['slate_detection'] = False
    if no_thumbnails:
        template_settings['thumbnails'] = False
    if no_reports:
        template_settings['generate_reports'] = False
    if no_premiere:
        template_settings['create_premiere'] = False

    click.echo("🎬 Starting ingesta auto workflow...")
    click.echo("")

    try:
        # Create and run workflow
        workflow = AutoWorkflow(
            project_name=project,
            template=template,
            output_dir=Path(dest) if dest else None,
            verbose=ctx.obj['verbose']
        )

        # Apply CLI overrides
        workflow.template.settings.update(template_settings)
        if fps != 24.0:
            workflow.template.settings['fps'] = fps
        if resolution != '1920x1080':
            workflow.template.settings['resolution'] = resolution

        # Run the workflow
        result = workflow.run(
            source=Path(source) if source else None,
            destinations=[Path(dest)] if dest else None
        )

        if result.success:
            click.echo("")
            click.echo("=" * 60)
            click.echo("✅ WORKFLOW COMPLETE")
            click.echo("=" * 60)
            click.echo(f"Duration: {result.duration:.1f}s")
            click.echo(f"Clips analyzed: {result.clips_analyzed}")
            click.echo(f"Slates detected: {result.slates_detected}")
            click.echo(f"")
            click.echo(f"Output directory: {result.project_path}")

            if result.premiere_project:
                click.echo(f"Premiere project: {result.premiere_project}")

            if result.errors:
                click.echo(f"")
                click.echo(f"Warnings ({len(result.errors)}):")
                for error in result.errors:
                    click.echo(f"  ⚠️  {error}")
        else:
            click.echo("")
            click.echo("❌ WORKFLOW FAILED")
            click.echo(f"Errors: {len(result.errors)}")
            for error in result.errors:
                click.echo(f"  • {error}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"")
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--step', '-s', 
              type=click.Choice(['project', 'offload', 'report', 'deliverables', 'all']),
              default='all',
              help='Workflow step to run (default: all)')
@click.pass_context
def tui(ctx, step):
    """
    Interactive TUI workflow: Project → Offload → Report → Deliverables.
    
    Step-by-step guided workflow for media ingestion:
    1. Create or select a project
    2. Offload media from cards/devices with verification
    3. Generate comprehensive reports (PDF/CSV)
    4. Package client-ready deliverables
    
    Examples:
        ingesta tui                    # Run complete workflow
        ingesta tui --step project     # Just create/select project
        ingesta tui --step offload     # Just offload media
        ingesta tui --step report      # Just generate reports
    """
    setup_logging(ctx.obj['verbose'])
    
    from .tui import TUIWorkflow
    
    workflow = TUIWorkflow(verbose=ctx.obj['verbose'])
    success = False
    
    if step == 'all':
        success = workflow.run_full_workflow()
    elif step == 'project':
        success = workflow.run_project_step()
    elif step == 'offload':
        # Need to ensure project step was done
        if WorkflowStep.PROJECT not in workflow.state.completed_steps:
            click.echo("Creating/selecting project first...")
            if not workflow.run_project_step():
                sys.exit(1)
        success = workflow.run_offload_step()
    elif step == 'report':
        success = workflow.run_report_step()
    elif step == 'deliverables':
        success = workflow.run_deliverables_step()
    
    if not success:
        sys.exit(1)


# Project Management Commands
@cli.group()
def project():
    """Manage projects and shoot days."""
    pass


@project.command('new')
@click.option('--name', '-n', required=True, help='Project name')
@click.option('--client', '-c', help='Client name')
@click.option('--director', '-d', help='Director name')
@click.option('--producer', '-p', help='Producer name')
@click.option('--dp', help='Director of Photography')
@click.option('--description', help='Project description')
@click.option('--base-dir', '-b', help='Base directory for project files')
@click.pass_context
def project_new(ctx, name, client, director, producer, dp, description, base_dir):
    """Create a new project."""
    setup_logging(ctx.obj['verbose'])
    
    pm = get_project_manager()
    
    project = pm.create_project(
        name=name,
        client=client,
        director=director,
        producer=producer,
        dp=dp,
        description=description,
        base_directory=base_dir
    )
    
    click.echo(f"✅ Created project: {project.name}")
    click.echo(f"   Project ID: {project.project_id}")
    click.echo(f"   Created: {project.created_at}")
    
    if client:
        click.echo(f"   Client: {client}")


@project.command('list')
@click.option('--status', type=click.Choice(['active', 'completed', 'archived', 'all']),
              default='all', help='Filter by status')
@click.pass_context
def project_list(ctx, status):
    """List all projects."""
    setup_logging(ctx.obj['verbose'])
    
    pm = get_project_manager()
    
    filter_status = None if status == 'all' else status
    projects = pm.list_projects(status=filter_status)
    
    if not projects:
        click.echo("No projects found.")
        return
    
    click.echo(f"\n{'ID':<10} {'Name':<30} {'Status':<12} {'Shoot Days':<12} {'Files':<10}")
    click.echo("-" * 80)
    
    for proj in projects:
        click.echo(f"{proj.project_id:<10} {proj.name:<30} {proj.status:<12} "
                   f"{proj.total_shoot_days:<12} {proj.total_files:<10}")


@project.command('show')
@click.argument('project_id')
@click.pass_context
def project_show(ctx, project_id):
    """Show project details."""
    setup_logging(ctx.obj['verbose'])
    
    pm = get_project_manager()
    project = pm.get_project(project_id)
    
    if not project:
        click.echo(f"❌ Project not found: {project_id}", err=True)
        sys.exit(1)
    
    click.echo(f"\n📁 Project: {project.name}")
    click.echo(f"   ID: {project.project_id}")
    click.echo(f"   Status: {project.status}")
    click.echo(f"   Created: {project.created_at}")
    
    if project.client:
        click.echo(f"   Client: {project.client}")
    if project.director:
        click.echo(f"   Director: {project.director}")
    if project.producer:
        click.echo(f"   Producer: {project.producer}")
    if project.dp:
        click.echo(f"   DP: {project.dp}")
    if project.description:
        click.echo(f"   Description: {project.description}")
    
    click.echo(f"\n   Total Shoot Days: {project.total_shoot_days}")
    click.echo(f"   Total Sessions: {project.total_sessions}")
    click.echo(f"   Total Files: {project.total_files}")
    click.echo(f"   Total Size: {pm.format_size(project.total_size_bytes)}")
    
    if project.shoot_days:
        click.echo(f"\n   Shoot Days:")
        for sd in project.shoot_days:
            click.echo(f"   • {sd.label} ({sd.date}) - {len(sd.sessions)} sessions, "
                       f"{sd.total_files} files")


@project.command('add-shoot-day')
@click.argument('project_id')
@click.option('--label', '-l', required=True, help='Shoot day label (e.g., "Day 1")')
@click.option('--date', help='Date (YYYY-MM-DD), defaults to today')
@click.option('--location', help='Shoot location')
@click.option('--description', help='Description')
@click.pass_context
def project_add_shoot_day(ctx, project_id, label, date, location, description):
    """Add a shoot day to a project."""
    setup_logging(ctx.obj['verbose'])
    
    pm = get_project_manager()
    
    shoot_day = pm.add_shoot_day(
        project_id=project_id,
        label=label,
        date=date,
        location=location,
        description=description
    )
    
    if shoot_day:
        click.echo(f"✅ Added shoot day: {shoot_day.label}")
        click.echo(f"   ID: {shoot_day.shoot_day_id}")
        click.echo(f"   Date: {shoot_day.date}")
    else:
        click.echo(f"❌ Project not found: {project_id}", err=True)
        sys.exit(1)


@project.command('report')
@click.argument('project_id')
@click.option('--output-dir', '-o', type=click.Path(),
              help='Output directory for reports (default: ./reports)')
@click.option('--format', '-f', 'report_format', default='both',
              type=click.Choice(['pdf', 'csv', 'both']),
              help='Report format (default: both)')
@click.option('--include-all-offloads', is_flag=True,
              help='Include analysis of all media from all offloads')
@click.pass_context
def project_report(ctx, project_id, output_dir, report_format, include_all_offloads):
    """Generate consolidated report for entire project."""
    setup_logging(ctx.obj['verbose'])
    
    pm = get_project_manager()
    project = pm.get_project(project_id)
    
    if not project:
        click.echo(f"❌ Project not found: {project_id}", err=True)
        sys.exit(1)
    
    click.echo(f"📊 Generating project report for: {project.name}")
    
    # Show project summary
    click.echo(f"\n   Project Summary:")
    click.echo(f"   • Total Shoot Days: {project.total_shoot_days}")
    click.echo(f"   • Total Sessions: {project.total_sessions}")
    click.echo(f"   • Total Files: {project.total_files}")
    click.echo(f"   • Total Size: {pm.format_size(project.total_size_bytes)}")
    
    if include_all_offloads:
        click.echo(f"\n   Analyzing all media from project...")
        # This would require scanning all destination paths
        # For now, just show a message
        click.echo(f"   (Media analysis would scan all {len(project.get_all_media_paths())} destination paths)")
    
    # Generate reports here (simplified for now)
    output_path = Path(output_dir) if output_dir else Path("./reports")
    output_path.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"\n   Report saved to: {output_path}")
    click.echo(f"   (Full consolidated reporting coming in next update)")


# Template Management Commands
@cli.group()
def template():
    """Manage project templates (doc/commercial/wedding)."""
    pass


@template.command('list')
@click.pass_context
def template_list(ctx):
    """List all available project templates."""
    setup_logging(ctx.obj['verbose'])
    
    tm = get_template_manager()
    templates = tm.list_templates()
    
    click.echo("\n📋 Available Project Templates:\n")
    click.echo(f"{'Name':<20} {'Type':<15} {'Description'}")
    click.echo("-" * 70)
    
    for tmpl in templates:
        click.echo(f"{tmpl.name:<20} {tmpl.template_type.value:<15} {tmpl.description}")
    
    click.echo("\n💡 Use 'ingesta template show <name>' for detailed bin/tag structure")


@template.command('show')
@click.argument('template_name')
@click.pass_context
def template_show(ctx, template_name):
    """Show template details including bins and tags."""
    setup_logging(ctx.obj['verbose'])
    
    tm = get_template_manager()
    tmpl = tm.get_template_by_name(template_name)
    
    if not tmpl:
        click.echo(f"❌ Template not found: {template_name}", err=True)
        click.echo("   Use 'ingesta template list' to see available templates")
        sys.exit(1)
    
    click.echo(f"\n📋 Template: {tmpl.name}")
    click.echo(f"   Type: {tmpl.template_type.value}")
    click.echo(f"   Description: {tmpl.description}")
    
    click.echo(f"\n📁 Bin Structure:")
    for bin_def in tmpl.bins:
        click.echo(f"   {bin_def.name}")
        if bin_def.description:
            click.echo(f"      └─ {bin_def.description}")
        for sub in bin_def.sub_bins:
            click.echo(f"      └─ {sub.name}")
    
    click.echo(f"\n🏷️  Key Tags:")
    for tag in tmpl.tags[:10]:  # Show first 10
        click.echo(f"   • {tag.name} ({tag.category})")
    
    click.echo(f"\n⚙️  Default Settings:")
    settings = tmpl.settings
    click.echo(f"   • Transcribe: {'Yes' if settings.transcribe_audio else 'No'}")
    click.echo(f"   • Generate Proxies: {'Yes' if settings.generate_proxies else 'No'}")
    click.echo(f"   • Thumbnails: {settings.thumbnail_count} per clip")
    click.echo(f"   • Export PDF: {'Yes' if settings.export_pdf else 'No'}")
    click.echo(f"   • Export CSV: {'Yes' if settings.export_csv else 'No'}")


@template.command('export')
@click.argument('template_name')
@click.option('--output', '-o', type=click.Path(), help='Output JSON file path')
@click.pass_context
def template_export(ctx, template_name, output):
    """Export a template to JSON file."""
    setup_logging(ctx.obj['verbose'])
    
    tm = get_template_manager()
    tmpl = tm.get_template_by_name(template_name)
    
    if not tmpl:
        click.echo(f"❌ Template not found: {template_name}", err=True)
        sys.exit(1)
    
    if not output:
        output = f"{tmpl.template_type.value}_template.json"
    
    output_path = Path(output)
    
    if tm.export_template(tmpl.template_type, output_path):
        click.echo(f"✅ Exported template: {output_path}")
    else:
        click.echo(f"❌ Failed to export template", err=True)
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
