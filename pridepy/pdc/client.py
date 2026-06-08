from __future__ import annotations

import csv
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pridepy.util.api_handling import Util

PDC_API = "https://pdc.cancer.gov/graphql"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT_SECONDS = 600

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PDCFileTypeFilter:
    data_category: Optional[str]
    file_format: Optional[str]
    filename_suffix: Optional[str] = None


@dataclass(frozen=True)
class PDCFile:
    study_id: str
    file_id: str
    file_name: str
    file_format: Optional[str]
    file_size: int
    data_category: Optional[str]
    file_type: Optional[str]
    file_location: Optional[str]
    md5sum: Optional[str]
    url: str


@dataclass(frozen=True)
class PDCDownloadRequest:
    study_id: str
    file_type: Optional[str]


PDC_FILE_TYPE_FILTERS: Dict[str, PDCFileTypeFilter] = {
    "mzid": PDCFileTypeFilter("Peptide Spectral Matches", "mzIdentML"),
    "psm": PDCFileTypeFilter("Peptide Spectral Matches", "tsv", ".psm"),
    "raw": PDCFileTypeFilter("Raw Mass Spectra", "vendor-specific"),
    "mzml": PDCFileTypeFilter("Processed Mass Spectra", "mzML"),
}

PDC_FILE_TYPE_COLUMNS = ("file-type", "file_type", "filetype")


FILES_PER_STUDY_QUERY = """
query FilesPerStudy($studyId: String!) {
  filesPerStudy(pdc_study_id: $studyId, acceptDUA: true) {
    file_id
    pdc_study_id
    file_name
    file_format
    file_size
    data_category
    file_type
    file_location
    md5sum
    signedUrl {
      url
    }
  }
}
"""

_refresh_lock = threading.Lock()


def split_accession_text(text: str) -> List[str]:
    items: List[str] = []
    for raw_item in text.replace(",", "\n").splitlines():
        item = raw_item.strip()
        if item and not item.startswith("#"):
            items.append(item)
    return items


def dedupe_keep_order(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(item for item in items if item))


def _study_id_column(columns: List[str], path: Path) -> str:
    if "pdc_id" in columns:
        return "pdc_id"
    if "pdc_study_id" in columns:
        return "pdc_study_id"
    raise ValueError(f"CSV must contain pdc_id or pdc_study_id column: {path}")


def _file_type_column(columns: List[str]) -> Optional[str]:
    for column in PDC_FILE_TYPE_COLUMNS:
        if column in columns:
            return column
    return None


def _read_accession_rows_from_csv(path: Path) -> Tuple[List[Tuple[str, Optional[str]]], bool]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        study_column = _study_id_column(columns, path)
        file_type_column = _file_type_column(columns)

        rows = []
        for row in reader:
            study_id = str(row.get(study_column) or "").strip()
            if not study_id:
                continue
            row_file_type = None
            if file_type_column:
                row_file_type = str(row.get(file_type_column) or "").strip() or None
            rows.append((study_id, row_file_type))

    if not rows:
        raise ValueError(f"Download accession list is empty: {path}")
    return rows, file_type_column is not None


def _read_accessions_from_csv(path: Path) -> List[str]:
    rows, _has_file_type_column = _read_accession_rows_from_csv(path)
    return dedupe_keep_order(study_id for study_id, _file_type in rows)


def parse_accessions(accession: str) -> List[str]:
    if not accession or not accession.strip():
        raise ValueError("--accession must not be empty")

    source_path = Path(accession).expanduser()
    if source_path.is_file():
        if source_path.suffix.lower() != ".csv":
            raise ValueError(f"Only CSV accession files are supported: {source_path}")
        return _read_accessions_from_csv(source_path)

    if source_path.suffix.lower() == ".csv" or os.path.sep in accession:
        raise ValueError(f"Accession CSV not found: {source_path}")

    accessions = dedupe_keep_order(split_accession_text(accession))
    if not accessions:
        raise ValueError("--accession did not contain any PDC study ID")
    return accessions


