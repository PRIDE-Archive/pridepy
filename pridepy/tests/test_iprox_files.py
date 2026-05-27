import tempfile
from unittest import TestCase
from unittest.mock import patch

from pridepy.files.files import Files


class TestIProXFiles(TestCase):
    def test_is_iprox_accession(self):
        assert Files.is_iprox_accession("IPX0000123")
        assert Files.is_iprox_accession("IPX0000123000")
        assert Files.is_iprox_accession("ipx1234567")
        assert not Files.is_iprox_accession("PXD000012")
        assert not Files.is_iprox_accession("MSV000012345")
        assert not Files.is_iprox_accession("IPX12")

    def test_is_direct_download_accession_includes_iprox(self):
        assert Files.is_direct_download_accession("IPX0000123000")

    def test_build_iprox_file_record_maps_collection_to_category(self):
        record = Files._build_iprox_file_record(
            "IPX0000123000",
            "ftp://ftp.iprox.cn/IPX0000123000/peak/sample.mzML",
        )

        assert record["fileName"] == "sample.mzML"
        assert record["collection"] == "peak"
        assert record["fileCategory"]["value"] == "PEAK"
        assert record["source"] == "iProX"

    def test_build_iprox_file_record_marks_raw_collection_as_raw(self):
        record = Files._build_iprox_file_record(
            "IPX0000123000",
            "ftp://ftp.iprox.cn/IPX0000123000/raw/run01.raw",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_get_all_raw_file_list_filters_iprox_records(self):
        files = Files()
        iprox_records = [
            Files._build_iprox_file_record(
                "IPX0000123000",
                "ftp://ftp.iprox.cn/IPX0000123000/raw/run1.raw",
            ),
            Files._build_iprox_file_record(
                "IPX0000123000",
                "ftp://ftp.iprox.cn/IPX0000123000/result/results.tsv",
            ),
        ]

        with patch.object(Files, "_list_iprox_public_files", return_value=iprox_records), patch.object(
            Files, "stream_all_files_by_project"
        ) as pride_mock:
            result = files.get_all_raw_file_list("IPX0000123000")

        pride_mock.assert_not_called()
        assert len(result) == 1
        assert {file["fileName"] for file in result} == {"run1.raw"}

    def test_download_file_by_name_uses_iprox_ftp_listing(self):
        files = Files()
        file_record = Files._build_iprox_file_record(
            "IPX0000123000",
            "ftp://ftp.iprox.cn/IPX0000123000/raw/folder/sample.raw",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                Files, "_list_iprox_public_files", return_value=[file_record]
            ), patch.object(Files, "download_ftp_urls") as download_mock:
                files.download_file_by_name(
                    accession="IPX0000123000",
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
            ftp_urls=["ftp://ftp.iprox.cn/IPX0000123000/raw/folder/sample.raw"],
            output_folder=tmp_dir,
            skip_if_downloaded_already=False,
        )
