#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging

from util.api_handling import Util


class MsRun:
    """
    This class handles metadata related to MSRuns.
    """

    base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def update_msrun_metadata(self, filename, token):
        """
        Updates the metadata extracted from the raw file into MongoDB database
        :param filename: metadata json file
        :param token: pride authentication token to access the api update method
        :return: response
        """

        # get project file accession from the prefix of the file name (e.g: PXF00000145820)
        accession = filename.split('-', 1)[0]

        url = self.base_url + "msruns/" + accession + "/updateMetadata"
        headers = {'Content-type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Bearer ' + token}

        with open(filename) as json_file:
            data = json.load(json_file)
            logging.debug(json.dumps(data))

            response = Util.update_api_call(url, headers, json.dumps(data))

        return response
