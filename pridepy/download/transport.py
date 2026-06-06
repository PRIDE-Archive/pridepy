"""Shared FTP / FTPS / HTTPS download transport.

Stateless helpers used by the per-repository adapters (and re-exported on
:class:`pridepy.download.client.Client` for downstream callers that use
``Client.download_ftp_urls`` etc.).
"""
import ftplib
import logging
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from ftplib import FTP
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from pridepy.util.api_handling import Util


def _safe_join(output_folder: str, relative_path: str) -> str:
    """Join ``output_folder`` with a dataset-relative path.

    Preserves sub-directory structure (so identically-named files in
    different collections don't collide). Guards against absolute paths or
    ``..`` traversal that would escape ``output_folder`` by falling back to
    the basename — provider relative paths are already dataset-relative, so
    this is purely defensive.
    """
    relative_path = (relative_path or "").lstrip("/")
    if not relative_path:
        return output_folder
    local_path = os.path.normpath(os.path.join(output_folder, relative_path))
    out_abs = os.path.abspath(output_folder)
    local_abs = os.path.abspath(local_path)
    if local_abs != out_abs and not local_abs.startswith(out_abs + os.sep):
        return os.path.join(output_folder, os.path.basename(relative_path))
    return local_path


def _dest_path(
    output_folder: str, url_path: str, relative_path: Optional[str]
) -> str:
    """Resolve the local destination for a download.

    Uses the dataset-relative path when available (preserving layout),
    otherwise falls back to the URL basename.
    """
    if relative_path:
        return _safe_join(output_folder, relative_path)
    return os.path.join(output_folder, os.path.basename(url_path))


def _open_ftp_connection(host: str, use_tls: bool, timeout: int = 30) -> FTP:
    """
    Open an anonymous FTP connection, transparently using FTPS when the
    server requires TLS (e.g., MassIVE). When ``use_tls`` is False but the
    server replies ``421 TLS is required`` to ``login``, transparently
    retry with FTPS so callers don't need to know the policy in advance.
    """
    if use_tls:
        ftp: FTP = ftplib.FTP_TLS(host, timeout=timeout)
        ftp.login()
        ftp.prot_p()
    else:
        ftp = FTP(host, timeout=timeout)
        try:
            ftp.login()
        except ftplib.error_temp as e:
            if "TLS" in str(e).upper():
                try:
                    ftp.close()
                except Exception:
                    pass
                ftp = ftplib.FTP_TLS(host, timeout=timeout)
                ftp.login()
                ftp.prot_p()
            else:
                raise
    ftp.set_pasv(True)
    return ftp


# Emit a progress line every this many directories while walking a remote
# tree. Large deposits (e.g. a MassIVE timsTOF dataset with thousands of .d
# directories, each needing its own TLS data connection to list) can take
# many minutes to enumerate; without progress the caller looks hung.
_WALK_PROGRESS_EVERY_DIRS = 100


def _walk_ftp_tree(
    ftp: FTP, remote_dir: str, _progress: Optional[dict] = None
) -> List[str]:
    """
    Recursively list files under a remote FTP directory.

    Emits an INFO progress heartbeat every ``_WALK_PROGRESS_EVERY_DIRS``
    directories, plus a final summary, so enumerating a large deposit does
    not look like a hang. ``_progress`` is internal recursion state; callers
    invoke this with ``(ftp, remote_dir)`` only.
    """
    import posixpath

    top_level = _progress is None
    if top_level:
        _progress = {"dirs": 0, "files": 0}

    def _note_dir_listed() -> None:
        _progress["dirs"] += 1
        if _progress["dirs"] % _WALK_PROGRESS_EVERY_DIRS == 0:
            logging.info(
                "Listing remote tree: %d directories scanned, "
                "%d files found so far...",
                _progress["dirs"],
                _progress["files"],
            )

    file_paths: List[str] = []
    try:
        entries = list(ftp.mlsd(remote_dir))
        _note_dir_listed()
        for name, facts in entries:
            if name in {".", ".."}:
                continue
            child_path = posixpath.join(remote_dir.rstrip("/"), name)
            if facts.get("type") == "dir":
                file_paths.extend(_walk_ftp_tree(ftp, child_path, _progress))
            elif facts.get("type") == "file":
                file_paths.append(child_path)
                _progress["files"] += 1
        if top_level:
            logging.info(
                "Listing remote tree complete: %d directories, %d files.",
                _progress["dirs"],
                _progress["files"],
            )
        return file_paths
    except (AttributeError, ftplib.error_perm):
        pass

    current_dir = ftp.pwd()
    listing: List[str] = []
    try:
        ftp.cwd(remote_dir)
        ftp.retrlines("LIST", listing.append)
        _note_dir_listed()
        for entry in listing:
            parts = entry.split(maxsplit=8)
            if len(parts) < 9:
                continue
            name = parts[8]
            if name in {".", ".."}:
                continue
            child_path = posixpath.join(remote_dir.rstrip("/"), name)
            if entry.startswith("d"):
                file_paths.extend(_walk_ftp_tree(ftp, child_path, _progress))
            else:
                file_paths.append(child_path)
                _progress["files"] += 1
    finally:
        ftp.cwd(current_dir)
    if top_level:
        logging.info(
            "Listing remote tree complete: %d directories, %d files.",
            _progress["dirs"],
            _progress["files"],
        )
    return file_paths


