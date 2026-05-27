import tempfile
from unittest import TestCase
from unittest.mock import patch

from pridepy.files.files import Files


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
        record = Files._build_jpost_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/peak/sample.mzML",
        )

        assert record["fileName"] == "sample.mzML"
        assert record["collection"] == "peak"
        assert record["fileCategory"]["value"] == "PEAK"
        assert record["source"] == "JPOST"

    def test_build_jpost_file_record_marks_raw_collection_as_raw(self):
        record = Files._build_jpost_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/raw/run01.raw",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_get_all_raw_file_list_filters_jpost_records(self):
        files = Files()
        jpost_records = [
            Files._build_jpost_file_record(
                "JPST000001",
                "ftp://ftp.jpostdb.org/JPST000001/raw/run1.raw",
            ),
            Files._build_jpost_file_record(
                "JPST000001",
                "ftp://ftp.jpostdb.org/JPST000001/result/results.tsv",
            ),
        ]

        with patch.object(Files, "_list_jpost_public_files", return_value=jpost_records), patch.object(
            Files, "stream_all_files_by_project"
        ) as pride_mock:
            result = files.get_all_raw_file_list("JPST000001")

        pride_mock.assert_not_called()
        assert len(result) == 1
        assert {file["fileName"] for file in result} == {"run1.raw"}

    def test_download_file_by_name_uses_jpost_ftp_listing(self):
        files = Files()
        file_record = Files._build_jpost_file_record(
            "JPST000001",
            "ftp://ftp.jpostdb.org/JPST000001/raw/folder/sample.raw",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                Files, "_list_jpost_public_files", return_value=[file_record]
            ), patch.object(Files, "download_ftp_urls") as download_mock:
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
        )
