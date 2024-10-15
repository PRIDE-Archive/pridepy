#!/usr/bin/env python
import ftplib
import importlib.resources
import logging
import os
import platform
import re
import subprocess
import urllib
import urllib.request
import time
from ftplib import FTP
from typing import Dict
import socket

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
    API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v2"
    API_PRIVATE_URL = "https://www.ebi.ac.uk/pride/private/ws/archive/v2"
    PRIDE_ARCHIVE_FTP = "ftp.pride.ebi.ac.uk"
    S3_URL = "https://hh.fire.sdo.ebi.ac.uk"
    S3_BUCKET = "pride-public"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    def __init__(self):
        pass

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
        await Util.stream_response_to_file(output_file, total_records, regex_search_pattern, request_url, headers)

    def get_all_paged_files(
        self, query_filter, page_size, page, sort_direction, sort_conditions
    ):
        """
         Get all filtered pride submission files
        :param query_filter: Parameters to filter the search results
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: paged file list on JSON format
        """
        """

        """
        request_url = self.API_BASE_URL + "/files?"

        if query_filter:
            request_url = request_url + "filter=" + query_filter + "&"

        request_url = (
            request_url
            + "pageSize="
            + str(page_size)
            + "&page="
            + str(page)
            + "&sortDirection="
            + sort_direction
            + "&sortConditions="
            + sort_conditions
        )

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_all_raw_file_list(self, project_accession):
        """
        Get all raw file lists from PRIDE API for a given project_accession
        :param project_accession: PRIDE accession
        :return: raw file list in JSON format
        """

        request_url = (
            self.API_BASE_URL
            + "/files/byProject?accession="
            + project_accession
            + ",fileCategory.value==RAW"
        )
        headers = {"Accept": "application/JSON"}

        response = Util.get_api_call(request_url, headers)
        return response.json()

    def download_all_raw_files(
        self,
        accession,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        aspera_maximum_bandwidth: str,
        checksum_check: bool = False,
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

        response_body = self.get_all_raw_file_list(accession)

        self.download_files(
            response_body,
            accession,
            output_folder,
            skip_if_downloaded_already,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
            checksum_check=checksum_check,
        )

    @staticmethod
    def download_files_from_ftp(file_list_json, output_folder, skip_if_downloaded_already, max_connection_retries=3,
                                max_download_retries=3):
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
                        new_file_path = Files.get_output_file_name(download_url, file, output_folder)

                        if skip_if_downloaded_already and os.path.exists(new_file_path):
                            logging.info("Skipping download as file already exists")
                            continue

                        # Extract file path from the download URL
                        ftp_file_path = download_url.replace(f"ftp://{Files.PRIDE_ARCHIVE_FTP}/", "")

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
                                    with tqdm(total=total_size, unit="B", unit_scale=True, desc=new_file_path) as pbar:
                                        def callback(data):
                                            f.write(data)
                                            pbar.update(len(data))

                                        # Retrieve the file with progress callback
                                        ftp.retrbinary(f"RETR {ftp_file_path}", callback)

                                logging.info(f"Successfully downloaded {new_file_path}")
                                break  # Exit download retry loop if successful
                            except (socket.timeout, ftplib.error_temp, ftplib.error_perm) as e:
                                download_attempt += 1
                                logging.error(
                                    f"Download failed for {new_file_path} (attempt {download_attempt}): {str(e)}")
                                if download_attempt >= max_download_retries:
                                    logging.error(
                                        f"Giving up on {new_file_path} after {max_download_retries} attempts.")
                                    break  # Give up on this file after max retries
                    except (KeyError, IndexError) as e:
                        logging.error(f"Failed to process file due to missing data: {str(e)}")
                    except Exception as e:
                        logging.error(f"Unexpected error while processing file: {str(e)}")
                ftp.quit()  # Close FTP connection after all files are downloaded
                logging.info(f"Disconnected from FTP host: {Files.PRIDE_ARCHIVE_FTP}")
                break  # Exit connection retry loop if everything was successful
            except (socket.timeout, ftplib.error_temp, ftplib.error_perm, socket.error) as e:
                connection_attempt += 1
                logging.error(f"FTP connection failed (attempt {connection_attempt}): {str(e)}")
                if connection_attempt < max_connection_retries:
                    logging.info("Retrying connection...")
                    time.sleep(5)  # Optional delay before retrying
                else:
                    logging.error(f"Giving up after {max_connection_retries} failed connection attempts.")
                    break

    @staticmethod
    def get_output_file_name(download_url, file, output_folder):
        public_filepath_part = download_url.rsplit("/", 1)
        logging.debug(file["accession"] + " -> " + public_filepath_part[1])
        new_file_path = os.path.join(output_folder, f"{public_filepath_part[1]}")
        return new_file_path

    @staticmethod
    def download_files_from_aspera(
        file_list_json: Dict,
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
            new_file_path = Files.get_output_file_name(
                download_url, file, output_folder
            )

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
    def download_files_from_globus(
        file_list_json, output_folder, skip_if_downloaded_already
    ):
        """
        Download files using globus transfer url with progress bar for each file
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder, exist_ok=True)

        for file in file_list_json:
            try:
                if file["publicFileLocations"][0]["name"] == "FTP Protocol":
                    download_url = file["publicFileLocations"][0]["value"]
                else:
                    download_url = file["publicFileLocations"][1]["value"]

                logging.debug(f"Downloading from Globus: {download_url}")
                ftp_base_url = "ftp://ftp.pride.ebi.ac.uk/"
                globus_base_url = "https://g-a8b222.dd271.03c0.data.globus.org/"
                download_url = download_url.replace(ftp_base_url, globus_base_url)

                # Create a clean filename to save the downloaded file
                new_file_path = Files.get_output_file_name(
                    download_url, file, output_folder
                )

                if skip_if_downloaded_already == True and os.path.exists(new_file_path):
                    logging.info("Skipping download as file already exists")
                    continue

                # Get total file size for progress tracking
                with urllib.request.urlopen(download_url) as response:
                    total_size = int(response.headers.get("Content-Length", 0))

                # Initialize progress bar
                progress = Progress(total_size, new_file_path)

                # Download the file with progress bar
                urllib.request.urlretrieve(
                    download_url,
                    new_file_path,
                    reporthook=lambda blocks, block_size, total_size: progress(
                        block_size
                    ),
                )

                progress.close()
                logging.info(f"Successfully downloaded {new_file_path}")

            except Exception as e:
                logging.error(
                    f"Download from Globus failed for {new_file_path}: {str(e)}"
                )

    @staticmethod
    def download_files_from_s3(
        file_list_json: Dict, output_folder: str, skip_if_downloaded_already
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
                new_file_path = Files.get_output_file_name(
                    download_url, file, output_folder
                )

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

    def get_file_from_api(self, accession, file_name):
        """
        Fetches file from API
        :param accession: PRIDE accession
        :param file_name: file name
        :return: file in json format
        """
        request_url = (
            self.API_BASE_URL
            + "/files/byProject?accession="
            + accession
            + ",fileName=="
            + file_name
        )
        headers = {"Accept": "application/JSON"}
        try:
            response = Util.get_api_call(request_url, headers)
            return response.json()
        except Exception as e:
            raise Exception("File not found " + str(e))

    def download_private_file_name(
        self, accession, file_name, output_folder, username, password
    ):
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

        url = self.API_PRIVATE_URL + "/projects/{}/files?search={}".format(
            accession, file_name
        )
        content = requests.get(
            url, headers={"Authorization": "Bearer {}".format(auth_token)}
        )
        if content.ok and content.status_code == 200:
            json_file = content.json()
            if (
                "_embedded" in json_file
                and "files" in json_file["_embedded"]
                and len(json_file["_embedded"]["files"]) == 1
            ):
                download_url = json_file["_embedded"]["files"][0]["_links"]["download"][
                    "href"
                ]
                logging.info(download_url)

                # Create a clean filename to save the downloaded file
                new_file_path = os.path.join(output_folder, f"{file_name}")

                session = (
                    Util.create_session_with_retries()
                )  # Create session with retries
                # Check if the file already exists
                if os.path.exists(new_file_path):
                    resume_header = {
                        "Range": f"bytes={os.path.getsize(new_file_path)}-"
                    }
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
        url = f"https://wwwdev.ebi.ac.uk/pride/ws/archive/v3/files/checksum/{accession}"
        headers = {"accept": "text/plain"}
        request = urllib.request.Request(url, headers=headers, method="GET")
        logging.info(f"Fetching checksum file from {url}")
        with urllib.request.urlopen(request) as response:
            data = response.read().decode("utf-8")
            # Save the data to a .tsv file
            output_path = os.path.join(output_folder, f"{accession}-checksum.tsv")
            with open(output_path, "w") as file:
                file.write(data)

    @staticmethod
    def download_files(
        file_list_json,
        accession,
        output_folder: str,
        skip_if_downloaded_already,
        protocol: str = "ftp",
        aspera_maximum_bandwidth: str = "100M",  # Aspera maximum bandwidth
        checksum_check=False,
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
            logging.error("Protocol should be either ftp, aspera, globus")
            return

        if checksum_check:
            Files.save_checksum_file(accession, output_folder)

        if protocol == "ftp":
            Files.download_files_from_ftp(
                file_list_json, output_folder, skip_if_downloaded_already
            )

        elif protocol == "aspera":
            Files.download_files_from_aspera(
                file_list_json,
                output_folder,
                skip_if_downloaded_already,
                maximum_bandwidth=aspera_maximum_bandwidth,
            )
        elif protocol == "globus":
            Files.download_files_from_globus(
                file_list_json, output_folder, skip_if_downloaded_already
            )
        elif protocol == "s3":
            Files.download_files_from_s3(
                file_list_json, output_folder, skip_if_downloaded_already
            )
