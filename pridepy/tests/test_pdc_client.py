import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

import pytest

from pridepy.pdc.client import (
    PDCDownloadRequest,
    PDCFile,
    entry_matches_file_type,
    fetch_study_files,
    parse_accessions,
    parse_download_requests,
    refresh_signed_url,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return FakeResponse(self.payload)


def _payload(entries):
    return {"data": {"filesPerStudy": entries}}


def _entry(name, file_format="tsv", data_category="Peptide Spectral Matches", md5sum="900150983cd24fb0d6963f7d28e17f72"):
    return {
        "file_id": "file-1",
        "pdc_study_id": "PDC000109",
        "file_name": name,
        "file_format": file_format,
        "file_size": "3",
        "data_category": data_category,
        "file_type": "Text",
        "file_location": "s3://bucket/key",
        "md5sum": md5sum,
        "signedUrl": {"url": f"https://example.org/{name}"},
    }


class TestPDCAccessions(TestCase):
    def test_single_accession(self):
        assert parse_accessions("PDC000109") == ["PDC000109"]

    def test_accession_not_confused_with_same_named_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            old_cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                os.makedirs("PDC000714")
                assert parse_accessions("PDC000714") == ["PDC000714"]
                assert parse_download_requests("PDC000714") == [PDCDownloadRequest("PDC000714", None)]
            finally:
                os.chdir(old_cwd)

    def test_comma_accessions_are_deduped(self):
        assert parse_accessions("PDC000109,PDC000110,PDC000109") == [
            "PDC000109",
            "PDC000110",
        ]

    def test_csv_pdc_id_column(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,name\nPDC000109,a\nPDC000110,b\nPDC000109,c\n")
            assert parse_accessions(path) == ["PDC000109", "PDC000110"]

    def test_csv_pdc_study_id_column(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_study_id\nPDC000111\n")
            assert parse_accessions(path) == ["PDC000111"]

    def test_csv_file_type_column_creates_mixed_download_requests(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,file-type\nPDC000109,raw\nPDC000110,mzml\n")
            assert parse_download_requests(path) == [
                PDCDownloadRequest("PDC000109", "raw"),
                PDCDownloadRequest("PDC000110", "mzml"),
            ]

    def test_csv_filetype_column_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,filetype\nPDC000109,psm\n")
            assert parse_download_requests(path) == [PDCDownloadRequest("PDC000109", "psm")]

    def test_command_line_file_type_overrides_csv_file_type(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,file-type\nPDC000109,not-a-type\n")
            with self.assertLogs("pridepy.pdc.client", level="WARNING") as logs:
                requests = parse_download_requests(path, file_type="raw")
            assert requests == [PDCDownloadRequest("PDC000109", "raw")]
            assert "overrides CSV file-type values" in "\n".join(logs.output)

    def test_no_file_type_downloads_all_files_for_plain_accession(self):
        assert parse_download_requests("PDC000109") == [PDCDownloadRequest("PDC000109", None)]

    def test_csv_without_file_type_column_downloads_all_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id\nPDC000109\n")
            assert parse_download_requests(path) == [PDCDownloadRequest("PDC000109", None)]

    def test_csv_mixed_file_type_and_no_file_type_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,file-type\nPDC000109,raw\nPDC000110,\n")
            assert parse_download_requests(path) == [
                PDCDownloadRequest("PDC000109", "raw"),
                PDCDownloadRequest("PDC000110", None),
            ]

    def test_csv_missing_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("study\nPDC000111\n")
            with pytest.raises(ValueError, match="pdc_id or pdc_study_id"):
                parse_accessions(path)

    def test_empty_csv_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "studies.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("pdc_study_id\n\n")
            with pytest.raises(ValueError, match="empty"):
                parse_accessions(path)


class TestPDCClient(TestCase):
    def test_psm_filter_keeps_only_psm_suffix(self):
        assert entry_matches_file_type(_entry("sample.psm"), "psm")
        assert not entry_matches_file_type(_entry("sample.tmt11.tsv"), "psm")

    def test_fetch_study_files_maps_graphql_entries(self):
        session = FakeSession(_payload([_entry("sample.psm")]))

        files = fetch_study_files("PDC000109", "psm", session=session)

        assert len(files) == 1
        assert files[0] == PDCFile(
            study_id="PDC000109",
            file_id="file-1",
            file_name="sample.psm",
            file_format="tsv",
            file_size=3,
            data_category="Peptide Spectral Matches",
            file_type="Text",
            file_location="s3://bucket/key",
            md5sum="900150983cd24fb0d6963f7d28e17f72",
            url="https://example.org/sample.psm",
        )
        assert session.calls[0][1]["json"]["variables"] == {"studyId": "PDC000109"}

    def test_fetch_study_files_skips_missing_signed_url(self):
        entry = _entry("sample.psm")
        entry["signedUrl"] = None
        session = FakeSession(_payload([entry]))

        assert fetch_study_files("PDC000109", "psm", session=session) == []

    def test_fetch_study_files_none_file_type_returns_all_files(self):
        entries = [
            _entry("sample.psm", file_format="tsv", data_category="Peptide Spectral Matches"),
            _entry("sample.raw", file_format="vendor-specific", data_category="Raw Mass Spectra"),
        ]
        session = FakeSession(_payload(entries))

        files = fetch_study_files("PDC000109", None, session=session)

        assert len(files) == 2
        assert {f.file_name for f in files} == {"sample.psm", "sample.raw"}

    def test_refresh_signed_url_returns_matching_file(self):
        files = [
            PDCFile("PDC000109", "1", "a.psm", "tsv", 3, "Peptide Spectral Matches", None, None, None, "old"),
            PDCFile("PDC000109", "2", "b.psm", "tsv", 3, "Peptide Spectral Matches", None, None, None, "new"),
        ]
        with patch("pridepy.pdc.client.fetch_study_files", return_value=files):
            assert refresh_signed_url("PDC000109", "b.psm", "psm") == "new"
