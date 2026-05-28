"""Download a subset of project files identified by a filename list."""
import logging
from typing import List, Optional

from pridepy.download import registry


def download_files_by_list(
    accession: str,
    file_names: List[str],
    output_folder: str,
    skip_if_downloaded_already: bool,
    protocol: str = "ftp",
    aspera_maximum_bandwidth: str = "100M",
    checksum_check: bool = False,
    parallel_files: int = 1,
) -> None:
    """Download a subset of project files identified by a filename list.

    Resolves each requested filename via the project metadata API and
    delegates to the provider's ``download_files`` so the existing batch +
    protocol fallback engine is reused.

    :param accession: PRIDE or MassIVE project accession (public)
    :param file_names: filenames to download
    :param output_folder: directory to write downloaded files into
    :param skip_if_downloaded_already: skip files already present locally
    :param protocol: preferred protocol; falls back across others on failure
    :param aspera_maximum_bandwidth: aspera ascp bandwidth cap
    :param checksum_check: download project checksums and validate
    :param parallel_files: number of files to download simultaneously for globus
    :raises ValueError: if ``file_names`` is empty or none match the project
    """
    if not file_names:
        raise ValueError("file_names must contain at least one filename")

    provider = registry.resolve(accession)
    all_files = provider.list_files(accession)

    requested = set(file_names)
    matched = [f for f in all_files if f.get("fileName") in requested]
    missing = sorted(requested - {f.get("fileName") for f in matched})
    if missing:
        logging.warning("Files not found in project %s: %s", accession, missing)
    if not matched:
        raise ValueError(
            f"No matching files in project {accession} for: {sorted(requested)}"
        )

    provider.download_files(
        accession=accession,
        records=matched,
        output_folder=output_folder,
        skip_if_downloaded_already=skip_if_downloaded_already,
        protocol=protocol,
        parallel_files=parallel_files,
        checksum_check=checksum_check,
        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
    )