def _list_ftp_repo_files(
    host: str,
    remote_root: str,
    error_label: str,
    use_tls: bool = False,
) -> List[str]:
    """
    Connect to an anonymous FTP host (FTP or FTPS), walk a directory tree,
    and return file paths.

    ``use_tls`` should be True for servers that reject plain FTP (e.g.
    MassIVE). Centralizes connection lifecycle so a constructor failure
    doesn't mask the underlying error in ``finally`` (PR #98 review).
    """
    ftp: Optional[FTP] = None
    try:
        ftp = _open_ftp_connection(host, use_tls=use_tls)
        logging.info(f"Connected to FTP host: {host} (tls={use_tls})")
        return _walk_ftp_tree(ftp, remote_root)
    except Exception as error:
        raise RuntimeError(
            f"Unable to list public files for {error_label}: {error}"
        ) from error
    finally:
        if ftp is not None:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass


def _resolve_and_walk_ftp_dataset(
    host: str,
    accession: str,
    error_label: str,
    use_tls: bool = False,
    prefer_prefix: str = "",
) -> List[str]:
    """
    Find which top-level directory on ``host`` holds ``accession`` and walk it.

    Some repositories (e.g. MassIVE) distribute datasets across several
    versioned root directories (``/v01`` … ``/vNN``, plus auxiliary roots like
    ``x01`` / ``z01`` that may hold only a partial, derived copy) and the
    version is not derivable from the accession. Probe each top-level directory
    for ``<root>/<accession>`` and walk the first match, reusing a single
    connection for both discovery and listing.

    ``prefer_prefix`` lets the caller try the canonical roots first: roots
    whose name starts with the prefix (e.g. ``"v"`` for MassIVE versioned
    storage) are probed before any others, so a complete copy is chosen over
    an auxiliary partial one when a dataset exists under both.

    :raises RuntimeError: on connection failure or when the accession is not
        found under any top-level directory.
    """
    ftp: Optional[FTP] = None
    try:
        ftp = _open_ftp_connection(host, use_tls=use_tls)
        logging.info(f"Connected to FTP host: {host} (tls={use_tls})")
        roots: List[str] = []
        ftp.retrlines("NLST /", roots.append)
        # Servers may return bare names or absolute paths; keep the leaf name.
        candidates = []
        for entry in roots:
            name = entry.strip().strip("/").split("/")[-1]
            if name and name not in {".", ".."}:
                candidates.append(name)
        if prefer_prefix:
            prefix = prefer_prefix.lower()
            candidates.sort(
                key=lambda n: (not n.lower().startswith(prefix), n)
            )
        for name in candidates:
            dataset_root = f"/{name}/{accession}"
            try:
                ftp.cwd(dataset_root)
            except ftplib.error_perm:
                continue
            logging.info(f"Found {accession} under {dataset_root} on {host}")
            return _walk_ftp_tree(ftp, dataset_root)
        raise RuntimeError(
            f"{accession} not found under any top-level directory on {host}"
        )
    except Exception as error:
        raise RuntimeError(
            f"Unable to list public files for {error_label}: {error}"
        ) from error
    finally:
        if ftp is not None:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass


