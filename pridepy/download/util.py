"""Cross-cutting utilities used by providers and the Client facade.

Pure functions (and one tiny Progress class) for checksums, record-shape
helpers, and download progress. Originally on the facade as @staticmethods;
moved here so providers can use them without depending on the facade at
import time, while :class:`~pridepy.download.client.Client` keeps shim
re-exports for backward compatibility with existing test patches.
"""
import hashlib
import logging
import os
from typing import Dict, Optional, Tuple

from tqdm import tqdm


class Progress:
    def __init__(self, total_size, file_name):
        self.pbar = tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc="Downloading {}".format(file_name),
        )

    def __call__(self, bytes_amount):
        self.pbar.update(bytes_amount)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pbar.close()

    def close(self):
        self.pbar.close()


def _find_tsv_columns(header: str) -> Optional[Tuple[int, int]]:
    """Return (name_idx, checksum_idx) from a TSV header, or None."""
    cols = [col.strip().lower() for col in header.split("\t")]
    required_cols = {"file-name", "file-md5checksum", "file-size"}
    if not required_cols.issubset(set(cols)):
        return None
    return cols.index("file-name"), cols.index("file-md5checksum")


def _is_md5_checksum(value: str) -> bool:
    return len(value) == 32 and all(char in "0123456789abcdef" for char in value)


def read_checksum_file(checksum_file_path: str) -> Dict[str, str]:
    """
    Read PRIDE API checksum TSV and build {file_name: md5} map.
    Expected format: File-Name\tFile-MD5Checksum\tFile-Size
    """
    checksums: Dict[str, str] = {}
    if not checksum_file_path or not os.path.exists(checksum_file_path):
        return checksums

    with open(checksum_file_path, "r", encoding="utf-8") as f:
        header = f.readline().strip()
        if not header:
            return checksums

        col_indices = _find_tsv_columns(header)
        if col_indices is None:
            logging.warning(f"Unrecognized checksum file format: {header}")
            return checksums

        name_idx, checksum_idx = col_indices
        min_cols = max(name_idx, checksum_idx) + 1
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= min_cols:
                fn = os.path.basename(parts[name_idx].strip())
                cs = parts[checksum_idx].strip().lower()
                if fn and _is_md5_checksum(cs):
                    checksums[fn] = cs

    return checksums


def compute_md5(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
    """
    Compute an MD5 checksum for integrity validation, not for security use.
    """
    try:
        md5 = hashlib.md5(usedforsecurity=False)
    except TypeError:
        md5 = hashlib.md5()
    with open(file_path, "rb") as file_handle:
        while True:
            chunk = file_handle.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def validate_download(file_path: str, expected_checksum: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate a local file exists, is non-empty, and checksum matches when provided.
    """
    if not os.path.exists(file_path):
        return False, "file does not exist"
    if os.path.getsize(file_path) == 0:
        return False, "file is empty"
    if expected_checksum:
        actual_checksum = compute_md5(file_path)
        if actual_checksum.lower() != expected_checksum.lower():
            return False, (
                f"checksum mismatch (expected={expected_checksum.lower()}, actual={actual_checksum.lower()})"
            )
    return True, "ok"


def _remove_if_exists(file_path: str) -> None:
    """
    Remove a file if it already exists locally.
    """
    if os.path.exists(file_path):
        os.remove(file_path)
