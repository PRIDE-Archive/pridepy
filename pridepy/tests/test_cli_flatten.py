"""CLI wiring for the --preserve-structure flag.

By default the download commands flatten into the output folder (flatten=True);
--preserve-structure flips that to flatten=False.
"""
from unittest import TestCase
from unittest.mock import patch

from click.testing import CliRunner

from pridepy.pridepy import main


class TestCliPreserveStructure(TestCase):
    def _invoke(self, args):
        return CliRunner().invoke(main, args, catch_exceptions=False)

    def test_download_all_public_raw_files_flattens_by_default(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                ["download-all-public-raw-files", "-a", "MSV000012345", "-o", "/tmp/x"]
            )
        kwargs = files_cls.return_value.download_all_raw_files.call_args.kwargs
        assert kwargs["flatten"] is True

    def test_download_all_public_raw_files_preserve_structure(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-all-public-raw-files",
                    "-a",
                    "MSV000012345",
                    "-o",
                    "/tmp/x",
                    "--preserve-structure",
                ]
            )
        kwargs = files_cls.return_value.download_all_raw_files.call_args.kwargs
        assert kwargs["flatten"] is False

    def test_download_all_public_category_files_preserve_structure(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-all-public-category-files",
                    "-a",
                    "MSV000012345",
                    "-o",
                    "/tmp/x",
                    "-c",
                    "RAW",
                    "--preserve-structure",
                ]
            )
        kwargs = files_cls.return_value.download_all_category_files.call_args.kwargs
        assert kwargs["flatten"] is False

    def test_download_files_by_list_preserve_structure(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-files-by-list",
                    "-a",
                    "MSV000012345",
                    "-o",
                    "/tmp/x",
                    "-f",
                    "a.raw",
                    "--preserve-structure",
                ]
            )
        kwargs = files_cls.return_value.download_files_by_list.call_args.kwargs
        assert kwargs["flatten"] is False

    def test_download_px_raw_files_preserve_structure(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-px-raw-files",
                    "-a",
                    "PXD000001",
                    "-o",
                    "/tmp/x",
                    "--preserve-structure",
                ]
            )
        kwargs = files_cls.return_value.download_px_raw_files.call_args.kwargs
        assert kwargs["flatten"] is False
