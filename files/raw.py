#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import requests

"""
This script mainly holds raw files related methods
"""

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"


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
