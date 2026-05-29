"""Tests for hardening fixes from PR #106 code review.

Covers: exception chaining, defensive guards for empty/partial listings,
FTP host validation, and protocol forwarding in the shared download path.
"""
import tempfile
from unittest import TestCase
from unittest.mock import patch

import pytest

from pridepy.download import registry, transport
from pridepy.download.client import Client
from pridepy.download.massive import MassiveProvider
from pridepy.download.pride import PrideProvider


class TestReviewFixes(TestCase):
    def test_get_file_from_api_chains_original_exception(self):
        with patch.object(registry, "resolve", side_effect=KeyError("boom")):
            with pytest.raises(Exception) as exc_info:
                Client().get_file_from_api("PXD000001", "x.raw")
        # The original cause must be preserved for debugging.
        assert isinstance(exc_info.value.__cause__, KeyError)

    def test_get_submitted_prefix_raises_clear_error_when_no_raw_files(self):
        provider = PrideProvider()
        records = [
            {
                "fileName": "results.tsv",
                "fileCategory": {"value": "SEARCH"},
                "publicFileLocations": [
                    {"name": "FTP Protocol", "value": "ftp://h/2018/10/PXD1/results.tsv"}
                ],
            }
        ]
        with patch.object(provider, "_list_files_checked", return_value=records):
            with pytest.raises(ValueError):  # not a bare IndexError
                provider.get_submitted_file_path_prefix("PXD1")

    def test_get_submitted_prefix_raises_clear_error_when_path_has_no_prefix(self):
        provider = PrideProvider()
        records = [
            {
                "fileName": "a.raw",
                "fileCategory": {"value": "RAW"},
                "publicFileLocations": [
                    {"name": "FTP Protocol", "value": "ftp://host/no-date-here/a.raw"}
                ],
            }
        ]
        with patch.object(provider, "_list_files_checked", return_value=records):
            with pytest.raises(ValueError):  # not a bare AttributeError on None.group()
                provider.get_submitted_file_path_prefix("PXD1")

    def test_download_ftp_urls_rejects_url_without_host(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(ValueError, match="host"):
                transport.download_ftp_urls(
                    ftp_urls=["ftp:///pride/data/x.raw"],  # no hostname
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                )

    def test_get_raw_files_tolerates_records_missing_category(self):
        records = [
            {"fileName": "a.raw"},  # no fileCategory at all
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/b.raw",
            ),
        ]
        with patch.object(MassiveProvider, "list_files", return_value=records):
            result = MassiveProvider().get_raw_files("MSV000012345")
        assert {r["fileName"] for r in result} == {"b.raw"}

    def test_download_files_forwards_protocol_to_get_download_url(self):
        seen = []

        class _CapturingProvider(MassiveProvider):
            def get_download_url(self, record, protocol="ftp"):
                seen.append(protocol)
                return record["publicFileLocations"][0]["value"]

        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a.raw",
        )
        with patch.object(transport, "download_ftp_urls"):
            _CapturingProvider().download_files(
                accession="MSV000012345",
                records=[record],
                output_folder="/tmp/x",
                skip_if_downloaded_already=False,
                protocol="aspera",
                parallel_files=1,
            )
        assert seen == ["aspera"]
