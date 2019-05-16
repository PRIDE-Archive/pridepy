from unittest import TestCase

from files.raw import RawFiles


class TestRawFiles(TestCase):


    def test_get_all_raw_file_list(self):
        raw = RawFiles()
        result = raw.get_all_raw_file_list("PXD008644")
