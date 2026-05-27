"""Cross-cutting utilities used by providers and the Files facade.

Pure functions (and one tiny Progress class) for checksums, record-shape
helpers, and download progress. Originally on ``Files`` as @staticmethods;
moved here so providers can use them without depending on Files at import
time, and Files keeps shim re-exports for backward compatibility with
existing test patches.
"""
import hashlib
import logging
import os
from typing import Dict, List, Optional, Tuple

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


def _get_download_url(file_record: Dict, protocol: str) -> str:
    """
    Resolve the public download URL for a file and protocol.

    Raises ValueError when the requested protocol has no suitable location.
    Aspera requires a dedicated "Aspera Protocol" entry; ftp/s3/globus
    derive their URL from the "FTP Protocol" entry (falling back to an
    arbitrary non-Aspera location would produce a URL the caller cannot
    actually transfer with).
    """
    # Lazy import to avoid module-load cycle with PrideProvider (which lives
    # in the providers package and imports back into util via _resolve_local_path).
    from pridepy.providers.pride import PrideProvider

    locations = file_record.get("publicFileLocations", [])
    if not locations:
        raise ValueError("No public file locations present")

    aspera_url = None
    ftp_url = None
    for location in locations:
        name = location.get("name")
        if name == "Aspera Protocol":
            aspera_url = location.get("value")
        elif name == "FTP Protocol":
            ftp_url = location.get("value")

    if protocol == "aspera":
        if not aspera_url:
            raise ValueError("Aspera URL not available")
        return aspera_url

    if not ftp_url:
        raise ValueError("FTP URL not available")
    if protocol == "ftp":
        return ftp_url
    if protocol == "globus":
        return ftp_url.replace(
            PrideProvider.ARCHIVE_FTP_URL_PREFIX,
            PrideProvider.ARCHIVE_HTTPS_URL_PREFIX,
            1,
        )
    if protocol == "s3":
        return ftp_url
    raise ValueError(f"Unsupported protocol: {protocol}")


def _resolve_local_path(file_record: Dict, output_folder: str) -> str:
    """
    Compute the canonical local path for a file regardless of transfer protocol.
    """
    # Lazy import to avoid module-load cycle with PrideProvider.
    from pridepy.providers.pride import PrideProvider

    try:
        canonical_url = _get_download_url(file_record, "ftp")
    except ValueError:
        canonical_url = ""
    if canonical_url:
        return PrideProvider.get_output_file_name(canonical_url, file_record, output_folder)
    return os.path.join(output_folder, file_record["fileName"])
