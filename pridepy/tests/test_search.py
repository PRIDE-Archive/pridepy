from unittest import TestCase

from pridepy.files.files import Files
from pridepy.project.project import Project
from pridepy.util.api_handling import Util
import logging


class TestSearch(TestCase):
    """
    A test class to test files related methods.
    """

    def test_search_projects(self):
        """
        A test method to search projects
        """
        project = Project()

        result = project.get_projects(77, 0, "ASC", "submission_date")
        assert len(result["_embedded"]["projects"]) == 68

        result = project.get_by_accession("PXD009476")
        assert result["accession"] == "PXD009476"

        result = project.get_reanalysis_projects_by_accession("PXD000419")
        assert result["accession"] == "PXD000419"

        result = project.get_files_by_accession(
            "PXD009476", "", 100, 0, "ASC", "fileName"
        )
        assert result["page"]["totalElements"] == 113

        result = project.get_files_by_accession(
            "PXD009476", "fileCategory.value==RAW", 100, 0, "ASC", "fileName"
        )
        assert result["page"]["totalElements"] == 109

        result = project.search_by_keywords_and_filters(
            "accession:PXD008644", "", 100, 0, "", "ASC", "submission_date"
        )
        assert len(result["_embedded"]["compactprojects"]) == 1

        result = project.search_by_keywords_and_filters(
            "", "accession==PXD008644", 100, 0, "", "ASC", "submission_date"
        )
        assert len(result["_embedded"]["compactprojects"]) == 1

    def test_search_files(self):
        """
        A test method to search files
        """

        files = Files()

        result = files.get_all_paged_files(
            "projectAccessions==PXD022105", "100", 0, "ASC", "submissionDate"
        )
        assert result["page"]["totalElements"] == 11

    def test_status_dataset(self):

        files = Files()
        accession = "PXD044389"

        project_status = Util.get_api_call(
            files.API_BASE_URL + "/status/{}".format(accession)
        )
        public_project = False
        if project_status.status_code == 200:
            if project_status.text == "PRIVATE":
                public_project = True
            elif project_status.text == "PUBLIC":
                public_project = False
            else:
                raise Exception(
                    "Dataset {} is not present in PRIDE Archive".format(accession)
                )
        logging.debug(f"Public project: {public_project}")
