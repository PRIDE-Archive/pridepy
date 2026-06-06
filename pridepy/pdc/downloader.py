from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from pridepy.download import transport
from pridepy.download.util import compute_md5
from pridepy.pdc.client import PDCFile, fetch_study_files, parse_download_requests, refresh_signed_url

LOGGER = logging.getLogger(__name__)

FetchFiles = Callable[[str, str], List[PDCFile]]
RefreshUrl = Callable[[str, str, str], Optional[str]]


@dataclass
class PDCDownloadStats:
    studies: int = 0
    total_files: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(frozen=True)
class PDCTransferResult:
    success: bool
    message: str
    http_status: Optional[int] = None


@dataclass(frozen=True)
class PDCDownloadFailure:
    study_id: str
    file_name: str
    message: str
    file_type: Optional[str] = None
    pdc_file: Optional[PDCFile] = None
    http_status: Optional[int] = None


def validate_pdc_file(path: Path, pdc_file: PDCFile, checksum_check: bool) -> Tuple[bool, str]:
    if not path.exists():
        return False, "file does not exist"

    actual_size = path.stat().st_size
    if pdc_file.file_size > 0 and actual_size != pdc_file.file_size:
        return False, f"size mismatch (expected={pdc_file.file_size}, actual={actual_size})"
    if pdc_file.file_size <= 0 and actual_size == 0:
        return False, "file is empty and PDC did not provide a positive file_size"

    if checksum_check:
        if pdc_file.md5sum:
            actual_md5 = compute_md5(str(path))
            if actual_md5.lower() != pdc_file.md5sum.lower():
                return False, (
                    f"checksum mismatch (expected={pdc_file.md5sum.lower()}, "
                    f"actual={actual_md5.lower()})"
                )
        else:
            LOGGER.warning(
                "PDC did not provide md5sum for %s/%s; falling back to size validation",
                pdc_file.study_id,
                pdc_file.file_name,
            )

    return True, "ok"


def _is_download_complete(path: Path, pdc_file: PDCFile, checksum_check: bool) -> bool:
    valid, reason = validate_pdc_file(path, pdc_file, checksum_check)
    if not valid:
        LOGGER.info("Existing file is incomplete: %s (%s)", path, reason)
    return valid


