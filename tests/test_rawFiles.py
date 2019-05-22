from unittest import TestCase
import re

from files.raw import RawFiles


class TestRawFiles(TestCase):

    def test_get_all_raw_file_list(self):
        raw = RawFiles()
        result = raw.get_all_raw_file_list("PXD008644")

    def test_get_raw_file_path_prefix(self):
        raw = RawFiles()
        assert raw.get_raw_file_path_prefix("PXD008644") == "2018/10/PXD008644"

    def test_copy_raw_files_from_dir(self):
        raw = RawFiles()
        raw.copy_raw_files_from_dir("PXD008644", "/Users/hewapathirana/Downloads/archive")
