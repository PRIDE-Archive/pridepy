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
        assert kwargs["download_threads"] == 1
        assert kwargs["parallel_files"] == 1

    def test_download_all_public_raw_files_parallel_files(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-all-public-raw-files",
                    "-a",
                    "MSV000012345",
                    "-o",
                    "/tmp/x",
                    "-w",
                    "8",
                ]
            )
        kwargs = files_cls.return_value.download_all_raw_files.call_args.kwargs
        assert kwargs["parallel_files"] == 8

    def test_download_all_public_raw_files_threads(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-all-public-raw-files",
                    "-a",
                    "MSV000012345",
                    "-o",
                    "/tmp/x",
                    "--threads",
                    "4",
                ]
            )
        kwargs = files_cls.return_value.download_all_raw_files.call_args.kwargs
        assert kwargs["download_threads"] == 4
        assert kwargs["parallel_files"] == 1

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
        assert kwargs["download_threads"] == 1
        assert kwargs["parallel_files"] == 1

    def test_download_all_public_category_files_parallel_files(self):
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
                    "-w",
                    "8",
                ]
            )
        kwargs = files_cls.return_value.download_all_category_files.call_args.kwargs
        assert kwargs["parallel_files"] == 8

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
        assert kwargs["download_threads"] == 1
        assert kwargs["parallel_files"] == 1

    def test_download_files_by_list_parallel_files(self):
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
                    "-w",
                    "8",
                ]
            )
        kwargs = files_cls.return_value.download_files_by_list.call_args.kwargs
        assert kwargs["parallel_files"] == 8

    def test_download_files_by_url_threads(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-files-by-url",
                    "-u",
                    "https://example.org/a.raw",
                    "-o",
                    "/tmp/x",
                    "-t",
                    "4",
                ]
            )
        kwargs = files_cls.download_files_by_url.call_args.kwargs
        assert kwargs["download_threads"] == 4
        assert kwargs["parallel_files"] == 1

    def test_download_files_by_url_parallel_files(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-files-by-url",
                    "-u",
                    "https://example.org/a.raw",
                    "-o",
                    "/tmp/x",
                    "-w",
                    "8",
                ]
            )
        kwargs = files_cls.download_files_by_url.call_args.kwargs
        assert kwargs["parallel_files"] == 8

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

    def test_download_px_raw_files_protocol_threads_parallel(self):
        with patch("pridepy.pridepy.Files") as files_cls:
            self._invoke(
                [
                    "download-px-raw-files",
                    "-a",
                    "PXD000001",
                    "-o",
                    "/tmp/x",
                    "-w",
                    "8",
                    "-t",
                    "4",
                    "-p",
                    "ftp",
                ]
            )
        kwargs = files_cls.return_value.download_px_raw_files.call_args.kwargs
        assert kwargs["parallel_files"] == 8
        assert kwargs["download_threads"] == 4
        assert kwargs["protocol"] == "ftp"
