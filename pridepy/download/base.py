"""Abstract base class for pridepy providers.

The :class:`Provider` base implements the download *workflow* via the
Template Method pattern: most adapters only fill in the holes
(:meth:`matches`, :meth:`list_files`) while the shared listing-filter and
download-orchestration methods live here. Adapters that need different
behaviour override the relevant hooks — e.g. PRIDE overrides
:meth:`get_download_url`, :meth:`download_files` (multi-protocol fallback),
and :meth:`download_by_name` (public/private split). Everything not
overridden routes through the inherited default that partitions record URLs
by scheme.
"""
import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

from pridepy.download import transport
from pridepy.download.util import flatten_relative_paths


class Provider(ABC):
    """Abstract base for every repository pridepy can list and download from."""

    name: ClassVar[str]  # "pride", "massive", "jpost", "iprox"
    use_tls: ClassVar[bool] = False

    # ------------------------------------------------------------------
    # Abstract holes — adapters must implement these.
    # ------------------------------------------------------------------

    @staticmethod
    @abstractmethod
    def matches(accession: str) -> bool:
        """Return True if this provider should handle ``accession``."""

    @abstractmethod
    def list_files(self, accession: str) -> List[Dict]:
        """Return pridepy file records for the dataset.

        Each record is a dict shaped like the PRIDE V3 API file response,
        with at minimum: ``accession``, ``fileName``, ``fileCategory``
        (with nested ``value``), ``publicFileLocations`` (list of
        ``{"name": ..., "value": <URL>}``).
        """

    # ------------------------------------------------------------------
    # Hook with default — adapters may override.
    # ------------------------------------------------------------------

    def get_download_url(self, record: Dict, protocol: str = "ftp") -> str:
        """Resolve the download URL for ``record``.

        Default: return the ``"FTP Protocol"`` public-file-location value
        (most direct-download adapters store their public URL there — ftp://
        for MassIVE/JPOST, http:// for iProX). Records that use a different
        location name (e.g. MassIVE's HTTPS fallback uses ``"HTTPS"``) fall
        through to the first location. Adapters with richer, protocol-aware
        resolution (PRIDE: aspera/globus/s3) override this.
        """
        locations = record.get("publicFileLocations", [])
        if not locations:
            raise ValueError("No public file locations present")
        for location in locations:
            if location.get("name") == "FTP Protocol":
                return location.get("value")
        return locations[0].get("value")

    # ------------------------------------------------------------------
    # Shared listing filters.
    # ------------------------------------------------------------------

    def _list_files_checked(self, accession: str) -> List[Dict]:
        """Call :meth:`list_files` and fail clearly if it yields no listing.

        The PRIDE API helper returns ``None`` on a network error (e.g. a read
        timeout), so guard here to raise an actionable error rather than a
        cryptic ``TypeError: 'NoneType' object is not iterable`` downstream.
        """
        records = self.list_files(accession)
        if records is None:
            raise RuntimeError(
                f"Could not list files for {accession}: the repository API "
                f"returned no data (it may be unreachable, or the accession "
                f"may be invalid)."
            )
        return records

    def get_raw_files(self, accession: str) -> List[Dict]:
        """Return records whose ``fileCategory.value`` is ``"RAW"``."""
        records = self._list_files_checked(accession)
        return [r for r in records if r["fileCategory"]["value"] == "RAW"]

    def get_category_files(
        self, accession: str, categories: "str | List[str]"
    ) -> List[Dict]:
        """Return records belonging to the given category (or categories)."""
        if isinstance(categories, str):
            categories = [categories]
        category_set = {c.upper() for c in categories}
        records = self._list_files_checked(accession)
        return [r for r in records if r["fileCategory"]["value"] in category_set]

    def find_file(self, accession: str, file_name: str) -> List[Dict]:
        """Return records whose ``fileName`` equals ``file_name``."""
        records = self._list_files_checked(accession)
        return [r for r in records if r["fileName"] == file_name]

    # ------------------------------------------------------------------
    # Shared download workflow (Template Method).
    # ------------------------------------------------------------------

    def download_all_raw(
        self,
        accession: str,
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        aspera_maximum_bandwidth: str = "100M",
        checksum_check: bool = False,
        parallel_files: int = 1,
        flatten: bool = True,
    ) -> None:
        """Download all RAW files for the dataset."""
        self.download_files(
            accession=accession,
            records=self.get_raw_files(accession),
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            flatten=flatten,
        )

    def download_category(
        self,
        accession: str,
        output_folder: str,
        categories: "str | List[str]",
        skip_if_downloaded_already: bool,
        protocol: str,
        aspera_maximum_bandwidth: str = "100M",
        checksum_check: bool = False,
        parallel_files: int = 1,
        flatten: bool = True,
    ) -> None:
        """Download all files of the given categories for the dataset."""
        self.download_files(
            accession=accession,
            records=self.get_category_files(accession, categories),
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            flatten=flatten,
        )

    def download_by_name(
        self,
        accession: str,
        file_name: str,
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        aspera_maximum_bandwidth: str = "100M",
        checksum_check: bool = False,
    ) -> None:
        """Download a single file by name from the dataset."""
        records = self.find_file(accession, file_name)
        if not records:
            raise Exception(
                f"File name {file_name} not found in dataset {accession}"
            )
        self.download_files(
            accession=accession,
            records=records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        )

    def download_by_filenames(
        self,
        accession: str,
        file_names: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str = "ftp",
        aspera_maximum_bandwidth: str = "100M",
        checksum_check: bool = False,
        parallel_files: int = 1,
        flatten: bool = True,
    ) -> None:
        """Download a subset of project files identified by a filename list.

        :raises ValueError: if ``file_names`` is empty or none match.
        """
        if not file_names:
            raise ValueError("file_names must contain at least one filename")

        all_files = self._list_files_checked(accession)
        requested = set(file_names)
        matched = [f for f in all_files if f.get("fileName") in requested]
        missing = sorted(requested - {f.get("fileName") for f in matched})
        if missing:
            logging.warning("Files not found in project %s: %s", accession, missing)
        if not matched:
            raise ValueError(
                f"No matching files in project {accession} for: {sorted(requested)}"
            )

        self.download_files(
            accession=accession,
            records=matched,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            flatten=flatten,
        )

    # ------------------------------------------------------------------
    # Default transport — adapters may override (e.g. PrideProvider).
    # ------------------------------------------------------------------

    def download_files(
        self,
        accession: str,
        records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool = False,
        protocol: str = "ftp",
        parallel_files: int = 1,
        checksum_check: bool = False,
        aspera_maximum_bandwidth: str = "100M",
        username: Optional[str] = None,
        password: Optional[str] = None,
        flatten: bool = True,
    ) -> None:
        """Partition record URLs by scheme and route to the matching transport.

        ``ftp://`` URLs are handed to :func:`transport.download_ftp_urls`
        (with this provider's :attr:`use_tls`); ``http(s)://`` URLs go to
        :func:`transport.download_http_urls`.

        When ``flatten`` is True (the default) every file is written directly
        into ``output_folder`` by its basename, de-duplicating colliding
        basenames across the whole set (they share one folder). When False the
        dataset's subdirectory layout is preserved via each record's
        ``relativePath``.
        """
        if protocol not in ("ftp", "https", "http"):
            logging.warning(
                "Direct downloads currently use ftp / http(s) only. "
                f"Ignoring requested protocol '{protocol}' for {accession}."
            )

        # Collect transfer entries in one pass, keeping order stable.
        entries = []  # list of (scheme, url, relpath)
        for record in records:
            url = self.get_download_url(record)
            relpath = record.get("relativePath")
            lowered = url.lower()
            if lowered.startswith("ftp://"):
                entries.append(("ftp", url, relpath))
            elif lowered.startswith(("http://", "https://")):
                entries.append(("http", url, relpath))
        if not entries:
            logging.info(
                f"No files matched for direct-download dataset {accession}"
            )
            return

        if flatten:
            # All files share one output folder, so dedup basenames globally;
            # fall back to the URL path when a record carries no relativePath.
            sources = [rel if rel else urlparse(url).path for _, url, rel in entries]
            dest_paths: List[Optional[str]] = flatten_relative_paths(sources)
        else:
            dest_paths = [rel for _, _, rel in entries]

        ftp_urls: List[str] = []
        ftp_relpaths: List[Optional[str]] = []
        http_urls: List[str] = []
        http_relpaths: List[Optional[str]] = []
        for (scheme, url, _), dest in zip(entries, dest_paths):
            if scheme == "ftp":
                ftp_urls.append(url)
                ftp_relpaths.append(dest)
            else:
                http_urls.append(url)
                http_relpaths.append(dest)

        if ftp_urls:
            transport.download_ftp_urls(
                ftp_urls=ftp_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=self.use_tls,
                parallel_files=parallel_files,
                relative_paths=ftp_relpaths,
            )
        if http_urls:
            transport.download_http_urls(
                http_urls=http_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
                relative_paths=http_relpaths,
            )
