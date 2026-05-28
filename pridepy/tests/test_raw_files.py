from unittest import TestCase

from pridepy.download.client import Client as Files
from pridepy.tests._live_api import tolerate_api_outage


class TestRawFiles(TestCase):
    """
    A test class to test files related methods.

    These hit the live PRIDE API; each call is wrapped in
    :func:`tolerate_api_outage` so a transient API outage skips rather than
    fails the build.
    """

    def test_get_all_raw_file_list(self):
        """
        A test method to check if it is possible to fetch the list of raw files
        """
        raw = Files()
        with tolerate_api_outage(self):
            # This project has only two files
            result = raw.get_all_raw_file_list("PXD008644")
            assert len(result) == 2

    def test_get_raw_file_path_prefix(self):
        """
        At pride repository, public data is disseminated according to a proper structure.
        I.e. base/path/ + yyyy/mm/accession/ + submitted/
        This tests the yyyy/mm/accession path fragment can be correctly extracted from the API by examine the file path
        of a public file.
        I.e. ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2018/10/PXD008644/7550GI_Y.raw
        """
        raw = Files()
        with tolerate_api_outage(self):
            assert raw.get_submitted_file_path_prefix("PXD008644") == "2018/10/PXD008644"

    def test_get_all_category_file_list(self):
        raw = Files()
        with tolerate_api_outage(self):
            result = raw.get_all_category_file_list("PXD008644", "RAW")
            assert len(result) == 2

            result = raw.get_all_category_file_list("PXD008644", "SEARCH")
            assert len(result) == 2

    def test_get_all_category_file_list_multiple(self):
        """
        Test filtering by multiple categories at once.
        PXD008644 has 2 RAW + 2 SEARCH = 4 files combined.
        """
        raw = Files()
        with tolerate_api_outage(self):
            result = raw.get_all_category_file_list("PXD008644", ["RAW", "SEARCH"])
            assert len(result) == 4

            # Verify both categories are present
            categories = {file["fileCategory"]["value"] for file in result}
            assert categories == {"RAW", "SEARCH"}
