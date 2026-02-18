"""
Duplicate and near-duplicate detection module.

Detects:
- Exact duplicates (same file hash)
- Near-duplicates (similar duration, size, perceptual hash)
- Similar filenames (potential duplicates with different names)

All processing is done locally.
"""

import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass, field


@dataclass
class DuplicateInfo:
    """Information about duplicate clips."""
    is_duplicate: bool
    duplicate_of: List[str] = field(default_factory=list)  # Filenames this is duplicate of
    duplicate_type: str = ""  # 'exact', 'near', 'filename'
    similarity_score: float = 0.0  # 0-1, higher = more similar


def calculate_file_hash(file_path: Path, algorithm: str = "xxhash") -> str:
    """
    Calculate file hash for exact duplicate detection.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (xxhash, md5, sha256)
        
    Returns:
        Hash string
    """
    try:
        if algorithm == "xxhash":
            try:
                import xxhash
                hasher = xxhash.xxh64()
            except ImportError:
                # Fallback to md5
                hasher = hashlib.md5()
        elif algorithm == "sha256":
            hasher = hashlib.sha256()
        else:
            hasher = hashlib.md5()
        
        # Read file in chunks
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        
        return hasher.hexdigest()
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Hash calculation failed for {file_path}: {e}")
        return ""


def are_near_duplicates(file1: Path, file2: Path, 
                       duration1: float, duration2: float,
                       threshold: float = 0.95) -> Tuple[bool, float]:
    """
    Check if two files are near-duplicates based on metadata.
    
    Args:
        file1: First file path
        file2: Second file path
        duration1: Duration of first file in seconds
        duration2: Duration of second file in seconds
        threshold: Similarity threshold (0-1)
        
    Returns:
        Tuple of (is_near_duplicate, similarity_score)
    """
    try:
        # Check file sizes
        size1 = file1.stat().st_size
        size2 = file2.stat().st_size
        
        # Calculate size similarity (files should be within 5% of each other)
        if size1 == 0 or size2 == 0:
            return False, 0.0
        
        size_ratio = min(size1, size2) / max(size1, size2)
        
        # Check duration similarity
        duration_ratio = 0.0
        if duration1 > 0 and duration2 > 0:
            duration_ratio = min(duration1, duration2) / max(duration1, duration2)
        
        # Check filename similarity
        name1 = file1.stem.lower()
        name2 = file2.stem.lower()
        
        # Extract common patterns
        import re
        # Remove numbers and common suffixes
        base1 = re.sub(r'\d+', '', name1)
        base2 = re.sub(r'\d+', '', name2)
        
        name_similarity = 0.0
        if base1 == base2:
            name_similarity = 1.0
        elif len(base1) > 0 and len(base2) > 0:
            # Simple string similarity
            from difflib import SequenceMatcher
            name_similarity = SequenceMatcher(None, base1, base2).ratio()
        
        # Combined similarity score
        # Weight: size 40%, duration 40%, name 20%
        similarity = (size_ratio * 0.4) + (duration_ratio * 0.4) + (name_similarity * 0.2)
        
        is_near_dup = similarity >= threshold and size_ratio > 0.9 and duration_ratio > 0.9
        
        return is_near_dup, similarity
        
    except Exception as e:
        logging.getLogger(__name__).warning(f"Near-duplicate check failed: {e}")
        return False, 0.0


def find_duplicates(file_list: List[Path], 
                   durations: Dict[Path, float],
                   check_exact: bool = True,
                   check_near: bool = True) -> Dict[Path, DuplicateInfo]:
    """
    Find duplicates in a list of files.
    
    Args:
        file_list: List of file paths
        durations: Dictionary mapping file paths to durations
        check_exact: Check for exact duplicates
        check_near: Check for near-duplicates
        
    Returns:
        Dictionary mapping file paths to DuplicateInfo
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Checking {len(file_list)} files for duplicates")
    
    results = {}
    
    # Initialize all as non-duplicates
    for file_path in file_list:
        results[file_path] = DuplicateInfo(is_duplicate=False)
    
    # Check for exact duplicates by hash
    if check_exact:
        logger.info("Checking for exact duplicates...")
        hash_map: Dict[str, List[Path]] = {}
        
        for file_path in file_list:
            file_hash = calculate_file_hash(file_path)
            if file_hash:
                if file_hash in hash_map:
                    hash_map[file_hash].append(file_path)
                else:
                    hash_map[file_hash] = [file_path]
        
        # Mark duplicates
        for file_hash, files in hash_map.items():
            if len(files) > 1:
                logger.info(f"  Found {len(files)} exact duplicates")
                for i, file_path in enumerate(files):
                    dup_of = [str(f.name) for j, f in enumerate(files) if j != i]
                    results[file_path] = DuplicateInfo(
                        is_duplicate=True,
                        duplicate_of=dup_of,
                        duplicate_type='exact',
                        similarity_score=1.0
                    )
    
    # Check for near-duplicates
    if check_near:
        logger.info("Checking for near-duplicates...")
        
        # Compare each pair (optimization: only compare if not already marked as exact)
        checked_pairs: Set[Tuple[str, str]] = set()
        
        for i, file1 in enumerate(file_list):
            if results[file1].duplicate_type == 'exact':
                continue
                
            for j, file2 in enumerate(file_list[i+1:], start=i+1):
                if results[file2].duplicate_type == 'exact':
                    continue
                
                # Avoid checking same pair twice
                pair_key = tuple(sorted([str(file1), str(file2)]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # Get durations
                dur1 = durations.get(file1, 0)
                dur2 = durations.get(file2, 0)
                
                # Check if near-duplicates
                is_near, similarity = are_near_duplicates(file1, file2, dur1, dur2)
                
                if is_near:
                    logger.info(f"  Near-duplicate: {file1.name} ~ {file2.name} ({similarity:.2f})")
                    
                    # Update both files
                    results[file1].is_duplicate = True
                    results[file1].duplicate_of.append(str(file2.name))
                    results[file1].duplicate_type = 'near'
                    results[file1].similarity_score = max(results[file1].similarity_score, similarity)
                    
                    results[file2].is_duplicate = True
                    results[file2].duplicate_of.append(str(file1.name))
                    results[file2].duplicate_type = 'near'
                    results[file2].similarity_score = max(results[file2].similarity_score, similarity)
    
    return results


class DuplicateDetector:
    """
    Detector for duplicate and near-duplicate video clips.
    
    Uses file hashing for exact duplicates and metadata comparison
    for near-duplicates. All processing is done locally.
    """
    
    def detect(self, file_list: List[Path], 
               durations: Dict[Path, float],
               check_exact: bool = True,
               check_near: bool = True) -> Dict[Path, DuplicateInfo]:
        """
        Detect duplicates in a list of files.
        
        Args:
            file_list: List of file paths to check
            durations: Dictionary mapping files to their durations
            check_exact: Whether to check for exact duplicates
            check_near: Whether to check for near-duplicates
            
        Returns:
            Dictionary mapping file paths to DuplicateInfo
        """
        return find_duplicates(file_list, durations, check_exact, check_near)
