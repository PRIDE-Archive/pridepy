#!/usr/bin/env python
"""Public Files facade — thin compatibility surface over the modular
provider architecture in :mod:`pridepy.providers`.

The provider classes own all transport/listing logic; this module exposes
a small set of high-level operations (CLI entry points + a handful of
one-line shims for downstream Python users).
"""
import logging
import os
from typing import Dict, List, Optional, Tuple

import requests  # noqa: F401 — kept as a patch target for tests

from pridepy.util.api_handling import Util

from pridepy.providers import registry, transport
from pridepy.providers import util as _provider_util
from pridepy.providers.iprox import IproxProvider
from pridepy.providers.jpost import JpostProvider
from pridepy.providers.massive import MASSIVE_CATEGORY_MAP, MassiveProvider
from pridepy.providers.pride import PrideProvider
from pridepy.providers.proteomexchange import ProteomeXchangeProvider
from pridepy.commands import by_list, by_url

# Re-export Progress so external `from pridepy.files.files import Progress`
# still works.
from pridepy.providers.util import Progress  # noqa: F401


class Files:
    """High-level facade over the per-repository providers."""

    # PRIDE class-attribute re-exports (kept here for back-compat).
    V3_API_BASE_URL = PrideProvider.V3_API_BASE_URL
    API_BASE_URL = PrideProvider.API_BASE_URL
    API_PRIVATE_URL = PrideProvider.API_PRIVATE_URL
    PRIDE_ARCHIVE_FTP = PrideProvider.ARCHIVE_FTP
    PRIDE_ARCHIVE_FTP_URL_PREFIX = PrideProvider.ARCHIVE_FTP_URL_PREFIX
    PRIDE_ARCHIVE_HTTPS_URL_PREFIX = PrideProvider.ARCHIVE_HTTPS_URL_PREFIX
    S3_URL = PrideProvider.S3_URL
    S3_BUCKET = PrideProvider.S3_BUCKET
    PROTOCOL_ORDER = PrideProvider.PROTOCOL_ORDER

    # MassIVE class-attribute re-exports.
    MASSIVE_ARCHIVE_FTP = MassiveProvider.ARCHIVE_FTP
    MASSIVE_ARCHIVE_FTP_URL_PREFIX = MassiveProvider.ARCHIVE_FTP_URL_PREFIX

    # JPOST class-attribute re-exports.
    JPOST_ARCHIVE_FTP = JpostProvider.ARCHIVE_FTP
    JPOST_ARCHIVE_FTP_URL_PREFIX = JpostProvider.ARCHIVE_FTP_URL_PREFIX
    JPOST_PROXI_BASE_URL = JpostProvider.PROXI_BASE_URL
    JPOST_PROXI_CATEGORY_MAP = JpostProvider.PROXI_CATEGORY_MAP

    # iProX class-attribute re-exports.
    IPROX_DOWNLOAD_BASE_URL = IproxProvider.DOWNLOAD_BASE_URL
    IPROX_PX_XML_URL_TEMPLATE = IproxProvider.PX_XML_URL_TEMPLATE
    IPROX_PX_CATEGORY_MAP = IproxProvider.PX_CATEGORY_MAP

    # MassIVE category map re-exported.
    MASSIVE_CATEGORY_MAP = MASSIVE_CATEGORY_MAP

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    def __init__(self):
        pass

    # Pure delegating shims kept for backward compatibility.

    @staticmethod
    def compute_md5(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
        """Shim — see :func:`pridepy.providers.util.compute_md5`."""
        return _provider_util.compute_md5(file_path, chunk_size)

    @staticmethod
    def validate_download(file_path: str, expected_checksum: Optional[str] = None) -> Tuple[bool, str]:
        """Shim — see :func:`pridepy.providers.util.validate_download`."""
        return _provider_util.validate_download(file_path, expected_checksum)

    @staticmethod
    def read_checksum_file(checksum_file_path: str) -> Dict[str, str]:
        """Shim — see :func:`pridepy.providers.util.read_checksum_file`."""
        return _provider_util.read_checksum_file(checksum_file_path)

    @staticmethod
    def download_ftp_urls(
        ftp_urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        max_connection_retries: int = 3,
        max_download_retries: int = 3,
        use_tls: bool = False,
        parallel_files: int = 1,
    ) -> None:
        """Shim — see :func:`pridepy.providers.transport.download_ftp_urls`."""
        return transport.download_ftp_urls(
            ftp_urls=ftp_urls,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            max_connection_retries=max_connection_retries,
            max_download_retries=max_download_retries,
            use_tls=use_tls,
            parallel_files=parallel_files,
        )

    @staticmethod
    def download_http_urls(
        http_urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        parallel_files: int = 1,
        max_retries: int = 3,
    ) -> None:
        """Shim — see :func:`pridepy.providers.transport.download_http_urls`."""
        return transport.download_http_urls(
            http_urls=http_urls,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            parallel_files=parallel_files,
            max_retries=max_retries,
        )

    # Accession-matcher convenience helpers (useful public API).

    @staticmethod
    def is_massive_accession(accession: str) -> bool:
        return MassiveProvider.matches(accession)

    @staticmethod
    def is_jpost_accession(accession: str) -> bool:
        return JpostProvider.matches(accession)

    @staticmethod
    def is_iprox_accession(accession: str) -> bool:
        return IproxProvider.matches(accession)

    @staticmethod
    def is_direct_download_accession(accession: str) -> bool:
        """True for MassIVE / JPOST / iProX (explicitly excludes PRIDE)."""
        try:
            provider = registry.resolve(accession)
        except ValueError:
            return False
        return provider.name != "pride"

    @staticmethod
    def _repo_uses_tls(accession: str) -> bool:
        """Return the resolved provider's ``use_tls`` flag (False if unknown)."""
        try:
            provider = registry.resolve(accession)
        except ValueError:
            return False
        return getattr(provider, "use_tls", False)

    # Listing / metadata.

    async def stream_all_files_metadata(self, output_file, accession=None):
        """Shim — see :meth:`PrideProvider.stream_all_files_metadata`."""
        return await PrideProvider().stream_all_files_metadata(output_file, accession)

    def get_all_raw_file_list(self, project_accession):
        """Get raw file list for any registered provider (records with fileCategory == "RAW")."""
        provider = registry.resolve(project_accession)
        records = provider.list_files(project_accession)
        return [r for r in records if r["fileCategory"]["value"] == "RAW"]

    def get_all_category_file_list(
        self, accession: str, categories: "str | List[str]"
    ) -> List[Dict]:
        """Retrieve project files belonging to the given categories."""
        if isinstance(categories, str):
            categories = [categories]
        category_set = {c.upper() for c in categories}
        records = registry.resolve(accession).list_files(accession)
        return [r for r in records if r["fileCategory"]["value"] in category_set]

    def get_submitted_file_path_prefix(self, accession):
        """Shim — see :meth:`PrideProvider.get_submitted_file_path_prefix`."""
        return PrideProvider().get_submitted_file_path_prefix(accession)

    def get_file_from_api(self, accession, file_name) -> List[Dict]:
        """Return records matching ``file_name`` from the provider's listing."""
        try:
            records = registry.resolve(accession).list_files(accession)
            return [r for r in records if r["fileName"] == file_name]
        except Exception as e:
            raise Exception("File not found " + str(e))

    # Download entry points.

    def download_all_raw_files(
        self,
        accession,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        aspera_maximum_bandwidth: str,
        checksum_check: bool = False,
        parallel_files: int = 1,
    ):
        """Download all RAW files for any registered provider."""
        if not os.path.isdir(output_folder):
            os.mkdir(output_folder)
        provider = registry.resolve(accession)
        records = self.get_all_raw_file_list(accession)
        provider.download_files(
            accession=accession,
            records=records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        )

    def download_all_category_files(
        self,
        accession: str,
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        aspera_maximum_bandwidth: str,
        checksum_check: bool,
        categories: List[str] = None,
        category: str = None,
        parallel_files: int = 1,
    ):
        """Download all files of the given categories from a project."""
        if categories is None:
            categories = [category] if category else ["RAW"]
        records = self.get_all_category_file_list(accession, categories)
        provider = registry.resolve(accession)
        provider.download_files(
            accession=accession,
            records=records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        )

    def download_file_by_name(
        self,
        accession,
        file_name,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        username,
        password,
        aspera_maximum_bandwidth,
        checksum_check,
    ):
        """Download a single file by name.

        PRIDE supports public / private modes via the V2 private API. Other
        providers (MassIVE / JPOST / iProX) only support public downloads.
        """
        if not os.path.isdir(output_folder):
            os.mkdir(output_folder)

        provider = registry.resolve(accession)

        # Direct-download providers always use the public path.
        if provider.name in ("massive", "jpost", "iprox"):
            logging.info(
                "Downloading file from public direct-download dataset {}".format(accession)
            )
            response = self.get_file_from_api(accession, file_name)
            if not response:
                raise Exception(
                    "File name {} not found in dataset {}".format(file_name, accession)
                )
            provider.download_files(
                accession=accession,
                records=response,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
            )
            return

        # PRIDE has a public/private split that needs status interrogation.
        public_project = False
        project_status = Util.get_api_call(self.API_BASE_URL + "/status/{}".format(accession))

        if project_status.status_code == 200:
            if project_status.text == "PRIVATE":
                public_project = False
            elif project_status.text == "PUBLIC":
                public_project = True
            else:
                raise Exception("Dataset {} is not present in PRIDE Archive".format(accession))

        if public_project:
            logging.info("Downloading file from public dataset {}".format(accession))
            response = self.get_file_from_api(accession, file_name)
            PrideProvider._download_files_batch(
                file_list_json=response,
                accession=accession,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
                aspera_maximum_bandwidth=aspera_maximum_bandwidth,
                checksum_check=checksum_check,
            )
        elif not public_project and (username is not None and password is not None):
            logging.info("Downloading file from private dataset {}".format(accession))
            PrideProvider().download_private_file_name(
                accession=accession,
                file_name=file_name,
                output_folder=output_folder,
                username=username,
                password=password,
            )
        else:
            logging.error(
                "For a private dataset {} you must provide a username and password".format(
                    accession
                )
            )
            raise Exception(
                "For a private dataset {} you must provide a username and password".format(
                    accession
                )
            )

    def download_files_by_list(
        self,
        accession: str,
        file_names: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str = "ftp",
        aspera_maximum_bandwidth: str = "100M",
        checksum_check: bool = False,
        parallel_files: int = 1,
    ) -> None:
        """Delegate to :func:`pridepy.commands.by_list.download_files_by_list`."""
        return by_list.download_files_by_list(
            accession=accession,
            file_names=file_names,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
        )

    @staticmethod
    def download_files_by_url(
        urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool = False,
        protocol: str = "ftp",
        parallel_files: int = 1,
        checksum_check: bool = False,
    ) -> None:
        """Delegate to :func:`pridepy.commands.by_url.download_files_by_url`."""
        return by_url.download_files_by_url(
            urls=urls,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
            checksum_check=checksum_check,
        )

    def download_px_raw_files(
        self,
        px_id_or_url: str,
        output_folder: str,
        skip_if_downloaded_already: bool = True,
    ) -> None:
        """Delegate to :meth:`ProteomeXchangeProvider.download_from_accession_or_url`."""
        return ProteomeXchangeProvider().download_from_accession_or_url(
            px_id_or_url, output_folder, skip_if_downloaded_already
        )
