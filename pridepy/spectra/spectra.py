#!/usr/bin/env python

from pridepy.util.api_handling import Util


class Spectra:
    """
    This class handles PRIDE API Spectra endpoint.
    """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def spectra_evidences(
        self,
        usi,
        project_accession,
        assay_accession,
        peptide_sequence,
        modified_sequence,
        result_type,
        page_size,
        page,
        sort_direction,
        sort_conditions,
    ):
        """
        Search spectra evidences from PRIDE API
        :param usi: USI
        :param project_accession: PRIDE project accession
        :param assay_accession: PRIDE assay accession
        :param peptide_sequence: PRIDE peptide sequence
        :param modified_sequence: modified sequence
        :param result_type: result type
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: spectra_evidences in JSON format
        """

        request_url = self.api_base_url + "spectra?"

        if usi:
            usi_array = usi.split("\\n")
            for usiElement in usi_array:
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

        request_url = (
            request_url
            + "pageSize="
            + str(page_size)
            + "&page="
            + str(page)
            + "&sortDirection="
            + sort_direction
            + "&sortConditions="
            + sort_conditions
        )

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()