def _download_one_ftp_path(
    ftp: FTP,
    ftp_path: str,
    local_path: str,
    skip_if_downloaded_already: bool,
    max_download_retries: int,
    position: int = 0,
) -> None:
    """
    Download a single FTP path over an existing connection, with REST resume
    and per-file retry. Raises on giving up so the caller can decide what to do.
    """
    if skip_if_downloaded_already and os.path.exists(local_path):
        logging.info(f"Skipping download as file already exists: {local_path}")
        return

    attempt = 0
    last_error: Optional[Exception] = None
    while attempt < max_download_retries:
        try:
            total_size = ftp.size(ftp_path)
            if os.path.exists(local_path):
                current_size = os.path.getsize(local_path)
                mode = "ab"
            else:
                current_size = 0
                mode = "wb"

            with open(local_path, mode) as f, tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                desc=local_path,
                initial=current_size,
                position=position,
                leave=True,
            ) as pbar:
                def callback(data):
                    f.write(data)
                    pbar.update(len(data))

                if current_size:
                    try:
                        ftp.sendcmd(f"REST {current_size}")
                    except Exception:
                        current_size = 0
                        f.seek(0)
                        f.truncate()
                ftp.retrbinary(f"RETR {ftp_path}", callback)

            # Post-transfer integrity check: server-reported size must match
            # the local size. Catches half-finished transfers that retrbinary
            # didn't raise on (e.g. server closed the data channel early).
            # The next iteration will REST-resume from where we left off.
            if total_size:
                final_size = os.path.getsize(local_path)
                if final_size != total_size:
                    attempt += 1
                    logging.error(
                        f"Size mismatch for {local_path}: "
                        f"got {final_size} bytes, expected {total_size} "
                        f"(attempt {attempt})"
                    )
                    continue
            logging.info(f"Successfully downloaded {local_path}")
            return
        except (socket.timeout, ftplib.error_temp, ftplib.error_perm) as e:
            attempt += 1
            last_error = e
            logging.error(
                f"Download failed for {local_path} (attempt {attempt}): {e}"
            )
    raise RuntimeError(
        f"Giving up on {local_path} after {max_download_retries} attempts"
    ) from last_error


