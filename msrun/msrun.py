#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import requests

"""
This script mainly holds msrun metadata related methods
"""

base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

def updateMsrunMetadata(filename, token):
    '''
    This method update the msrun metadata into PRIDE mongoDB by an endpoint
    :param filename: JSON file with metadata
    :param token: AAP token for authentication
    :return:
    '''

    # get project file accession from the prefix of the file name
    accession = filename.split('-', 1)[0]

    url = base_url + "msruns/" + accession + "/updateMetadata"
    headers = {'Content-type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token}

    with open(filename) as json_file:
        data = json.load(json_file)
        response = requests.put(url, data=json.dumps(data), headers=headers)

        if (not response.ok) or response.status_code != 200:
            return response.raise_for_status()
        else:
            return response