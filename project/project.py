#!/usr/bin/env python

from util.api_handling import Util


class Project:
    """
    This class handles PRIDE submission raw files.
    """

    api_base_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/"

    def __init__(self):
        pass

    def get_projects(self, page_size, page, sort_direction, sort_conditions):
        """
            search from PRIDE api in JSON format
            :return: project list on JSON format
        """
        request_url = self.api_base_url + "projects?" + "pageSize=" + str(page_size) + "&page=" + str(page) + "&sortDirection=" + sort_direction + "&sortConditions=" + sort_conditions
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_reanalysis_projects_by_accession(self, accession):
        """
            search PRIDE projects by reanalysis accession
            :return: project list on JSON format
        """
        request_url = self.api_base_url + "projects/reanalysis/" + accession
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_by_accession(self, accession):
        """
            search PRIDE projects by accession
            :return: project list on JSON format
        """
        request_url = self.api_base_url + "projects/" + accession
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_files_by_accession(self, accession, query_filter, page_size, page, sort_direction, sort_conditions):
        """
            search PRIDE project's files by accession
            :return: file list on JSON format
        """
        request_url = self.api_base_url + "projects/" + accession + "/files?"

        if query_filter:
            request_url = request_url + "filter=" + query_filter + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + "&sortDirection=" + sort_direction + "&sortConditions=" + sort_conditions

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_similar_projects_by_accession(self, accession):
        """
            search PRIDE project's files by accession
            :return: file list on JSON format
        """
        request_url = self.api_base_url + "projects/" + accession + "/files"
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def search_by_keywords_and_filters(self, keyword, filter, page_size, page, date_gap, sort_direction, sort_fields):
        """
        search from PRIDE api in JSON format
        :return: project list on JSON format
        """

        request_url = self.api_base_url + "search/projects?keyword=" + keyword + "&"

        if filter:
            request_url = request_url + "filter=" + filter + "&"

        request_url = request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + "&"

        if date_gap != "":
            request_url = request_url + "dateGap=" + str(date_gap) + "&"

        request_url = request_url + "sortDirection=" + sort_direction + "&sortFields=" + sort_fields

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()
