"""Unit tests for ``download-files-by-list`` (Case 1).

Covers the :class:`Files` method and the CLI manifest-parsing helper.
Network is fully mocked.
"""

import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

import click
import pytest

from pridepy.files.files import Files
from pridepy.pridepy import _read_filename_arguments
from pridepy.providers.pride import PrideProvider


class TestDownloadFilesByList(TestCase):
    """End-to-end behaviour of ``Files.download_files_by_list``."""

    def test_raises_on_empty_list(self):
        with pytest.raises(ValueError, match="must contain at least one"):
            Files().download_files_by_list(
                accession="PXD001819",
                file_names=[],
                output_folder="/tmp",
                skip_if_downloaded_already=False,
            )

    def test_filters_metadata_and_delegates(self):
        files_obj = Files()
        api_response = [
            {"fileName": "a.raw"},
            {"fileName": "b.raw"},
            {"fileName": "c.raw"},
        ]
        with patch.object(
            PrideProvider, "list_files", return_value=api_response
        ), patch.object(PrideProvider, "download_files") as mock_download:
            files_obj.download_files_by_list(
                accession="PXD001819",
                file_names=["a.raw", "c.raw"],
                output_folder="/tmp",
                skip_if_downloaded_already=False,
                protocol="ftp",
            )

        _, kwargs = mock_download.call_args
        matched = kwargs["records"]
        assert {f["fileName"] for f in matched} == {"a.raw", "c.raw"}

    def test_warns_on_partial_match(self):
        files_obj = Files()
        api_response = [{"fileName": "a.raw"}]
        with patch.object(
            PrideProvider, "list_files", return_value=api_response
        ), patch.object(PrideProvider, "download_files") as mock_download, self.assertLogs(
            level="WARNING"
        ) as log_ctx:
            files_obj.download_files_by_list(
                accession="PXD001819",
                file_names=["a.raw", "missing.raw"],
                output_folder="/tmp",
                skip_if_downloaded_already=False,
            )

        assert any("missing.raw" in record.getMessage() for record in log_ctx.records)
        mock_download.assert_called_once()

    def test_raises_when_no_files_match(self):
        files_obj = Files()
        with patch.object(
            PrideProvider, "list_files", return_value=[]
        ):
            with pytest.raises(ValueError, match="No matching files"):
                files_obj.download_files_by_list(
                    accession="PXD001819",
                    file_names=["a.raw"],
                    output_folder="/tmp",
                    skip_if_downloaded_already=False,
                )


class TestReadFilenameArguments(TestCase):
    """CLI helper that builds the deduplicated filename list."""

    def test_no_input_raises(self):
        with pytest.raises(click.BadParameter):
            _read_filename_arguments(None, None)

    def test_csv_only(self):
        assert _read_filename_arguments(None, "a.raw,b.raw,c.raw") == [
            "a.raw",
            "b.raw",
            "c.raw",
        ]

    def test_manifest_skips_blank_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = os.path.join(tmp_dir, "files.txt")
            with open(manifest, "w", encoding="utf-8") as handle:
                handle.write("a.raw\n\n# comment line\nb.raw\nc.raw\tftp\n")
            assert _read_filename_arguments(manifest, None) == [
                "a.raw",
                "b.raw",
                "c.raw",
            ]

    def test_dedupe(self):
        assert _read_filename_arguments(None, "a.raw,b.raw,a.raw") == [
            "a.raw",
            "b.raw",
        ]

    def test_manifest_plus_csv_dedup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = os.path.join(tmp_dir, "files.txt")
            with open(manifest, "w", encoding="utf-8") as handle:
                handle.write("a.raw\nb.raw\n")
            assert _read_filename_arguments(manifest, "b.raw,c.raw") == [
                "a.raw",
                "b.raw",
                "c.raw",
            ]