def normalize_file_type(file_type: str) -> str:
    normalized = str(file_type or "").strip().lower()
    if normalized not in PDC_FILE_TYPE_FILTERS:
        valid = ", ".join(sorted(PDC_FILE_TYPE_FILTERS))
        raise ValueError(f"Unsupported PDC file type: {file_type}. Valid values: {valid}")
    return normalized


def parse_download_requests(accession: str, file_type: Optional[str] = None) -> List[PDCDownloadRequest]:
    if not accession or not accession.strip():
        raise ValueError("--accession must not be empty")

    command_file_type = normalize_file_type(file_type) if file_type else None
    source_path = Path(accession).expanduser()

    if source_path.is_file():
        if source_path.suffix.lower() != ".csv":
            raise ValueError(f"Only CSV accession files are supported: {source_path}")

        rows, has_csv_file_type = _read_accession_rows_from_csv(source_path)
        if has_csv_file_type and command_file_type:
            LOGGER.warning(
                "CSV contains file-type column; --file-type=%s overrides CSV file-type values",
                command_file_type,
            )

        requests = []
        for study_id, csv_file_type in rows:
            request_file_type = command_file_type
            if request_file_type is None and csv_file_type is not None:
                request_file_type = normalize_file_type(csv_file_type)
            requests.append(PDCDownloadRequest(study_id, request_file_type))
        return list(dict.fromkeys(requests))

    study_ids = parse_accessions(accession)
    return [PDCDownloadRequest(study_id, command_file_type) for study_id in study_ids]


def get_file_type_filter(file_type: str) -> PDCFileTypeFilter:
    return PDC_FILE_TYPE_FILTERS[normalize_file_type(file_type)]


def entry_matches_file_type(entry: Dict, file_type: str) -> bool:
    file_filter = get_file_type_filter(file_type)
    if file_filter.data_category is not None and entry.get("data_category") != file_filter.data_category:
        return False
    if file_filter.file_format is not None and entry.get("file_format") != file_filter.file_format:
        return False
    if file_filter.filename_suffix is not None:
        file_name = str(entry.get("file_name") or "")
        if not file_name.endswith(file_filter.filename_suffix):
            return False
    return True


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_pdc_file(entry: Dict, fallback_study_id: str) -> Optional[PDCFile]:
    file_name = str(entry.get("file_name") or "").strip()
    signed_url = (entry.get("signedUrl") or {}).get("url")
    if not file_name or not signed_url:
        return None

    md5sum = entry.get("md5sum")
    return PDCFile(
        study_id=str(entry.get("pdc_study_id") or fallback_study_id),
        file_id=str(entry.get("file_id") or ""),
        file_name=file_name,
        file_format=entry.get("file_format"),
        file_size=_safe_int(entry.get("file_size")),
        data_category=entry.get("data_category"),
        file_type=entry.get("file_type"),
        file_location=entry.get("file_location"),
        md5sum=str(md5sum).lower() if md5sum else None,
        url=str(signed_url),
    )


def post_graphql(query: str, variables: Dict, session=None) -> Dict:
    active_session = session or Util.create_session_with_retries()
    response = active_session.post(
        PDC_API,
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"PDC GraphQL returned errors: {payload['errors']}")
    return payload


def fetch_study_files(study_id: str, file_type: Optional[str], session=None) -> List[PDCFile]:
    payload = post_graphql(FILES_PER_STUDY_QUERY, {"studyId": study_id}, session=session)
    raw_files = payload.get("data", {}).get("filesPerStudy", []) or []
    files: List[PDCFile] = []
    for entry in raw_files:
        if file_type is not None and not entry_matches_file_type(entry, file_type):
            continue
        pdc_file = normalize_pdc_file(entry, study_id)
        if pdc_file is None:
            LOGGER.warning("Skipping PDC file without name or signed URL in study %s", study_id)
            continue
        files.append(pdc_file)
    return files


def refresh_signed_url(study_id: str, file_name: str, file_type: Optional[str], session=None) -> Optional[str]:
    with _refresh_lock:
        for pdc_file in fetch_study_files(study_id, file_type, session=session):
            if pdc_file.file_name == file_name:
                return pdc_file.url
    return None
