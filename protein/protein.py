#!/usr/bin/env python

from util.api_handling import Util


class Protein:
    """
        This class handles PRIDE API Protein endpoint.
    """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def protein_evidences(self, project_accession, assay_accession, reported_accession, page_size,
                          page, sort_direction, sort_conditions):
        """
        search protein_evidences from PRIDE API
        :param project_accession: PRIDE accession
        :param assay_accession: PRIDE assay accession
        :param reported_accession: PRIDE reported accession
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: return protein evidences in json format
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
