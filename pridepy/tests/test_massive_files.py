import tempfile
from unittest import TestCase
from unittest.mock import patch

from pridepy.files.files import Files


class TestMassIVEFiles(TestCase):
    def test_is_massive_accession(self):
        assert Files.is_massive_accession("MSV000012345")
        assert Files.is_massive_accession("rmsv000012345")
        assert not Files.is_massive_accession("PXD000012")
        assert not Files.is_massive_accession("MSV123")

    def test_build_massive_file_record_maps_collection_to_category(self):
        record = Files._build_massive_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/ccms_peak/converted/sample.mzML",
        )

        assert record["fileName"] == "sample.mzML"
        assert record["collection"] == "ccms_peak"
        assert record["fileCategory"]["value"] == "PEAK"

    def test_build_massive_file_record_marks_raw_collection_as_raw(self):
        record = Files._build_massive_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run01.raw",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_build_massive_file_record_keeps_non_raw_collection_even_for_raw_like_file_names(self):
        record = Files._build_massive_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/uploads/run01.raw",
        )

        assert record["collection"] == "uploads"
        assert record["fileCategory"]["value"] == "OTHER"

    def test_build_massive_file_record_marks_ab_sciex_scan_sidecar_as_raw_when_under_raw(self):
        record = Files._build_massive_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/sample.wiff.scan",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_get_all_raw_file_list_filters_massive_records(self):
        files = Files()
        massive_records = [
            Files._build_massive_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run1.raw",
            ),
            Files._build_massive_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/quant/results.tsv",
            ),
            Files._build_massive_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/uploads/run2.mzML",
            ),
        ]

        with patch.object(Files, "_list_massive_public_files", return_value=massive_records):
            result = files.get_all_raw_file_list("MSV000012345")

        assert len(result) == 1
        assert {file["fileName"] for file in result} == {"run1.raw"}

    def test_download_file_by_name_uses_massive_ftp_listing(self):
        files = Files()
        file_record = Files._build_massive_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/folder/sample.raw",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(Files, "_list_massive_public_files", return_value=[file_record]), patch.object(
                Files, "download_ftp_urls"
            ) as download_mock:
                files.download_file_by_name(
                    accession="MSV000012345",
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
            ftp_urls=["ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/folder/sample.raw"],
            output_folder=tmp_dir,
            skip_if_downloaded_already=False,
            use_tls=True,
            parallel_files=1,
        )

    def test_repo_uses_tls_true_for_massive_false_for_jpost(self):
        assert Files._repo_uses_tls("MSV000012345") is True
        assert Files._repo_uses_tls("JPST000001") is False
        assert Files._repo_uses_tls("PXD000012") is False

    def test_download_all_raw_files_threads_parallel_files_for_massive(self):
        files = Files()
        massive_records = [
            Files._build_massive_file_record(
                "MSV000012345",
                f"ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run{i}.raw",
            )
            for i in range(3)
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                Files, "_list_massive_public_files", return_value=massive_records
            ), patch.object(Files, "download_ftp_urls") as download_mock:
                files.download_all_raw_files(
                    accession="MSV000012345",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                    aspera_maximum_bandwidth="100M",
                    checksum_check=False,
                    parallel_files=3,
                )

        kwargs = download_mock.call_args.kwargs
        assert kwargs["use_tls"] is True
        assert kwargs["parallel_files"] == 3
