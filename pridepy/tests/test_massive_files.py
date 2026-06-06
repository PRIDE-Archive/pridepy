import ftplib
import tempfile
from unittest import TestCase
from unittest.mock import patch

from pridepy.download.client import Client as Files
from pridepy.download import transport
from pridepy.download.massive import MassiveProvider


class TestMassIVEFiles(TestCase):
    def test_is_massive_accession(self):
        assert Files.is_massive_accession("MSV000012345")
        assert Files.is_massive_accession("rmsv000012345")
        assert not Files.is_massive_accession("PXD000012")
        assert not Files.is_massive_accession("MSV123")

    def test_build_massive_file_record_maps_collection_to_category(self):
        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/ccms_peak/converted/sample.mzML",
        )

        assert record["fileName"] == "sample.mzML"
        assert record["collection"] == "ccms_peak"
        assert record["fileCategory"]["value"] == "PEAK"

    def test_build_massive_file_record_marks_raw_collection_as_raw(self):
        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run01.raw",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_build_massive_file_record_keeps_non_raw_collection_even_for_raw_like_file_names(self):
        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/uploads/run01.raw",
        )

        assert record["collection"] == "uploads"
        assert record["fileCategory"]["value"] == "OTHER"

    def test_build_massive_file_record_marks_ab_sciex_scan_sidecar_as_raw_when_under_raw(self):
        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/sample.wiff.scan",
        )

        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"

    def test_get_all_raw_file_list_filters_massive_records(self):
        files = Files()
        massive_records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run1.raw",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/quant/results.tsv",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/uploads/run2.mzML",
            ),
        ]

        with patch.object(MassiveProvider, "list_files", return_value=massive_records):
            result = files.get_all_raw_file_list("MSV000012345")

        assert len(result) == 1
        assert {file["fileName"] for file in result} == {"run1.raw"}

    def test_download_file_by_name_uses_massive_ftp_listing(self):
        files = Files()
        file_record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/folder/sample.raw",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(MassiveProvider, "list_files", return_value=[file_record]), patch.object(
                transport, "download_ftp_urls"
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
            relative_paths=["sample.raw"],
        )

    def test_repo_uses_tls_true_for_massive_false_for_jpost(self):
        assert Files._repo_uses_tls("MSV000012345") is True
        assert Files._repo_uses_tls("JPST000001") is False
        assert Files._repo_uses_tls("PXD000012") is False

    def test_download_all_raw_files_threads_parallel_files_for_massive(self):
        files = Files()
        massive_records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                f"ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/run{i}.raw",
            )
            for i in range(3)
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                MassiveProvider, "list_files", return_value=massive_records
            ), patch.object(transport, "download_ftp_urls") as download_mock:
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

    def test_base_direct_download_provider_partitions_urls_by_scheme(self):
        """Records mixing ftp:// and http(s):// route to the right transport."""
        from pridepy.download.massive import MassiveProvider

        provider = MassiveProvider()
        records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a.raw",
            ),
            # Synthetic http record to verify partitioning (real MassIVE uses ftp).
            {
                "accession": "MSV000012345",
                "fileName": "b.raw",
                "fileCategory": {"value": "RAW"},
                "publicFileLocations": [
                    {"name": "FTP Protocol", "value": "http://example.org/b.raw"}
                ],
            },
        ]
        with patch.object(transport, "download_ftp_urls") as ftp_mock, \
             patch.object(transport, "download_http_urls") as http_mock:
            provider.download_files(
                accession="MSV000012345",
                records=records,
                output_folder="/tmp/test",
                skip_if_downloaded_already=False,
                protocol="ftp",
                parallel_files=1,
            )

        ftp_mock.assert_called_once()
        assert ftp_mock.call_args.kwargs["use_tls"] is True
        assert ftp_mock.call_args.kwargs["ftp_urls"] == [
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a.raw"
        ]
        http_mock.assert_called_once()
        assert http_mock.call_args.kwargs["http_urls"] == ["http://example.org/b.raw"]

    def test_download_files_flattens_into_output_folder_by_default(self):
        """By default, files land directly in the output folder (no tree), and
        colliding basenames are de-duplicated."""
        provider = MassiveProvider()
        records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a/run.raw",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/b/run.raw",
            ),
        ]
        with patch.object(transport, "download_ftp_urls") as ftp_mock:
            provider.download_files(
                accession="MSV000012345",
                records=records,
                output_folder="/tmp/test",
                skip_if_downloaded_already=False,
                protocol="ftp",
                parallel_files=1,
            )

        assert ftp_mock.call_args.kwargs["relative_paths"] == ["run.raw", "run_1.raw"]

    def test_download_files_preserves_structure_when_flatten_false(self):
        provider = MassiveProvider()
        records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a/run.raw",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/b/run.raw",
            ),
        ]
        with patch.object(transport, "download_ftp_urls") as ftp_mock:
            provider.download_files(
                accession="MSV000012345",
                records=records,
                output_folder="/tmp/test",
                skip_if_downloaded_already=False,
                protocol="ftp",
                parallel_files=1,
                flatten=False,
            )

        assert ftp_mock.call_args.kwargs["relative_paths"] == [
            "raw/a/run.raw",
            "raw/b/run.raw",
        ]

    def test_client_download_all_raw_files_flattens_by_default(self):
        files = Files()
        records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a/run.raw",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/b/run.raw",
            ),
        ]
        with patch.object(MassiveProvider, "list_files", return_value=records), patch.object(
            transport, "download_ftp_urls"
        ) as ftp_mock:
            files.download_all_raw_files(
                accession="MSV000012345",
                output_folder="/tmp/test",
                skip_if_downloaded_already=False,
                protocol="ftp",
                aspera_maximum_bandwidth="100M",
                checksum_check=False,
                parallel_files=1,
            )
        assert ftp_mock.call_args.kwargs["relative_paths"] == ["run.raw", "run_1.raw"]

    def test_client_download_all_raw_files_preserve_structure(self):
        files = Files()
        records = [
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a/run.raw",
            ),
            MassiveProvider._build_file_record(
                "MSV000012345",
                "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/b/run.raw",
            ),
        ]
        with patch.object(MassiveProvider, "list_files", return_value=records), patch.object(
            transport, "download_ftp_urls"
        ) as ftp_mock:
            files.download_all_raw_files(
                accession="MSV000012345",
                output_folder="/tmp/test",
                skip_if_downloaded_already=False,
                protocol="ftp",
                aspera_maximum_bandwidth="100M",
                checksum_check=False,
                parallel_files=1,
                flatten=False,
            )
        assert ftp_mock.call_args.kwargs["relative_paths"] == [
            "raw/a/run.raw",
            "raw/b/run.raw",
        ]

    def test_get_https_url_builds_proteosafe_endpoint(self):
        url = MassiveProvider._get_https_url(
            "MSV000012345", "raw/Raw spec/C 3.raw"
        )
        # Path slashes/dots preserved, spaces percent-encoded.
        assert url == (
            "https://massive.ucsd.edu/ProteoSAFe/DownloadResultFile?forceDownload=true"
            "&file=f.MSV000012345/raw/Raw%20spec/C%203.raw"
        )

    def test_build_massive_file_record_handles_non_v01_version_root(self):
        """Datasets live under v01..vNN; records must preserve the real root."""
        record = MassiveProvider._build_file_record(
            "MSV000088302",
            "ftp://massive-ftp.ucsd.edu/v04/MSV000088302/ccms_peak/run.mzML",
        )

        assert record["relativePath"] == "ccms_peak/run.mzML"
        assert record["collection"] == "ccms_peak"
        assert record["fileName"] == "run.mzML"
        assert record["fileCategory"]["value"] == "PEAK"
        assert (
            record["publicFileLocations"][0]["value"]
            == "ftp://massive-ftp.ucsd.edu/v04/MSV000088302/ccms_peak/run.mzML"
        )

    def test_get_public_ftp_url_preserves_version_root(self):
        url = MassiveProvider._get_public_ftp_url(
            "MSV000088302", "/v04/MSV000088302/ccms_peak/run.mzML"
        )
        assert url == "ftp://massive-ftp.ucsd.edu/v04/MSV000088302/ccms_peak/run.mzML"

    def test_list_files_discovers_version_root_when_not_v01(self):
        """list_files probes top-level roots and walks the one holding the
        dataset, so a dataset under /v04 is listed with v04 download URLs."""
        def fake_nlst(command, callback):
            assert command == "NLST /"
            for name in ["v01", "v02", "v03", "v04", "v05"]:
                callback(name)

        def fake_cwd(path):
            # Only the real root accepts the CWD; others 550.
            if path != "/v04/MSV000088302":
                raise ftplib.error_perm("550 CD issue: file does not exist")

        with patch.object(transport, "_open_ftp_connection") as open_conn, patch.object(
            transport,
            "_walk_ftp_tree",
            return_value=["/v04/MSV000088302/ccms_peak/run.mzML"],
        ) as walk_mock:
            fake_ftp = open_conn.return_value
            fake_ftp.retrlines.side_effect = fake_nlst
            fake_ftp.cwd.side_effect = fake_cwd

            records = MassiveProvider().list_files("MSV000088302")

        walk_mock.assert_called_once_with(fake_ftp, "/v04/MSV000088302")
        assert len(records) == 1
        assert records[0]["relativePath"] == "ccms_peak/run.mzML"
        assert (
            records[0]["publicFileLocations"][0]["value"]
            == "ftp://massive-ftp.ucsd.edu/v04/MSV000088302/ccms_peak/run.mzML"
        )

    def test_list_files_prefers_versioned_root_over_auxiliary_root(self):
        """x01/z01 can hold a partial (peak-only) copy while the full dataset
        lives under a vNN root, so the versioned root must win even when both
        exist."""
        def fake_nlst(command, callback):
            for name in ["x01", "z01", "v04"]:
                callback(name)

        existing = {"/z01/MSV000088302", "/v04/MSV000088302"}

        def fake_cwd(path):
            if path not in existing:
                raise ftplib.error_perm("550 CD issue: file does not exist")

        with patch.object(transport, "_open_ftp_connection") as open_conn, patch.object(
            transport,
            "_walk_ftp_tree",
            return_value=["/v04/MSV000088302/raw/run.raw"],
        ) as walk_mock:
            fake_ftp = open_conn.return_value
            fake_ftp.retrlines.side_effect = fake_nlst
            fake_ftp.cwd.side_effect = fake_cwd

            records = MassiveProvider().list_files("MSV000088302")

        walk_mock.assert_called_once_with(fake_ftp, "/v04/MSV000088302")
        assert (
            records[0]["publicFileLocations"][0]["value"]
            == "ftp://massive-ftp.ucsd.edu/v04/MSV000088302/raw/run.raw"
        )

    def test_build_https_file_record_sets_relpath_category_and_https_location(self):
        record = MassiveProvider._build_https_file_record(
            "MSV000012345", "raw/sub/run.raw"
        )
        assert record["relativePath"] == "raw/sub/run.raw"
        assert record["fileName"] == "run.raw"
        assert record["collection"] == "raw"
        assert record["fileCategory"]["value"] == "RAW"
        location = record["publicFileLocations"][0]
        assert location["value"].startswith(
            "https://massive.ucsd.edu/ProteoSAFe/DownloadResultFile?"
        )
        assert location["value"].endswith("file=f.MSV000012345/raw/sub/run.raw")

    def test_list_files_falls_back_to_https_when_ftps_blocked(self):
        """When the FTPS tree walk raises (e.g. FTPS blocked), list_files must
        fall back to the HTTPS file index and emit HTTPS-download records."""
        csv_text = (
            "usi,filepath\n"
            "mzspec:MSV000012345:raw/a/run.raw,raw/a/run.raw\n"
            "mzspec:MSV000012345:raw/b/run.raw,raw/b/run.raw\n"
            "mzspec:MSV000012345:ccms_result/x.mzid,ccms_result/x.mzid\n"
        )

        class _FakeCSVResponse:
            def raise_for_status(self):
                return None

            def iter_lines(self):
                for line in csv_text.splitlines():
                    yield line.encode("utf-8")

        with patch.object(
            transport,
            "_resolve_and_walk_ftp_dataset",
            side_effect=RuntimeError("FTPS blocked"),
        ), patch(
            "pridepy.download.massive.requests.get", return_value=_FakeCSVResponse()
        ):
            records = MassiveProvider().list_files("MSV000012345")

        assert {r["relativePath"] for r in records} == {
            "raw/a/run.raw",
            "raw/b/run.raw",
            "ccms_result/x.mzid",
        }
        # Same-basename files in different collections are kept distinct.
        run_records = [r for r in records if r["fileName"] == "run.raw"]
        assert len(run_records) == 2
        for record in records:
            assert record["publicFileLocations"][0]["value"].startswith("https://")
        # Downstream RAW filtering still works on the HTTPS records.
        raw_names = {
            rec["fileName"]
            for rec in records
            if rec["fileCategory"]["value"] == "RAW"
        }
        assert raw_names == {"run.raw"}
