"""
Checksum utilities for file verification.

Supports xxhash (Shotput Pro compatible), MD5, and SHA256 hashing with progress tracking.
"""

import hashlib
from pathlib import Path
from typing import Union, Callable, Optional

try:
    import xxhash
    XXHASH_AVAILABLE = True
except ImportError:
    XXHASH_AVAILABLE = False


def calculate_checksum(
    file_path: Union[str, Path],
    algorithm: str = "xxhash64",
    chunk_size: int = 8192,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> str:
    """
    Calculate checksum for a file.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm ('xxhash64', 'xxhash32', 'md5', 'sha256')
                  Default is 'xxhash64' (Shotput Pro compatible)
        chunk_size: Size of chunks to read (default: 8192 bytes)
        progress_callback: Optional callback(total_bytes, processed_bytes)
    
    Returns:
        Hex digest of the file
    
    Raises:
        ValueError: If algorithm is not supported
        FileNotFoundError: If file doesn't exist
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    algorithm = algorithm.lower()
    
    # Initialize hash object based on algorithm
    if algorithm == "xxhash64":
        if not XXHASH_AVAILABLE:
            raise ImportError("xxhash library not installed. Run: pip install xxhash")
        hash_obj = xxhash.xxh64()
    elif algorithm == "xxhash32":
        if not XXHASH_AVAILABLE:
            raise ImportError("xxhash library not installed. Run: pip install xxhash")
        hash_obj = xxhash.xxh32()
    elif algorithm == "xxhash128":
        if not XXHASH_AVAILABLE:
            raise ImportError("xxhash library not installed. Run: pip install xxhash")
        hash_obj = xxhash.xxh128()
    elif algorithm == "md5":
        hash_obj = hashlib.md5()
    elif algorithm == "sha256":
        hash_obj = hashlib.sha256()
    elif algorithm == "sha1":
        hash_obj = hashlib.sha1()
    else:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}. "
            f"Use 'xxhash64', 'xxhash32', 'xxhash128', 'md5', 'sha256', or 'sha1'"
        )
    
    total_size = file_path.stat().st_size
    processed = 0
    
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
            processed += len(chunk)
            
            if progress_callback:
                progress_callback(total_size, processed)
    
    return hash_obj.hexdigest()


def verify_checksum(
    file_path: Union[str, Path],
    expected_checksum: str,
    algorithm: str = "xxhash64",
    chunk_size: int = 8192,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> bool:
    """
    Verify a file against an expected checksum.
    
    Args:
        file_path: Path to the file
        expected_checksum: Expected checksum value
        algorithm: Hash algorithm ('xxhash64', 'md5', 'sha256', etc.)
        chunk_size: Size of chunks to read
        progress_callback: Optional callback(total_bytes, processed_bytes)
    
    Returns:
        True if checksum matches, False otherwise
    """
    actual_checksum = calculate_checksum(file_path, algorithm, chunk_size, progress_callback)
    return actual_checksum.lower() == expected_checksum.lower()


def calculate_checksum_streaming(
    source_path: Union[str, Path],
    dest_path: Union[str, Path],
    algorithm: str = "xxhash64",
    chunk_size: int = 8192,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> tuple[str, str]:
    """
    Calculate checksums for both source and destination files.
    
    This is useful for verifying a copy operation.
    
    Args:
        source_path: Path to source file
        dest_path: Path to destination file
        algorithm: Hash algorithm
        chunk_size: Size of chunks to read
        progress_callback: Optional callback(total_bytes, processed_bytes)
    
    Returns:
        Tuple of (source_checksum, dest_checksum)
    """
    source_checksum = calculate_checksum(source_path, algorithm, chunk_size, progress_callback)
    dest_checksum = calculate_checksum(dest_path, algorithm, chunk_size, progress_callback)
    
    return source_checksum, dest_checksum


def get_supported_algorithms() -> list[str]:
    """
    Get list of supported checksum algorithms.
    
    Returns:
        List of algorithm names
    """
    algorithms = ["md5", "sha1", "sha256"]
    if XXHASH_AVAILABLE:
        algorithms.extend(["xxhash32", "xxhash64", "xxhash128"])
    return algorithms
