#!/usr/bin/env python
import ftplib
import hashlib
import importlib.resources
import logging
import os
import platform
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


class Progress:
    def __init__(self, total_size, file_name):
        self.pbar = tqdm(
            total=total_size,
            unit="B",
            unit_scale=True,
            desc="Downloading {}".format(file_name),
        )

    def __call__(self, bytes_amount):
        self.pbar.update(bytes_amount)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pbar.close()

    def close(self):
        self.pbar.close()


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
    S3_URL = "https://hh.fire.sdo.ebi.ac.uk"
    S3_BUCKET = "pride-public"
    PROTOCOL_ORDER = ["aspera", "s3", "ftp", "globus"]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    def __init__(self):
        pass

    @staticmethod
    def _find_tsv_columns(header: str) -> Optional[Tuple[int, int]]:
        """Return (name_idx, checksum_idx) from a TSV header, or None."""
        cols = [col.strip().lower() for col in header.split("\t")]
        required_cols = {"file-name", "file-md5checksum", "file-size"}
        if not required_cols.issubset(set(cols)):
            return None
        return cols.index("file-name"), cols.index("file-md5checksum")

    @staticmethod
    def _is_md5_checksum(value: str) -> bool:
        return len(value) == 32 and all(char in "0123456789abcdef" for char in value)

    @staticmethod
    def read_checksum_file(checksum_file_path: str) -> Dict[str, str]:
        """
        Read PRIDE API checksum TSV and build {file_name: md5} map.
        Expected format: File-Name\tFile-MD5Checksum\tFile-Size
        """
        checksums: Dict[str, str] = {}
        if not checksum_file_path or not os.path.exists(checksum_file_path):
            return checksums

        with open(checksum_file_path, "r", encoding="utf-8") as f:
            header = f.readline().strip()
            if not header:
                return checksums

            col_indices = Files._find_tsv_columns(header)
            if col_indices is None:
                logging.warning(f"Unrecognized checksum file format: {header}")
                return checksums

            name_idx, checksum_idx = col_indices
            min_cols = max(name_idx, checksum_idx) + 1
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= min_cols:
                    fn = os.path.basename(parts[name_idx].strip())
                    cs = parts[checksum_idx].strip().lower()
                    if fn and Files._is_md5_checksum(cs):
                        checksums[fn] = cs

        return checksums

    @staticmethod
    def compute_md5(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
        """
        Compute an MD5 checksum for integrity validation, not for security use.
        """
        try:
            md5 = hashlib.md5(usedforsecurity=False)
        except TypeError:
            md5 = hashlib.md5()
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break
                md5.update(chunk)
        return md5.hexdigest()

    @staticmethod
    def validate_download(file_path: str, expected_checksum: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate a local file exists, is non-empty, and checksum matches when provided.
        """
        if not os.path.exists(file_path):
            return False, "file does not exist"
        if os.path.getsize(file_path) == 0:
            return False, "file is empty"
        if expected_checksum:
            actual_checksum = Files.compute_md5(file_path)
            if actual_checksum.lower() != expected_checksum.lower():
                return False, (
                    f"checksum mismatch (expected={expected_checksum.lower()}, actual={actual_checksum.lower()})"
                )
        return True, "ok"

    @staticmethod
    def _remove_if_exists(file_path: str) -> None:
        """
        Remove a file if it already exists locally.
        """
        if os.path.exists(file_path):
            os.remove(file_path)

    @staticmethod
    def _get_download_url(file_record: Dict, protocol: str) -> str:
        """
        Resolve the public download URL for a file and protocol.

        Raises ValueError when the requested protocol has no suitable location.
        Aspera requires a dedicated "Aspera Protocol" entry; ftp/s3/globus
        derive their URL from the "FTP Protocol" entry (falling back to an
        arbitrary non-Aspera location would produce a URL the caller cannot
        actually transfer with).
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
                Files.PRIDE_ARCHIVE_FTP_URL_PREFIX,
                Files.PRIDE_ARCHIVE_HTTPS_URL_PREFIX,
                1,
            )
        if protocol == "s3":
            return ftp_url
        raise ValueError(f"Unsupported protocol: {protocol}")

    @staticmethod
    def _resolve_local_path(file_record: Dict, output_folder: str) -> str:
        """
        Compute the canonical local path for a file regardless of transfer protocol.
        """
        try:
            canonical_url = Files._get_download_url(file_record, "ftp")
        except ValueError:
            canonical_url = ""
        if canonical_url:
            return Files.get_output_file_name(canonical_url, file_record, output_folder)
        return os.path.join(output_folder, file_record["fileName"])

    @staticmethod
    def _protocol_sequence(protocol: str) -> List[str]:
        """
        Build the ordered list of protocols to try for a requested download mode.
        """
        if protocol not in Files.PROTOCOL_ORDER:
            return []
        return [protocol] + [p for p in Files.PROTOCOL_ORDER if p != protocol]

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
                        ftp_file_path = download_url.replace(
                            f"ftp://{Files.PRIDE_ARCHIVE_FTP}/", ""
                        )

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
    def _parallel_download(url, file_path):
        """Download a file using parallel Range requests, like browser parallel downloading.
        Supports resume: if a partial file exists, continues from where it left off."""
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
            with tqdm(total=total_size, unit="B", unit_scale=True, desc=file_path,
                      initial=resume_size) as pbar:
                mode = "ab" if resume_size > 0 else "wb"
                with open(file_path, mode, buffering=8 * 1024 * 1024) as f:
                    for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

    @staticmethod
    def _globus_download_one(file, output_folder, skip_if_downloaded_already, max_retries=6):
        """Download a single file via globus; used as a worker target."""
        download_url = Files._get_download_url(file, "globus")
        new_file_path = Files.get_output_file_name(download_url, file, output_folder)

        if skip_if_downloaded_already and os.path.exists(new_file_path):
            logging.info(f"Skipping download as file already exists: {new_file_path}")
            return

        for attempt in range(1, max_retries + 1):
            try:
                Files._parallel_download(download_url, new_file_path)
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
            os.mkdir(output_folder, exist_ok=True)

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
        parallel_files = min(parallel_files, 3)
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
                    ): file
                    for file in files_to_download
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
    ) -> None:
        """Download a subset of project files identified by a filename list.

        Resolves each requested filename via the project metadata API and
        delegates to :meth:`download_files` so the existing batch + protocol
        fallback engine is reused.

        :param accession: PRIDE project accession (public)
        :param file_names: filenames to download
        :param output_folder: directory to write downloaded files into
        :param skip_if_downloaded_already: skip files already present locally
        :param protocol: preferred protocol; falls back across others on failure
        :param aspera_maximum_bandwidth: aspera ascp bandwidth cap
        :param checksum_check: download project checksums and validate
        :raises ValueError: if ``file_names`` is empty or none match the project
        """
        if not file_names:
            raise ValueError("file_names must contain at least one filename")

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

        self.download_files(
            matched,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
        )

    @staticmethod
    def download_files_by_url(
        urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool = False,
        protocol: str = "ftp",
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
            ``globus`` for parallel multi-Range downloads on http/https URLs
            (no effect on ftp:// URLs which always use single-connection FTP)
        :raises ValueError: if ``urls`` is empty
        :raises RuntimeError: if one or more URLs failed
        """
        if not urls:
            raise ValueError("urls must contain at least one URL")

        os.makedirs(output_folder, exist_ok=True)

        failures: List[Tuple[str, str]] = []
        for url in urls:
            try:
                Files._download_single_url(
                    url, output_folder, skip_if_downloaded_already, protocol,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logging.error("Failed to download %s: %s", url, exc)
                failures.append((url, str(exc)))

        if failures:
            summary = ", ".join(f"{u} ({e})" for u, e in failures)
            raise RuntimeError(
                f"Failed to download {len(failures)} URL(s): {summary}"
            )

    @staticmethod
    def _download_single_url(
        url: str,
        output_folder: str,
        skip_if_exists: bool = False,
        protocol: str = "ftp",
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

        Files._dispatch_url_scheme(parsed, target, protocol)

        ok, reason = Files.validate_download(target)
        if not ok:
            Files._remove_if_exists(target)
            raise RuntimeError(f"Download invalid: {reason} ({target})")
        return target

    @staticmethod
    def _dispatch_url_scheme(parsed, target: str, protocol: str = "ftp") -> None:
        """Route a parsed URL to its protocol-specific downloader.

        ``protocol='globus'`` swaps the http/https single-connection streamer
        for :meth:`_parallel_download` (single-connection with progress bar).
        ftp:// URLs are unaffected.
        """
        scheme = (parsed.scheme or "").lower()
        if scheme in ("http", "https"):
            if protocol == "globus":
                Files._parallel_download(parsed.geturl(), target)
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
        record_files = self.stream_all_files_by_project(accession)
        if isinstance(categories, str):
            categories = [categories]
        category_set = set(categories)
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
        filename = os.path.basename(urlparse(download_url).path)
        return os.path.join(output_folder, filename)

    @staticmethod
    def download_ftp_urls(
        ftp_urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
        max_connection_retries: int = 3,
        max_download_retries: int = 3,
    ) -> None:
        """
        Download a list of FTP URLs using a single connection, with retries and progress bars.
        """
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        def connect_ftp(host: str):
            ftp = FTP(host, timeout=30)
            ftp.login()
            ftp.set_pasv(True)
            logging.info(f"Connected to FTP host: {host}")
            return ftp

        # Group URLs by host to reuse connections efficiently
        host_to_paths: Dict[str, List[str]] = {}
        for url in ftp_urls:
            parsed = urlparse(url)
            host_to_paths.setdefault(parsed.hostname, []).append(parsed.path.lstrip("/"))

        for host, paths in host_to_paths.items():
            connection_attempt = 0
            while connection_attempt < max_connection_retries:
                try:
                    ftp = connect_ftp(host)
                    for ftp_path in paths:
                        try:
                            local_path = os.path.join(output_folder, os.path.basename(ftp_path))
                            if skip_if_downloaded_already and os.path.exists(local_path):
                                logging.info("Skipping download as file already exists")
                                continue

                            logging.info(f"Starting FTP download: {host}/{ftp_path}")
                            download_attempt = 0
                            while download_attempt < max_download_retries:
                                try:
                                    total_size = ftp.size(ftp_path)
                                    # Try to resume using REST if partial file exists
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
                                    ) as pbar:
                                        def callback(data):
                                            f.write(data)
                                            pbar.update(len(data))

                                        if current_size:
                                            try:
                                                ftp.sendcmd(f"REST {current_size}")
                                            except Exception:
                                                # If REST not supported, fall back to full download
                                                current_size = 0
                                                f.seek(0)
                                                f.truncate()
                                        ftp.retrbinary(f"RETR {ftp_path}", callback)
                                    logging.info(f"Successfully downloaded {local_path}")
                                    break
                                except (socket.timeout, ftplib.error_temp, ftplib.error_perm) as e:
                                    download_attempt += 1
                                    logging.error(
                                        f"Download failed for {local_path} (attempt {download_attempt}): {str(e)}"
                                    )
                                    if download_attempt >= max_download_retries:
                                        logging.error(
                                            f"Giving up on {local_path} after {max_download_retries} attempts."
                                        )
                                        break
                        except Exception as e:
                            logging.error(f"Unexpected error while processing FTP path {ftp_path}: {str(e)}")
                    ftp.quit()
                    logging.info(f"Disconnected from FTP host: {host}")
                    break
                except (socket.timeout, ftplib.error_temp, ftplib.error_perm, socket.error) as e:
                    connection_attempt += 1
                    logging.error(f"FTP connection failed (attempt {connection_attempt}): {str(e)}")
                    if connection_attempt < max_connection_retries:
                        logging.info("Retrying connection...")
                        time.sleep(5)
                    else:
                        logging.error(
                            f"Giving up after {max_connection_retries} failed connection attempts to {host}."
                        )

    @staticmethod
    def download_http_urls(
        http_urls: List[str],
        output_folder: str,
        skip_if_downloaded_already: bool,
    ) -> None:
        """
        Download a list of HTTP(S) URLs with resume support and progress bars.
        """
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        session = Util.create_session_with_retries()
        for url in http_urls:
            try:
                local_path = Files._local_path_for_url(url, output_folder)
                if skip_if_downloaded_already and os.path.exists(local_path):
                    logging.info("Skipping download as file already exists")
                    continue

                if os.path.exists(local_path):
                    resume_size = os.path.getsize(local_path)
                    headers = {"Range": f"bytes={resume_size}-"}
                    mode = "ab"
                else:
                    resume_size = 0
                    headers = {}
                    mode = "wb"

                with session.get(url, stream=True, headers=headers, timeout=(10, 60)) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0)) + resume_size
                    block_size = 1024 * 1024
                    with tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        desc=local_path,
                        initial=resume_size,
                    ) as pbar:
                        with open(local_path, mode) as f:
                            for chunk in r.iter_content(chunk_size=block_size):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                logging.info(f"Successfully downloaded {local_path}")
            except Exception as e:
                logging.error(f"HTTP download failed for {url}: {str(e)}")
