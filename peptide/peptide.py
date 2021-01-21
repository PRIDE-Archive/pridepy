#!/usr/bin/env python

from util.api_handling import Util


class Peptide:
    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def peptide_evidences(self, project_accession, assay_accession, protein_accession,
                          peptide_evidence_accession, peptide_sequence,
                          page_size, page, sort_direction, sort_conditions):
        """
        search peptide_evidences from PRIDE api in JSON format
        :return: peptide_evidences on JSON format
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

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + \
                      "&sortDirection=" + sort_direction + \
                      "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()