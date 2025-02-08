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

        result = project.search_by_keywords_and_filters(
            keyword="PXD009476",
            query_filter="",
            page_size=100,
            page=0,
            sort_direction="DESC",
            sort_fields="accession",
        )
        assert len(result) > 0  # Search should return at least one result
        assert any(
            r["accession"] == "PXD009476" for r in result
        )  # Search should return the queried project

        result = project.get_projects(77, 0, "ASC", "submission_date")
        assert len(result) == 77

        result = project.get_by_accession("PXD009476")
        assert result["accession"] == "PXD009476"

        assert (
            len(
                project.get_files_by_accession(
                    "PXD009476",
                )
            )
            == 100
        )

    def test_status_dataset(self):

        files = Files()
        accession = "PXD044389"

        project_status = Util.get_api_call(files.API_BASE_URL + "/status/{}".format(accession))
        public_project = False
        if project_status.status_code == 200:
            if project_status.text == "PRIVATE":
                public_project = True
            elif project_status.text == "PUBLIC":
                public_project = False
            else:
                raise Exception("Dataset {} is not present in PRIDE Archive".format(accession))
        logging.debug(f"Public project: {public_project}")
