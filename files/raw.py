#!/usr/bin/env python

"""
This script mainly holds raw files related methods
"""
import os
import re
import glob
import urllib
import shutil
import urllib.request
from util.api_handling import Util


class RawFiles:
    """ This class handles PRIDE submission raw files """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def get_all_raw_file_list(self, project_accession):
        """
        Get all the file list from PRIDE api in JSON format
        :return: file list on JSON format
        """
        request_url = self.api_base_url + "files/byProject?accession=" + project_accession + ",fileCategory.value==RAW"
        headers = {"Accept": "application/JSON"}

        response = Util.call_api(request_url, headers)
        return response.json()

    def download_raw_files_from_ftp(self, accession, output_folder):
        """
        This method will download all the raw files from PRIDE FTP
        :param output_folder: output directory where raw files will get saved
        :param accession: PRIDE accession
        :return: None
        """

        if not (os.path.isdir(output_folder)):
            os.mkdir(output_folder)

        response_body = self.get_all_raw_file_list(accession)

        for raw_file in response_body:
            ftp_filepath = raw_file['publicFileLocations'][0]['value']
            print('ftp_filepath:' + ftp_filepath)
            public_filepath_part = ftp_filepath.rsplit('/', 1)
            print(raw_file['accession'] + " -> " + public_filepath_part[1])
            new_file_path = raw_file['accession'] + "-" + public_filepath_part[1]
            urllib.request.urlretrieve(ftp_filepath, output_folder + new_file_path)

    def get_raw_file_path_prefix(self, accession):

        results = self.get_all_raw_file_list(accession)
        first_file = results[0]['publicFileLocations'][0]['value']
        path_fragment = re.search(r'\d{4}/\d{2}/PXD\d*', first_file).group()
        return path_fragment

    def get_raw_files_from_dir(self, location):
        """
        Copy raw files from the given directory
        :param location:
        :return:
        """

        file_list_from_dir = []

        for file in glob.glob(location + "*.raw"):
            print("found file: " + file)
            filename = file.rsplit('/', 1)[1]
            file_list_from_dir.append(filename)
        return file_list_from_dir

    def copy_raw_files_from_dir(self, accession, source_base_directory):
        """
        This function copy files from the given directory if they are in the PRIDE FTP folder.
        When copying, prefix the file accession given by PRIDE archive
        :param accession: pride project accession
        :param file_list_from_dir: list of raw files in the given directory
        :param source_directory: file path of the given directory
        :return:
        """

        # get the full path where you can find the raw files in the file system
        # to support that, data should be written in following format:
        # base/path/ + yyyy/mm/accession/ + submitted/
        path_fragment = self.get_raw_file_path_prefix(accession)
        complete_source_dir = source_base_directory + "/" + path_fragment + "/submitted/"

        if not (os.path.isdir(complete_source_dir)):
            print("Folder does not exists! " + complete_source_dir)

        # get the list of raw files from the given directory
        file_list_from_dir = self.get_raw_files_from_dir(complete_source_dir)

        response_body = self.get_all_raw_file_list(accession)

        for raw_file in response_body:
            ftp_filepath = raw_file['publicFileLocations'][0]['value']
            file_name_from_ftp = ftp_filepath.rsplit('/', 1)[1]
            if file_name_from_ftp in file_list_from_dir:
                source_file = complete_source_dir + file_name_from_ftp
                destination_file = raw_file['accession'] + "-" + file_name_from_ftp
                print(source_file + "-->" + destination_file)
                shutil.copy2(source_file, destination_file)
            else:
                print(file_name_from_ftp + " not found in " + complete_source_dir)
