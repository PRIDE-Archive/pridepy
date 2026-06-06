"""Download a list of explicit URLs (ftp/http/https).

Each URL is dispatched to the matching transport based on its scheme.
PRIDE checksum validation is supported when the accession can be
inferred from the URL path.
"""
import ftplib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from ftplib import FTP
from typing import List, Tuple
from urllib.parse import urlparse

from tqdm import tqdm

from pridepy.download import transport
from pridepy.download import util as _provider_util
from pridepy.download.pride import PrideProvider
from pridepy.util.api_handling import Util


def _http_download_url(url: str, target: str) -> None:
    """Stream an http/https URL into ``target`` with a progress bar."""
    session = Util.create_session_with_retries()
    with session.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))
        # When the server applied Content-Encoding (gzip/deflate), requests
        # decompresses transparently, so the on-disk size is the decompressed
        # size while Content-Length is the compressed size — skip the size
        # check to avoid a false "incomplete" on an intact file.
        content_encoding = response.headers.get("Content-Encoding")
        with open(target, "wb") as out, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            desc=os.path.basename(target),
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    out.write(chunk)
                    pbar.update(len(chunk))
    if total and not content_encoding:
        actual = os.path.getsize(target)
        if actual != total:
            raise RuntimeError(
                f"Incomplete download for {target}: got {actual} bytes, "
                f"expected {total}"
            )


def _ftp_download_url(parsed, target: str) -> None:
    """Download a single file from an ftp:// URL with a progress bar."""
    host = parsed.hostname
    if not host:
        raise ValueError(f"FTP URL missing host: {parsed.geturl()}")
    port = parsed.port or 21
    user = parsed.username or "anonymous"
    pwd = parsed.password or "anonymous@"
    remote_path = parsed.path
    with FTP() as ftp:
        ftp.connect(host, port, timeout=60)
        ftp.login(user, pwd)
        try:
            total = ftp.size(remote_path) or 0
        except ftplib.error_perm:
            total = 0
        with open(target, "wb") as out, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            desc=os.path.basename(target),
        ) as pbar:

            def _callback(data: bytes) -> None:
                out.write(data)
                pbar.update(len(data))

            ftp.retrbinary(f"RETR {remote_path}", _callback)
    if total:
        actual = os.path.getsize(target)
        if actual != total:
            raise RuntimeError(
                f"Incomplete download for {target}: got {actual} bytes, "
                f"expected {total}"
            )


def _dispatch_url_scheme(
    parsed,
    target: str,
    protocol: str = "ftp",
    position: int = 0,
    download_threads: int = 1,
) -> None:
    """Route a parsed URL to its protocol-specific downloader.

    ``protocol='globus'`` swaps the http/https single-connection streamer
    for :func:`pridepy.download.transport._parallel_download` (single-connection
    with progress bar). ftp:// URLs are unaffected.
    """
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        if download_threads and download_threads > 1:
            transport._multipart_download(
                parsed.geturl(), target, threads=download_threads, position=position
            )
        elif protocol == "globus":
            transport._parallel_download(parsed.geturl(), target, position=position)
        else:
            _http_download_url(parsed.geturl(), target)
    elif scheme == "ftp":
        _ftp_download_url(parsed, target)
    else:
        raise ValueError(f"Unsupported URL scheme: {scheme}")


def _download_single_url(
    url: str,
    output_folder: str,
    skip_if_exists: bool = False,
    protocol: str = "ftp",
    position: int = 0,
    download_threads: int = 1,
) -> str:
    """Download one URL, dispatched by scheme; return the local file path."""
    parsed = urlparse(url)
    if not (parsed.scheme or "").lower():
        raise ValueError(f"URL missing scheme: {url}")

    file_name = os.path.basename(parsed.path)
    if not file_name:
        raise ValueError(f"Cannot derive filename from URL: {url}")

    target = os.path.join(output_folder, file_name)
    if skip_if_exists and os.path.isfile(target) and os.path.getsize(target) > 0:
        logging.info("Skipping %s: already downloaded", file_name)
        return target

    try:
        _dispatch_url_scheme(
            parsed,
            target,
            protocol,
            position=position,
            download_threads=download_threads,
        )
    except Exception:
        # Don't leave a truncated/partial file behind — a non-empty partial
        # would otherwise be wrongly skipped on the next run.
        _provider_util._remove_if_exists(target)
        raise

    ok, reason = _provider_util.validate_download(target)
    if not ok:
        _provider_util._remove_if_exists(target)
        raise RuntimeError(f"Download invalid: {reason} ({target})")
    return target


def download_files_by_url(
    urls: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool = False,
    protocol: str = "ftp",
    parallel_files: int = 1,
    checksum_check: bool = False,
    download_threads: int = 1,
) -> None:
    """Download files from a list of raw URLs, dispatched by URL scheme.

    Supported schemes: ``http``, ``https``, ``ftp``. Each URL is downloaded
    independently; per-URL errors are logged, then aggregated and re-raised
    as a single :class:`RuntimeError` so callers see a complete failure
    summary.

    :param urls: fully-qualified URLs (each contains its scheme)
    :param output_folder: directory to write downloaded files into
    :param skip_if_downloaded_already: skip URLs whose target file exists
    :param protocol: ``ftp`` (default) for single-connection per URL scheme;
        ``globus`` for resume-capable http/https downloads (single-connection stream)
        (no effect on ftp:// URLs which always use single-connection FTP)
    :param checksum_check: validate downloads against PRIDE checksum API;
        accessions are inferred from URL paths (only PRIDE URLs supported)
    :raises ValueError: if ``urls`` is empty
    :raises RuntimeError: if one or more URLs failed
    """
    if not urls:
        raise ValueError("urls must contain at least one URL")

    os.makedirs(output_folder, exist_ok=True)

    workers = min(parallel_files, 3, len(urls))
    failures: List[Tuple[str, str]] = []

    if workers > 1:
        logging.info(
            "Downloading %d URL(s) with %d parallel workers",
            len(urls), workers,
        )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _download_single_url,
                url,
                output_folder,
                skip_if_downloaded_already,
                protocol,
                position=idx,
                download_threads=download_threads,
            ): url
            for idx, url in enumerate(urls)
        }
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()
            except Exception as exc:  # pylint: disable=broad-except
                logging.error("Failed to download %s: %s", url, exc)
                failures.append((url, str(exc)))

    if failures:
        summary = ", ".join(f"{u} ({e})" for u, e in failures)
        raise RuntimeError(
            f"Failed to download {len(failures)} URL(s): {summary}"
        )

    if checksum_check:
        PrideProvider.validate_urls_checksums(urls, output_folder)
