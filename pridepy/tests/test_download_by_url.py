"""Unit tests for ``download-files-by-url`` (Case 4).

Covers :meth:`Files.download_files_by_url`, the per-URL dispatcher, and the CLI
manifest-parsing helper. All network access is mocked.
"""

import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

import click
import pytest

from pridepy.commands import by_url
from pridepy.files.files import Files
from pridepy.pridepy import _read_url_arguments


def _touch_valid(path):
    """Create a non-empty file at *path* (used as a faux successful download)."""
    with open(path, "wb") as handle:
        handle.write(b"data")


class TestDownloadFilesByUrl(TestCase):
    """Behaviour of ``Files.download_files_by_url``."""

    def test_raises_on_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(ValueError, match="must contain at least one"):
                Files.download_files_by_url(urls=[], output_folder=tmp_dir)

    def test_dispatches_http(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "sample.raw")

            def fake_http(_url, target_path):
                _touch_valid(target_path)

            with patch.object(
                by_url, "_http_download_url", side_effect=fake_http
            ) as mock_http:
                Files.download_files_by_url(
                    urls=["https://example.org/sample.raw"],
                    output_folder=tmp_dir,
                )

            mock_http.assert_called_once()
            assert os.path.exists(target)

    def test_dispatches_ftp(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "sample.raw")

            def fake_ftp(_parsed, target_path):
                _touch_valid(target_path)

            with patch.object(
                by_url, "_ftp_download_url", side_effect=fake_ftp
            ) as mock_ftp:
                Files.download_files_by_url(
                    urls=["ftp://ftp.pride.ebi.ac.uk/path/sample.raw"],
                    output_folder=tmp_dir,
                )

            mock_ftp.assert_called_once()
            assert os.path.exists(target)

    def test_unsupported_scheme_aggregates_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(RuntimeError, match=r"Failed to download 1 URL"):
                Files.download_files_by_url(
                    urls=["s3://bucket/key/sample.raw"],
                    output_folder=tmp_dir,
                )

    def test_aggregates_multiple_failures(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(RuntimeError, match=r"Failed to download 2 URL"):
                Files.download_files_by_url(
                    urls=["s3://b/k/x.raw", "wat://y/z.raw"],
                    output_folder=tmp_dir,
                )

    def test_skip_if_exists_short_circuits(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "existing.raw")
            _touch_valid(target)
            with patch.object(by_url, "_http_download_url") as mock_http:
                Files.download_files_by_url(
                    urls=["https://example.org/existing.raw"],
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=True,
                )

            mock_http.assert_not_called()
            assert os.path.isfile(target)

    def test_no_scheme_raises_aggregated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(RuntimeError, match=r"Failed to download 1 URL"):
                Files.download_files_by_url(
                    urls=["bare-string-without-scheme"],
                    output_folder=tmp_dir,
                )


class TestReadUrlArguments(TestCase):
    """CLI helper that builds the deduplicated URL list."""

    def test_no_input_raises(self):
        with pytest.raises(click.BadParameter):
            _read_url_arguments(None)

    def test_single_url(self):
        assert _read_url_arguments(None, "https://example.org/a.raw") == [
            "https://example.org/a.raw"
        ]

    def test_multiple_urls_csv(self):
        assert _read_url_arguments(
            None,
            "https://a.com/x.raw,ftp://b.com/y.raw,https://a.com/x.raw",
        ) == ["https://a.com/x.raw", "ftp://b.com/y.raw"]

    def test_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = os.path.join(tmp_dir, "urls.txt")
            with open(manifest, "w", encoding="utf-8") as handle:
                handle.write(
                    "https://a.com/x.raw\n"
                    "# comment\n"
                    "\n"
                    "ftp://b.com/y.raw\n"
                )
            assert _read_url_arguments(manifest, None) == [
                "https://a.com/x.raw",
                "ftp://b.com/y.raw",
            ]

    def test_manifest_plus_csv_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest = os.path.join(tmp_dir, "urls.txt")
            with open(manifest, "w", encoding="utf-8") as handle:
                handle.write("https://a.com/x.raw\nhttps://a.com/y.raw\n")
            assert _read_url_arguments(
                manifest, "https://a.com/y.raw,ftp://b.com/z.raw"
            ) == [
                "https://a.com/x.raw",
                "https://a.com/y.raw",
                "ftp://b.com/z.raw",
            ]
