#!/usr/bin/env python

from pridepy.authentication.authentication import Authentication
from pridepy.util.api_handling import Util


class Project:
    """
    This class handles PRIDE API Projects endpoint.
    """

    API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v2/"
    V3_API_BASE_URL = "https://www.ebi.ac.uk/pride/ws/archive/v3/"
    PRIVATE_API_BASE_URL = "https://www.ebi.ac.uk/pride/private/ws/archive/v2/"

    def __init__(self):
        pass

    def get_projects(self, page_size, page, sort_direction, sort_conditions):
        """
        get projects from PRIDE API in JSON format
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: paged peptide_evidences in json format
        """
        request_url = (
            self.API_BASE_URL
            + "projects?"
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

    async def stream_all_projects(self, output_file):
        """
        get stream of all projects from PRIDE API in JSON format
        """
        request_url = self.V3_API_BASE_URL + "projects/all"
        count_request_url = self.V3_API_BASE_URL + "projects/count"
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(count_request_url, headers)
        total_records = response.json()
        regex_search_pattern = '"projectDescription"'
        await Util.stream_response_to_file(output_file, total_records, regex_search_pattern, request_url, headers)

    def get_reanalysis_projects_by_accession(self, accession):
        """
        search PRIDE projects by reanalysis accession
        :return: project list on JSON format
        """
        request_url = self.API_BASE_URL + "projects/reanalysis/" + accession
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_by_accession(self, accession):
        """
        search PRIDE projects by accession
        :param accession: PRIDE accession
        :return: project list on JSON format
        """
        request_url = self.API_BASE_URL + "projects/" + accession
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_files_by_accession(
        self, accession, query_filter, page_size, page, sort_direction, sort_conditions
    ):
        """
        search PRIDE project's files by accession
        :param accession: PRIDE project accession
        :param query_filter: Parameters to filter the search results
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_conditions: Field(s) for sorting the results on
        :return: PRIDE project files
        """
        request_url = self.API_BASE_URL + "projects/" + accession + "/files?"

        if query_filter:
            request_url = request_url + "filter=" + query_filter + "&"

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

    def get_private_files_by_accession(self, accession, user, passwd):

        auth = Authentication()
        aap_token = auth.get_token(user, passwd)

        request_url = self.PRIVATE_API_BASE_URL + "projects/" + accession + "/files"
        headers = {"Authorization": "Bearer " + aap_token}

        all_files = []

        while True:
            response = Util.get_api_call(request_url, headers)
            response_json = response.json()
            if "_embedded" in response_json:
                files = response_json["_embedded"]["files"]
                if len(files) > 0:
                    all_files.extend(files)
                    request_url = response_json["_links"]["next"]["href"]
            else:
                break

        return all_files

    def get_similar_projects_by_accession(self, accession):
        """
        Search similar projects by accession
        :param accession: PRIDE accession
        :return: similar PRIDE projects
        """
        """
            search PRIDE project's files by accession
            :return: file list on JSON format
        """
        request_url = self.API_BASE_URL + "projects/" + accession + "/files"
        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def search_by_keywords_and_filters(
        self,
        keyword,
        query_filter,
        page_size,
        page,
        date_gap,
        sort_direction,
        sort_fields,
    ):
        """
        search PRIDE API projects by keyword and filters
        :param keyword: keyword to search projects
        :param query_filter: Parameters to filter the search results
        :param page_size: Number of results to fetch in a page
        :param page: Identifies which page of results to fetch
        :param date_gap: A date range field with possible values of +1MONTH, +1YEAR
        :param sort_direction: Sorting direction: ASC or DESC
        :param sort_fields: Field(s) for sorting the results on
        :return: PRIDE projects in json format
        """
        request_url = self.API_BASE_URL + "search/projects?keyword=" + keyword + "&"

        if query_filter:
            request_url = request_url + "filter=" + query_filter + "&"

        request_url = (
            request_url + "pageSize=" + str(page_size) + "&page=" + str(page) + "&"
        )

        if date_gap != "":
            request_url = request_url + "dateGap=" + str(date_gap) + "&"

        request_url = (
            request_url
            + "sortDirection="
            + sort_direction
            + "&sortFields="
            + sort_fields
        )

        headers = {"Accept": "application/JSON"}
        response = Util.get_api_call(request_url, headers)
        return response.json()

    def get_project_file_names(
        self, accession: str, user: str = None, password: str = None
    ) -> list:

        if user and password:
            files = self.get_private_files_by_accession(accession, user, password)
        else:
            files = self.get_files_by_accession(
                accession, "", 100, 0, "ASC", "fileName"
            )["list"]

        return [file["fileName"] for file in files]
