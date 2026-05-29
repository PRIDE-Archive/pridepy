import json
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pridepy.download.client import Client as Files
from pridepy.download import transport
from pridepy.download.jpost import JpostProvider


class TestJPOSTFiles(TestCase):
    def test_is_jpost_accession(self):
        assert Files.is_jpost_accession("JPST000001")
        assert Files.is_jpost_accession("jpst123456")
        assert not Files.is_jpost_accession("PXD000012")
        assert not Files.is_jpost_accession("MSV000012345")
        assert not Files.is_jpost_accession("JPST12")

    def test_is_direct_download_accession_includes_jpost(self):
        assert Files.is_direct_download_accession("JPST000001")

    def test_build_jpost_file_record_maps_collection_to_category(self):
        record = JpostProvider._build_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/peak/sample.mzML",
        )

        assert record["fileName"] == "sample.mzML"
        assert record["collection"] == "peak"
        assert record["fileCategory"]["value"] == "PEAK"
        assert record["source"] == "JPOST"

    def test_build_jpost_file_record_marks_raw_collection_as_raw(self):
        record = JpostProvider._build_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/raw/run01.raw",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_get_all_raw_file_list_filters_jpost_records(self):
        files = Files()
        jpost_records = [
            JpostProvider._build_file_record(
                "JPST000001",
                "ftp://ftp.jpostdb.org/JPST000001/raw/run1.raw",
            ),
            JpostProvider._build_file_record(
                "JPST000001",
                "ftp://ftp.jpostdb.org/JPST000001/result/results.tsv",
            ),
        ]

        with patch.object(JpostProvider, "list_files", return_value=jpost_records):
            result = files.get_all_raw_file_list("JPST000001")

        assert len(result) == 1
        assert {file["fileName"] for file in result} == {"run1.raw"}

    def test_download_file_by_name_uses_jpost_ftp_listing(self):
        files = Files()
        file_record = JpostProvider._build_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/raw/folder/sample.raw",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                JpostProvider, "list_files", return_value=[file_record]
            ), patch.object(transport, "download_ftp_urls") as download_mock:
                files.download_file_by_name(
                    accession="JPST000001",
                    file_name="sample.raw",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                    username=None,
                    password=None,
                    aspera_maximum_bandwidth="100M",
                    checksum_check=False,
                )

        download_mock.assert_called_once_with(
            ftp_urls=["ftp://ftp.jpostdb.org/JPST000001/raw/folder/sample.raw"],
            output_folder=tmp_dir,
            skip_if_downloaded_already=False,
            use_tls=False,
            parallel_files=1,
            relative_paths=["sample.raw"],
        )

    def test_proxi_listing_maps_cv_name_to_category(self):
        proxi_response = {
            "datasetFiles": [
                {
                    "accession": "PRIDE:0000404",
                    "name": "Associated raw file URI",
                    "value": "ftp://ftp.jpostdb.org/JPST002311/sample01.raw",
                },
                {
                    "accession": "PRIDE:0000408",
                    "name": "Search engine output file URI",
                    "value": "ftp://ftp.jpostdb.org/JPST002311/sample01.sne",
                },
                {
                    "accession": "PRIDE:0000999",
                    "name": "Some unknown CV",
                    "value": "ftp://ftp.jpostdb.org/JPST002311/misc/sample01.txt",
                },
                {
                    "accession": "PRIDE:0000404",
                    "name": "Associated raw file URI",
                    "value": "https://example.org/not-ftp.raw",
                },
            ]
        }
        fake_response = MagicMock()
        fake_response.content = json.dumps(proxi_response).encode("utf-8")
        fake_response.raise_for_status = MagicMock()
        with patch("pridepy.download.jpost.requests.get", return_value=fake_response) as req_mock:
            records = JpostProvider()._list_via_proxi("JPST002311")

        req_mock.assert_called_once()
        call_url = req_mock.call_args[0][0]
        assert call_url == "https://repository.jpostdb.org/proxi/datasets/JPST002311"
        # Non-FTP URI ignored; three FTP entries kept.
        assert len(records) == 3
        cats = {r["fileName"]: r["fileCategory"]["value"] for r in records}
        assert cats["sample01.raw"] == "RAW"
        assert cats["sample01.sne"] == "SEARCH"
        # Unknown CV falls back to path-based heuristic (collection "misc" -> OTHER).
        assert cats["sample01.txt"] == "OTHER"

    def test_proxi_falls_back_to_ftp_walk_on_error(self):
        with patch.object(
            JpostProvider,
            "_list_via_proxi",
            side_effect=RuntimeError("proxi down"),
        ), patch.object(
            transport, "_list_ftp_repo_files", return_value=["/JPST000001/raw/x.raw"]
        ) as ftp_mock:
            result = JpostProvider().list_files("JPST000001")

        ftp_mock.assert_called_once()
        assert len(result) == 1
        assert result[0]["fileName"] == "x.raw"
        assert result[0]["source"] == "JPOST"
