"""PRIDE Archive provider.

PRIDE has the richest behaviour of all providers: multi-protocol batch
download with aspera/s3/ftp/globus fallback, private-dataset path with
username/password auth, checksum TSV validation, and submitter-path
helpers. This module owns all of that logic; the
:class:`~pridepy.download.client.Client` facade exposes a thin public
surface for downstream callers.

Implementation note: PRIDE provider methods route through other
PrideProvider methods (``PrideProvider.X(...)``) or directly through the
shared ``transport`` / ``util`` helpers — they do NOT call back into the
``Client`` facade. Tests patch the canonical locations
(``PrideProvider.X``, ``transport.X``, ``util.X``) directly.
"""
import ftplib
import importlib.resources
import logging
import os
import platform
import re
import socket
import subprocess
import time
import urllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from ftplib import FTP
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

import boto3
import botocore
import requests
from botocore.config import Config
from tqdm import tqdm

from pridepy.authentication.authentication import Authentication
from pridepy.download import registry, transport
from pridepy.download import util as _provider_util
from pridepy.download.base import Provider
from pridepy.download.util import Progress
from pridepy.util.api_handling import Util


@registry.register
class PrideProvider(Provider):
    """PRIDE Archive provider with multi-protocol fallback orchestration."""

    name: ClassVar[str] = "pride"

    V3_API_BASE_URL: ClassVar[str] = "https://www.ebi.ac.uk/pride/ws/archive/v3"
    API_BASE_URL: ClassVar[str] = "https://www.ebi.ac.uk/pride/ws/archive/v3"
    API_PRIVATE_URL: ClassVar[str] = "https://www.ebi.ac.uk/pride/private/ws/archive/v2"
    ARCHIVE_FTP: ClassVar[str] = "ftp.pride.ebi.ac.uk"
    ARCHIVE_FTP_URL_PREFIX: ClassVar[str] = "ftp://ftp.pride.ebi.ac.uk/"
    ARCHIVE_HTTPS_URL_PREFIX: ClassVar[str] = "https://ftp.pride.ebi.ac.uk/"
    S3_URL: ClassVar[str] = "https://hh.fire.sdo.ebi.ac.uk"
    S3_BUCKET: ClassVar[str] = "pride-public"
    PROTOCOL_ORDER: ClassVar[List[str]] = ["aspera", "s3", "ftp", "globus"]

    @staticmethod
    def matches(accession: str) -> bool:
        """Return True when ``accession`` is a PRIDE dataset accession."""
        if not accession:
            return False
        return bool(re.fullmatch(r"(?:PXD|PRD)\d+", accession.upper()))

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

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

    def list_files(self, accession: str) -> List[Dict]:
        """Return PRIDE file records for the dataset."""
        return self.stream_all_files_by_project(accession)

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
        records = self.list_files(accession)
        raw_files = [r for r in records if r["fileCategory"]["value"] == "RAW"]
        first_file = raw_files[0]["publicFileLocations"][0]["value"]
        path_fragment = re.search(r"\d{4}/\d{2}/PXD\d*", first_file).group()
        return path_fragment

    # ------------------------------------------------------------------
    # Static utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _protocol_sequence(protocol: str) -> List[str]:
        """
        Build the ordered list of protocols to try for a requested download mode.
        """
        if protocol not in PrideProvider.PROTOCOL_ORDER:
            return []
        return [protocol] + [p for p in PrideProvider.PROTOCOL_ORDER if p != protocol]

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
    def get_output_file_name(download_url, file, output_folder):
        """Build the local output path for ``download_url`` inside ``output_folder``."""
        public_filepath_part = download_url.rsplit("/", 1)
        accession = file.get("accession", "unknown-accession")
        logging.debug(accession + " -> " + public_filepath_part[1])
        new_file_path = os.path.join(output_folder, f"{public_filepath_part[1]}")
        return new_file_path

    @staticmethod
    def _get_download_url(file_record: Dict, protocol: str) -> str:
        """Resolve the PRIDE public download URL for a file and protocol.

        Raises ValueError when the requested protocol has no suitable location.
        Aspera requires a dedicated "Aspera Protocol" entry; ftp/s3/globus
        derive their URL from the "FTP Protocol" entry (falling back to an
        arbitrary non-Aspera location would produce a URL the caller cannot
        actually transfer with). The globus URL is the FTP path rewritten to
        the PRIDE archive HTTPS prefix.
        """
        locations = file_record.get("publicFileLocations", [])
        if not locations:
            raise ValueError("No public file locations present")

        aspera_url = None
        ftp_url = None
        for location in locations:
            name = location.get("name")
            if name == "Aspera Protocol":
                aspera_url = location.get("value")
            elif name == "FTP Protocol":
                ftp_url = location.get("value")

        if protocol == "aspera":
            if not aspera_url:
                raise ValueError("Aspera URL not available")
            return aspera_url

        if not ftp_url:
            raise ValueError("FTP URL not available")
        if protocol == "ftp":
            return ftp_url
        if protocol == "globus":
            return ftp_url.replace(
                PrideProvider.ARCHIVE_FTP_URL_PREFIX,
                PrideProvider.ARCHIVE_HTTPS_URL_PREFIX,
                1,
            )
        if protocol == "s3":
            return ftp_url
        raise ValueError(f"Unsupported protocol: {protocol}")

    def get_download_url(self, record: Dict, protocol: str = "ftp") -> str:
        """Override the base hook with PRIDE's multi-protocol resolution."""
        return PrideProvider._get_download_url(record, protocol)

    @staticmethod
    def _resolve_local_path(file_record: Dict, output_folder: str) -> str:
        """Compute the canonical local path for a file regardless of protocol."""
        try:
            canonical_url = PrideProvider._get_download_url(file_record, "ftp")
        except ValueError:
            canonical_url = ""
        if canonical_url:
            return PrideProvider.get_output_file_name(canonical_url, file_record, output_folder)
        return os.path.join(output_folder, file_record["fileName"])

    @staticmethod
    def extract_accession_from_url(url: str) -> Optional[str]:
        """Extract a PRIDE accession (PXD/PRD followed by digits) from a URL.

        PRIDE archive URLs follow the pattern
        ``…/pride/data/archive/YYYY/MM/<ACCESSION>/filename``.
        Returns ``None`` when no accession can be identified.
        """
        match = re.search(r"((?:PXD|PRD)\d{4,})", url)
        return match.group(1) if match else None

    @staticmethod
    def validate_urls_checksums(urls: List[str], output_folder: str) -> None:
        """Validate downloaded files against the PRIDE checksum API.

        Accessions are inferred from URL paths via
        :meth:`extract_accession_from_url`. URLs that do not contain a
        recognisable PRIDE accession are skipped with a warning.

        :raises RuntimeError: if one or more files fail validation
        """
        accession_urls: Dict[str, List[str]] = {}
        for url in urls:
            acc = PrideProvider.extract_accession_from_url(url)
            if acc:
                accession_urls.setdefault(acc, []).append(url)
            else:
                logging.warning(
                    "Cannot infer PRIDE accession from URL, skipping checksum: %s", url
                )

        validation_failures: List[str] = []
        for acc, acc_urls in accession_urls.items():
            checksum_file_path = PrideProvider.save_checksum_file(acc, output_folder)
            checksum_map = _provider_util.read_checksum_file(checksum_file_path)
            logging.info(
                "Loaded checksums for %d files (project %s)",
                len(checksum_map), acc,
            )
            for url in acc_urls:
                file_name = os.path.basename(urlparse(url).path)
                target = os.path.join(output_folder, file_name)
                expected = checksum_map.get(file_name)
                logging.info("Validating %s", file_name)
                valid, reason = _provider_util.validate_download(target, expected)
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
    def save_checksum_file(accession, output_folder):
        """
        Download and persist the checksum manifest for a PRIDE accession.
        """
        os.makedirs(output_folder, exist_ok=True)
        url = f"{PrideProvider.V3_API_BASE_URL}/files/checksum/{accession}"
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

    # ------------------------------------------------------------------
    # Per-protocol single-file workers
    # ------------------------------------------------------------------

    @staticmethod
    def _globus_download_one(file, output_folder, skip_if_downloaded_already, max_retries=6, position=0):
        """Download a single file via globus; used as a worker target."""
        download_url = PrideProvider._get_download_url(file, "globus")
        new_file_path = PrideProvider.get_output_file_name(download_url, file, output_folder)

        if skip_if_downloaded_already and os.path.exists(new_file_path):
            logging.info(f"Skipping download as file already exists: {new_file_path}")
            return

        for attempt in range(1, max_retries + 1):
            try:
                transport._parallel_download(download_url, new_file_path, position=position)
                return
            except Exception as e:
                logging.warning(f"Attempt {attempt}/{max_retries} failed for {file.get('fileName', '?')}: {e}")
                if attempt == max_retries:
                    raise

    # ------------------------------------------------------------------
    # Per-protocol batch helpers
    # ------------------------------------------------------------------

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
            ftp = FTP(PrideProvider.ARCHIVE_FTP, timeout=30)
            ftp.login()  # Anonymous login
            ftp.set_pasv(True)  # Enable passive mode
            logging.info(f"Connected to FTP host: {PrideProvider.ARCHIVE_FTP}")
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
                        new_file_path = PrideProvider.get_output_file_name(
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
                logging.info(f"Disconnected from FTP host: {PrideProvider.ARCHIVE_FTP}")
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
        ascp_path = PrideProvider.get_ascp_binary()
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
            new_file_path = PrideProvider.get_output_file_name(download_url, file, output_folder)

            if skip_if_downloaded_already and os.path.exists(new_file_path):
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
            download_url = PrideProvider._get_download_url(file, "globus")
            new_file_path = PrideProvider.get_output_file_name(download_url, file, output_folder)
            if skip_if_downloaded_already and os.path.exists(new_file_path):
                expected_cs = checksum_map.get(file.get("fileName", ""))
                if expected_cs:
                    valid, reason = _provider_util.validate_download(new_file_path, expected_cs)
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
                    PrideProvider._globus_download_one(
                        file, output_folder, False
                    )
                    new_file_path = PrideProvider.get_output_file_name(
                        PrideProvider._get_download_url(file, "globus"), file, output_folder
                    )
                    logging.info(f"Successfully downloaded {new_file_path}")
                except Exception as e:
                    logging.error(f"Download from Globus failed: {str(e)}")
        else:
            logging.info(f"Downloading {len(files_to_download)} file(s) with {parallel_files} parallel workers")
            with ThreadPoolExecutor(max_workers=parallel_files) as executor:
                futures = {
                    executor.submit(
                        PrideProvider._globus_download_one,
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
            endpoint_url=PrideProvider.S3_URL,
        )
        bucket = s3_resource.Bucket(PrideProvider.S3_BUCKET)

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
                new_file_path = PrideProvider.get_output_file_name(download_url, file, output_folder)

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

    # ------------------------------------------------------------------
    # Private dataset download
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Multi-protocol orchestrator
    # ------------------------------------------------------------------

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
            PrideProvider.download_files_from_ftp(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
            )
            return
        if protocol == "aspera":
            PrideProvider.download_files_from_aspera(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                maximum_bandwidth=aspera_maximum_bandwidth,
            )
            return
        if protocol == "globus":
            PrideProvider.download_files_from_globus(
                file_list,
                output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
                checksum_map=checksum_map or {},
            )
            return
        if protocol == "s3":
            PrideProvider.download_files_from_s3(
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
        local_path = PrideProvider._resolve_local_path(file_record, output_folder)

        for protocol in protocol_sequence:
            for attempt in range(1, max_protocol_retries + 1):
                logging.info(
                    f"Downloading {file_record['fileName']} via {protocol} "
                    f"(attempt {attempt}/{max_protocol_retries})"
                )
                try:
                    _provider_util._remove_if_exists(local_path)
                    PrideProvider._batch_download_by_protocol(
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

                valid, reason = _provider_util.validate_download(local_path, expected_checksum)
                if valid:
                    logging.info(
                        f"File {file_record['fileName']} downloaded successfully via {protocol}"
                    )
                    return True

                logging.warning(
                    f"Validation failed for {file_record['fileName']} via {protocol}: {reason}"
                )
                _provider_util._remove_if_exists(local_path)

            logging.warning(
                f"Protocol {protocol} exhausted for {file_record['fileName']}, switching protocol."
            )

        logging.error(f"All protocol attempts failed for {file_record['fileName']}")
        return False

    def download_files(
        self,
        accession,
        records: List[Dict],
        output_folder: str,
        skip_if_downloaded_already: bool = False,
        protocol: str = "ftp",
        parallel_files: int = 1,
        checksum_check: bool = False,
        aspera_maximum_bandwidth: str = "100M",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """Override Provider.download_files with the multi-protocol orchestrator.

        Reuses the legacy batch downloader: Phase 1 batches the requested
        protocol over a single connection, Phase 2 validates every file, and
        Phase 3 falls back per-file across the remaining protocols.
        """
        PrideProvider._download_files_batch(
            file_list_json=records,
            accession=accession,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
            parallel_files=parallel_files,
        )

    def download_by_name(
        self,
        accession,
        file_name,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        username=None,
        password=None,
        aspera_maximum_bandwidth="100M",
        checksum_check=False,
    ):
        """Download a single file by name, honouring PRIDE's public/private split.

        PRIDE exposes private datasets via the V2 private API (username +
        password); public datasets route through the standard listing +
        multi-protocol download path inherited from :class:`Provider`.
        """
        public_project = False
        project_status = Util.get_api_call(
            self.API_BASE_URL + "/status/{}".format(accession)
        )

        if project_status.status_code == 200:
            if project_status.text == "PRIVATE":
                public_project = False
            elif project_status.text == "PUBLIC":
                public_project = True
            else:
                raise Exception(
                    "Dataset {} is not present in PRIDE Archive".format(accession)
                )

        if public_project:
            logging.info("Downloading file from public dataset {}".format(accession))
            super().download_by_name(
                accession=accession,
                file_name=file_name,
                output_folder=output_folder,
                skip_if_downloaded_already=skip_if_downloaded_already,
                protocol=protocol,
                username=username,
                password=password,
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

    @staticmethod
    def _download_files_batch(
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
            checksum_file_path = PrideProvider.save_checksum_file(accession, output_folder)
            checksum_map = _provider_util.read_checksum_file(checksum_file_path)
            logging.info(f"Loaded checksums for {len(checksum_map)} files")

        if not file_list_json:
            return

        protocol_sequence = PrideProvider._protocol_sequence(protocol)
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
            PrideProvider._batch_download_by_protocol(
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
            local_path = PrideProvider._resolve_local_path(file_record, output_folder)
            logging.info("Validating [%d/%d] %s", i, len(file_list_json), file_record["fileName"])
            valid, reason = _provider_util.validate_download(local_path, expected_checksum)
            if valid:
                continue

            logging.warning(
                f"{file_record['fileName']} invalid after {primary_protocol} ({reason})"
            )
            if "checksum mismatch" in reason:
                _provider_util._remove_if_exists(local_path)

            if not fallback_sequence:
                failed_files.append(file_record.get("fileName", "<unknown>"))
                continue

            success = PrideProvider._download_with_fallback(
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
