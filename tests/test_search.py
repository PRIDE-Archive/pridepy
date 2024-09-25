from unittest import TestCase

from files.files import Files
from project.project import Project


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
        assert len(result['_embedded']['projects']) == 77

        result = project.get_by_accession("PXD009476")
        assert result['accession'] == "PXD009476"

        result = project.get_reanalysis_projects_by_accession("PXD000419")
        assert result['accession'] == "PXD000419"

        result = project.get_files_by_accession("PXD009476", "", 100, 0, "ASC", "fileName")
        assert result['page']['totalElements'] == 113

        result = project.get_files_by_accession("PXD009476", "fileCategory.value==RAW", 100, 0, "ASC", "fileName")
        assert result['page']['totalElements'] == 109

        result = project.search_by_keywords_and_filters("accession:PXD008644", "", 100, 0, "", "ASC", "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

        result = project.search_by_keywords_and_filters("", "accession==PXD008644", 100, 0, "", "ASC",
                                                        "submission_date")
        assert len(result['_embedded']['compactprojects']) == 1

    def test_search_files(self):
        """
        A test method to search files
        """

        files = Files()

        result = files.get_all_paged_files("projectAccessions==PXD022105", "100", 0, "ASC", "submissionDate")
        assert result['page']['totalElements'] == 11
