#!/usr/bin/env python
import ftplib
import logging
import os
import re
import urllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from ftplib import FTP
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from tqdm import tqdm

from pridepy.util.api_handling import Util


# Re-export from providers.util so external `from pridepy.files.files import Progress`
# still works.
from pridepy.providers.util import Progress  # noqa: F401


class Files:
    """
    This class handles PRIDE API files endpoint.
    """

    # Re-exported from providers/pride.py — kept here for back-compat.
    from pridepy.providers.pride import PrideProvider as _PrideProvider
    V3_API_BASE_URL = _PrideProvider.V3_API_BASE_URL
    API_BASE_URL = _PrideProvider.API_BASE_URL
    API_PRIVATE_URL = _PrideProvider.API_PRIVATE_URL
    PRIDE_ARCHIVE_FTP = _PrideProvider.ARCHIVE_FTP
    PRIDE_ARCHIVE_FTP_URL_PREFIX = _PrideProvider.ARCHIVE_FTP_URL_PREFIX
    PRIDE_ARCHIVE_HTTPS_URL_PREFIX = _PrideProvider.ARCHIVE_HTTPS_URL_PREFIX
    S3_URL = _PrideProvider.S3_URL
    S3_BUCKET = _PrideProvider.S3_BUCKET
    PROTOCOL_ORDER = _PrideProvider.PROTOCOL_ORDER
    del _PrideProvider
    # Re-exported from providers/massive.py — kept here for back-compat.
    from pridepy.providers.massive import (  # noqa: E402
        MASSIVE_CATEGORY_MAP as _MASSIVE_CATEGORY_MAP,
        MassiveProvider as _MassiveProvider,
    )
    MASSIVE_CATEGORY_MAP = _MASSIVE_CATEGORY_MAP
    MASSIVE_ARCHIVE_FTP = _MassiveProvider.ARCHIVE_FTP
    MASSIVE_ARCHIVE_FTP_URL_PREFIX = _MassiveProvider.ARCHIVE_FTP_URL_PREFIX
    del _MASSIVE_CATEGORY_MAP, _MassiveProvider
    from pridepy.providers.jpost import JpostProvider as _JpostProvider
    JPOST_ARCHIVE_FTP = _JpostProvider.ARCHIVE_FTP
    JPOST_ARCHIVE_FTP_URL_PREFIX = _JpostProvider.ARCHIVE_FTP_URL_PREFIX
    JPOST_PROXI_BASE_URL = _JpostProvider.PROXI_BASE_URL
    JPOST_PROXI_CATEGORY_MAP = _JpostProvider.PROXI_CATEGORY_MAP
    del _JpostProvider
    from pridepy.providers.iprox import IproxProvider as _IproxProvider
    IPROX_DOWNLOAD_BASE_URL = _IproxProvider.DOWNLOAD_BASE_URL
    IPROX_PX_XML_URL_TEMPLATE = _IproxProvider.PX_XML_URL_TEMPLATE
    IPROX_PX_CATEGORY_MAP = _IproxProvider.PX_CATEGORY_MAP
    del _IproxProvider
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    def __init__(self):
        pass

    @staticmethod
    def _find_tsv_columns(header: str) -> Optional[Tuple[int, int]]:
        """Shim — see :func:`pridepy.providers.util._find_tsv_columns`."""
        from pridepy.providers import util
        return util._find_tsv_columns(header)

    @staticmethod
    def _is_md5_checksum(value: str) -> bool:
        """Shim — see :func:`pridepy.providers.util._is_md5_checksum`."""
        from pridepy.providers import util
        return util._is_md5_checksum(value)

    @staticmethod
    def read_checksum_file(checksum_file_path: str) -> Dict[str, str]:
        """Shim — see :func:`pridepy.providers.util.read_checksum_file`."""
        from pridepy.providers import util
        return util.read_checksum_file(checksum_file_path)

    @staticmethod
    def compute_md5(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
        """Shim — see :func:`pridepy.providers.util.compute_md5`."""
        from pridepy.providers import util
        return util.compute_md5(file_path, chunk_size)

    @staticmethod
    def validate_download(file_path: str, expected_checksum: Optional[str] = None) -> Tuple[bool, str]:
        """Shim — see :func:`pridepy.providers.util.validate_download`."""
        from pridepy.providers import util
        return util.validate_download(file_path, expected_checksum)

    @staticmethod
    def _remove_if_exists(file_path: str) -> None:
        """Shim — see :func:`pridepy.providers.util._remove_if_exists`."""
        from pridepy.providers import util
        return util._remove_if_exists(file_path)

    @staticmethod
    def _get_download_url(file_record: Dict, protocol: str) -> str:
        """Shim — see :func:`pridepy.providers.util._get_download_url`."""
        from pridepy.providers import util
        return util._get_download_url(file_record, protocol)

    @staticmethod
    def _resolve_local_path(file_record: Dict, output_folder: str) -> str:
        """Shim — see :func:`pridepy.providers.util._resolve_local_path`."""
        from pridepy.providers import util
        return util._resolve_local_path(file_record, output_folder)

    @staticmethod
    def _protocol_sequence(protocol: str) -> List[str]:
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider._protocol_sequence`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider._protocol_sequence(protocol)

    @staticmethod
    def is_massive_accession(accession: str) -> bool:
        """Shim — see :meth:`pridepy.providers.massive.MassiveProvider.matches`."""
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider.matches(accession)

    @staticmethod
    def _get_massive_public_root(accession: str) -> str:
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider._get_public_root(accession)

    @staticmethod
    def _get_massive_public_ftp_url(accession: str, remote_path: str) -> str:
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider._get_public_ftp_url(accession, remote_path)

    @staticmethod
    def _map_massive_collection_to_category(collection: str) -> str:
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider._map_collection_to_category(collection)

    @staticmethod
    def _build_massive_file_record(accession: str, ftp_url: str) -> Dict:
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider._build_file_record(accession, ftp_url)

    @staticmethod
    def is_jpost_accession(accession: str) -> bool:
        """Shim — see :meth:`pridepy.providers.jpost.JpostProvider.matches`."""
        from pridepy.providers.jpost import JpostProvider
        return JpostProvider.matches(accession)

    @staticmethod
    def _get_jpost_public_root(accession: str) -> str:
        from pridepy.providers.jpost import JpostProvider
        return JpostProvider._get_public_root(accession)

    @staticmethod
    def _get_jpost_public_ftp_url(accession: str, remote_path: str) -> str:
        from pridepy.providers.jpost import JpostProvider
        return JpostProvider._get_public_ftp_url(accession, remote_path)

    @staticmethod
    def _build_jpost_file_record(accession, ftp_url, category_from_proxi=None):
        from pridepy.providers.jpost import JpostProvider
        return JpostProvider._build_file_record(accession, ftp_url, category_from_proxi)

    @staticmethod
    def _build_iprox_file_record(accession, https_url, category_from_px=None):
        """Shim — see :meth:`pridepy.providers.iprox.IproxProvider._build_file_record`."""
        from pridepy.providers.iprox import IproxProvider
        return IproxProvider._build_file_record(accession, https_url, category_from_px)

    @staticmethod
    def _get_iprox_public_root(accession: str) -> str:
        from pridepy.providers.iprox import IproxProvider
        return IproxProvider._get_public_root(accession)

    @staticmethod
    def _get_iprox_public_ftp_url(accession: str, remote_path: str) -> str:
        from pridepy.providers.iprox import IproxProvider
        return IproxProvider._get_public_ftp_url(accession, remote_path)

    @staticmethod
    def is_direct_download_accession(accession: str) -> bool:
        """Shim — True for MassIVE/JPOST/iProX (explicitly excludes PRIDE).

        PRIDE is also a registered provider but PRIDE downloads go through
        the multi-protocol orchestrator (FTP/Aspera/S3/Globus with checksum
        validation and fallback), not the direct-download partitioned-by-URL-
        scheme path. So we filter PRIDE out here.
        """
        from pridepy.providers import registry
        try:
            provider = registry.resolve(accession)
        except ValueError:
            return False
        return provider.name != "pride"

    @staticmethod
    def is_iprox_accession(accession: str) -> bool:
        """Shim — see :meth:`pridepy.providers.iprox.IproxProvider.matches`."""
        from pridepy.providers.iprox import IproxProvider
        return IproxProvider.matches(accession)

    @staticmethod
    def _repo_uses_tls(accession: str) -> bool:
        """Shim — returns the resolved provider's use_tls flag (False if unknown)."""
        from pridepy.providers import registry
        try:
            provider = registry.resolve(accession)
        except ValueError:
            return False
        return getattr(provider, "use_tls", False)

    @staticmethod
    def _walk_ftp_tree(ftp: FTP, remote_dir: str) -> List[str]:
        """Shim — see :func:`pridepy.providers.transport._walk_ftp_tree`."""
        from pridepy.providers import transport
        return transport._walk_ftp_tree(ftp=ftp, remote_dir=remote_dir)

    @staticmethod
    def _open_ftp_connection(host: str, use_tls: bool, timeout: int = 30) -> FTP:
        """Shim — see :func:`pridepy.providers.transport._open_ftp_connection`."""
        from pridepy.providers import transport
        return transport._open_ftp_connection(host=host, use_tls=use_tls, timeout=timeout)

    @staticmethod
    def _list_ftp_repo_files(host, remote_root, error_label, use_tls=False):
        """Shim — see :func:`pridepy.providers.transport._list_ftp_repo_files`."""
        from pridepy.providers import transport
        return transport._list_ftp_repo_files(host=host, remote_root=remote_root, error_label=error_label, use_tls=use_tls)

    def _list_massive_public_files(self, accession: str) -> List[Dict]:
        """Shim — see :meth:`pridepy.providers.massive.MassiveProvider.list_files`."""
        from pridepy.providers.massive import MassiveProvider
        return MassiveProvider().list_files(accession)

    def _download_massive_file_records(
        self,
        accession: str,
        file_records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        parallel_files: int = 1,
    ) -> None:
        """
        Download public MassIVE files via anonymous FTP (now FTPS).
        Backward-compat shim — dispatches via the provider registry.
        """
        from pridepy.providers import registry
        registry.resolve(accession).download_files(
            accession=accession,
            records=file_records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
        )

    def _list_jpost_public_files(self, accession: str) -> List[Dict]:
        """
        Discover all public files for a JPOST dataset.

        Delegates to JpostProvider but routes via the shim methods so that
        test patches on ``_list_jpost_public_files_via_proxi`` and
        ``_list_ftp_repo_files`` continue to intercept.
        """
        from pridepy.providers.jpost import JpostProvider
        normalized_accession = accession.upper()
        try:
            return self._list_jpost_public_files_via_proxi(normalized_accession)
        except Exception as proxi_error:
            logging.warning(
                f"JPOST PROXI listing failed for {normalized_accession} "
                f"({proxi_error}); falling back to FTP tree walk."
            )
            remote_root = JpostProvider._get_public_root(normalized_accession)
            remote_files = self._list_ftp_repo_files(
                host=JpostProvider.ARCHIVE_FTP,
                remote_root=remote_root,
                error_label=f"JPOST dataset {normalized_accession}",
            )
            return [
                self._build_jpost_file_record(
                    normalized_accession,
                    JpostProvider._get_public_ftp_url(normalized_accession, remote_file),
                )
                for remote_file in remote_files
            ]

    def _list_jpost_public_files_via_proxi(self, accession: str) -> List[Dict]:
        """Shim — see :meth:`pridepy.providers.jpost.JpostProvider._list_via_proxi`."""
        from pridepy.providers.jpost import JpostProvider
        return JpostProvider()._list_via_proxi(accession)

    def _list_iprox_public_files(self, accession: str) -> List[Dict]:
        """Shim — see :meth:`pridepy.providers.iprox.IproxProvider.list_files`."""
        from pridepy.providers.iprox import IproxProvider
        return IproxProvider().list_files(accession)


    async def stream_all_files_metadata(self, output_file, accession=None):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.stream_all_files_metadata`."""
        from pridepy.providers.pride import PrideProvider
        return await PrideProvider().stream_all_files_metadata(output_file, accession)

    def stream_all_files_by_project(self, accession) -> List[Dict]:
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.stream_all_files_by_project`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider().stream_all_files_by_project(accession)

    def get_all_raw_file_list(self, project_accession):
        """Get raw file list for any registered provider.

        Returns the dataset's file records filtered to fileCategory == "RAW".
        """
        from pridepy.providers import registry
        provider = registry.resolve(project_accession)
        records = provider.list_files(project_accession)
        return [r for r in records if r["fileCategory"]["value"] == "RAW"]

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
        from pridepy.providers import registry
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

    @staticmethod
    def download_files_from_ftp(
        file_list_json,
        output_folder,
        skip_if_downloaded_already,
        max_connection_retries=3,
        max_download_retries=3,
    ):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.download_files_from_ftp`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider.download_files_from_ftp(
            file_list_json,
            output_folder,
            skip_if_downloaded_already,
            max_connection_retries=max_connection_retries,
            max_download_retries=max_download_retries,
        )

    @staticmethod
    def get_output_file_name(download_url, file, output_folder):
        public_filepath_part = download_url.rsplit("/", 1)
        accession = file.get("accession", "unknown-accession")
        logging.debug(accession + " -> " + public_filepath_part[1])
        new_file_path = os.path.join(output_folder, f"{public_filepath_part[1]}")
        return new_file_path

    @staticmethod
    def download_files_from_aspera(
        file_list_json: List[Dict],
        output_folder: str,
        skip_if_downloaded_already,
        maximum_bandwidth: str = "100M",
    ):
        """
        Download files using aspera transfer url
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        :param maximum_bandwidth: parameter in Aspera sets the maximum bandwidth for the transfer.
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        """
        ascp_path = Files.get_ascp_binary()
        key_full_path = importlib.resources.files("pridepy").joinpath(
            "aspera/key/asperaweb_id_dsa.openssh"
        )
        key_path = os.path.abspath(key_full_path)
        for file in file_list_json:
            if file["publicFileLocations"][0]["name"] == "Aspera Protocol":
                download_url = file["publicFileLocations"][0]["value"]
            else:
                download_url = file["publicFileLocations"][1]["value"]

            # Create a clean filename to save the downloaded file
            logging.debug(f"Downloading via Aspera: {download_url}")
            new_file_path = Files.get_output_file_name(download_url, file, output_folder)

            if skip_if_downloaded_already == True and os.path.exists(new_file_path):
                logging.info("Skipping download as file already exists")
                continue

            try:
                # Execute the ascp command using subprocess
                subprocess.run(
                    [
                        ascp_path,
                        "-QT",
                        "-P",
                        "33001",
                        "-l",
                        maximum_bandwidth,  # Options for Aspera: adjust as necessary
                        "-i",
                        key_path,
                        download_url,
                        new_file_path,  # Source and destination
                    ],
                    check=True,
                )
                logging.info(f"Successfully downloaded {new_file_path} via Aspera")
            except subprocess.CalledProcessError as e:
                logging.error(f"Aspera download failed for {new_file_path}: {str(e)}")

    @staticmethod
    def _download_range(url, file_path, start, end, pbar, max_retries=3):
        """Download a byte range directly into the target file using seek."""
        for attempt in range(1, max_retries + 1):
            try:
                session = Util.create_session_with_retries()
                headers = {"Range": f"bytes={start}-{end}"}
                with session.get(url, headers=headers, stream=True, timeout=(15, 15)) as r:
                    r.raise_for_status()
                    if r.status_code != 206:
                        raise RuntimeError(f"Server did not honor Range request: {r.status_code}")
                    content_range = r.headers.get("Content-Range", "")
                    if not content_range.lower().startswith(f"bytes {start}-{end}/"):
                        raise RuntimeError(f"Unexpected Content-Range header: {content_range}")
                    with open(file_path, "r+b") as f:
                        f.seek(start)
                        for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                return
            except (requests.RequestException, RuntimeError, OSError) as exc:
                logging.warning(
                    f"Range {start}-{end} attempt {attempt}/{max_retries} failed: {exc}"
                )
                if attempt >= max_retries:
                    raise
                time.sleep(2 * attempt)

    @staticmethod
    def _parallel_download(url, file_path, position=0):
        """Shim — see :func:`pridepy.providers.transport._parallel_download`."""
        from pridepy.providers import transport
        return transport._parallel_download(url=url, file_path=file_path, position=position)

    @staticmethod
    def _globus_download_one(file, output_folder, skip_if_downloaded_already, max_retries=6, position=0):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider._globus_download_one`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider._globus_download_one(
            file, output_folder, skip_if_downloaded_already,
            max_retries=max_retries, position=position,
        )

    @staticmethod
    def download_files_from_globus(
        file_list_json: List[Dict], output_folder, skip_if_downloaded_already,
        parallel_files: int = 1,
        checksum_map: Optional[Dict[str, str]] = None,
    ):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.download_files_from_globus`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider.download_files_from_globus(
            file_list_json, output_folder, skip_if_downloaded_already,
            parallel_files=parallel_files,
            checksum_map=checksum_map,
        )

    @staticmethod
    def download_files_from_s3(
        file_list_json: List[Dict], output_folder: str, skip_if_downloaded_already
    ):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.download_files_from_s3`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider.download_files_from_s3(
            file_list_json, output_folder, skip_if_downloaded_already,
        )

    def get_submitted_file_path_prefix(self, accession):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.get_submitted_file_path_prefix`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider().get_submitted_file_path_prefix(accession)

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
        """
        Download files from url
        :param accession: PRIDE accession
        :param file_name: file name to download
        :param output_folder: folder to download the files
        :param protocol: ftp, aspera, globus
        :param username: Username for private datasets
        :param password: Password for private datasets
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        :param aspera_maximum_bandwidth: Aspera maximum bandwidth
        :param checksum_check: Download checksum for a given project.
        """

        if not os.path.isdir(output_folder):
            os.mkdir(output_folder)

        from pridepy.providers import registry
        provider = registry.resolve(accession)

        ## Check type of project
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
            self.download_files(
                response,
                accession,
                output_folder,
                skip_if_downloaded_already,
                protocol,
                aspera_maximum_bandwidth=aspera_maximum_bandwidth,
                checksum_check=checksum_check,
            )
        elif not public_project and (username is not None and password is not None):
            logging.info("Downloading file from private dataset {}".format(accession))
            self.download_private_file_name(
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

    def get_file_from_api(self, accession, file_name) -> List[Dict]:
        """
        Fetches file from API
        :param accession: PRIDE accession
        :param file_name: file name
        :return: file in json format
        """
        from pridepy.providers import registry
        try:
            records = registry.resolve(accession).list_files(accession)
            return [r for r in records if r["fileName"] == file_name]
        except Exception as e:
            raise Exception("File not found " + str(e))

    def download_private_file_name(self, accession, file_name, output_folder, username, password):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.download_private_file_name`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider().download_private_file_name(
            accession, file_name, output_folder, username, password,
        )

    @staticmethod
    def get_ascp_binary():
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.get_ascp_binary`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider.get_ascp_binary()

    @staticmethod
    def save_checksum_file(accession, output_folder):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider.save_checksum_file`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider.save_checksum_file(accession, output_folder)

    @staticmethod
    def _batch_download_by_protocol(
        file_list: List[Dict],
        output_folder: str,
        protocol: str,
        skip_if_downloaded_already: bool,
        aspera_maximum_bandwidth: str,
        parallel_files: int = 1,
        checksum_map: Optional[Dict[str, str]] = None,
    ) -> None:
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider._batch_download_by_protocol`.

        Tests patch this method via ``patch.object(Files, "_batch_download_by_protocol")``;
        :class:`PrideProvider` calls back through ``Files.X`` so those patches
        keep intercepting.
        """
        from pridepy.providers.pride import PrideProvider
        return PrideProvider._batch_download_by_protocol(
            file_list,
            output_folder,
            protocol,
            skip_if_downloaded_already,
            aspera_maximum_bandwidth,
            parallel_files=parallel_files,
            checksum_map=checksum_map,
        )

    @staticmethod
    def _download_with_fallback(
        file_record: Dict,
        output_folder: str,
        protocol_sequence: List[str],
        expected_checksum: Optional[str],
        aspera_maximum_bandwidth: str,
        max_protocol_retries: int = 2,
        parallel_files: int = 1,
    ) -> bool:
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider._download_with_fallback`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider._download_with_fallback(
            file_record,
            output_folder,
            protocol_sequence,
            expected_checksum,
            aspera_maximum_bandwidth,
            max_protocol_retries=max_protocol_retries,
            parallel_files=parallel_files,
        )

    @staticmethod
    def download_files(
        file_list_json: List[Dict],
        accession,
        output_folder: str,
        skip_if_downloaded_already,
        protocol: str = "ftp",
        aspera_maximum_bandwidth: str = "100M",  # Aspera maximum bandwidth
        checksum_check=False,
        parallel_files: int = 1,
    ):
        """Shim — see :meth:`pridepy.providers.pride.PrideProvider._download_files_batch`."""
        from pridepy.providers.pride import PrideProvider
        return PrideProvider._download_files_batch(
            file_list_json,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol=protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
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
        """Download a subset of project files identified by a filename list.

        Resolves each requested filename via the project metadata API and
        delegates to :meth:`download_files` so the existing batch + protocol
        fallback engine is reused.

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

        from pridepy.providers import registry
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

    @staticmethod
    def _extract_pride_accession(url: str) -> Optional[str]:
        """Extract a PRIDE accession (PXD/PRD followed by digits) from a URL path.

        PRIDE archive URLs follow the pattern
        ``…/pride/data/archive/YYYY/MM/<ACCESSION>/filename``.
        Returns ``None`` when no accession can be identified.
        """
        match = re.search(r"((?:PXD|PRD)\d{4,})", url)
        return match.group(1) if match else None

    @staticmethod
    def download_files_by_url(
        urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool = False,
        protocol: str = "ftp",
        parallel_files: int = 1,
        checksum_check: bool = False,
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

        parallel_files = min(parallel_files, 3, len(urls))
        failures: List[Tuple[str, str]] = []
        if parallel_files < 2:
            for url in urls:
                try:
                    Files._download_single_url(
                        url, output_folder, skip_if_downloaded_already, protocol,
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logging.error("Failed to download %s: %s", url, exc)
                    failures.append((url, str(exc)))
        else:
            logging.info(
                "Downloading %d URL(s) with %d parallel workers",
                len(urls), parallel_files,
            )
            with ThreadPoolExecutor(max_workers=parallel_files) as executor:
                futures = {
                    executor.submit(
                        Files._download_single_url,
                        url, output_folder, skip_if_downloaded_already, protocol,
                        position=idx,
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
            Files._validate_urls_checksums(urls, output_folder)

    @staticmethod
    def _validate_urls_checksums(urls: List[str], output_folder: str) -> None:
        """Validate downloaded files against PRIDE checksum API.

        Accessions are inferred from URL paths via
        :meth:`_extract_pride_accession`.  URLs that do not contain a
        recognisable PRIDE accession are skipped with a warning.

        :raises RuntimeError: if one or more files fail validation
        """
        accession_urls: Dict[str, List[str]] = {}
        for url in urls:
            acc = Files._extract_pride_accession(url)
            if acc:
                accession_urls.setdefault(acc, []).append(url)
            else:
                logging.warning(
                    "Cannot infer PRIDE accession from URL, skipping checksum: %s", url
                )

        validation_failures: List[str] = []
        for acc, acc_urls in accession_urls.items():
            checksum_file_path = Files.save_checksum_file(acc, output_folder)
            checksum_map = Files.read_checksum_file(checksum_file_path)
            logging.info(
                "Loaded checksums for %d files (project %s)",
                len(checksum_map), acc,
            )
            for url in acc_urls:
                file_name = os.path.basename(urlparse(url).path)
                target = os.path.join(output_folder, file_name)
                expected = checksum_map.get(file_name)
                logging.info("Validating %s", file_name)
                valid, reason = Files.validate_download(target, expected)
                if not valid:
                    logging.error("Validation failed for %s: %s", file_name, reason)
                    validation_failures.append(f"{file_name} ({reason})")
                else:
                    logging.info("Checksum OK: %s", file_name)

        if validation_failures:
            raise RuntimeError(
                f"Checksum validation failed for {len(validation_failures)} file(s): "
                + ", ".join(validation_failures)
            )

    @staticmethod
    def _download_single_url(
        url: str,
        output_folder: str,
        skip_if_exists: bool = False,
        protocol: str = "ftp",
        position: int = 0,
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

        Files._dispatch_url_scheme(parsed, target, protocol, position=position)

        ok, reason = Files.validate_download(target)
        if not ok:
            Files._remove_if_exists(target)
            raise RuntimeError(f"Download invalid: {reason} ({target})")
        return target

    @staticmethod
    def _dispatch_url_scheme(parsed, target: str, protocol: str = "ftp", position: int = 0) -> None:
        """Route a parsed URL to its protocol-specific downloader.

        ``protocol='globus'`` swaps the http/https single-connection streamer
        for :meth:`_parallel_download` (single-connection with progress bar).
        ftp:// URLs are unaffected.
        """
        scheme = (parsed.scheme or "").lower()
        if scheme in ("http", "https"):
            if protocol == "globus":
                Files._parallel_download(parsed.geturl(), target, position=position)
            else:
                Files._http_download_url(parsed.geturl(), target)
        elif scheme == "ftp":
            Files._ftp_download_url(parsed, target)
        else:
            raise ValueError(f"Unsupported URL scheme: {scheme}")

    @staticmethod
    def _http_download_url(url: str, target: str) -> None:
        """Stream an http/https URL into ``target`` with a progress bar."""
        session = Util.create_session_with_retries()
        with session.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
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

    @staticmethod
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
        """
        Download all files of specified categories from a PRIDE project.

        :param accession: The PRIDE project accession identifier.
        :param output_folder: The directory where the files will be downloaded.
        :param skip_if_downloaded_already: If True, skips downloading files that already exist.
        :param protocol: The transfer protocol to use (e.g., ftp, aspera, globus, s3).
        :param aspera_maximum_bandwidth: Maximum bandwidth for Aspera transfers.
        :param checksum_check: If True, downloads the checksum file for the project.
        :param categories: List of file categories to download.
        :param category: Single file category (deprecated, use categories instead).
        """
        if categories is None:
            categories = [category] if category else ["RAW"]
        records = self.get_all_category_file_list(accession, categories)
        from pridepy.providers import registry
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

    def get_all_category_file_list(
        self, accession: str, categories: "str | List[str]"
    ) -> List[Dict]:
        """
        Retrieve a list of files from a specific project that belong to given categories.

        :param accession: The PRIDE project accession identifier.
        :param categories: A single category string or list of categories to filter by.
        :return: A list of files matching the specified categories.
        """
        if isinstance(categories, str):
            categories = [categories]
        category_set = {c.upper() for c in categories}
        from pridepy.providers import registry
        records = registry.resolve(accession).list_files(accession)
        return [r for r in records if r["fileCategory"]["value"] in category_set]

    # -------------------------------
    # ProteomeXchange support
    # -------------------------------

    @staticmethod
    def _normalize_px_xml_url(px_id_or_url: str) -> str:
        """
        Build the ProteomeXchange XML endpoint from a dataset accession or a dataset web URL.
        Examples accepted:
          - PXD039236
          - https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236
          - https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236&anything
        """
        if px_id_or_url.startswith("http://") or px_id_or_url.startswith("https://"):
            parsed = urlparse(px_id_or_url)
            # keep the ID param value if present; otherwise fallback to the path tail
            query = parsed.query or ""
            if "ID=" in query:
                id_value = [q.split("=", 1)[1] for q in query.split("&") if q.startswith("ID=")]
                if id_value:
                    return (
                        f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={id_value[0]}&outputMode=XML&test=no"
                    )
            # If the input URL already requests XML, just ensure flags
            if parsed.path.endswith("/cgi/GetDataset"):
                return (
                    f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?{query}&outputMode=XML&test=no"
                )
        # Assume it's a plain accession if not a URL
        return (
            f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={px_id_or_url}&outputMode=XML&test=no"
        )

    @staticmethod
    def _parse_px_xml_for_raw_file_urls(px_xml_url: str) -> List[str]:
        """
        Parse the PX XML and return a list of associated raw file URIs.
        We extract cvParam with name "Associated raw file URI" under each DatasetFile.
        """
        headers = {"Accept": "application/xml"}
        response = Util.get_api_call(px_xml_url, headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        urls: List[str] = []
        # The XML namespace is often absent in PX XML; access elements directly
        for dataset_file in root.iter("DatasetFile"):
            for cv in dataset_file.findall("cvParam"):
                name = cv.attrib.get("name")
                value = cv.attrib.get("value")
                if name == "Associated raw file URI" and value:
                    urls.append(value)
        return urls

    def download_px_raw_files(
        self,
        px_id_or_url: str,
        output_folder: str,
        skip_if_downloaded_already: bool = True,
    ) -> None:
        """
        Download all raw files referenced by a ProteomeXchange dataset.
        Prefer FTP when the URL is ftp://, otherwise use HTTP(S). Supports resume and skip.
        """
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        px_xml_url = self._normalize_px_xml_url(px_id_or_url)
        logging.info(f"Fetching PX XML: {px_xml_url}")
        urls = self._parse_px_xml_for_raw_file_urls(px_xml_url)
        if not urls:
            logging.info("No Associated raw file URIs found in PX XML")
            return

        ftp_urls = [u for u in urls if u.lower().startswith("ftp://")]
        http_urls = [u for u in urls if u.lower().startswith("http://") or u.lower().startswith("https://")]

        if ftp_urls:
            self.download_ftp_urls(ftp_urls, output_folder, skip_if_downloaded_already)
        if http_urls:
            self.download_http_urls(http_urls, output_folder, skip_if_downloaded_already)

    @staticmethod
    def _local_path_for_url(download_url: str, output_folder: str) -> str:
        """Shim — see :func:`pridepy.providers.transport._local_path_for_url`."""
        from pridepy.providers import transport
        return transport._local_path_for_url(download_url=download_url, output_folder=output_folder)

    @staticmethod
    def _download_one_ftp_path(
        ftp: FTP,
        ftp_path: str,
        local_path: str,
        skip_if_downloaded_already: bool,
        max_download_retries: int,
        position: int = 0,
    ) -> None:
        """Shim — see :func:`pridepy.providers.transport._download_one_ftp_path`."""
        from pridepy.providers import transport
        return transport._download_one_ftp_path(
            ftp=ftp,
            ftp_path=ftp_path,
            local_path=local_path,
            skip_if_downloaded_already=skip_if_downloaded_already,
            max_download_retries=max_download_retries,
            position=position,
        )

    @staticmethod
    def _download_ftp_paths_serial(
        host: str,
        paths: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        use_tls: bool,
        max_connection_retries: int,
        max_download_retries: int,
    ) -> None:
        """Shim — see :func:`pridepy.providers.transport._download_ftp_paths_serial`."""
        from pridepy.providers import transport
        return transport._download_ftp_paths_serial(
            host=host,
            paths=paths,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            use_tls=use_tls,
            max_connection_retries=max_connection_retries,
            max_download_retries=max_download_retries,
        )

    @staticmethod
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
        """Shim — see :func:`pridepy.providers.transport._download_ftp_paths_parallel`."""
        from pridepy.providers import transport
        return transport._download_ftp_paths_parallel(
            host=host,
            paths=paths,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            use_tls=use_tls,
            max_connection_retries=max_connection_retries,
            max_download_retries=max_download_retries,
            parallel_files=parallel_files,
        )

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
        from pridepy.providers import transport
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
    def _http_download_one(
        url: str,
        output_folder: str,
        skip_if_downloaded_already: bool,
        max_retries: int = 3,
        position: int = 0,
    ) -> None:
        """Shim — see :func:`pridepy.providers.transport._http_download_one`."""
        from pridepy.providers import transport
        return transport._http_download_one(
            url=url,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            max_retries=max_retries,
            position=position,
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
        from pridepy.providers import transport
        return transport.download_http_urls(
            http_urls=http_urls,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            parallel_files=parallel_files,
            max_retries=max_retries,
        )
