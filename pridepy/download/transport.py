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
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from pridepy.util.api_handling import Util


def _local_path_for_url(download_url: str, output_folder: str) -> str:
    filename = os.path.basename(urlparse(download_url).path)
    return os.path.join(output_folder, filename)


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


def _walk_ftp_tree(ftp: FTP, remote_dir: str) -> List[str]:
    """
    Recursively list files under a remote FTP directory.
    """
    import posixpath
    file_paths: List[str] = []
    try:
        entries = list(ftp.mlsd(remote_dir))
        for name, facts in entries:
            if name in {".", ".."}:
                continue
            child_path = posixpath.join(remote_dir.rstrip("/"), name)
            if facts.get("type") == "dir":
                file_paths.extend(_walk_ftp_tree(ftp, child_path))
            elif facts.get("type") == "file":
                file_paths.append(child_path)
        return file_paths
    except (AttributeError, ftplib.error_perm):
        pass

    current_dir = ftp.pwd()
    listing: List[str] = []
    try:
        ftp.cwd(remote_dir)
        ftp.retrlines("LIST", listing.append)
        for entry in listing:
            parts = entry.split(maxsplit=8)
            if len(parts) < 9:
                continue
            name = parts[8]
            if name in {".", ".."}:
                continue
            child_path = posixpath.join(remote_dir.rstrip("/"), name)
            if entry.startswith("d"):
                file_paths.extend(_walk_ftp_tree(ftp, child_path))
            else:
                file_paths.append(child_path)
    finally:
        ftp.cwd(current_dir)
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
    paths: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    use_tls: bool,
    max_connection_retries: int,
    max_download_retries: int,
) -> None:
    """Download all paths from one host over a single (reused) connection."""
    connection_attempt = 0
    while connection_attempt < max_connection_retries:
        try:
            ftp = _open_ftp_connection(host, use_tls=use_tls)
            logging.info(f"Connected to FTP host: {host} (tls={use_tls})")
            for ftp_path in paths:
                local_path = os.path.join(output_folder, os.path.basename(ftp_path))
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
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass
            logging.info(f"Disconnected from FTP host: {host}")
            return
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


def _download_ftp_paths_parallel(
    host: str,
    paths: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    use_tls: bool,
    max_connection_retries: int,
    max_download_retries: int,
    parallel_files: int,
) -> None:
    """
    Download paths concurrently using ``parallel_files`` workers; each
    worker opens its own FTP connection so transfers don't serialize.
    """
    def worker(ftp_path: str, position: int) -> None:
        local_path = os.path.join(output_folder, os.path.basename(ftp_path))
        if skip_if_downloaded_already and os.path.exists(local_path):
            logging.info(f"Skipping download as file already exists: {local_path}")
            return
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
                    return
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
        logging.error(f"Giving up on {ftp_path} from {host}")

    with ThreadPoolExecutor(max_workers=parallel_files) as executor:
        futures = [
            executor.submit(worker, path, idx) for idx, path in enumerate(paths)
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Parallel FTP download error: {e}")


def download_ftp_urls(
    ftp_urls: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    max_connection_retries: int = 3,
    max_download_retries: int = 3,
    use_tls: bool = False,
    parallel_files: int = 1,
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
    """
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    host_to_paths: Dict[str, List[str]] = {}
    for url in ftp_urls:
        parsed = urlparse(url)
        host_to_paths.setdefault(parsed.hostname, []).append(parsed.path.lstrip("/"))

    for host, paths in host_to_paths.items():
        workers = max(1, min(parallel_files, len(paths)))
        if workers > 1:
            _download_ftp_paths_parallel(
                host=host,
                paths=paths,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=use_tls,
                max_connection_retries=max_connection_retries,
                max_download_retries=max_download_retries,
                parallel_files=workers,
            )
        else:
            _download_ftp_paths_serial(
                host=host,
                paths=paths,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=use_tls,
                max_connection_retries=max_connection_retries,
                max_download_retries=max_download_retries,
            )


def _parallel_download(url, file_path, position=0):
    """Download a file via a single-connection HTTP stream with optional resume.
    If a partial file exists and the server supports Range requests, resumes
    from where it left off; otherwise restarts from scratch."""
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
    with session.get(url, headers=headers, stream=True, timeout=(30, 60)) as r:
        r.raise_for_status()
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


def _http_download_one(
    url: str,
    output_folder: str,
    skip_if_downloaded_already: bool,
    max_retries: int = 3,
    position: int = 0,
) -> None:
    """
    Download a single HTTP(S) URL with HEAD-then-Range resume and retry.
    Used as the worker target for both the serial loop and the parallel
    ThreadPoolExecutor path. Reuses :meth:`_parallel_download` so the same
    resume / restart-on-non-206 behaviour is shared with globus downloads.
    """
    local_path = _local_path_for_url(url, output_folder)
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
) -> None:
    """
    Download a list of HTTP(S) URLs with HEAD-then-Range resume, per-file
    retries, and an optional ``parallel_files`` worker pool.

    When ``parallel_files`` > 1, downloads run concurrently using a
    :class:`ThreadPoolExecutor`. Each worker manages its own file (a new
    ``requests`` session is opened inside ``_parallel_download``) so the
    only shared resource is the output directory.
    """
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    if not http_urls:
        return

    workers = max(1, min(parallel_files, len(http_urls)))
    if workers > 1:
        logging.info(
            f"Downloading {len(http_urls)} HTTP(S) file(s) with {workers} parallel workers"
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _http_download_one,
                    url,
                    output_folder,
                    skip_if_downloaded_already,
                    max_retries,
                    idx,
                )
                for idx, url in enumerate(http_urls)
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Parallel HTTP download error: {e}")
    else:
        for url in http_urls:
            try:
                _http_download_one(
                    url,
                    output_folder,
                    skip_if_downloaded_already,
                    max_retries,
                )
            except Exception as e:
                logging.error(f"HTTP download failed for {url}: {e}")
