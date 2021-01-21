#!/usr/bin/env python

from util.api_handling import Util


class Protein:

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def protein_evidences(self, project_accession, assay_accession, reported_accession, page_size,
                          page, sort_direction, sort_conditions):
        """
        search protein evidences from PRIDE api in JSON format
        :return: protein list on JSON format
        """

        request_url = self.api_base_url + "proteinevidences?"

        if project_accession:
            request_url = request_url + "projectAccession=" + project_accession + "&"

        if assay_accession:
            request_url = request_url + "assayAccession=" + assay_accession + "&"

        if reported_accession:
            request_url = request_url + "reportedAccession=" + reported_accession + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + \
                      "&sortDirection=" + sort_direction + \
                      "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()