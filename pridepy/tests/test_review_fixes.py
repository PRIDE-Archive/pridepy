"""Tests for hardening fixes from PR #106 code review.

Covers: exception chaining, defensive guards for empty/partial listings,
FTP host validation, and protocol forwarding in the shared download path.
"""
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

import pytest

from pridepy.download import registry, transport
from pridepy.download.client import Client
from pridepy.download.massive import MassiveProvider
from pridepy.download.pride import PrideProvider


def _pride_record(file_name="a.raw", accession="PXD000001", date="2018/10"):
    return {
        "fileName": file_name,
        "accession": accession,
        "fileCategory": {"value": "RAW"},
        "publicFileLocations": [
            {
                "name": "FTP Protocol",
                "value": f"ftp://ftp.pride.ebi.ac.uk/pride/data/archive/{date}/{accession}/{file_name}",
            }
        ],
    }


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

    def test_get_submitted_prefix_supports_prd_accessions(self):
        provider = PrideProvider()
        records = [_pride_record("a.raw", accession="PRD000123", date="2012/03")]
        with patch.object(provider, "_list_files_checked", return_value=records):
            assert provider.get_submitted_file_path_prefix("PRD000123") == "2012/03/PRD000123"

    def test_aspera_batch_raises_when_a_file_fails(self):
        records = [
            {
                "fileName": "a.raw",
                "accession": "PXD000001",
                "publicFileLocations": [
                    {"name": "Aspera Protocol", "value": "faspe://h/a.raw"}
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(PrideProvider, "get_ascp_binary", return_value="/bin/false"), patch(
                "pridepy.download.pride.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "ascp"),
            ):
                with pytest.raises(RuntimeError, match="Aspera"):
                    PrideProvider.download_files_from_aspera(
                        records, tmp_dir, skip_if_downloaded_already=False
                    )

    def test_globus_batch_raises_when_a_file_fails(self):
        records = [_pride_record("a.raw")]
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                PrideProvider, "_globus_download_one", side_effect=RuntimeError("boom")
            ):
                with pytest.raises(RuntimeError, match="Globus"):
                    PrideProvider.download_files_from_globus(
                        records, tmp_dir, skip_if_downloaded_already=False
                    )

    def test_s3_batch_raises_when_a_file_fails(self):
        records = [_pride_record("a.raw")]
        mock_obj = Mock()
        mock_obj.content_length = 10
        mock_bucket = Mock()
        mock_bucket.Object.return_value = mock_obj
        mock_bucket.download_file.side_effect = Exception("boom")
        mock_resource = Mock()
        mock_resource.Bucket.return_value = mock_bucket
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("pridepy.download.pride.boto3.resource", return_value=mock_resource):
                with pytest.raises(RuntimeError, match="S3"):
                    PrideProvider.download_files_from_s3(
                        records, tmp_dir, skip_if_downloaded_already=False
                    )

    def test_fire_protocol_uses_internal_endpoint_and_derives_key(self):
        """`fire` must hit the EBI-internal FIRE endpoint and map the FTP path
        to the correct pride-public S3 object key."""
        records = [_pride_record("a.raw", accession="PXD002137", date="2015/08")]
        mock_obj = Mock()
        mock_obj.content_length = 10
        mock_bucket = Mock()
        mock_bucket.Object.return_value = mock_obj
        mock_resource = Mock()
        mock_resource.Bucket.return_value = mock_bucket
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.download.pride.boto3.resource", return_value=mock_resource
            ) as mock_boto:
                PrideProvider._batch_download_by_protocol(
                    records,
                    tmp_dir,
                    protocol="fire",
                    skip_if_downloaded_already=False,
                    aspera_maximum_bandwidth="100M",
                )
        # boto3.resource was created against the internal hl.fire endpoint.
        assert mock_boto.call_args.kwargs["endpoint_url"] == PrideProvider.FIRE_S3_URL
        assert "hl.fire.sdo.ebi.ac.uk" in PrideProvider.FIRE_S3_URL
        # The object key is the archive-relative path, no ftp:// prefix.
        mock_bucket.Object.assert_called_once_with("2015/08/PXD002137/a.raw")

    def test_fire_protocol_sequence_requested_only(self):
        """`fire` is tried first when requested, then the public protocols;
        it is never folded into another protocol's fallback chain."""
        assert PrideProvider._protocol_sequence("fire") == [
            "fire", "aspera", "s3", "ftp", "globus",
        ]
        assert "fire" not in PrideProvider._protocol_sequence("ftp")
        assert "fire" not in PrideProvider._protocol_sequence("s3")

    def test_fire_not_retried_in_phase2_fallback(self):
        """After a FIRE (endpoint-level) failure, the per-file Phase-2 fallback
        must go straight to the public protocols and never re-attempt fire."""
        record = _pride_record("a.raw", accession="PXD002137", date="2015/08")
        captured = {}

        def _fake_fallback(*, file_record, output_folder, protocol_sequence, **kw):
            captured["seq"] = protocol_sequence
            return True  # pretend a public protocol succeeded

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(PrideProvider, "_batch_download_by_protocol"), \
                 patch("pridepy.download.pride._provider_util.validate_download",
                       return_value=(False, "missing")), \
                 patch.object(PrideProvider, "_download_with_fallback",
                              side_effect=_fake_fallback):
                PrideProvider._download_files_batch(
                    file_list_json=[record],
                    accession="PXD002137",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="fire",
                )
        assert captured["seq"] == ["aspera", "s3", "ftp", "globus"]
        assert "fire" not in captured["seq"]

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