def _http_status_from_exception(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        try:
            return int(status_code)
        except (TypeError, ValueError):
            return None
    if "403" in str(exc):
        return 403
    return None


def _part_path(target: Path) -> Path:
    return target.with_name(target.name + ".part")


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except FileNotFoundError:
        return


def _download_to_part(pdc_file: PDCFile, target: Path, checksum_check: bool, download_threads: int) -> PDCTransferResult:
    part = _part_path(target)
    _remove_file(part)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        LOGGER.info("Downloading %s/%s", pdc_file.study_id, pdc_file.file_name)
        if download_threads > 1:
            transport._multipart_download(pdc_file.url, str(part), threads=download_threads)
        else:
            transport._parallel_download(pdc_file.url, str(part))

        valid, reason = validate_pdc_file(part, pdc_file, checksum_check)
        if not valid:
            _remove_file(part)
            return PDCTransferResult(False, reason)

        os.replace(part, target)
        return PDCTransferResult(True, "ok")
    except Exception as exc:  # pylint: disable=broad-except
        _remove_file(part)
        return PDCTransferResult(False, str(exc), _http_status_from_exception(exc))


def _download_with_retries(
    pdc_file: PDCFile,
    target: Path,
    checksum_check: bool,
    download_threads: int,
    file_type: str,
    refresh_url: RefreshUrl,
    refresh_on_403: bool,
    max_attempts: int,
) -> PDCTransferResult:
    current_file = pdc_file
    result = PDCTransferResult(False, "not attempted")
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            LOGGER.info(
                "Retrying %s/%s (%d/%d)",
                current_file.study_id,
                current_file.file_name,
                attempt,
                max_attempts,
            )

        result = _download_to_part(current_file, target, checksum_check, download_threads)
        if result.success:
            return result

        if result.http_status == 403 and refresh_on_403:
            fresh_url = refresh_url(current_file.study_id, current_file.file_name, file_type)
            if fresh_url:
                current_file = replace(current_file, url=fresh_url)
                LOGGER.info("Refreshed signed URL for %s/%s", current_file.study_id, current_file.file_name)
            else:
                LOGGER.warning(
                    "Could not refresh signed URL for %s/%s",
                    current_file.study_id,
                    current_file.file_name,
                )

        if attempt < max_attempts:
            time.sleep(min(60, 2 ** attempt))

    return result


def _target_path(output_folder: Path, pdc_file: PDCFile) -> Path:
    return output_folder / pdc_file.study_id / pdc_file.file_name


def _write_failed_files(output_folder: Path, failures: List[PDCDownloadFailure]) -> Path:
    failed_log = output_folder / "failed_files.txt"
    with failed_log.open("w", encoding="utf-8") as handle:
        handle.write("# PDC download failures\n")
        handle.write("# study_id\tfile_name\tmessage\n")
        for failure in failures:
            handle.write(f"{failure.study_id}\t{failure.file_name}\t{failure.message}\n")
    return failed_log


def _failure_from_result(pdc_file: PDCFile, result: PDCTransferResult, file_type: str) -> PDCDownloadFailure:
    return PDCDownloadFailure(
        study_id=pdc_file.study_id,
        file_name=pdc_file.file_name,
        message=result.message,
        file_type=file_type,
        pdc_file=pdc_file,
        http_status=result.http_status,
    )


def _fetch_study_file_list(
    study_id: str,
    file_type: str,
    fetch_files: FetchFiles,
) -> Tuple[List[PDCFile], Optional[PDCDownloadFailure]]:
    try:
        return fetch_files(study_id, file_type), None
    except Exception as exc:  # pylint: disable=broad-except
        return [], PDCDownloadFailure(study_id, "<metadata>", str(exc), file_type=file_type)


def _download_study_files(
    study_id: str,
    study_files: List[PDCFile],
    output_path: Path,
    options: "PDCDownloadOptions",
    stats: PDCDownloadStats,
) -> List[PDCDownloadFailure]:
    failures: List[PDCDownloadFailure] = []
    for file_index, pdc_file in enumerate(study_files, 1):
        target = _target_path(output_path, pdc_file)
        LOGGER.info("[%s %d/%d] %s", study_id, file_index, len(study_files), pdc_file.file_name)

        if options.skip_existing and _is_download_complete(target, pdc_file, options.checksum_check):
            stats.skipped += 1
            LOGGER.info("Skipped existing file: %s", target)
            continue

        result = _download_with_retries(
            pdc_file,
            target,
            options.checksum_check,
            options.download_threads,
            options.file_type,
            options.refresh_url,
            refresh_on_403=False,
            max_attempts=1,
        )
        if result.success:
            stats.downloaded += 1
        else:
            failures.append(_failure_from_result(pdc_file, result, options.file_type))
            LOGGER.error("Failed %s/%s: %s", pdc_file.study_id, pdc_file.file_name, result.message)
    return failures


@dataclass(frozen=True)
class PDCDownloadOptions:
    file_type: str
    skip_existing: bool
    checksum_check: bool
    download_threads: int
    refresh_url: RefreshUrl


def _refresh_before_retry(
    failure: PDCDownloadFailure,
    file_type: str,
    refresh_url: RefreshUrl,
) -> PDCFile:
    retry_file = failure.pdc_file
    if retry_file is None:
        raise ValueError("Cannot retry metadata failure")
    if failure.http_status != 403:
        return retry_file

    fresh_url = refresh_url(retry_file.study_id, retry_file.file_name, file_type)
    if fresh_url:
        retry_file = replace(retry_file, url=fresh_url)
        LOGGER.info("Refreshed signed URL for %s/%s", retry_file.study_id, retry_file.file_name)
    return retry_file


def _retry_failed_downloads(
    failures: List[PDCDownloadFailure],
    output_path: Path,
    options: PDCDownloadOptions,
    stats: PDCDownloadStats,
) -> List[PDCDownloadFailure]:
    retry_failures: List[PDCDownloadFailure] = []
    LOGGER.info("Retrying %d failed PDC file(s)", len(failures))
    for failure in failures:
        if failure.pdc_file is None:
            retry_failures.append(failure)
            continue

        retry_file_type = failure.file_type or options.file_type
        retry_file = _refresh_before_retry(failure, retry_file_type, options.refresh_url)
        result = _download_with_retries(
            retry_file,
            _target_path(output_path, retry_file),
            options.checksum_check,
            options.download_threads,
            retry_file_type,
            options.refresh_url,
            refresh_on_403=True,
            max_attempts=3,
        )
        if result.success:
            stats.downloaded += 1
            LOGGER.info("Recovered %s/%s", failure.study_id, failure.file_name)
        else:
            retry_failures.append(_failure_from_result(retry_file, result, retry_file_type))
    return retry_failures


def download_pdc_files(
    accession: str,
    file_type: Optional[str],
    output_folder: str,
    skip_if_downloaded_already: bool = False,
    checksum_check: bool = True,
    download_threads: int = 1,
    retry: bool = False,
    fetch_files: FetchFiles = fetch_study_files,
    refresh_url: RefreshUrl = refresh_signed_url,
) -> PDCDownloadStats:
    requests = parse_download_requests(accession, file_type)
    output_path = Path(output_folder).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)
    active_download_threads = max(1, min(32, int(download_threads or 1)))
    retry_options = PDCDownloadOptions(
        file_type=requests[0].file_type,
        skip_existing=skip_if_downloaded_already,
        checksum_check=checksum_check,
        download_threads=active_download_threads,
        refresh_url=refresh_url,
    )

    stats = PDCDownloadStats(studies=len(dict.fromkeys(request.study_id for request in requests)))
    failures: List[PDCDownloadFailure] = []
    empty_match_failures: List[PDCDownloadFailure] = []

    for request_index, request in enumerate(requests, 1):
        LOGGER.info(
            "[%d/%d] Fetching PDC files for %s file_type=%s",
            request_index,
            len(requests),
            request.study_id,
            request.file_type,
        )
        study_files, metadata_failure = _fetch_study_file_list(request.study_id, request.file_type, fetch_files)
        if metadata_failure:
            failures.append(metadata_failure)
            continue

        stats.total_files += len(study_files)
        if not study_files:
            message = f"No PDC files matched file_type={request.file_type}"
            LOGGER.warning("%s for %s", message, request.study_id)
            empty_match_failures.append(
                PDCDownloadFailure(
                    request.study_id,
                    f"<{request.file_type}>",
                    message,
                    file_type=request.file_type,
                )
            )
            continue

        options = PDCDownloadOptions(
            file_type=request.file_type,
            skip_existing=skip_if_downloaded_already,
            checksum_check=checksum_check,
            download_threads=active_download_threads,
            refresh_url=refresh_url,
        )
        failures.extend(_download_study_files(request.study_id, study_files, output_path, options, stats))

    if failures and retry:
        failures = _retry_failed_downloads(failures, output_path, retry_options, stats)

    if stats.downloaded == 0 and stats.skipped == 0 and empty_match_failures:
        failures.extend(empty_match_failures)

    stats.failed = len(failures)
    if failures:
        failed_log = _write_failed_files(output_path, failures)
        raise RuntimeError(f"Failed to download {len(failures)} PDC file(s). See {failed_log}")

    LOGGER.info(
        "PDC download finished: studies=%d total=%d downloaded=%d skipped=%d failed=%d",
        stats.studies,
        stats.total_files,
        stats.downloaded,
        stats.skipped,
        stats.failed,
    )
    return stats
