"""
Comprehensive unit tests for ingesta core functionality.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
import json
import csv

from ingesta import calculate_checksum, verify_checksum, ingest_media, IngestionJob
from ingesta.analysis import ClipAnalysis, ClipType, AudioType, ContentAnalyzer
from ingesta.checksum import calculate_checksum as calc_checksum


class TestChecksum:
    """Test checksum functionality."""
    
    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content for checksum")
        return test_file
    
    def test_md5_checksum(self, test_file):
        """Test MD5 checksum calculation."""
        checksum = calculate_checksum(test_file, algorithm="md5")
        assert len(checksum) == 32
        assert checksum.isalnum()
    
    def test_sha256_checksum(self, test_file):
        """Test SHA256 checksum calculation."""
        checksum = calculate_checksum(test_file, algorithm="sha256")
        assert len(checksum) == 64
        assert checksum.isalnum()
    
    def test_xxhash64_checksum(self, test_file):
        """Test xxhash64 checksum calculation."""
        checksum = calculate_checksum(test_file, algorithm="xxhash64")
        assert len(checksum) == 16
        assert checksum.isalnum()
    
    def test_checksum_consistency(self, test_file):
        """Test that checksums are consistent."""
        checksum1 = calculate_checksum(test_file, algorithm="md5")
        checksum2 = calculate_checksum(test_file, algorithm="md5")
        assert checksum1 == checksum2
    
    def test_verify_checksum(self, test_file):
        """Test checksum verification."""
        checksum = calculate_checksum(test_file, algorithm="md5")
        assert verify_checksum(test_file, checksum, algorithm="md5") is True
        assert verify_checksum(test_file, "wrong_checksum", algorithm="md5") is False
    
    def test_nonexistent_file(self, tmp_path):
        """Test handling of nonexistent files."""
        with pytest.raises(FileNotFoundError):
            calculate_checksum(tmp_path / "nonexistent.txt")


class TestIngestion:
    """Test ingestion functionality."""
    
    @pytest.fixture
    def source_dir(self, tmp_path):
        """Create source directory with test files."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "file1.txt").write_text("content1")
        (src / "file2.txt").write_text("content2")
        return src
    
    @pytest.fixture
    def dest_dir(self, tmp_path):
        """Create destination directory."""
        return tmp_path / "dest"
    
    def test_single_destination_ingest(self, source_dir, dest_dir):
        """Test ingestion to single destination."""
        job = ingest_media(
            source=source_dir,
            destinations=[dest_dir],
            checksum_algorithm="md5",
            verify=True
        )
        
        assert job.success_count == 2
        assert job.failure_count == 0
        assert (dest_dir / "file1.txt").exists()
        assert (dest_dir / "file2.txt").exists()
    
    def test_multi_destination_ingest(self, source_dir, tmp_path):
        """Test ingestion to multiple destinations."""
        dest1 = tmp_path / "dest1"
        dest2 = tmp_path / "dest2"
        
        job = ingest_media(
            source=source_dir,
            destinations=[dest1, dest2],
            checksum_algorithm="md5",
            verify=True
        )
        
        assert job.success_count == 4  # 2 files × 2 destinations
        assert (dest1 / "file1.txt").exists()
        assert (dest2 / "file1.txt").exists()
    
    def test_safe_to_format_true(self, source_dir, dest_dir):
        """Test SAFE TO FORMAT when all verifications pass."""
        job = ingest_media(
            source=source_dir,
            destinations=[dest_dir],
            checksum_algorithm="md5",
            verify=True
        )
        
        assert job.is_safe_to_format is True
        status = job.safe_to_format_status
        assert status['safe'] is True
        assert 'SAFE TO FORMAT' in status['badge']
    
    def test_ingestion_job_stats(self, source_dir, dest_dir):
        """Test ingestion job statistics."""
        job = ingest_media(
            source=source_dir,
            destinations=[dest_dir],
            checksum_algorithm="md5"
        )
        
        assert job.total_bytes > 0
        assert job.start_time is not None
        assert job.end_time is not None
    
    def test_json_export(self, source_dir, dest_dir, tmp_path):
        """Test JSON export of ingestion job."""
        job = ingest_media(
            source=source_dir,
            destinations=[dest_dir],
            checksum_algorithm="md5"
        )
        
        report_path = tmp_path / "report.json"
        job.save_report(report_path)
        
        assert report_path.exists()
        with open(report_path) as f:
            data = json.load(f)
            assert data['summary']['total_files'] == 2


