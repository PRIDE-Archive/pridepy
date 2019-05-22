#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script mainly fetches a access token from the API and
secondly update the msrun metadata via API endpoint
"""

import json
import sys

import requests


class MsRun:
    base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def update_msrun_metadata(self, filename, token):
        # get project file accession from the prefix of the file name (e.g: PXF00000145820)
        accession = filename.split('-', 1)[0]

        url = self.base_url + "msruns/" + accession + "/updateMetadata"
        headers = {'Content-type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token}

        with open(filename) as json_file:
            data = json.load(json_file)
            print(json.dumps(data))
            response = requests.put(url, data=json.dumps(data), headers=headers)

            if (not response.ok) or response.status_code != 200:
                response.raise_for_status()
                sys.exit()
            else:
                print(response)