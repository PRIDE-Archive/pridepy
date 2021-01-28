#!/usr/bin/env python

from util.api_handling import Util


class Peptide:
    """
        This class handles PRIDE API Peptide endpoint.
    """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def peptide_evidences(self, project_accession, assay_accession, protein_accession,
                          peptide_evidence_accession, peptide_sequence,
                          page_size, page, sort_direction, sort_conditions):
        """
        search peptide_evidences from PRIDE API in JSON format
        :param project_accession: PRIDE accession
        :param assay_accession: PRIDE assay accession
        :param protein_accession: PRIDE protein accession
        :param peptide_evidence_accession: PRIDE peptide evidence accession
        :param peptide_sequence: PRIDE peptide sequence
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: paged peptide_evidences in json format
        """

        request_url = self.api_base_url + "peptideevidences?"

        if project_accession:
            request_url = request_url + "projectAccession=" + project_accession + "&"

        if assay_accession:
            request_url = request_url + "assayAccession=" + assay_accession + "&"

        if protein_accession:
            request_url = request_url + "proteinAccession=" + protein_accession + "&"

        if peptide_evidence_accession:
            request_url = request_url + "peptideEvidenceAccession=" + peptide_evidence_accession + "&"

        if peptide_sequence:
            request_url = request_url + "peptideSequence=" + peptide_sequence + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(
            page) + "&sortDirection=" + sort_direction + "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()