class TestAnalysis:
    """Test content analysis functionality."""
    
    def test_clip_analysis_creation(self):
        """Test ClipAnalysis dataclass creation."""
        analysis = ClipAnalysis(
            file_path=Path("/test.mp4"),
            clip_type=ClipType.INTERVIEW,
            audio_type=AudioType.CLEAR_DIALOGUE,
            duration=10.0,
            has_audio=True,
            is_syncable=True,
            motion_score=0.3,
            audio_score=0.8,
            confidence=0.75
        )
        
        assert analysis.duration == 10.0
        assert analysis.is_syncable is True
        assert analysis.clip_type == ClipType.INTERVIEW
    
    def test_clip_analysis_to_dict(self):
        """Test ClipAnalysis serialization."""
        analysis = ClipAnalysis(
            file_path=Path("/test.mp4"),
            clip_type=ClipType.B_ROLL,
            audio_type=AudioType.AMBIENT,
            duration=5.0,
            has_audio=True,
            is_syncable=False,
            motion_score=0.6,
            audio_score=0.3,
            confidence=0.5
        )
        
        data = analysis.to_dict()
        assert data['duration'] == 5.0
        assert data['clip_type'] == 'b_roll'
        assert data['is_syncable'] is False


class TestReports:
    """Test report generation."""
    
    @pytest.fixture
    def sample_analyses(self):
        """Create sample clip analyses."""
        return [
            ClipAnalysis(
                file_path=Path("/clip1.mp4"),
                clip_type=ClipType.INTERVIEW,
                audio_type=AudioType.CLEAR_DIALOGUE,
                duration=30.0,
                has_audio=True,
                is_syncable=True,
                motion_score=0.2,
                audio_score=0.8,
                confidence=0.75
            ),
            ClipAnalysis(
                file_path=Path("/clip2.mp4"),
                clip_type=ClipType.B_ROLL,
                audio_type=AudioType.AMBIENT,
                duration=15.0,
                has_audio=True,
                is_syncable=False,
                motion_score=0.6,
                audio_score=0.4,
                confidence=0.5
            )
        ]
    
    def test_csv_report_generation(self, sample_analyses, tmp_path):
        """Test CSV report generation."""
        from ingesta.reports import CSVReportGenerator
        
        output_path = tmp_path / "report.csv"
        generator = CSVReportGenerator(output_path=output_path)
        result_path = generator.generate_report(sample_analyses)
        
        assert result_path.exists()
        
        with open(result_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
    
    def test_summary_csv_generation(self, sample_analyses, tmp_path):
        """Test summary CSV generation."""
        from ingesta.reports import CSVReportGenerator
        
        output_path = tmp_path / "report.csv"
        generator = CSVReportGenerator(output_path=output_path)
        summary_path = generator.generate_summary_csv(sample_analyses)
        
        assert summary_path.exists()


class TestCLI:
    """Test CLI commands."""
    
    def test_cli_import(self):
        """Test that CLI can be imported."""
        from ingesta.cli import cli
        assert cli is not None
    
    def test_ingest_command_help(self):
        """Test ingest command help."""
        from click.testing import CliRunner
        from ingesta.cli import ingest
        
        runner = CliRunner()
        result = runner.invoke(ingest, ['--help'])
        assert result.exit_code == 0
        assert 'Copy media' in result.output


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_source_directory(self, tmp_path):
        """Test ingestion from empty directory."""
        empty_src = tmp_path / "empty"
        empty_src.mkdir()
        dest = tmp_path / "dest"
        
        job = ingest_media(
            source=empty_src,
            destinations=[dest],
            checksum_algorithm="md5"
        )
        
        assert job.success_count == 0
        assert len(job.files_processed) == 0
    
    def test_very_small_file(self, tmp_path):
        """Test ingestion of very small files."""
        src = tmp_path / "source"
        src.mkdir()
        (src / "tiny.txt").write_text("")  # Empty file
        dest = tmp_path / "dest"
        
        job = ingest_media(
            source=src,
            destinations=[dest],
            checksum_algorithm="md5",
            verify=True
        )
        
        assert job.success_count == 1
        assert (dest / "tiny.txt").exists()
    
    def test_large_file_simulation(self, tmp_path):
        """Test ingestion handles larger files correctly."""
        src = tmp_path / "source"
        src.mkdir()
        
        # Create a 1MB test file
        large_file = src / "large.bin"
        large_file.write_bytes(b"x" * (1024 * 1024))
        
        dest = tmp_path / "dest"
        
        job = ingest_media(
            source=src,
            destinations=[dest],
            checksum_algorithm="md5",
            verify=True
        )
        
        assert job.success_count == 1
        assert job.total_bytes == 1024 * 1024


if __name__ == '__main__':
    pytest.main([__file__, '-v'])