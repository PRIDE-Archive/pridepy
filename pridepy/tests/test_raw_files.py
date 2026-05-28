import unittest
from unittest import TestCase

import requests

from pridepy.download.client import Client as Files

_PRIDE_API_ROOT = "https://www.ebi.ac.uk/pride/ws/archive/v3/"


def _pride_api_reachable() -> bool:
    """Return True if the live PRIDE API answers; False on a network error.

    These are integration tests that hit the real API. Skipping (rather than
    failing) when the API is unreachable keeps CI deterministic instead of
    flaking on a transient read timeout.
    """
    try:
        requests.get(_PRIDE_API_ROOT, timeout=15)
        return True
    except requests.RequestException:
        return False


@unittest.skipUnless(
    _pride_api_reachable(), "PRIDE API not reachable (live integration test)"
)
class TestRawFiles(TestCase):
    """
    A test class to test files related methods.
    """

    def test_get_all_raw_file_list(self):
        """
        A test method to check if it is possible to fetch the list of raw files
        """
        raw = Files()

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
        assert raw.get_submitted_file_path_prefix("PXD008644") == "2018/10/PXD008644"

    def test_get_all_category_file_list(self):

        raw = Files()
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
        result = raw.get_all_category_file_list("PXD008644", ["RAW", "SEARCH"])
        assert len(result) == 4

        # Verify both categories are present
        categories = {file["fileCategory"]["value"] for file in result}
        assert categories == {"RAW", "SEARCH"}