def _download_ftp_paths_serial(
    host: str,
    items: List[Tuple[str, str]],
    skip_if_downloaded_already: bool,
    use_tls: bool,
    max_connection_retries: int,
    max_download_retries: int,
) -> List[str]:
    """Download all paths from one host over a single (reused) connection.

    ``items`` is a list of ``(ftp_path, local_path)`` pairs; ``local_path``
    is the precomputed destination (already including any sub-directories).

    Returns the list of ``ftp_path`` values that could not be downloaded
    (connection never established, or per-file giving up) so the caller can
    surface a failure instead of reporting false success.
    """
    connection_attempt = 0
    while connection_attempt < max_connection_retries:
        failed: List[str] = []
        try:
            ftp = _open_ftp_connection(host, use_tls=use_tls)
            logging.info(f"Connected to FTP host: {host} (tls={use_tls})")
            for ftp_path, local_path in items:
                parent = os.path.dirname(local_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                try:
                    _download_one_ftp_path(
                        ftp=ftp,
                        ftp_path=ftp_path,
                        local_path=local_path,
                        skip_if_downloaded_already=skip_if_downloaded_already,
                        max_download_retries=max_download_retries,
                    )
                except Exception as e:
                    logging.error(
                        f"Failed to download {ftp_path} from {host}: {e}"
                    )
                    failed.append(ftp_path)
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass
            logging.info(f"Disconnected from FTP host: {host}")
            return failed
        except (socket.timeout, ftplib.error_temp, ftplib.error_perm, OSError) as e:
            connection_attempt += 1
            logging.error(
                f"FTP connection failed (attempt {connection_attempt}): {e}"
            )
            if connection_attempt < max_connection_retries:
                logging.info("Retrying connection...")
                time.sleep(5)
            else:
                logging.error(
                    f"Giving up after {max_connection_retries} failed connection attempts to {host}."
                )
                return [ftp_path for ftp_path, _ in items]
    return [ftp_path for ftp_path, _ in items]


def _download_ftp_paths_parallel(
    host: str,
    items: List[Tuple[str, str]],
    skip_if_downloaded_already: bool,
    use_tls: bool,
    max_connection_retries: int,
    max_download_retries: int,
    parallel_files: int,
) -> List[str]:
    """
    Download paths concurrently using ``parallel_files`` workers; each
    worker opens its own FTP connection so transfers don't serialize.

    ``items`` is a list of ``(ftp_path, local_path)`` pairs. Returns the list
    of ``ftp_path`` values that failed so the caller can surface a failure.
    """
    def worker(item: Tuple[str, str], position: int) -> Optional[str]:
        ftp_path, local_path = item
        if skip_if_downloaded_already and os.path.exists(local_path):
            logging.info(f"Skipping download as file already exists: {local_path}")
            return None
        parent = os.path.dirname(local_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        connection_attempt = 0
        while connection_attempt < max_connection_retries:
            try:
                ftp = _open_ftp_connection(host, use_tls=use_tls)
                try:
                    _download_one_ftp_path(
                        ftp=ftp,
                        ftp_path=ftp_path,
                        local_path=local_path,
                        skip_if_downloaded_already=False,
                        max_download_retries=max_download_retries,
                        position=position,
                    )
                    return None
                finally:
                    try:
                        ftp.quit()
                    except Exception:
                        try:
                            ftp.close()
                        except Exception:
                            pass
            except (socket.timeout, ftplib.error_temp, ftplib.error_perm, OSError) as e:
                connection_attempt += 1
                logging.error(
                    f"FTP connection failed for {ftp_path} (attempt {connection_attempt}): {e}"
                )
                if connection_attempt < max_connection_retries:
                    time.sleep(5)
            except Exception as e:
                logging.error(f"Failed to download {ftp_path} from {host}: {e}")
                return ftp_path
        logging.error(f"Giving up on {ftp_path} from {host}")
        return ftp_path

    failed: List[str] = []
    with ThreadPoolExecutor(max_workers=parallel_files) as executor:
        future_to_path = {
            executor.submit(worker, item, idx): item[0]
            for idx, item in enumerate(items)
        }
        for future in as_completed(future_to_path):
            try:
                result = future.result()
                if result is not None:
                    failed.append(result)
            except Exception as e:
                logging.error(f"Parallel FTP download error: {e}")
                failed.append(future_to_path[future])
    return failed


def download_ftp_urls(
    ftp_urls: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    max_connection_retries: int = 3,
    max_download_retries: int = 3,
    use_tls: bool = False,
    parallel_files: int = 1,
    relative_paths: Optional[List[str]] = None,
) -> None:
    """
    Download a list of FTP URLs with retries, REST-based resume, and
    optional parallel workers.

    :param use_tls: Open the FTP connection with TLS (FTP_TLS / PROT P).
        Required for hosts that reject plain anonymous FTP (e.g. MassIVE).
        When False but the server replies ``421 TLS is required``, the
        connection is transparently retried over TLS.
    :param parallel_files: When >1, downloads run concurrently with that
        many worker connections per host (capped at the number of files).
    :param relative_paths: Optional per-URL dataset-relative destination
        paths (parallel to ``ftp_urls``). When given, files are written to
        ``output_folder/<relative_path>`` so identically-named files in
        different collections don't collide. When omitted, the URL basename
        is used (legacy flat layout).
    :raises RuntimeError: after attempting every file, if one or more failed.
    """
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    host_to_items: Dict[str, List[Tuple[str, str]]] = {}
    for idx, url in enumerate(ftp_urls):
        parsed = urlparse(url)
        remote_path = parsed.path.lstrip("/")
        relpath = (
            relative_paths[idx]
            if relative_paths and idx < len(relative_paths)
            else None
        )
        if not parsed.hostname:
            raise ValueError(
                f"Cannot download FTP URL with no host: {url!r}"
            )
        local_path = _dest_path(output_folder, remote_path, relpath)
        host_to_items.setdefault(parsed.hostname, []).append((remote_path, local_path))

    failed: List[str] = []
    for host, items in host_to_items.items():
        workers = max(1, min(parallel_files, len(items)))
        if workers > 1:
            failed.extend(_download_ftp_paths_parallel(
                host=host,
                items=items,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=use_tls,
                max_connection_retries=max_connection_retries,
                max_download_retries=max_download_retries,
                parallel_files=workers,
            ))
        else:
            failed.extend(_download_ftp_paths_serial(
                host=host,
                items=items,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=use_tls,
                max_connection_retries=max_connection_retries,
                max_download_retries=max_download_retries,
            ))

    if failed:
        raise RuntimeError(
            f"Failed to download {len(failed)} FTP file(s): {failed}"
        )


def _parallel_download(url, file_path, position=0):
    """Download a file via a single-connection HTTP stream with optional resume.
    If a partial file exists and the server supports Range requests, resumes
    from where it left off; otherwise restarts from scratch."""
    parent = os.path.dirname(file_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    session = Util.create_session_with_retries()
    try:
        head = session.head(url, timeout=(30, 30))
        head.raise_for_status()
        total_size = int(head.headers.get("content-length", 0))
        accept_ranges = head.headers.get("accept-ranges", "none").strip().lower()
    except (requests.RequestException, ValueError) as exc:
        logging.info(f"HEAD request failed, falling back to single connection: {exc}")
        total_size = 0
        accept_ranges = "none"

    resume_size = 0
    if os.path.exists(file_path) and accept_ranges == "bytes" and total_size > 0:
        resume_size = os.path.getsize(file_path)
        if resume_size >= total_size:
            logging.info(f"File already complete: {file_path}")
            return
        if resume_size > 0:
            logging.info(f"Resuming download from {resume_size} bytes: {file_path}")

    headers = {"Range": f"bytes={resume_size}-"} if resume_size > 0 else {}
    content_encoding = None
    with session.get(url, headers=headers, stream=True, timeout=(30, 60)) as r:
        r.raise_for_status()
        content_encoding = r.headers.get("Content-Encoding")
        if resume_size > 0 and r.status_code != 206:
            logging.warning("Server did not honor Range request (status %s), restarting download", r.status_code)
            resume_size = 0
        with tqdm(total=total_size, unit="B", unit_scale=True, desc=file_path,
                  initial=resume_size, position=position, leave=True) as pbar:
            mode = "ab" if resume_size > 0 else "wb"
            with open(file_path, mode, buffering=8 * 1024 * 1024) as f:
                for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

    # Post-transfer integrity check mirroring the FTP path: the written size
    # must match the server-reported Content-Length. A server that closes the
    # data channel mid-stream without raising leaves a truncated file; raising
    # here lets the caller's retry loop re-download (Range-resuming when able).
    # Skipped when the server applied Content-Encoding (gzip/deflate): requests
    # decompresses transparently, so on-disk size won't match Content-Length.
    if total_size and not content_encoding:
        actual_size = os.path.getsize(file_path)
        if actual_size != total_size:
            raise RuntimeError(
                f"Incomplete download for {file_path}: got {actual_size} bytes, "
                f"expected {total_size}"
            )


def _http_download_one(
    url: str,
    output_folder: str,
    skip_if_downloaded_already: bool,
    max_retries: int = 3,
    position: int = 0,
    relative_path: Optional[str] = None,
) -> None:
    """
    Download a single HTTP(S) URL with HEAD-then-Range resume and retry.
    Used as the worker target for both the serial loop and the parallel
    ThreadPoolExecutor path. Reuses :meth:`_parallel_download` so the same
    resume / restart-on-non-206 behaviour is shared with globus downloads.

    ``relative_path`` (when given) is the dataset-relative destination, so
    files keep their collection layout instead of being flattened to the
    URL basename.
    """
    local_path = _dest_path(output_folder, urlparse(url).path, relative_path)
    if skip_if_downloaded_already and os.path.exists(local_path):
        logging.info(f"Skipping download as file already exists: {local_path}")
        return
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            _parallel_download(url, local_path, position=position)
            logging.info(f"Successfully downloaded {local_path}")
            return
        except Exception as e:
            last_error = e
            logging.warning(
                f"HTTP download attempt {attempt}/{max_retries} failed for {url}: {e}"
            )
    raise RuntimeError(
        f"Giving up on {local_path} after {max_retries} HTTP attempts"
    ) from last_error


def download_http_urls(
    http_urls: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    parallel_files: int = 1,
    max_retries: int = 3,
    relative_paths: Optional[List[str]] = None,
) -> None:
    """
    Download a list of HTTP(S) URLs with HEAD-then-Range resume, per-file
    retries, and an optional ``parallel_files`` worker pool.

    When ``parallel_files`` > 1, downloads run concurrently using a
    :class:`ThreadPoolExecutor`. Each worker manages its own file (a new
    ``requests`` session is opened inside ``_parallel_download``) so the
    only shared resource is the output directory.

    :param relative_paths: Optional per-URL dataset-relative destination
        paths (parallel to ``http_urls``); see :func:`download_ftp_urls`.
    :raises RuntimeError: after attempting every URL, if one or more failed.
    """
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    if not http_urls:
        return

    def _rel(idx: int) -> Optional[str]:
        if relative_paths and idx < len(relative_paths):
            return relative_paths[idx]
        return None

    failed: List[str] = []
    workers = max(1, min(parallel_files, len(http_urls)))
    if workers > 1:
        logging.info(
            f"Downloading {len(http_urls)} HTTP(S) file(s) with {workers} parallel workers"
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_url = {
                executor.submit(
                    _http_download_one,
                    url,
                    output_folder,
                    skip_if_downloaded_already,
                    max_retries,
                    idx,
                    _rel(idx),
                ): url
                for idx, url in enumerate(http_urls)
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"HTTP download failed for {url}: {e}")
                    failed.append(url)
    else:
        for idx, url in enumerate(http_urls):
            try:
                _http_download_one(
                    url,
                    output_folder,
                    skip_if_downloaded_already,
                    max_retries,
                    relative_path=_rel(idx),
                )
            except Exception as e:
                logging.error(f"HTTP download failed for {url}: {e}")
                failed.append(url)

    if failed:
        raise RuntimeError(
            f"Failed to download {len(failed)} HTTP(S) file(s): {failed}"
        )
