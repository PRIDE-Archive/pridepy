from unittest import TestCase

from pridepy.files.files import Files


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
