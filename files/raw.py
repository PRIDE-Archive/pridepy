#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import glob
import sys
import requests
from util.api_handling import APIUtil

"""
This script mainly holds raw files related methods
"""

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

def get_all_raw_file_list(project_accession):
    """
    Get all the file list from PRIDE api in JSON format
    :return: file list on JSON format
    """
    requestURL = base_url + "files/byProject?accession=" + project_accession + ",fileCategory.value==RAW"
    headers = {"Accept": "application/JSON"}

    response = APIUtil.call_api(requestURL, headers)

    return response.json()

def getProjectPublicFTPPath(project_accession):
    """
    This method returns the project file FTP path which contains all the files in the submission
    :param project_accession: Project accession
    :return: FTP file path for all the files
    """
    requestURL = base_url + "files/byProject?accession=" + project_accession + ",fileCategory.value==RAW"
    response = requests.get(requestURL, headers={"Accept": "application/JSON"})

    if (not response.ok) or response.status_code != 200:
        response.raise_for_status()
        sys.exit()

    responseBody = response.json()
    raw_file = responseBody[0]
    public_filepath = raw_file['publicFileLocations'][0]['value']
    public_filepath_part = public_filepath.rsplit('/', 1)
    public_filepath_folder = public_filepath_part[0] + "/"
    return public_filepath_folder

def copy_raw_files_from_dir(project_accession, location):
    """
    Copy raw files from the given directory
    :param location:
    :return:
    """

    # if location does not end with a slash, then add a one
    if not location.endswith('/'):
        location += '/'

    for file in glob.glob(location + "*.*"):
        raw_filename = os.path.split(file)[1]
        print(raw_filename)

    response = get_all_raw_file_list(project_accession)

if __name__ == '__main__':
    copy_raw_files_from_dir('PXD008644', '/Users/hewapathirana/Downloads/nextflow_data/PXD008644/data/')