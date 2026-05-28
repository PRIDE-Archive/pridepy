"""Abstract base classes for pridepy providers."""
import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Dict, List, Optional

from pridepy.download import transport
from pridepy.download import util as _provider_util


class Provider(ABC):
    """Abstract base for every repository pridepy can list and download from."""

    name: ClassVar[str]  # "pride", "massive", "jpost", "iprox"

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

    @abstractmethod
    def download_files(
        self,
        accession: str,
        records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        parallel_files: int = 1,
        checksum_check: bool = False,
        aspera_maximum_bandwidth: str = "100M",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Download the given records into ``output_folder``."""


class BaseDirectDownloadProvider(Provider):
    """Shared ``download_files`` for MassIVE / JPOST / iProX.

    Subclasses set the ``use_tls`` class var (True for MassIVE FTPS, False for
    JPOST plain FTP) and override :meth:`list_files`. The shared
    ``download_files`` implementation partitions record URLs by scheme:
    ``ftp://`` URLs are handed to :func:`transport.download_ftp_urls`;
    ``http(s)://`` URLs go to :func:`transport.download_http_urls`.
    """

    use_tls: ClassVar[bool] = False

    def download_files(
        self,
        accession: str,
        records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        parallel_files: int = 1,
        checksum_check: bool = False,
        aspera_maximum_bandwidth: str = "100M",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        if protocol not in ("ftp", "https", "http"):
            logging.warning(
                "Direct downloads currently use ftp / https only. "
                f"Ignoring requested protocol '{protocol}' for {accession}."
            )

        all_urls = [_provider_util._get_download_url(record, "ftp") for record in records]
        ftp_urls = [u for u in all_urls if u.lower().startswith("ftp://")]
        http_urls = [
            u for u in all_urls if u.lower().startswith(("http://", "https://"))
        ]
        if not ftp_urls and not http_urls:
            logging.info(
                f"No files matched for direct-download dataset {accession}"
            )
            return

        if ftp_urls:
            transport.download_ftp_urls(
                ftp_urls=ftp_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=self.use_tls,
                parallel_files=parallel_files,
            )
        if http_urls:
            transport.download_http_urls(
                http_urls=http_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
            )
