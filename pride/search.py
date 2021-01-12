#!/usr/bin/env python

from util.api_handling import Util


class Search:
    """
    This class handles PRIDE submission raw files.
    """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def projects(self, keywords, filters, page_size, page, date_gap, sort_direction, sort_fields):
        """
        search from PRIDE api in JSON format
        :return: project list on JSON format
        """

        request_url = self.api_base_url + "search/projects?keywords=" + keywords + "&"

        if filters:
            request_url = request_url + "filters=" + filters + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + "&"

        if date_gap != "":
            request_url = request_url + "dateGap=" + str(date_gap) + "&"

        request_url = request_url + "sortDirection=" + sort_direction + "&sortFields=" + sort_fields

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

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

    def spectra_evidences(self, usi, project_accession, assay_accession, peptide_sequence, modified_sequence,
                          result_type,
                          page_size, page, sort_direction, sort_conditions):
        """
        search spectra from PRIDE api in JSON format
        :return: spectra_evidences on JSON format
        """

        request_url = self.api_base_url + "spectra?"

        if usi:
            usiArray = usi.split("\\n")
            for usiElement in usiArray:
                request_url = request_url + "usi=" + usiElement + "&"

        if project_accession:
            request_url = request_url + "projectAccession=" + project_accession + "&"

        if assay_accession:
            request_url = request_url + "assayAccession=" + assay_accession + "&"

        if peptide_sequence:
            request_url = request_url + "peptideSequence=" + peptide_sequence + "&"

        if modified_sequence:
            request_url = request_url + "modifiedSequence=" + modified_sequence + "&"

        if result_type:
            request_url = request_url + "resultType=" + result_type + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + \
                      "&sortDirection=" + sort_direction + \
                      "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()
