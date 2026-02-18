"""
Smart multicam detection and sync analysis module for ingesta.

Goes beyond simple sync to:
1. Detect overlapping timecode to create multicam bins
2. Analyze unsynced clips to categorize them (B-roll vs broken multicam)
3. Detect visual patterns suggesting multicam sequences
4. Identify timecode discontinuities indicating recording issues
5. Provide reasoning for sync failures and categorization

Unlike PluralEyes which dumps unsynced clips at the end, this module
analyzes WHY a clip didn't sync and categorizes it appropriately.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import re

from ..analysis import ClipAnalysis, ClipType


logger = logging.getLogger(__name__)


class UnsyncedCategory(Enum):
    """Categories for unsynced clips."""
    B_ROLL = "b_roll"  # Likely B-roll, intentionally no external audio
    BROKEN_MULTICAM = "broken_multicam"  # Should have synced but didn't
    TECHNICAL_ISSUE = "technical_issue"  # Corrupted, wrong format
    UNKNOWN = "unknown"  # Can't determine
    NO_AUDIO = "no_audio"  # Clip has no audio to sync
    OUT_OF_RANGE = "out_of_range"  # Timecode outside sync window


class MulticamReason(Enum):
    """Reasons for multicam categorization."""
    TIME_OVERLAP = "time_overlap"  # Timecode overlaps with other cameras
    VISUAL_SIMILARITY = "visual_similarity"  # Similar visual content
    SLATE_MATCH = "slate_match"  # Same slate/scene/take
    AUDIO_CORRELATION = "audio_correlation"  # Similar ambient audio
    TEMPORAL_PROXIMITY = "temporal_proximity"  # Close in time


@dataclass
class MulticamGroup:
    """A group of clips that form a multicam sequence."""
    group_id: str
    clips: List[ClipAnalysis] = field(default_factory=list)
    start_timecode: Optional[str] = None
    end_timecode: Optional[str] = None
    reasons: List[MulticamReason] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class UnsyncedClipAnalysis:
    """Analysis of a clip that couldn't be synced."""
    clip: ClipAnalysis
    category: UnsyncedCategory
    confidence: float  # 0.0 to 1.0
    reasons: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    potential_multicam_groups: List[str] = field(default_factory=list)


