#!/usr/bin/env python

import importlib.resources
import logging
import os
import platform
import re
import subprocess
import urllib
import urllib.request
from typing import Dict

import boto3
import botocore
from botocore.config import Config
from tqdm import tqdm

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


class Files:
    """
    This class handles PRIDE API files endpoint.
    """

    API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v2/"
    S3_URL = "https://hh.fire.sdo.ebi.ac.uk"
    S3_BUCKET = "pride-public"
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    def __init__(self):
        pass

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
        request_url = self.API_BASE_URL + "files?"

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
            + "files/byProject?accession="
            + project_accession
            + ",fileCategory.value==RAW"
        )
        headers = {"Accept": "application/JSON"}

        response = Util.get_api_call(request_url, headers)
        return response.json()

    def download_all_raw_files(
        self, accession, output_folder, protocol, aspera_maximum_bandwidth: str
    ):
        """
        This method will download all the raw files from PRIDE PROJECT
        :param output_folder: output directory where raw files will get saved
        :param accession: PRIDE accession
        :param protocol: ftp, aspera, globus
        :param aspera_maximum_bandwidth: Aspera maximum bandwidth
        :return: None
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        response_body = self.get_all_raw_file_list(accession)

        self.download_files(
            response_body,
            output_folder,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        )

    @staticmethod
    def download_files_from_ftp(file_list_json, output_folder):
        """
        Download files using ftp transfer url with progress bar for each file
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        for file in file_list_json:
            try:
                if file["publicFileLocations"][0]["name"] == "FTP Protocol":
                    download_url = file["publicFileLocations"][0]["value"]
                else:
                    download_url = file["publicFileLocations"][1]["value"]

                logging.debug("ftp_filepath:" + download_url)

                new_file_path = Files.get_output_file_name(
                    download_url, file, output_folder
                )

                # Fetch the total file size from the headers for progress tracking
                with urllib.request.urlopen(download_url, timeout=30) as response:
                    total_size = int(response.headers.get("Content-Length", 0))

                # Initialize progress bar
                progress = Progress(total_size, new_file_path)

                # Download with progress bar
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
                logging.error(f"Failed to download {new_file_path}: {str(e)}")

    @staticmethod
    def get_output_file_name(download_url, file, output_folder):
        public_filepath_part = download_url.rsplit("/", 1)
        logging.debug(file["accession"] + " -> " + public_filepath_part[1])
        new_file_path = os.path.join(output_folder, f"{public_filepath_part[1]}")
        return new_file_path

    @staticmethod
    def download_files_from_aspera(
        file_list_json: Dict, output_folder: str, maximum_bandwidth: str = "100M"
    ):
        """
        Download files using aspera transfer url
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        :param maximum_bandwidth: parameter in Aspera sets the maximum bandwidth for the transfer.
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
    def download_files_from_globus(file_list_json, output_folder):
        """
        Download files using globus transfer url with progress bar for each file
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

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
    def download_files_from_s3(file_list_json, output_folder):
        """
        Download files using s3 transfer url with progress bar for each file
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        s3_resource = boto3.resource(
            "s3",
            config=Config(signature_version=botocore.UNSIGNED),
            endpoint_url=Files.S3_URL,
        )

        for file in file_list_json:
            try:
                bucket = s3_resource.Bucket(Files.S3_BUCKET)
                if file["publicFileLocations"][0]["name"] == "FTP Protocol":
                    download_url = file["publicFileLocations"][0]["value"]
                else:
                    download_url = file["publicFileLocations"][1]["value"]

                ftp_base_url = "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/"
                s3_path = download_url.replace(ftp_base_url, "")
                new_file_path = Files.get_output_file_name(
                    download_url, file, output_folder
                )

                logging.debug(f"Downloading From S3: {s3_path}")

                # Get the file size for progress tracking
                obj = bucket.Object(s3_path)
                total_size = obj.content_length

                # Initialize progress bar
                progress = Progress(total_size, new_file_path)

                # Download with progress bar
                bucket.download_file(s3_path, new_file_path, Callback=progress)

                progress.close()

                logging.info(f"Successfully downloaded {new_file_path}")

            except botocore.exceptions.ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    print("The object does not exist.")
                else:
                    raise

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
        self, accession, file_name, output_folder, protocol, aspera_maximum_bandwidth
    ):
        """
        Download files from url
        :param accession: PRIDE accession
        :param file_name: file name to download
        :param output_folder: folder to download the files
        :param protocol: ftp, aspera, globus
        :param aspera_maximum_bandwidth: Aspera maximum bandwidth
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)
        response = self.get_file_from_api(accession, file_name)
        self.download_files(
            response,
            output_folder,
            protocol,
            aspera_maximum_bandwidth=aspera_maximum_bandwidth,
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
            + "files/byProject?accession="
            + accession
            + ",fileName=="
            + file_name
        )
        headers = {"Accept": "application/JSON"}
        try:
            response = Util.get_api_call(request_url, headers)
            return response.json()
        except Exception as e:
            raise Exception("File not found" + str(e))

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
    def download_files(
        file_list_json,
        output_folder: str,
        protocol: str = "ftp",
        aspera_maximum_bandwidth: str = "100M",
    ):
        """
        Download files using either FTP or Aspera transfer protocol.
        :param file_list_json: File list in JSON format
        :param output_folder: Folder to download the files
        :param protocol: ftp, aspera, globus
        :param aspera_maximum_bandwidth: parameter in Aspera sets the maximum bandwidth for the transfer.
        """
        protocols_supported = ["ftp", "aspera", "globus", "s3"]
        if protocol not in protocols_supported:
            logging.error("Protocol should be either ftp, aspera, globus")
            return

        if protocol == "ftp":
            Files.download_files_from_ftp(file_list_json, output_folder)
        elif protocol == "aspera":
            Files.download_files_from_aspera(
                file_list_json,
                output_folder,
                maximum_bandwidth=aspera_maximum_bandwidth,
            )
        elif protocol == "globus":
            Files.download_files_from_globus(file_list_json, output_folder)
        elif protocol == "s3":
            Files.download_files_from_s3(file_list_json, output_folder)