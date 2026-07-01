import hashlib
import os
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from pridepy.download import by_url
from pridepy.download.client import Client as Files
from pridepy.download import transport
from pridepy.download import util as provider_util
from pridepy.download.massive import MassiveProvider
from pridepy.download.pride import PrideProvider
from pridepy.download.proteomexchange import ProteomeXchangeProvider


class TestDownloadResilience(TestCase):
    def test_read_checksum_file_parses_pride_api_format(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checksum_path = os.path.join(tmp_dir, "checksums.tsv")
            with open(checksum_path, "w", encoding="utf-8") as handle:
                handle.write("File-Name\tFile-MD5Checksum\tFile-Size\n")
                handle.write("fileA.raw\t900150983cd24fb0d6963f7d28e17f72\t1024\n")
                handle.write("fileB.raw\td41d8cd98f00b204e9800998ecf8427e\t2048\n")
                handle.write("fileC.raw\tnot-a-md5\t4096\n")

            checksum_map = Files.read_checksum_file(checksum_path)

            assert checksum_map["fileA.raw"] == "900150983cd24fb0d6963f7d28e17f72"
            assert checksum_map["fileB.raw"] == "d41d8cd98f00b204e9800998ecf8427e"
            assert "fileC.raw" not in checksum_map

    def test_read_checksum_file_returns_empty_on_bad_header(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checksum_path = os.path.join(tmp_dir, "checksums.tsv")
            with open(checksum_path, "w", encoding="utf-8") as handle:
                handle.write("random header\n")
                handle.write("some data\n")

            checksum_map = Files.read_checksum_file(checksum_path)
            assert len(checksum_map) == 0

    def test_get_download_url_maps_globus_to_pride_archive_https(self):
        file_record = {
            "publicFileLocations": [
                {"name": "FTP Protocol", "value": "ftp://ftp.pride.ebi.ac.uk/path/file.raw"}
            ]
        }

        download_url = PrideProvider._get_download_url(file_record, "globus")

        assert download_url == "https://ftp.pride.ebi.ac.uk/path/file.raw"

    def test_parallel_download_streams_full_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "file.raw")
            session = Mock()
            head = Mock()
            head.headers = {"content-length": "3", "accept-ranges": "bytes"}
            head.raise_for_status.return_value = None
            session.head.return_value = head

            stream_response = Mock()
            stream_response.raise_for_status.return_value = None
            stream_response.headers = {}
            stream_response.iter_content.return_value = [b"abc"]
            stream_response.__enter__ = Mock(return_value=stream_response)
            stream_response.__exit__ = Mock(return_value=None)
            session.get.return_value = stream_response

            with patch(
                "pridepy.download.transport.Util.create_session_with_retries",
                return_value=session,
            ):
                transport._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                )

            with open(output_file, "rb") as handle:
                assert handle.read() == b"abc"

    def test_parallel_download_falls_back_when_head_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "file.raw")
            session = Mock()
            session.head.side_effect = ValueError("bad content length")

            fallback_response = Mock()
            fallback_response.raise_for_status.return_value = None
            fallback_response.headers = {}
            fallback_response.iter_content.return_value = [b"abc"]
            fallback_response.__enter__ = Mock(return_value=fallback_response)
            fallback_response.__exit__ = Mock(return_value=None)
            session.get.return_value = fallback_response

            with patch(
                "pridepy.download.transport.Util.create_session_with_retries",
                return_value=session,
            ):
                transport._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                )

            with open(output_file, "rb") as handle:
                assert handle.read() == b"abc"

    def test_parallel_download_falls_back_without_accept_ranges(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "file.raw")
            session = Mock()
            head = Mock()
            head.headers = {"content-length": "3", "accept-ranges": "none"}
            head.raise_for_status.return_value = None
            session.head.return_value = head

            fallback_response = Mock()
            fallback_response.raise_for_status.return_value = None
            fallback_response.headers = {}
            fallback_response.iter_content.return_value = [b"abc"]
            fallback_response.__enter__ = Mock(return_value=fallback_response)
            fallback_response.__exit__ = Mock(return_value=None)
            session.get.return_value = fallback_response

            with patch(
                "pridepy.download.transport.Util.create_session_with_retries",
                return_value=session,
            ):
                transport._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                )

            with open(output_file, "rb") as handle:
                assert handle.read() == b"abc"

    def test_parallel_download_raises_on_truncated_stream(self):
        """A stream shorter than Content-Length must raise so the caller retries."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "file.raw")
            session = Mock()
            head = Mock()
            head.headers = {"content-length": "5", "accept-ranges": "none"}
            head.raise_for_status.return_value = None
            session.head.return_value = head

            stream_response = Mock()
            stream_response.raise_for_status.return_value = None
            stream_response.headers = {}  # no Content-Encoding -> size check active
            stream_response.iter_content.return_value = [b"ab"]  # only 2 of 5 bytes
            stream_response.__enter__ = Mock(return_value=stream_response)
            stream_response.__exit__ = Mock(return_value=None)
            session.get.return_value = stream_response

            with patch(
                "pridepy.download.transport.Util.create_session_with_retries",
                return_value=session,
            ):
                with self.assertRaisesRegex(RuntimeError, "Incomplete download"):
                    transport._parallel_download(
                        "https://example.org/file.raw",
                        output_file,
                    )

    def test_safe_join_preserves_subdirs_and_blocks_escape(self):
        out = os.path.join("/tmp", "out")
        # Nested dataset-relative path is preserved under output_folder.
        assert transport._safe_join(out, "raw/sub/run.raw") == os.path.join(
            out, "raw", "sub", "run.raw"
        )
        # Traversal that escapes output_folder falls back to the basename.
        assert transport._safe_join(out, "../../etc/passwd") == os.path.join(
            out, "passwd"
        )

    def test_download_files_preserves_relative_paths_when_flatten_false(self):
        """With flatten=False, base.Provider.download_files threads each
        record's relativePath through to the transport layer so same-basename
        files in different collections keep their subdirectory layout."""
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
                output_folder="/tmp/out",
                skip_if_downloaded_already=False,
                protocol="ftp",
                parallel_files=1,
                flatten=False,
            )
        kwargs = ftp_mock.call_args.kwargs
        assert kwargs["relative_paths"] == ["raw/a/run.raw", "raw/b/run.raw"]

    def test_download_files_threads_relative_paths_for_http(self):
        """With flatten=False, the HTTP partition also forwards relativePath to
        download_http_urls."""

        class _HttpProvider(MassiveProvider):
            pass

        provider = _HttpProvider()
        records = [
            {
                "accession": "MSV000012345",
                "fileName": "run.raw",
                "fileCategory": {"value": "RAW"},
                "publicFileLocations": [
                    {"name": "FTP Protocol", "value": "http://example.org/d1/run.raw"}
                ],
                "relativePath": "raw/d1/run.raw",
            },
        ]
        with patch.object(transport, "download_http_urls") as http_mock:
            provider.download_files(
                accession="MSV000012345",
                records=records,
                output_folder="/tmp/out",
                skip_if_downloaded_already=False,
                protocol="ftp",
                parallel_files=1,
                flatten=False,
            )
        assert http_mock.call_args.kwargs["relative_paths"] == ["raw/d1/run.raw"]

    def test_download_http_urls_raises_when_a_file_fails(self):
        """A failed HTTP transfer must surface as an exception, not be
        swallowed into a false success."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                transport, "_parallel_download", side_effect=RuntimeError("boom")
            ):
                with self.assertRaisesRegex(RuntimeError, "Failed to download"):
                    transport.download_http_urls(
                        http_urls=["https://example.org/a.raw"],
                        output_folder=tmp_dir,
                        skip_if_downloaded_already=False,
                        max_retries=1,
                    )

    def test_download_http_urls_clamps_combined_connection_cap(self):
        """parallel_files x download_threads must be clamped to
        transport.MAX_TOTAL_HTTP_CONNECTIONS, with a warning explaining why,
        so e.g. -w 32 -t 32 doesn't open 1024 connections."""
        seen_threads = []

        def fake_http_download_one(url, output_folder, skip_if_downloaded_already,
                                    max_retries=3, position=0, relative_path=None,
                                    download_threads=1):
            seen_threads.append(download_threads)

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(
                transport, "_http_download_one", side_effect=fake_http_download_one
            ):
                with self.assertLogs(level="WARNING") as log_ctx:
                    transport.download_http_urls(
                        http_urls=[
                            "https://example.org/a.raw",
                            "https://example.org/b.raw",
                            "https://example.org/c.raw",
                        ],
                        output_folder=tmp_dir,
                        skip_if_downloaded_already=False,
                        parallel_files=32,
                        download_threads=32,
                    )
        assert any("connection cap" in m.lower() for m in log_ctx.output)
        workers = min(32, 3)
        expected_threads = max(1, transport.MAX_TOTAL_HTTP_CONNECTIONS // workers)
        assert workers * expected_threads <= transport.MAX_TOTAL_HTTP_CONNECTIONS
        assert all(t == expected_threads for t in seen_threads)

    def test_download_ftp_urls_raises_when_a_file_fails(self):
        """A failed FTP transfer must surface as an exception."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_ftp = Mock()
            with patch.object(
                transport, "_open_ftp_connection", return_value=fake_ftp
            ), patch.object(
                transport, "_download_one_ftp_path", side_effect=RuntimeError("boom")
            ):
                with self.assertRaisesRegex(RuntimeError, "Failed to download"):
                    transport.download_ftp_urls(
                        ftp_urls=["ftp://ftp.example.org/p/a.raw"],
                        output_folder=tmp_dir,
                        skip_if_downloaded_already=False,
                    )

    def test_by_url_http_download_raises_on_truncated_content(self):
        """by_url's HTTP downloader must reject a stream shorter than
        Content-Length instead of accepting a truncated file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "a.raw")
            session = Mock()
            response = Mock()
            response.raise_for_status.return_value = None
            response.headers = {"Content-Length": "5"}
            response.iter_content.return_value = [b"ab"]  # only 2 of 5 bytes
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=None)
            session.get.return_value = response
            with patch(
                "pridepy.download.by_url.Util.create_session_with_retries",
                return_value=session,
            ):
                with self.assertRaisesRegex(RuntimeError, "Incomplete download"):
                    by_url._http_download_url("https://example.org/a.raw", target)

    def test_by_url_http_download_skips_size_check_when_encoded(self):
        """A gzip/deflate response is decompressed by requests, so the on-disk
        size won't match Content-Length — the size check must be skipped to
        avoid a false 'Incomplete download' on an intact file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "a.txt")
            session = Mock()
            response = Mock()
            response.raise_for_status.return_value = None
            # Content-Length is the compressed size; decompressed payload is larger.
            response.headers = {"Content-Length": "5", "Content-Encoding": "gzip"}
            response.iter_content.return_value = [b"abcdefghij"]  # 10 decompressed bytes
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=None)
            session.get.return_value = response
            with patch(
                "pridepy.download.by_url.Util.create_session_with_retries",
                return_value=session,
            ):
                by_url._http_download_url("https://example.org/a.txt", target)
            with open(target, "rb") as handle:
                assert handle.read() == b"abcdefghij"

    def test_proteomexchange_relative_paths_handle_root_common_prefix(self):
        """When raw URIs live in different top-level directories (common
        prefix is '/'), the paths must still be disambiguated, not collapsed
        to a colliding basename."""
        urls = [
            "ftp://ftp.example.org/run1/sample.raw",
            "ftp://ftp.example.org/run2/sample.raw",
        ]
        with patch.object(
            ProteomeXchangeProvider, "_normalize_px_xml_url", return_value="http://x"
        ), patch.object(
            ProteomeXchangeProvider,
            "_parse_px_xml_for_raw_file_urls",
            return_value=urls,
        ):
            records = ProteomeXchangeProvider().list_files("PXD1")
        assert {r["relativePath"] for r in records} == {
            "run1/sample.raw",
            "run2/sample.raw",
        }

    def test_download_files_propagates_transport_failure(self):
        """Provider.download_files must propagate a transport failure so the
        direct-download path doesn't report false success (parity with PRIDE)."""
        provider = MassiveProvider()
        record = MassiveProvider._build_file_record(
            "MSV000012345",
            "ftp://massive-ftp.ucsd.edu/v01/MSV000012345/raw/a.raw",
        )
        with patch.object(
            transport, "download_ftp_urls", side_effect=RuntimeError("download failed")
        ):
            with self.assertRaises(RuntimeError):
                provider.download_files(
                    accession="MSV000012345",
                    records=[record],
                    output_folder="/tmp/does-not-matter",
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                )

    def test_proteomexchange_relative_paths_disambiguate_duplicate_basenames(self):
        """download-px-raw-files must not flatten duplicate basenames from
        different directories onto the same local file."""
        urls = [
            "ftp://ftp.pride.ebi.ac.uk/pride/PXD1/run1/sample.raw",
            "ftp://ftp.pride.ebi.ac.uk/pride/PXD1/run2/sample.raw",
        ]
        with patch.object(
            ProteomeXchangeProvider, "_normalize_px_xml_url", return_value="http://x"
        ), patch.object(
            ProteomeXchangeProvider,
            "_parse_px_xml_for_raw_file_urls",
            return_value=urls,
        ):
            records = ProteomeXchangeProvider().list_files("PXD1")

        assert {r["relativePath"] for r in records} == {
            "run1/sample.raw",
            "run2/sample.raw",
        }

    def test_proteomexchange_single_file_relative_path_is_basename(self):
        urls = ["ftp://ftp.pride.ebi.ac.uk/pride/PXD1/run1/sample.raw"]
        with patch.object(
            ProteomeXchangeProvider, "_normalize_px_xml_url", return_value="http://x"
        ), patch.object(
            ProteomeXchangeProvider,
            "_parse_px_xml_for_raw_file_urls",
            return_value=urls,
        ):
            records = ProteomeXchangeProvider().list_files("PXD1")
        assert records[0]["relativePath"] == "sample.raw"

    def test_validate_download_rejects_empty_and_bad_checksum(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "test.raw")

            with open(file_path, "wb") as handle:
                handle.write(b"")
            valid, reason = Files.validate_download(file_path, None)
            assert not valid
            assert "empty" in reason

            with open(file_path, "wb") as handle:
                handle.write(b"abc")
            valid, reason = Files.validate_download(file_path, "ffffffffffffffffffffffffffffffff")
            assert not valid
            assert "checksum mismatch" in reason

    def test_protocol_sequence_prefers_requested_then_fallback(self):
        assert PrideProvider._protocol_sequence("ftp") == ["ftp", "aspera", "s3", "globus"]
        assert PrideProvider._protocol_sequence("aspera") == ["aspera", "s3", "ftp", "globus"]

    def test_pride_ftp_batch_routes_through_shared_transport(self):
        """PRIDE FTP batch downloads must use transport.download_ftp_urls
        (per-file reconnect + REST resume + size checks) instead of the legacy
        single-connection loop that cascades on one timeout (issue #107)."""
        records = [
            {
                "fileName": "a.raw",
                "accession": "PXD000001",
                "publicFileLocations": [
                    {
                        "name": "FTP Protocol",
                        "value": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2024/05/PXD000001/a.raw",
                    }
                ],
            },
            {
                "fileName": "b.raw",
                "accession": "PXD000001",
                "publicFileLocations": [
                    {
                        "name": "FTP Protocol",
                        "value": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2024/05/PXD000001/b.raw",
                    }
                ],
            },
        ]
        with patch.object(transport, "download_ftp_urls") as ftp_mock:
            PrideProvider._batch_download_by_protocol(
                records,
                "/tmp/out",
                "ftp",
                skip_if_downloaded_already=False,
                aspera_maximum_bandwidth="100M",
                parallel_files=2,
            )

        ftp_mock.assert_called_once()
        kwargs = ftp_mock.call_args.kwargs
        assert kwargs["ftp_urls"] == [
            "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2024/05/PXD000001/a.raw",
            "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2024/05/PXD000001/b.raw",
        ]
        assert kwargs["use_tls"] is False
        assert kwargs["parallel_files"] == 2
        assert kwargs["skip_if_downloaded_already"] is False

    def test_download_with_fallback_switches_protocol_after_invalid_file(self):
        file_record = {
            "fileName": "sample.raw",
            "publicFileLocations": [
                {"name": "FTP Protocol", "value": "ftp://ftp.pride.ebi.ac.uk/p.raw"}
            ],
        }
        expected_checksum = hashlib.md5(b"abc").hexdigest()

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, "p.raw")
            attempted_protocols = []

            def fake_batch(file_list, output_folder, protocol, skip_if_downloaded_already,
                           aspera_maximum_bandwidth, **kwargs):
                attempted_protocols.append(protocol)
                if protocol == "aspera":
                    with open(local_path, "wb") as handle:
                        handle.write(b"")
                elif protocol == "s3":
                    with open(local_path, "wb") as handle:
                        handle.write(b"abc")

            with patch.object(PrideProvider, "_batch_download_by_protocol", side_effect=fake_batch):
                success = PrideProvider._download_with_fallback(
                    file_record=file_record,
                    output_folder=tmp_dir,
                    protocol_sequence=["aspera", "s3"],
                    expected_checksum=expected_checksum,
                    aspera_maximum_bandwidth="100M",
                    max_protocol_retries=1,
                )

            assert success is True
            assert attempted_protocols == ["aspera", "s3"]

    def test_download_files_batch_first_skips_fallback_on_success(self):
        """
        When the primary-protocol batch produces valid files, the per-file
        fallback path must not be invoked.
        """
        file_record = {
            "fileName": "happy.raw",
            "publicFileLocations": [
                {"name": "FTP Protocol", "value": "ftp://ftp.pride.ebi.ac.uk/happy.raw"}
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, "happy.raw")

            def fake_batch(file_list, output_folder, protocol, skip_if_downloaded_already,
                           aspera_maximum_bandwidth, **kwargs):
                with open(local_path, "wb") as handle:
                    handle.write(b"data")

            with patch.object(PrideProvider, "_batch_download_by_protocol", side_effect=fake_batch) as batch_mock, \
                 patch.object(PrideProvider, "_download_with_fallback") as fallback_mock:
                PrideProvider._download_files_batch(
                    file_list_json=[file_record],
                    accession="PXD000000",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                )

            assert batch_mock.call_count == 1
            assert batch_mock.call_args.args[2] == "ftp"
            fallback_mock.assert_not_called()

    def test_globus_parallel_workers_capped_to_file_count(self):
        """When parallel_files exceeds the number of files to download,
        the worker pool must not allocate more threads than files."""
        file_records = [
            {
                "fileName": "only.raw",
                "publicFileLocations": [
                    {"name": "FTP Protocol",
                     "value": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2024/01/PXD000001/only.raw"}
                ],
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(PrideProvider, "_globus_download_one") as mock_one:
                PrideProvider.download_files_from_globus(
                    file_list_json=file_records,
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    parallel_files=3,
                )
                # With 1 file and parallel_files=3, should fall through to
                # the serial path (parallel_files capped to 1 < 2).
                mock_one.assert_called_once()

    def test_url_parallel_workers_capped_to_url_count(self):
        """download_files_by_url must cap workers to len(urls)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(by_url, "_download_single_url") as mock_single:
                Files.download_files_by_url(
                    urls=["https://example.org/a.raw"],
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="globus",
                    parallel_files=3,
                )
                # 1 URL with parallel_files=3 → capped to 1, serial path.
                mock_single.assert_called_once()

    def test_download_files_raises_when_any_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_list = [{"fileName": "missing.raw"}]

            with patch.object(PrideProvider, "_batch_download_by_protocol"), \
                 patch.object(PrideProvider, "_download_with_fallback", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "missing.raw"):
                    PrideProvider._download_files_batch(
                        file_list_json=file_list,
                        accession="PXD000000",
                        output_folder=tmp_dir,
                        skip_if_downloaded_already=False,
                        protocol="ftp",
                    )

    def test_facade_dispatches_pride_through_registry_to_fallback(self):
        """Files().download_all_raw_files for a PXD accession must flow:
        Files facade -> Registry.resolve -> PrideProvider.download_files
        -> _batch_download_by_protocol (mocked).

        Patching PrideProvider._batch_download_by_protocol proves the patch
        intercepts (i.e. PrideProvider owns the multi-protocol orchestrator
        and no longer routes through Files).
        """
        fake_records = [
            {
                "accession": "PXD000001",
                "fileName": "x.raw",
                "fileCategory": {"value": "RAW"},
                "publicFileLocations": [
                    {"name": "FTP Protocol", "value": "ftp://ftp.pride.ebi.ac.uk/.../x.raw"}
                ],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(PrideProvider, "list_files", return_value=fake_records), \
                 patch.object(PrideProvider, "_batch_download_by_protocol", return_value=[]) as batch_mock, \
                 patch.object(provider_util, "validate_download", return_value=(True, "ok")), \
                 patch.object(PrideProvider, "_download_with_fallback") as fallback_mock:
                Files().download_all_raw_files(
                    accession="PXD000001",
                    output_folder=tmp,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                    aspera_maximum_bandwidth="100M",
                )

        batch_mock.assert_called_once()
        # No fallback expected because all files passed validation after
        # the primary-protocol batch run.
        fallback_mock.assert_not_called()