@dataclass
class SyncAnalysisResult:
    """Complete sync analysis result."""
    synced_clips: List[Tuple[ClipAnalysis, ClipAnalysis]] = field(default_factory=list)  # (video, audio) pairs
    multicam_groups: List[MulticamGroup] = field(default_factory=list)
    unsynced_analysis: List[UnsyncedClipAnalysis] = field(default_factory=list)
    timecode_gaps: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class MulticamDetector:
    """Detect multicam sequences from clip analyses."""
    
    # Thresholds
    TIMECODE_OVERLAP_THRESHOLD_SECONDS = 30  # Min overlap to be considered multicam
    TEMPORAL_PROXIMITY_THRESHOLD_SECONDS = 60  # Clips within this time might be related
    VISUAL_SIMILARITY_THRESHOLD = 0.6  # Confidence threshold
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_timecode(self, tc: Optional[str]) -> Optional[int]:
        """
        Parse timecode string to total seconds.
        
        Supports formats:
        - HH:MM:SS:FF
        - HH:MM:SS
        - HH:MM:SS;FF (drop frame)
        """
        if not tc:
            return None
        
        # Clean up timecode
        tc = tc.strip().replace(';', ':')
        
        # Try HH:MM:SS:FF format
        pattern = r'(\d+):(\d+):(\d+)(?::(\d+))?'
        match = re.match(pattern, tc)
        
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            # frames = int(match.group(4)) if match.group(4) else 0
            
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return total_seconds
        
        return None
    
    def timecode_overlap(self, start1: str, end1: str, start2: str, end2: str) -> float:
        """Calculate overlap in seconds between two timecode ranges."""
        s1 = self.parse_timecode(start1) or 0
        e1 = self.parse_timecode(end1) or s1
        s2 = self.parse_timecode(start2) or 0
        e2 = self.parse_timecode(end2) or s2
        
        # Calculate overlap
        overlap_start = max(s1, s2)
        overlap_end = min(e1, e2)
        
        if overlap_end > overlap_start:
            return overlap_end - overlap_start
        
        return 0.0
    
    def detect_multicam_groups(self, analyses: List[ClipAnalysis]) -> List[MulticamGroup]:
        """
        Detect multicam groups based on timecode overlap and other signals.
        
        Args:
            analyses: List of clip analyses
            
        Returns:
            List of detected multicam groups
        """
        groups = []
        processed = set()
        
        # Group by camera/reel ID
        by_camera: Dict[str, List[ClipAnalysis]] = defaultdict(list)
        for analysis in analyses:
            reel_id = getattr(analysis, 'reel_id', None)
            camera_id = getattr(analysis, 'camera_id', None)
            key = reel_id or camera_id or analysis.file_path.stem[:4]
            by_camera[key].append(analysis)
        
        # Look for timecode overlaps between different cameras
        camera_ids = list(by_camera.keys())
        
        for i, cam1 in enumerate(camera_ids):
            for cam2 in camera_ids[i+1:]:
                for clip1 in by_camera[cam1]:
                    if id(clip1) in processed:
                        continue
                    
                    for clip2 in by_camera[cam2]:
                        if id(clip2) in processed:
                            continue
                        
                        # Check timecode overlap
                        tc1_start = getattr(clip1, 'timecode_start', None)
                        tc1_end = getattr(clip1, 'timecode_end', None)
                        tc2_start = getattr(clip2, 'timecode_start', None)
                        tc2_end = getattr(clip2, 'timecode_end', None)
                        
                        if tc1_start and tc1_end and tc2_start and tc2_end:
                            overlap = self.timecode_overlap(
                                tc1_start, tc1_end,
                                tc2_start, tc2_end
                            )
                            
                            if overlap >= self.TIMECODE_OVERLAP_THRESHOLD_SECONDS:
                                # Create multicam group
                                group = MulticamGroup(
                                    group_id=f"multicam_{len(groups)+1:03d}",
                                    clips=[clip1, clip2],
                                    start_timecode=min(tc1_start, tc2_start),
                                    end_timecode=max(tc1_end, tc2_end),
                                    reasons=[MulticamReason.TIME_OVERLAP],
                                    confidence=min(overlap / 60.0, 1.0)  # Scale confidence
                                )
                                groups.append(group)
                                processed.add(id(clip1))
                                processed.add(id(clip2))
        
        self.logger.info(f"Detected {len(groups)} multicam groups")
        return groups
    
    def analyze_unsynced_clip(self, 
                             clip: ClipAnalysis,
                             all_clips: List[ClipAnalysis],
                             multicam_groups: List[MulticamGroup]) -> UnsyncedClipAnalysis:
        """
        Analyze why a clip couldn't be synced and categorize it.
        
        This goes beyond PluralEyes' simple "dump at end" approach
        to provide intelligent categorization and reasoning.
        
        Args:
            clip: The unsynced clip
            all_clips: All clips in the project
            multicam_groups: Detected multicam groups
            
        Returns:
            UnsyncedClipAnalysis with categorization and reasoning
        """
        reasons = []
        recommendations = []
        potential_groups = []
        confidence = 0.5
        
        # Check 1: Does it have audio?
        if not clip.has_audio:
            category = UnsyncedCategory.NO_AUDIO
            reasons.append("Clip has no audio stream")
            recommendations.append("This appears to be intentionally shot without audio (B-roll)")
            confidence = 0.9
            
            # But check if it SHOULD have audio based on context
            scene = getattr(clip, 'scene', None)
            if scene:
                # Check if other clips in same scene have audio
                scene_clips = [c for c in all_clips 
                              if getattr(c, 'scene', None) == scene and c.has_audio]
                if scene_clips:
                    category = UnsyncedCategory.BROKEN_MULTICAM
                    reasons.append(f"Other clips in scene {scene} have audio - this clip should too")
                    recommendations.append("Possible camera audio recording failure")
                    confidence = 0.7
            
            return UnsyncedClipAnalysis(
                clip=clip,
                category=category,
                confidence=confidence,
                reasons=reasons,
                recommendations=recommendations,
                potential_multicam_groups=potential_groups
            )
        
        # Check 2: Is it clearly B-roll based on characteristics?
        if (clip.clip_type in [ClipType.B_ROLL, ClipType.ESTABLISHING] and 
            clip.duration < 10 and not clip.is_syncable):
            category = UnsyncedCategory.B_ROLL
            reasons.append(f"Clip classified as {clip.clip_type.value} with short duration ({clip.duration:.1f}s)")
            reasons.append("No clear dialogue or sync audio detected")
            recommendations.append("Likely B-roll footage - no external audio expected")
            confidence = 0.85
            
            return UnsyncedClipAnalysis(
                clip=clip,
                category=category,
                confidence=confidence,
                reasons=reasons,
                recommendations=recommendations
            )
        
        # Check 3: Does it overlap with multicam groups but didn't sync?
        clip_start = self.parse_timecode(getattr(clip, 'timecode_start', None))
        clip_end = self.parse_timecode(getattr(clip, 'timecode_end', None))
        
        if clip_start and clip_end:
            for group in multicam_groups:
                group_start = self.parse_timecode(group.start_timecode)
                group_end = self.parse_timecode(group.end_timecode)
                
                if group_start and group_end:
                    overlap = self.timecode_overlap(
                        getattr(clip, 'timecode_start', ''),
                        getattr(clip, 'timecode_end', ''),
                        group.start_timecode or '',
                        group.end_timecode or ''
                    )
                    
                    if overlap > 10:  # Significant overlap
                        potential_groups.append(group.group_id)
                        category = UnsyncedCategory.BROKEN_MULTICAM
                        reasons.append(f"Timecode overlaps with multicam group {group.group_id}")
                        reasons.append(f"Overlap: {overlap:.1f} seconds")
                        reasons.append("Should have synced but waveform matching failed")
                        recommendations.append("Check if camera audio was recorded")
                        recommendations.append("Verify external audio recorder was running")
                        recommendations.append("Possible timecode drift between devices")
                        confidence = 0.75
                        
                        return UnsyncedClipAnalysis(
                            clip=clip,
                            category=category,
                            confidence=confidence,
                            reasons=reasons,
                            recommendations=recommendations,
                            potential_multicam_groups=potential_groups
                        )
        
        # Check 4: Same slate/scene/take as synced clips?
        clip_slate = getattr(clip, 'slate_text', None)
        clip_scene = getattr(clip, 'scene', None)
        clip_take = getattr(clip, 'take', None)
        
        if clip_slate or clip_scene:
            matching_synced = []
            for other in all_clips:
                if other == clip:
                    continue
                
                other_slate = getattr(other, 'slate_text', None)
                other_scene = getattr(other, 'scene', None)
                other_take = getattr(other, 'take', None)
                
                # Check for matches
                if (clip_slate and clip_slate == other_slate) or \
                   (clip_scene and clip_scene == other_scene and 
                    clip_take and clip_take == other_take):
                    matching_synced.append(other)
            
            if matching_synced:
                category = UnsyncedCategory.BROKEN_MULTICAM
                reasons.append(f"Same slate/scene as {len(matching_synced)} synced clip(s)")
                if clip_slate:
                    reasons.append(f"Slate: {clip_slate}")
                if clip_scene:
                    reasons.append(f"Scene {clip_scene}, Take {clip_take}")
                recommendations.append("Clip should sync with matching takes - check audio waveform")
                confidence = 0.8
                
                return UnsyncedClipAnalysis(
                    clip=clip,
                    category=category,
                    confidence=confidence,
                    reasons=reasons,
                    recommendations=recommendations
                )
        
        # Check 5: Check for technical issues
        is_corrupted = getattr(clip, 'is_corrupted', False)
        quality_warnings = getattr(clip, 'quality_warnings', [])
        
        if is_corrupted or quality_warnings:
            category = UnsyncedCategory.TECHNICAL_ISSUE
            reasons.append("Technical issues detected")
            if is_corrupted:
                reasons.append("File appears corrupted")
            for warning in quality_warnings[:3]:
                reasons.append(f"QC: {warning}")
            recommendations.append("Check source media integrity")
            recommendations.append("Re-copy file if needed")
            confidence = 0.9
            
            return UnsyncedClipAnalysis(
                clip=clip,
                category=category,
                confidence=confidence,
                reasons=reasons,
                recommendations=recommendations
            )
        
        # Default: Unknown
        category = UnsyncedCategory.UNKNOWN
        reasons.append("Unable to determine why clip didn't sync")
        recommendations.append("Manual review required")
        if clip.is_syncable:
            reasons.append("Clip has syncable audio but waveform matching failed")
            recommendations.append("Try manual sync or adjust sync tolerance")
        
        return UnsyncedClipAnalysis(
            clip=clip,
            category=category,
            confidence=0.3,
            reasons=reasons,
            recommendations=recommendations
        )
    
    def find_timecode_gaps(self, analyses: List[ClipAnalysis]) -> List[Dict[str, Any]]:
        """
        Find timecode gaps that might indicate recording issues.
        
        Args:
            analyses: List of clip analyses
            
        Returns:
            List of detected gaps with details
        """
        gaps = []
        
        # Group by camera
        by_camera: Dict[str, List[ClipAnalysis]] = defaultdict(list)
        for analysis in analyses:
            reel_id = getattr(analysis, 'reel_id', None)
            camera_id = getattr(analysis, 'camera_id', None)
            key = reel_id or camera_id or 'unknown'
            by_camera[key].append(analysis)
        
        # Sort each camera's clips by timecode
        for camera_id, clips in by_camera.items():
            clips_with_tc = []
            for clip in clips:
                tc_start = self.parse_timecode(getattr(clip, 'timecode_start', None))
                tc_end = self.parse_timecode(getattr(clip, 'timecode_end', None))
                if tc_start is not None:
                    clips_with_tc.append((tc_start, tc_end or tc_start, clip))
            
            # Sort by start time
            clips_with_tc.sort(key=lambda x: x[0])
            
            # Look for gaps
            for i in range(len(clips_with_tc) - 1):
                current_end = clips_with_tc[i][1]
                next_start = clips_with_tc[i + 1][0]
                gap = next_start - current_end
                
                if gap > 60:  # Gap larger than 60 seconds
                    gaps.append({
                        'camera': camera_id,
                        'gap_seconds': gap,
                        'gap_formatted': self._format_duration(gap),
                        'before_clip': clips_with_tc[i][2].file_path.name,
                        'after_clip': clips_with_tc[i + 1][2].file_path.name,
                        'potential_issue': gap > 300  # Flag if > 5 minutes
                    })
        
        return gaps
    
    def _format_duration(self, seconds: float) -> str:
        """Format seconds as readable duration."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def analyze_sync_results(self, 
                            video_clips: List[ClipAnalysis],
                            audio_clips: List[ClipAnalysis],
                            synced_pairs: List[Tuple[ClipAnalysis, ClipAnalysis]],
                            unsynced_videos: List[ClipAnalysis]) -> SyncAnalysisResult:
        """
        Comprehensive sync analysis including multicam detection.
        
        Args:
            video_clips: All video clips
            audio_clips: All audio clips
            synced_pairs: Successfully synced (video, audio) pairs
            unsynced_videos: Video clips that couldn't be synced
            
        Returns:
            SyncAnalysisResult with full analysis
        """
        all_clips = video_clips + audio_clips
        
        # Detect multicam groups
        multicam_groups = self.detect_multicam_groups(video_clips)
        
        # Analyze each unsynced clip
        unsynced_analysis = []
        for clip in unsynced_videos:
            analysis = self.analyze_unsynced_clip(clip, all_clips, multicam_groups)
            unsynced_analysis.append(analysis)
        
        # Find timecode gaps
        timecode_gaps = self.find_timecode_gaps(video_clips)
        
        # Generate summary
        summary = self._generate_summary(
            video_clips, audio_clips, synced_pairs, 
            unsynced_analysis, multicam_groups
        )
        
        return SyncAnalysisResult(
            synced_clips=synced_pairs,
            multicam_groups=multicam_groups,
            unsynced_analysis=unsynced_analysis,
            timecode_gaps=timecode_gaps,
            summary=summary
        )
    
    def _generate_summary(self,
                         video_clips: List[ClipAnalysis],
                         audio_clips: List[ClipAnalysis],
                         synced_pairs: List[Tuple[ClipAnalysis, ClipAnalysis]],
                         unsynced_analysis: List[UnsyncedClipAnalysis],
                         multicam_groups: List[MulticamGroup]) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_videos = len(video_clips)
        total_audio = len(audio_clips)
        synced_count = len(synced_pairs)
        unsynced_count = len(unsynced_analysis)
        
        # Categorize unsynced
        category_counts = defaultdict(int)
        for analysis in unsynced_analysis:
            category_counts[analysis.category.value] += 1
        
        # Count potential issues
        broken_multicam = sum(1 for a in unsynced_analysis 
                             if a.category == UnsyncedCategory.BROKEN_MULTICAM)
        technical_issues = sum(1 for a in unsynced_analysis 
                              if a.category == UnsyncedCategory.TECHNICAL_ISSUE)
        
        return {
            'total_video_clips': total_videos,
            'total_audio_clips': total_audio,
            'synced_count': synced_count,
            'unsynced_count': unsynced_count,
            'sync_rate': synced_count / total_videos if total_videos > 0 else 0,
            'multicam_groups_detected': len(multicam_groups),
            'unsynced_by_category': dict(category_counts),
            'potential_broken_multicam': broken_multicam,
            'technical_issues': technical_issues,
            'requires_manual_review': sum(1 for a in unsynced_analysis 
                                         if a.category == UnsyncedCategory.UNKNOWN),
        }
    
    def export_analysis_report(self, result: SyncAnalysisResult, output_path: Path) -> Path:
        """
        Export sync analysis as formatted text report.
        
        Args:
            result: SyncAnalysisResult to export
            output_path: Path to save report
            
        Returns:
            Path to exported file
        """
        lines = []
        lines.append("=" * 80)
        lines.append("SMART SYNC ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        # Summary
        summary = result.summary
        lines.append("SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Video clips: {summary['total_video_clips']}")
        lines.append(f"Audio clips: {summary['total_audio_clips']}")
        lines.append(f"Successfully synced: {summary['synced_count']} ({summary['sync_rate']:.1%})")
        lines.append(f"Unsynced: {summary['unsynced_count']}")
        lines.append(f"Multicam groups: {summary['multicam_groups_detected']}")
        lines.append("")
        
        # Unsynced breakdown
        if result.unsynced_analysis:
            lines.append("UNSYNCED CLIP ANALYSIS")
            lines.append("-" * 80)
            lines.append("")
            
            # Group by category
            by_category: Dict[UnsyncedCategory, List[UnsyncedClipAnalysis]] = defaultdict(list)
            for analysis in result.unsynced_analysis:
                by_category[analysis.category].append(analysis)
            
            for category in [UnsyncedCategory.BROKEN_MULTICAM, 
                           UnsyncedCategory.B_ROLL,
                           UnsyncedCategory.TECHNICAL_ISSUE,
                           UnsyncedCategory.NO_AUDIO,
                           UnsyncedCategory.UNKNOWN]:
                if category in by_category:
                    items = by_category[category]
                    lines.append(f"\n{category.value.upper().replace('_', ' ')} ({len(items)} clips)")
                    lines.append("-" * 40)
                    
                    for item in items:
                        lines.append(f"\n  Clip: {item.clip.file_path.name}")
                        lines.append(f"  Confidence: {item.confidence:.0%}")
                        lines.append("  Reasons:")
                        for reason in item.reasons:
                            lines.append(f"    • {reason}")
                        if item.recommendations:
                            lines.append("  Recommendations:")
                            for rec in item.recommendations:
                                lines.append(f"    → {rec}")
        
        # Multicam groups
        if result.multicam_groups:
            lines.append("\n\n")
            lines.append("DETECTED MULTICAM GROUPS")
            lines.append("-" * 80)
            
            for group in result.multicam_groups:
                lines.append(f"\n{group.group_id}")
                lines.append(f"  Clips: {len(group.clips)}")
                lines.append(f"  Timecode: {group.start_timecode} - {group.end_timecode}")
                lines.append(f"  Confidence: {group.confidence:.0%}")
                lines.append("  Clips in group:")
                for clip in group.clips:
                    lines.append(f"    • {clip.file_path.name}")
        
        # Timecode gaps
        if result.timecode_gaps:
            lines.append("\n\n")
            lines.append("TIMECODE GAPS DETECTED")
            lines.append("-" * 80)
            
            for gap in result.timecode_gaps:
                lines.append(f"\nCamera: {gap['camera']}")
                lines.append(f"  Gap: {gap['gap_formatted']}")
                lines.append(f"  Between: {gap['before_clip']} → {gap['after_clip']}")
                if gap['potential_issue']:
                    lines.append("  ⚠️  Potential recording issue - gap is unusually large")
        
        lines.append("\n")
        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return output_path


def detect_multicam_sequences(clips: List[ClipAnalysis]) -> List[MulticamGroup]:
    """Convenience function to detect multicam sequences."""
    detector = MulticamDetector()
    return detector.detect_multicam_groups(clips)


def analyze_sync_failure(clip: ClipAnalysis, 
                        all_clips: List[ClipAnalysis]) -> UnsyncedClipAnalysis:
    """Convenience function to analyze a single sync failure."""
    detector = MulticamDetector()
    return detector.analyze_unsynced_clip(clip, all_clips, [])