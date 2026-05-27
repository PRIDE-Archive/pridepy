#!/usr/bin/env python
import ftplib
import hashlib
import importlib.resources
import logging
import os
import platform
import posixpath
import re
import subprocess
import urllib
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from ftplib import FTP
from typing import Dict, List, Optional, Tuple
import socket
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import boto3
import botocore
import requests
from botocore.config import Config
from tqdm import tqdm

from pridepy.authentication.authentication import Authentication
from pridepy.util.api_handling import Util


# Re-export from providers.util so external `from pridepy.files.files import Progress`
# still works.
from pridepy.providers.util import Progress  # noqa: F401


class Files:
    """
    This class handles PRIDE API files endpoint.
    """

    V3_API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v3"
    API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v3"
    API_PRIVATE_URL = "https://www.ebi.ac.uk/pride/private/ws/archive/v2"
    PRIDE_ARCHIVE_FTP = "ftp.pride.ebi.ac.uk"
    PRIDE_ARCHIVE_FTP_URL_PREFIX = "ftp://ftp.pride.ebi.ac.uk/"
    PRIDE_ARCHIVE_HTTPS_URL_PREFIX = "https://ftp.pride.ebi.ac.uk/"
    MASSIVE_ARCHIVE_FTP = "massive-ftp.ucsd.edu"
    MASSIVE_ARCHIVE_FTP_URL_PREFIX = "ftp://massive-ftp.ucsd.edu/v01/"
    JPOST_ARCHIVE_FTP = "ftp.jpostdb.org"
    JPOST_ARCHIVE_FTP_URL_PREFIX = "ftp://ftp.jpostdb.org/"
    JPOST_PROXI_BASE_URL = "https://repository.jpostdb.org/proxi/datasets/"
    JPOST_PROXI_CATEGORY_MAP = {
        "Associated raw file URI": "RAW",
        "Result file URI": "RESULT",
        "Search engine output file URI": "SEARCH",
        "Peak list file URI": "PEAK",
        "Spectrum library file URI": "SPECTRUM_LIBRARY",
        "Sequence database URI": "FASTA",
        "Quantification file URI": "RESULT",
    }
    IPROX_DOWNLOAD_BASE_URL = "http://download.iprox.org/"
    IPROX_PX_XML_URL_TEMPLATE = (
        "http://download.iprox.org/{accession}/PX_{accession}.xml"
    )
    # iProX PX XML uses the same PSI-MS cvParam "name" values as JPOST, so the
    # JPOST PROXI category map applies. PX XML cvParam "Associated raw file URI"
    # is the canonical raw-file label per the PSI-MS CV (MS:1002846).
    IPROX_PX_CATEGORY_MAP = JPOST_PROXI_CATEGORY_MAP
    S3_URL = "https://hh.fire.sdo.ebi.ac.uk"
    S3_BUCKET = "pride-public"
    PROTOCOL_ORDER = ["aspera", "s3", "ftp", "globus"]
    MASSIVE_CATEGORY_MAP = {
        "raw": "RAW",
        "peak": "PEAK",
        "ccms_peak": "PEAK",
        "search": "SEARCH",
        "result": "RESULT",
        "ccms_result": "RESULT",
        "quant": "RESULT",
        "fasta": "FASTA",
        "spectrum_library": "SPECTRUM_LIBRARY",
        "library": "SPECTRUM_LIBRARY",
    }
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
        """
        Build the ordered list of protocols to try for a requested download mode.
        """
        if protocol not in Files.PROTOCOL_ORDER:
            return []
        return [protocol] + [p for p in Files.PROTOCOL_ORDER if p != protocol]

    @staticmethod
    def is_massive_accession(accession: str) -> bool:
        """
        Return True when the accession looks like a MassIVE dataset accession.
        """
        if not accession:
            return False
        return bool(re.fullmatch(r"R?MSV\d{9}", accession.upper()))

    @staticmethod
    def _get_massive_public_root(accession: str) -> str:
        normalized_accession = accession.upper()
        return f"/v01/{normalized_accession}"

    @staticmethod
    def _get_massive_public_ftp_url(accession: str, remote_path: str) -> str:
        root_path = Files._get_massive_public_root(accession).rstrip("/")
        relative_path = remote_path
        if remote_path.startswith(root_path):
            relative_path = remote_path[len(root_path) :].lstrip("/")
        return f"{Files.MASSIVE_ARCHIVE_FTP_URL_PREFIX}{accession.upper()}/{relative_path}"

    @staticmethod
    def _map_massive_collection_to_category(collection: str) -> str:
        return Files.MASSIVE_CATEGORY_MAP.get(collection.lower(), "OTHER")

    @staticmethod
    def _build_massive_file_record(accession: str, ftp_url: str) -> Dict:
        parsed = urlparse(ftp_url)
        root_prefix = f"/v01/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix) :]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": Files._map_massive_collection_to_category(collection)},
            "publicFileLocations": [{"name": "FTP Protocol", "value": ftp_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "MassIVE",
        }

    @staticmethod
    def is_jpost_accession(accession: str) -> bool:
        """
        Return True when the accession looks like a JPOST dataset accession.
        """
        if not accession:
            return False
        return bool(re.fullmatch(r"JPST\d{6}", accession.upper()))

    @staticmethod
    def _get_jpost_public_root(accession: str) -> str:
        return f"/{accession.upper()}"

    @staticmethod
    def _get_jpost_public_ftp_url(accession: str, remote_path: str) -> str:
        root_path = Files._get_jpost_public_root(accession).rstrip("/")
        relative_path = remote_path
        if remote_path.startswith(root_path):
            relative_path = remote_path[len(root_path) :].lstrip("/")
        return f"{Files.JPOST_ARCHIVE_FTP_URL_PREFIX}{accession.upper()}/{relative_path}"

    @staticmethod
    def _build_jpost_file_record(
        accession: str, ftp_url: str, category_from_proxi: Optional[str] = None
    ) -> Dict:
        """
        Build a pridepy file record for a JPOST file.

        When ``category_from_proxi`` is provided (e.g. ``"Associated raw file URI"``),
        the PROXI CV name takes precedence over the heuristic collection-from-path
        mapping. Falls back to the same path-segment heuristic used for MassIVE
        when the category isn't known.
        """
        parsed = urlparse(ftp_url)
        root_prefix = f"/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix) :]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        if category_from_proxi and category_from_proxi in Files.JPOST_PROXI_CATEGORY_MAP:
            category = Files.JPOST_PROXI_CATEGORY_MAP[category_from_proxi]
        else:
            category = Files._map_massive_collection_to_category(collection)
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": category},
            "publicFileLocations": [{"name": "FTP Protocol", "value": ftp_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "JPOST",
        }

    @staticmethod
    def _build_iprox_file_record(
        accession: str, https_url: str, category_from_px: Optional[str] = None
    ) -> Dict:
        """
        Build a pridepy file record for an iProX file. iProX exposes files
        over anonymous HTTPS at
        ``http://download.iprox.org/<accession>/<sub-accession>/<filename>``;
        ``category_from_px`` is the ``cvParam`` ``name`` from the dataset's
        ProteomeXchange XML (e.g. ``"Associated raw file URI"``).
        """
        parsed = urlparse(https_url)
        root_prefix = f"/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix) :]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        if category_from_px and category_from_px in Files.IPROX_PX_CATEGORY_MAP:
            category = Files.IPROX_PX_CATEGORY_MAP[category_from_px]
        else:
            category = Files._map_massive_collection_to_category(collection)
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": category},
            # ``FTP Protocol`` is the existing label the download dispatcher
            # uses to locate a file URL; here it actually points at HTTPS.
            # ``_download_direct_download_records`` routes by URL scheme.
            "publicFileLocations": [{"name": "FTP Protocol", "value": https_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "iProX",
        }

    @staticmethod
    def is_direct_download_accession(accession: str) -> bool:
        """
        Return True when the accession is served by a public repository that
        pridepy supports via direct downloads (no ProteomeXchange API).
        MassIVE and JPOST use FTP(S); iProX uses anonymous HTTPS via
        ``download.iprox.org``.
        """
        return (
            Files.is_massive_accession(accession)
            or Files.is_jpost_accession(accession)
            or Files.is_iprox_accession(accession)
        )

    @staticmethod
    def is_iprox_accession(accession: str) -> bool:
        """
        Return True when the accession looks like an iProX dataset accession
        (``IPX`` followed by 7-10 digits). iProX exposes the dataset
        ProteomeXchange XML at
        ``http://download.iprox.org/<accession>/PX_<accession>.xml`` and the
        referenced files are downloadable from ``download.iprox.org`` over
        anonymous HTTPS with byte-range support.
        """
        if not accession:
            return False
        return bool(re.fullmatch(r"IPX\d{7,10}", accession.upper()))

    @staticmethod
    def _repo_uses_tls(accession: str) -> bool:
        """
        Whether the public FTP server for ``accession`` requires FTP over TLS.
        MassIVE rejects plain anonymous FTP (``421 TLS is required``); JPOST
        accepts plain FTP.
        """
        return Files.is_massive_accession(accession)

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
        """
        Discover all public files for a MassIVE dataset from its anonymous FTP tree.
        """
        normalized_accession = accession.upper()
        remote_root = self._get_massive_public_root(normalized_accession)
        remote_files = self._list_ftp_repo_files(
            host=self.MASSIVE_ARCHIVE_FTP,
            remote_root=remote_root,
            error_label=f"MassIVE dataset {normalized_accession}",
            use_tls=True,
        )
        return [
            self._build_massive_file_record(
                normalized_accession,
                self._get_massive_public_ftp_url(normalized_accession, remote_file),
            )
            for remote_file in remote_files
        ]

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
        Backward-compat wrapper around :meth:`_download_direct_download_records`.
        """
        self._download_direct_download_records(
            accession=accession,
            file_records=file_records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            parallel_files=parallel_files,
        )

    def _list_jpost_public_files(self, accession: str) -> List[Dict]:
        """
        Discover all public files for a JPOST dataset.

        Prefers the JPOST PROXI JSON endpoint at
        ``https://repository.jpostdb.org/proxi/datasets/<acc>`` since it
        returns file URLs with category labels and avoids the anonymous-FTP
        rate limit that ``ftp.jpostdb.org`` applies per source IP. Falls back
        to walking the FTP tree if PROXI is unreachable or returns no files.
        """
        normalized_accession = accession.upper()
        try:
            return self._list_jpost_public_files_via_proxi(normalized_accession)
        except Exception as proxi_error:
            logging.warning(
                f"JPOST PROXI listing failed for {normalized_accession} "
                f"({proxi_error}); falling back to FTP tree walk."
            )
            remote_root = self._get_jpost_public_root(normalized_accession)
            remote_files = self._list_ftp_repo_files(
                host=self.JPOST_ARCHIVE_FTP,
                remote_root=remote_root,
                error_label=f"JPOST dataset {normalized_accession}",
            )
            return [
                self._build_jpost_file_record(
                    normalized_accession,
                    self._get_jpost_public_ftp_url(normalized_accession, remote_file),
                )
                for remote_file in remote_files
            ]

    def _list_jpost_public_files_via_proxi(self, accession: str) -> List[Dict]:
        """
        Fetch the JPOST PROXI dataset metadata and turn each ``datasetFiles``
        entry into a pridepy file record. The PROXI ``name`` field is mapped to
        a PRIDE-style category so existing RAW/SEARCH/RESULT filtering works.
        """
        import json as _json

        proxi_url = f"{self.JPOST_PROXI_BASE_URL}{accession}"
        logging.info(f"Fetching JPOST PROXI metadata: {proxi_url}")
        response = requests.get(
            proxi_url,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = _json.loads(response.content)
        dataset_files = data.get("datasetFiles") or []
        records: List[Dict] = []
        for entry in dataset_files:
            value = (entry or {}).get("value")
            if not value or not value.startswith("ftp://"):
                continue
            records.append(
                self._build_jpost_file_record(
                    accession,
                    value,
                    category_from_proxi=(entry or {}).get("name"),
                )
            )
        if not records:
            raise RuntimeError(
                f"JPOST PROXI returned no FTP file URIs for {accession}"
            )
        return records

    def _list_iprox_public_files(self, accession: str) -> List[Dict]:
        """
        Discover all public files for an iProX dataset.

        iProX publishes the ProteomeXchange XML for every public dataset at a
        deterministic path on its anonymous HTTPS download server::

            http://download.iprox.org/<accession>/PX_<accession>.xml

        We fetch that XML, walk every ``<DatasetFile>``'s ``cvParam`` entries,
        and turn each ``Associated raw file URI`` (and sibling URIs for
        search-engine output, result files, etc.) into a pridepy file record.
        File downloads themselves go through plain HTTPS on the same host,
        which supports ``Range`` requests for resume.
        """
        normalized_accession = accession.upper()
        xml_url = self.IPROX_PX_XML_URL_TEMPLATE.format(accession=normalized_accession)
        logging.info(f"Fetching iProX PX XML: {xml_url}")
        response = requests.get(xml_url, timeout=30)
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as parse_error:
            raise RuntimeError(
                f"Unable to parse iProX PX XML for {normalized_accession}: {parse_error}"
            ) from parse_error

        records: List[Dict] = []
        for dataset_file in root.iter("DatasetFile"):
            for cv in dataset_file.findall("cvParam"):
                name = cv.attrib.get("name")
                value = cv.attrib.get("value")
                if not value or not name or not name.endswith("URI"):
                    continue
                if not value.lower().startswith(("http://", "https://")):
                    continue
                records.append(
                    self._build_iprox_file_record(
                        normalized_accession,
                        value,
                        category_from_px=name,
                    )
                )
        if not records:
            raise RuntimeError(
                f"iProX PX XML for {normalized_accession} contained no downloadable HTTPS URIs"
            )
        return records

    def _list_direct_download_files(self, accession: str) -> List[Dict]:
        """
        Dispatch to the right listing transport for a direct-download
        repository: MassIVE walks FTPS, JPOST uses PROXI JSON over HTTPS with
        an FTP fallback, iProX uses the dataset's PX XML over HTTPS.
        """
        if self.is_massive_accession(accession):
            return self._list_massive_public_files(accession)
        if self.is_jpost_accession(accession):
            return self._list_jpost_public_files(accession)
        if self.is_iprox_accession(accession):
            return self._list_iprox_public_files(accession)
        raise ValueError(
            f"Accession {accession} is not a direct-download repository accession"
        )

    def _download_direct_download_records(
        self,
        accession: str,
        file_records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool,
        protocol: str,
        parallel_files: int = 1,
    ) -> None:
        """
        Download files from a direct-download repository.

        MassIVE and JPOST use anonymous FTP(S) with REST-based resume and
        per-host parallel workers. iProX uses anonymous HTTPS via
        ``download.iprox.org`` with ``Range``-based resume and per-file
        parallel workers. URLs are partitioned by scheme so a mixed batch
        (e.g. a JPOST PX XML that ever pointed at HTTPS) routes correctly.
        """
        if protocol not in ("ftp", "https", "http"):
            logging.warning(
                "Direct downloads currently use ftp / https only. "
                f"Ignoring requested protocol '{protocol}' for {accession}."
            )

        all_urls = [self._get_download_url(record, "ftp") for record in file_records]
        ftp_urls = [u for u in all_urls if u.lower().startswith("ftp://")]
        http_urls = [u for u in all_urls if u.lower().startswith(("http://", "https://"))]
        if not ftp_urls and not http_urls:
            logging.info(f"No files matched for direct-download dataset {accession}")
            return

        if ftp_urls:
            self.download_ftp_urls(
                ftp_urls=ftp_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                use_tls=self._repo_uses_tls(accession),
                parallel_files=parallel_files,
            )
        if http_urls:
            self.download_http_urls(
                http_urls=http_urls,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
            )

    async def stream_all_files_metadata(self, output_file, accession=None):
        """
        get stream all project files from PRIDE API in JSON format
        """
        if accession is None:
            request_url = f"{self.V3_API_BASE_URL}/files/all"
            count_request_url = f"{self.V3_API_BASE_URL}/files/count"
        else:
            request_url = f"{self.V3_API_BASE_URL}/projects/{accession}/files/all"
            count_request_url = f"{self.V3_API_BASE_URL}/projects/{accession}/files/count"
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(count_request_url, headers)
        total_records = response.json()

        regex_search_pattern = '"fileName"'
        await Util.stream_response_to_file(
            output_file, total_records, regex_search_pattern, request_url, headers
        )

    def stream_all_files_by_project(self, accession) -> List[Dict]:
        """
        get stream all project files from PRIDE API in JSON format
        """
        request_url = f"{self.V3_API_BASE_URL}/projects/{accession}/files/all"
        headers = {"Accept": "application/JSON"}
        record_files = Util.read_json_stream(api_url=request_url, headers=headers)
        return record_files

    def get_all_raw_file_list(self, project_accession):
        """
        Get all raw file lists from PRIDE API for a given project_accession
        :param project_accession: PRIDE accession
        :return: raw file list in JSON format
        """
        if self.is_direct_download_accession(project_accession):
            record_files = self._list_direct_download_files(project_accession)
            return [
                file for file in record_files if file["fileCategory"]["value"] == "RAW"
            ]

        record_files = self.stream_all_files_by_project(project_accession)

        # Filter projects by fileCategory = RAW
        raw_files = [file for file in record_files if file["fileCategory"]["value"] == "RAW"]
        return raw_files

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
        """
        This method will download all the raw files from PRIDE PROJECT
        :param output_folder: output directory where raw files will get saved
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        :param accession: PRIDE accession
        :param protocol: ftp, aspera, globus
        :param aspera_maximum_bandwidth: Aspera maximum bandwidth
        :param checksum_check: Download checksum for a given project.
        :return: None
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        raw_files = self.get_all_raw_file_list(accession)

        if self.is_direct_download_accession(accession):
            self._download_direct_download_records(
                accession=accession,
                file_records=raw_files,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
                parallel_files=parallel_files,
            )
            return

        self.download_files(
            raw_files,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
        )

    @staticmethod
    def download_files_from_ftp(
        file_list_json,
        output_folder,
        skip_if_downloaded_already,
        max_connection_retries=3,
        max_download_retries=3,
    ):
        """
        Download files using a single FTP connection with a retry mechanism and a progress bar for each file.
        :param file_list_json: file list in JSON format
        :param output_folder: folder to download the files
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        :param max_connection_retries: Number of attempts to reconnect to the FTP server if the connection is lost.
        :param max_download_retries: Number of attempts to retry the download of a file in case of failure.
        """

        if not os.path.isdir(output_folder):
            os.makedirs(output_folder)

        def connect_ftp():
            """Helper function to establish FTP connection."""
            ftp = FTP(Files.PRIDE_ARCHIVE_FTP, timeout=30)
            ftp.login()  # Anonymous login
            ftp.set_pasv(True)  # Enable passive mode
            logging.info(f"Connected to FTP host: {Files.PRIDE_ARCHIVE_FTP}")
            return ftp

        connection_attempt = 0
        while connection_attempt < max_connection_retries:
            try:
                ftp = connect_ftp()
                for file in file_list_json:
                    try:
                        # Get FTP download URL
                        if file["publicFileLocations"][0]["name"] == "FTP Protocol":
                            download_url = file["publicFileLocations"][0]["value"]
                        else:
                            download_url = file["publicFileLocations"][1]["value"]

                        logging.debug("ftp_filepath:" + download_url)

                        # Get output file path
                        new_file_path = Files.get_output_file_name(
                            download_url, file, output_folder
                        )

                        if skip_if_downloaded_already and os.path.exists(new_file_path):
                            logging.info("Skipping download as file already exists")
                            continue

                        # Extract file path from the download URL
                        parsed_url = urlparse(download_url)
                        ftp_file_path = urllib.parse.unquote(parsed_url.path.lstrip("/"))

                        logging.info(f"Starting FTP download: {ftp_file_path}")

                        # Retry download in case of failure
                        download_attempt = 0
                        while download_attempt < max_download_retries:
                            try:
                                # Get file size for progress tracking
                                total_size = ftp.size(ftp_file_path)
                                logging.info(f"File size: {total_size} bytes")

                                # Initialize progress bar
                                with open(new_file_path, "wb") as f:
                                    with tqdm(
                                        total=total_size,
                                        unit="B",
                                        unit_scale=True,
                                        desc=new_file_path,
                                    ) as pbar:

                                        def callback(data):
                                            f.write(data)
                                            pbar.update(len(data))

                                        # Retrieve the file with progress callback
                                        ftp.retrbinary(f"RETR {ftp_file_path}", callback)

                                logging.info(f"Successfully downloaded {new_file_path}")
                                break  # Exit download retry loop if successful
                            except (
                                socket.timeout,
                                ftplib.error_temp,
                                ftplib.error_perm,
                            ) as e:
                                download_attempt += 1
                                logging.error(
                                    f"Download failed for {new_file_path} (attempt {download_attempt}): {str(e)}"
                                )
                                if download_attempt >= max_download_retries:
                                    logging.error(
                                        f"Giving up on {new_file_path} after {max_download_retries} attempts."
                                    )
                                    break  # Give up on this file after max retries
                    except (KeyError, IndexError) as e:
                        logging.error(f"Failed to process file due to missing data: {str(e)}")
                    except Exception as e:
                        logging.error(f"Unexpected error while processing file: {str(e)}")
                ftp.quit()  # Close FTP connection after all files are downloaded
                logging.info(f"Disconnected from FTP host: {Files.PRIDE_ARCHIVE_FTP}")
                break  # Exit connection retry loop if everything was successful
            except (
                socket.timeout,
                ftplib.error_temp,
                ftplib.error_perm,
                socket.error,
            ) as e:
                connection_attempt += 1
                logging.error(f"FTP connection failed (attempt {connection_attempt}): {str(e)}")
                if connection_attempt < max_connection_retries:
                    logging.info("Retrying connection...")
                    time.sleep(5)  # Optional delay before retrying
                else:
                    logging.error(
                        f"Giving up after {max_connection_retries} failed connection attempts."
                    )
                    break

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
        """Download a single file via globus; used as a worker target."""
        download_url = Files._get_download_url(file, "globus")
        new_file_path = Files.get_output_file_name(download_url, file, output_folder)

        if skip_if_downloaded_already and os.path.exists(new_file_path):
            logging.info(f"Skipping download as file already exists: {new_file_path}")
            return

        for attempt in range(1, max_retries + 1):
            try:
                Files._parallel_download(download_url, new_file_path, position=position)
                return
            except Exception as e:
                logging.warning(f"Attempt {attempt}/{max_retries} failed for {file.get('fileName', '?')}: {e}")
                if attempt == max_retries:
                    raise

    @staticmethod
    def download_files_from_globus(
        file_list_json: List[Dict], output_folder, skip_if_downloaded_already,
        parallel_files: int = 1,
        checksum_map: Optional[Dict[str, str]] = None,
    ):
        """
        Download files using globus transfer url with progress bar for each file.
        When skip_if_downloaded_already is True, files are pre-filtered so that
        only missing or incomplete files are submitted to the worker pool,
        ensuring the -w parallel_files parameter is fully utilised.
        When checksum_map is provided, existing files are validated against
        their expected checksum; corrupted files are re-downloaded.
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        :param parallel_files: number of files to download simultaneously
        :param checksum_map: mapping of file name to expected MD5 checksum
        """
        if checksum_map is None:
            checksum_map = {}

        if not (os.path.isdir(output_folder)):
            os.makedirs(output_folder, exist_ok=True)

        # --- Phase 0: pre-filter files that need downloading -----------------
        files_to_download: List[Dict] = []
        for file in file_list_json:
            download_url = Files._get_download_url(file, "globus")
            new_file_path = Files.get_output_file_name(download_url, file, output_folder)
            if skip_if_downloaded_already and os.path.exists(new_file_path):
                expected_cs = checksum_map.get(file.get("fileName", ""))
                if expected_cs:
                    valid, reason = Files.validate_download(new_file_path, expected_cs)
                    if not valid:
                        logging.warning(f"Corrupted file detected ({reason}), will re-download: {new_file_path}")
                        files_to_download.append(file)
                        continue
                logging.info(f"Skipping download as file already exists: {new_file_path}")
                continue
            files_to_download.append(file)

        if not files_to_download:
            logging.info("All files already downloaded, nothing to do.")
            return

        logging.info(
            f"{len(file_list_json) - len(files_to_download)} file(s) skipped, "
            f"{len(files_to_download)} file(s) to download"
        )

        # --- Phase 1: download (skip check already done, pass False) ---------
        parallel_files = min(parallel_files, 3, len(files_to_download))
        if parallel_files < 2:
            for file in files_to_download:
                try:
                    Files._globus_download_one(
                        file, output_folder, False
                    )
                    new_file_path = Files.get_output_file_name(
                        Files._get_download_url(file, "globus"), file, output_folder
                    )
                    logging.info(f"Successfully downloaded {new_file_path}")
                except Exception as e:
                    logging.error(f"Download from Globus failed: {str(e)}")
        else:
            logging.info(f"Downloading {len(files_to_download)} file(s) with {parallel_files} parallel workers")
            with ThreadPoolExecutor(max_workers=parallel_files) as executor:
                futures = {
                    executor.submit(
                        Files._globus_download_one,
                        file, output_folder, False,
                        position=idx,
                    ): file
                    for idx, file in enumerate(files_to_download)
                }
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Download from Globus failed: {str(e)}")

    @staticmethod
    def download_files_from_s3(
        file_list_json: List[Dict], output_folder: str, skip_if_downloaded_already
    ):
        """
        Download files using S3 transfer URL with a progress bar and retry logic.
        :param file_list_json: file list in JSON format
        :param output_folder: folder to download the files
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        """

        if not os.path.isdir(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        # Retry and timeout config
        retry_config = Config(
            retries={"max_attempts": 5, "mode": "standard"},
            connect_timeout=120,  # Increase timeout to 120 seconds
            read_timeout=120,  # Timeout for reading data
            signature_version=botocore.UNSIGNED,  # Unsigned requests for public data
        )

        s3_resource = boto3.resource(
            "s3",
            config=retry_config,
            endpoint_url=Files.S3_URL,
        )
        bucket = s3_resource.Bucket(Files.S3_BUCKET)

        for file in file_list_json:
            try:
                # Determine S3 or FTP path
                download_url = (
                    file["publicFileLocations"][0]["value"]
                    if file["publicFileLocations"][0]["name"] == "FTP Protocol"
                    else file["publicFileLocations"][1]["value"]
                )

                ftp_base_url = "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/"
                s3_path = download_url.replace(ftp_base_url, "")
                new_file_path = Files.get_output_file_name(download_url, file, output_folder)

                if skip_if_downloaded_already == True and os.path.exists(new_file_path):
                    logging.info("Skipping download as file already exists")
                    continue

                logging.debug(f"Downloading From S3: {s3_path}")

                # Get file size for progress tracking
                obj = bucket.Object(s3_path)
                total_size = obj.content_length

                # Initialize progress bar
                progress = Progress(total_size, new_file_path)

                # Download with progress bar and retry handling
                for attempt in range(5):
                    try:
                        bucket.download_file(s3_path, new_file_path, Callback=progress)
                        progress.close()
                        logging.info(f"Successfully downloaded {new_file_path}")
                        break
                    except botocore.exceptions.ClientError as e:
                        if e.response["Error"]["Code"] == "404":
                            logging.error("The object does not exist.")
                            break
                        else:
                            logging.error(f"Download failed: {e}")
                            if attempt < 4:
                                time.sleep(2**attempt)  # Exponential backoff
                                logging.info(f"Retrying... ({attempt + 1}/5)")
                            else:
                                raise
            except Exception as e:
                logging.error(f"Failed to download {file['fileName']}: {e}")

    def get_submitted_file_path_prefix(self, accession):
        """
        At pride repository, public data is disseminated according to a proper structure.
        I.e. base/path/ + yyyy/mm/accession/ + submitted/
        This extracts the yyyy/mm/accession path fragment from the API by examine the file path
        of a public file.
        I.e. ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2018/10/PXD008644/7550GI_Y.raw
        :param accession: PRIDE accession
        :return: path fragment (eg: 2018/10/PXD008644)
        """
        results = self.get_all_raw_file_list(accession)
        first_file = results[0]["publicFileLocations"][0]["value"]
        path_fragment = re.search(r"\d{4}/\d{2}/PXD\d*", first_file).group()
        return path_fragment

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

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        ## Check type of project
        if self.is_direct_download_accession(accession):
            logging.info(
                "Downloading file from public direct-download dataset {}".format(accession)
            )
            response = self.get_file_from_api(accession, file_name)
            if not response:
                raise Exception(
                    "File name {} not found in dataset {}".format(file_name, accession)
                )
            self._download_direct_download_records(
                accession=accession,
                file_records=response,
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

        try:
            if self.is_direct_download_accession(accession):
                files = self._list_direct_download_files(accession)
                return [f for f in files if f["fileName"] == file_name]
            files = self.stream_all_files_by_project(accession)
            file = [f for f in files if f["fileName"] == file_name]
            return file
        except Exception as e:
            raise Exception("File not found " + str(e))

    def download_private_file_name(self, accession, file_name, output_folder, username, password):
        """
        Get the information for a given private file to be downloaded from the api.
        :param accession: Project accession
        :param file_name: The file name to be downloaded
        :param username: Username with access to the dataset
        :param password: Password for user with access to the dataset
        """

        auth = Authentication()
        auth_token = auth.get_token(username, password)
        validate_token = auth.validate_token(auth_token)
        logging.info("Valid token after login: {}".format(validate_token))

        url = self.API_PRIVATE_URL + "/projects/{}/files?search={}".format(accession, file_name)
        content = requests.get(url, headers={"Authorization": "Bearer {}".format(auth_token)})
        if content.ok and content.status_code == 200:
            json_file = content.json()
            if (
                "_embedded" in json_file
                and "files" in json_file["_embedded"]
                and len(json_file["_embedded"]["files"]) == 1
            ):
                download_url = json_file["_embedded"]["files"][0]["_links"]["download"]["href"]
                logging.info(download_url)

                # Create a clean filename to save the downloaded file
                new_file_path = os.path.join(output_folder, f"{file_name}")

                session = Util.create_session_with_retries()  # Create session with retries
                # Check if the file already exists
                if os.path.exists(new_file_path):
                    resume_header = {"Range": f"bytes={os.path.getsize(new_file_path)}-"}
                    mode = "ab"  # Append to file
                    resume_size = os.path.getsize(new_file_path)
                else:
                    resume_header = {}
                    mode = "wb"  # Write new file
                    resume_size = 0

                with session.get(
                    download_url, stream=True, headers=resume_header, timeout=(10, 60)
                ) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0)) + resume_size
                    block_size = 1024 * 1024  # 1 MB chunks

                    with tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        desc=new_file_path,
                        initial=resume_size,
                    ) as pbar:
                        with open(new_file_path, mode) as f:
                            for chunk in r.iter_content(chunk_size=block_size):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))

                logging.info(f"Successfully downloaded {new_file_path}")

            else:
                logging.info(
                    "File name {} found more than once for the given project {}".format(
                        file_name, accession
                    )
                )
        else:
            logging.info(
                f"File name {file_name} now found in the project {accession}, or user don't have access"
            )
            raise Exception(
                f"File name {file_name} now found in the project {accession}, or user don't have access"
            )

    @staticmethod
    def get_ascp_binary():
        """
        Detect the OS and architecture, and return the appropriate ascp binary path.

        Returns:
            str: Path to the correct ascp binary.
        """
        os_type = platform.system().lower()
        arch, _ = platform.architecture()
        aspera_dir = importlib.resources.files("pridepy").joinpath("aspera/")

        if os_type == "linux":
            if arch == "32bit":
                return os.path.join(aspera_dir, "linux-32", "ascp")
            elif arch == "64bit":
                return os.path.join(aspera_dir, "linux-64", "ascp")
        elif os_type == "darwin":  # macOS (intel-based)
            return os.path.join(aspera_dir, "mac-intel", "ascp")
        elif os_type == "windows":
            if arch == "32bit":
                return os.path.join(aspera_dir, "windows-32", "ascp.exe")
            elif arch == "64bit":
                return os.path.join(aspera_dir, "windows-64", "ascp.exe")
        else:
            raise OSError(f"Unsupported OS or architecture: {os_type}, {arch}")

    @staticmethod
    def save_checksum_file(accession, output_folder):
        """
        Download and persist the checksum manifest for a PRIDE accession.
        """
        os.makedirs(output_folder, exist_ok=True)
        url = f"{Files.V3_API_BASE_URL}/files/checksum/{accession}"
        headers = {"accept": "text/plain"}
        request = urllib.request.Request(url, headers=headers, method="GET")
        logging.info(f"Fetching checksum file from {url}")
        with urllib.request.urlopen(request) as response:
            data = response.read().decode("utf-8")
            # Save the data to a .tsv file
            output_path = os.path.join(output_folder, f"{accession}-checksum.tsv")
            with open(output_path, "w", encoding="utf-8") as file:
                file.write(data)
            return output_path

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
        """
        Transfer a batch of files with one protocol, reusing a single
        connection where the underlying helper supports it (FTP, S3).
        """
        if not file_list:
            return
        if protocol == "ftp":
            Files.download_files_from_ftp(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
            )
            return
        if protocol == "aspera":
            Files.download_files_from_aspera(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                maximum_bandwidth=aspera_maximum_bandwidth,
            )
            return
        if protocol == "globus":
            Files.download_files_from_globus(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
                checksum_map=checksum_map or {},
            )
            return
        if protocol == "s3":
            Files.download_files_from_s3(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
            )
            return
        raise ValueError(f"Unsupported protocol: {protocol}")

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
        """
        Download one file by trying each protocol in sequence, validating
        after every attempt. Intended as the per-file fallback path; batch
        download of the primary protocol is handled separately.
        """
        local_path = Files._resolve_local_path(file_record, output_folder)

        for protocol in protocol_sequence:
            for attempt in range(1, max_protocol_retries + 1):
                logging.info(
                    f"Downloading {file_record['fileName']} via {protocol} "
                    f"(attempt {attempt}/{max_protocol_retries})"
                )
                try:
                    Files._remove_if_exists(local_path)
                    Files._batch_download_by_protocol(
                        [file_record],
                        output_folder,
                        protocol,
                        skip_if_downloaded_already=False,
                        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
                        parallel_files=parallel_files,
                    )
                except Exception as error:
                    logging.error(
                        f"Protocol {protocol} failed for {file_record['fileName']}: {error}"
                    )

                valid, reason = Files.validate_download(local_path, expected_checksum)
                if valid:
                    logging.info(
                        f"File {file_record['fileName']} downloaded successfully via {protocol}"
                    )
                    return True

                logging.warning(
                    f"Validation failed for {file_record['fileName']} via {protocol}: {reason}"
                )
                Files._remove_if_exists(local_path)

            logging.warning(
                f"Protocol {protocol} exhausted for {file_record['fileName']}, switching protocol."
            )

        logging.error(f"All protocol attempts failed for {file_record['fileName']}")
        return False

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
        """
        Download files using either FTP or Aspera transfer protocol.
        :param file_list_json: File list in JSON format
        :param accession:  Project accession
        :param output_folder: Folder to download the files
        :param protocol: ftp, aspera, globus
        :param aspera_maximum_bandwidth: parameter in Aspera sets the maximum bandwidth for the transfer.
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        """
        protocols_supported = ["ftp", "aspera", "globus", "s3"]
        if protocol not in protocols_supported:
            logging.error("Protocol should be one of ftp, aspera, globus, s3")
            return

        os.makedirs(output_folder, exist_ok=True)

        checksum_map: Dict[str, str] = {}
        if checksum_check:
            checksum_file_path = Files.save_checksum_file(accession, output_folder)
            checksum_map = Files.read_checksum_file(checksum_file_path)
            logging.info(f"Loaded checksums for {len(checksum_map)} files")

        if not file_list_json:
            return

        protocol_sequence = Files._protocol_sequence(protocol)
        primary_protocol = protocol_sequence[0]
        # Retry with the primary protocol first, then fall back to others
        fallback_sequence = protocol_sequence

        # Phase 1: batch download with the requested protocol. Reuses a single
        # FTP/S3 connection for all files (the previous behaviour) instead of
        # paying the per-file reconnect cost in the common happy path.
        logging.info(
            f"Downloading {len(file_list_json)} file(s) via {primary_protocol} (batch)"
        )
        try:
            Files._batch_download_by_protocol(
                file_list_json,
                output_folder,
                primary_protocol,
                skip_if_downloaded_already=skip_if_downloaded_already,
                aspera_maximum_bandwidth=aspera_maximum_bandwidth,
                parallel_files=parallel_files,
                checksum_map=checksum_map,
            )
        except Exception as exc:
            logging.warning(
                f"Batch {primary_protocol} run hit an error; will retry individual failures: {exc}"
            )

        # Phase 2: validate every file and fall back per-file for the ones
        # that are missing or invalid.
        logging.info("Phase 2: validating %d downloaded file(s)", len(file_list_json))
        failed_files: List[str] = []
        for i, file_record in enumerate(file_list_json, 1):
            expected_checksum = checksum_map.get(file_record["fileName"])
            local_path = Files._resolve_local_path(file_record, output_folder)
            logging.info("Validating [%d/%d] %s", i, len(file_list_json), file_record["fileName"])
            valid, reason = Files.validate_download(local_path, expected_checksum)
            if valid:
                continue

            logging.warning(
                f"{file_record['fileName']} invalid after {primary_protocol} ({reason})"
            )
            if "checksum mismatch" in reason:
                Files._remove_if_exists(local_path)

            if not fallback_sequence:
                failed_files.append(file_record.get("fileName", "<unknown>"))
                continue

            success = Files._download_with_fallback(
                file_record=file_record,
                output_folder=output_folder,
                protocol_sequence=fallback_sequence,
                expected_checksum=expected_checksum,
                aspera_maximum_bandwidth=aspera_maximum_bandwidth,
                parallel_files=parallel_files,
            )
            if not success:
                failed_files.append(file_record.get("fileName", "<unknown>"))

        if failed_files:
            failed_summary = ", ".join(failed_files)
            logging.error(f"Failed to download {len(failed_files)} file(s): {failed_summary}")
            raise RuntimeError(f"Failed to download {len(failed_files)} file(s): {failed_summary}")

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

        if self.is_direct_download_accession(accession):
            all_files = self._list_direct_download_files(accession)
        else:
            all_files = self.stream_all_files_by_project(accession)
        requested = set(file_names)
        matched = [f for f in all_files if f.get("fileName") in requested]
        missing = sorted(requested - {f.get("fileName") for f in matched})
        if missing:
            logging.warning("Files not found in project %s: %s", accession, missing)
        if not matched:
            raise ValueError(
                f"No matching files in project {accession} for: {sorted(requested)}"
            )

        if self.is_direct_download_accession(accession):
            self._download_direct_download_records(
                accession=accession,
                file_records=matched,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
                parallel_files=parallel_files,
            )
            return

        self.download_files(
            matched,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
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
        raw_files = self.get_all_category_file_list(accession, categories)
        if self.is_direct_download_accession(accession):
            self._download_direct_download_records(
                accession=accession,
                file_records=raw_files,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
                parallel_files=parallel_files,
            )
            return
        self.download_files(
            raw_files,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
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
        category_set = {category.upper() for category in categories}

        if self.is_direct_download_accession(accession):
            record_files = self._list_direct_download_files(accession)
        else:
            record_files = self.stream_all_files_by_project(accession)

        category_files = [
            file for file in record_files if file["fileCategory"]["value"] in category_set
        ]
        return category_files

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
