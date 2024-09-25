#!/usr/bin/env python

import glob
import logging
import os
import platform
import re
import shutil
import subprocess
import urllib
import urllib.request

import boto3
import botocore
from botocore.config import Config

from util.api_handling import Util


class Files:
    """
    This class handles PRIDE API files endpoint.
    """

    API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v2/"
    S3_URL = 'https://hh.fire.sdo.ebi.ac.uk'
    S3_BUCKET = 'pride-public'
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def __init__(self):
        pass

    def get_all_paged_files(self, query_filter, page_size, page, sort_direction, sort_conditions):
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

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(
            page) + "&sortDirection=" + sort_direction + "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_all_raw_file_list(self, project_accession):
        """
        Get all raw file list from PRIDE API for a given project_accession
        :param project_accession: PRIDE accession
        :return: raw file list in JSON format
        """

        request_url = self.API_BASE_URL + "files/byProject?accession=" + project_accession + ",fileCategory.value==RAW"
        headers = {"Accept": "application/JSON"}

        response = Util.get_api_call(request_url, headers)
        return response.json()

    def download_all_raw_files(self, accession, output_folder, protocol):
        """
        This method will download all the raw files from PRIDE PROJECT
        :param output_folder: output directory where raw files will get saved
        :param accession: PRIDE accession
        :param protocol: ftp, aspera, globus
        :return: None
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        response_body = self.get_all_raw_file_list(accession)

        self.download_files(response_body, output_folder, protocol)

    @staticmethod
    def download_files_from_ftp(file_list_json, output_folder):
        """
        Download files using ftp transfer url
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        """
        for file in file_list_json:
            if file['publicFileLocations'][0]['name'] == 'FTP Protocol':
                download_url = file['publicFileLocations'][0]['value']
            else:
                download_url = file['publicFileLocations'][1]['value']
            logging.debug('ftp_filepath:' + download_url)
            new_file_path = Files.get_output_file_name(download_url, file, output_folder)
            from tqdm import tqdm

            with tqdm(unit='B', unit_scale=True, unit_divisor=1024, miniters=1, desc=file['accession']) as progress_bar:
                urllib.request.urlretrieve(download_url, new_file_path, reporthook=lambda blocks, block_size, total_size: progress_bar.update(block_size))

    @staticmethod
    def get_output_file_name(download_url, file, output_folder):
        public_filepath_part = download_url.rsplit('/', 1)
        logging.debug(file['accession'] + " -> " + public_filepath_part[1])
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        new_file_path = os.path.join(output_folder, f"{file['accession']}-{unique_id}-{public_filepath_part[1]}")
        return new_file_path

    @staticmethod
    def download_files_from_aspera(file_list_json, output_folder):
        """
        Download files using aspera transfer url
        :param file_list_json: file list in json format
        :param output_folder: folder to download the files
        """
        ascp_path = Files.get_ascp_binary()
        key_path = os.path.abspath('aspera/key/asperaweb_id_dsa.openssh')
        for file in file_list_json:
            if file['publicFileLocations'][0]['name'] == 'Aspera Protocol':
                download_url = file['publicFileLocations'][0]['value']
            else:
                download_url = file['publicFileLocations'][1]['value']

            # Create a clean filename to save the downloaded file
            logging.debug(f'Downloading via Aspera: {download_url}')
            new_file_path = Files.get_output_file_name(download_url, file, output_folder)
            try:
                # Execute the ascp command using subprocess
                subprocess.run([
                    ascp_path, '-QT', '-P', '33001', '-l', '100M',  # Options for Aspera: adjust as necessary
                    '-i', key_path,
                    download_url, new_file_path  # Source and destination
                ], check=True)
                logging.info(f'Successfully downloaded {new_file_path} via Aspera')
            except subprocess.CalledProcessError as e:
                logging.error(f'Aspera download failed for {new_file_path}: {str(e)}')

    @staticmethod
    def download_files_from_globus(file_list_json, output_folder):
        """
           Download files using globus transfer url
           :param file_list_json: file list in json format
           :param output_folder: folder to download the files
        """
        for file in file_list_json:
            if file['publicFileLocations'][0]['name'] == 'FTP Protocol':
                download_url = file['publicFileLocations'][0]['value']
            else:
                download_url = file['publicFileLocations'][1]['value']
            logging.debug(f'Downloading fron Globus: {download_url}')
            ftp_base_url = "ftp://ftp.pride.ebi.ac.uk/"
            globus_base_url = "https://g-a8b222.dd271.03c0.data.globus.org/"
            download_url = download_url.replace(ftp_base_url, globus_base_url)
            # Globus download using urllib
            logging.debug(f'Downloading From Globus: {download_url}')
            # Create a clean filename to save the downloaded file
            new_file_path = Files.get_output_file_name(download_url, file, output_folder)
            try:
                urllib.request.urlretrieve(download_url, new_file_path)
                logging.info(f'Successfully downloaded {new_file_path}')
            except Exception as e:
                logging.error(f'Download from globus failed for {new_file_path}: {str(e)}')

    @staticmethod
    def download_files_from_s3(file_list_json, output_folder):
        """
           Download files using s3 transfer url
           :param file_list_json: file list in json format
           :param output_folder: folder to download the files
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        s3_resource = boto3.resource('s3', config=Config(signature_version=botocore.UNSIGNED),
                                     endpoint_url=Files.S3_URL)
        for file in file_list_json:
            try:
                bucket = s3_resource.Bucket(Files.S3_BUCKET)
                if file['publicFileLocations'][0]['name'] == 'FTP Protocol':
                    download_url = file['publicFileLocations'][0]['value']
                else:
                    download_url = file['publicFileLocations'][1]['value']

                ftp_base_url = "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/"
                s3_path = download_url.replace(ftp_base_url, "")
                new_file_path = Files.get_output_file_name(download_url, file, output_folder)
                logging.debug(f'Downloading From S3: {s3_path}')
                bucket.download_file(s3_path, new_file_path)
                logging.info(f'Successfully downloaded {new_file_path}')
                before_last_slash, _, _ = s3_path.rpartition('/')
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "404":
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
        first_file = results[0]['publicFileLocations'][0]['value']
        path_fragment = re.search(r'\d{4}/\d{2}/PXD\d*', first_file).group()
        return path_fragment

    @staticmethod
    def get_files_from_dir(location, regex):
        """
        match files with provided regex in the source location
        :param regex: files to match
        :param location: location to search files
        :return:
        """

        file_list_from_dir = []

        for file in glob.glob(location + regex):
            logging.debug("found file: " + file)
            filename = file.rsplit('/', 1)[1]
            file_list_from_dir.append(filename)
        return file_list_from_dir

    def copy_raw_files_from_dir(self, accession, source_base_directory):
        """
        This function copy raw files from the given directory if they are in the PRIDE FTP folder.
        When copying, prefix the file accession given by PRIDE archive
        :param accession: pride project accession
        :param source_base_directory : file path of the given directory
        """

        # get the full path where you can find the raw files in the file system
        # to support that, data should be written in the following format:
        # base/path/ + yyyy/mm/accession/ + submitted/
        path_fragment = self.get_submitted_file_path_prefix(accession)
        complete_source_dir = source_base_directory + "/" + path_fragment + "/submitted/"

        if not (os.path.isdir(complete_source_dir)):
            logging.exception("Folder does not exists! " + complete_source_dir)

        # get the list of raw files from the given directory
        file_list_from_dir = self.get_files_from_dir(complete_source_dir, "*.raw")

        response_body = self.get_all_raw_file_list(accession)

        self.copy_from_dir(complete_source_dir, file_list_from_dir, response_body)

    def download_file_by_name(self, accession, file_name, output_folder, protocol):
        """
        Download files from url
        :param accession: PRIDE accession
        :param file_name: file name to download
        :param output_folder: folder to download the files
        :param protocol: ftp, aspera, globus
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)
        response = self.get_file_from_api(accession, file_name)
        self.download_files(response, output_folder, protocol)

    def copy_file_from_dir_by_name(self, accession, file_name, input_folder):
        path_fragment = self.get_submitted_file_path_prefix(accession)
        complete_source_dir = input_folder + "/" + path_fragment + "/submitted/"

        if not (os.path.isdir(complete_source_dir)):
            logging.exception("Folder does not exists! " + complete_source_dir)

        file_list_from_dir = self.get_files_from_dir(complete_source_dir, file_name)
        response_body = self.get_file_from_api(accession, file_name)

        self.copy_from_dir(complete_source_dir, file_list_from_dir, response_body)

    def get_file_from_api(self, accession, file_name):
        """
        Fetches file from API
        :param accession: PRIDE accession
        :param file_name: file name
        :return: file in json format
        """
        request_url = self.API_BASE_URL + "files/byProject?accession=" + accession + ",fileName==" + file_name
        headers = {"Accept": "application/JSON"}
        try:
            response = Util.get_api_call(request_url, headers)
            return response.json()
        except Exception as e:
            raise Exception("File not found" + str(e))

    @staticmethod
    def copy_from_dir(complete_source_dir, file_list_from_dir, file_list_json):
        """
        Copy files from nfs directory
        :param complete_source_dir: nfs directory
        :param file_list_from_dir: files to copy
        :param file_list_json: file list from api
        :return:
        """
        for file in file_list_json:
            ftp_filepath = file['publicFileLocations'][0]['value']
            file_name_from_ftp = ftp_filepath.rsplit('/', 1)[1]
            if file_name_from_ftp in file_list_from_dir:
                source_file = complete_source_dir + file_name_from_ftp
                destination_file = file['accession'] + "-" + file_name_from_ftp
                shutil.copy2(source_file, destination_file)
            else:
                logging.error(file_name_from_ftp + " not found in " + complete_source_dir)

    @staticmethod
    def get_ascp_binary():
        """
        Detect the OS and architecture, and return the appropriate ascp binary path.

        Returns:
            str: Path to the correct ascp binary.
        """
        os_type = platform.system().lower()
        arch, _ = platform.architecture()
        aspera_dir = os.path.abspath('aspera/')

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
    def download_files(file_list_json, output_folder, protocol='ftp'):
        """
        Download files using either FTP or Aspera transfer protocol.
        :param file_list_json: File list in JSON format
        :param output_folder: Folder to download the files
        :param protocol: ftp, aspera, globus
        """
        protocols_supported = ['ftp', 'aspera', 'globus', 's3']
        if protocol not in protocols_supported:
            logging.error('Protocol should be either ftp, aspera, globus')
            return

        if protocol == 'ftp':
            Files.download_files_from_ftp(file_list_json, output_folder)
        elif protocol == 'aspera':
            Files.download_files_from_aspera(file_list_json, output_folder)
        elif protocol == 'globus':
            Files.download_files_from_globus(file_list_json, output_folder)
        elif protocol == 's3':
            Files.download_files_from_s3(file_list_json, output_folder)
