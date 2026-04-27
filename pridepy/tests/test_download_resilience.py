import hashlib
import os
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from pridepy.files.files import Files


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

        download_url = Files._get_download_url(file_record, "globus")

        assert download_url == "https://ftp.pride.ebi.ac.uk/path/file.raw"

    def test_parallel_download_falls_back_when_range_not_honored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = os.path.join(tmp_dir, "file.raw")
            session = Mock()
            head = Mock()
            head.headers = {"content-length": "1", "accept-ranges": "bytes"}
            head.raise_for_status.return_value = None
            session.head.return_value = head

            ranged_response = Mock()
            ranged_response.status_code = 200
            ranged_response.headers = {}
            ranged_response.raise_for_status.return_value = None
            ranged_response.__enter__ = Mock(return_value=ranged_response)
            ranged_response.__exit__ = Mock(return_value=None)

            fallback_response = Mock()
            fallback_response.raise_for_status.return_value = None
            fallback_response.iter_content.return_value = [b"abc"]
            fallback_response.__enter__ = Mock(return_value=fallback_response)
            fallback_response.__exit__ = Mock(return_value=None)
            session.get.side_effect = [ranged_response, fallback_response]

            with patch(
                "pridepy.files.files.Util.create_session_with_retries",
                return_value=session,
            ):
                Files._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                    num_connections=2,
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
            fallback_response.iter_content.return_value = [b"abc"]
            fallback_response.__enter__ = Mock(return_value=fallback_response)
            fallback_response.__exit__ = Mock(return_value=None)
            session.get.return_value = fallback_response

            with patch(
                "pridepy.files.files.Util.create_session_with_retries",
                return_value=session,
            ):
                Files._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                    num_connections=2,
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
            fallback_response.iter_content.return_value = [b"abc"]
            fallback_response.__enter__ = Mock(return_value=fallback_response)
            fallback_response.__exit__ = Mock(return_value=None)
            session.get.return_value = fallback_response

            with patch(
                "pridepy.files.files.Util.create_session_with_retries",
                return_value=session,
            ):
                Files._parallel_download(
                    "https://example.org/file.raw",
                    output_file,
                    num_connections=2,
                )

            with open(output_file, "rb") as handle:
                assert handle.read() == b"abc"

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
        assert Files._protocol_sequence("ftp") == ["ftp", "aspera", "s3", "globus"]
        assert Files._protocol_sequence("aspera") == ["aspera", "s3", "ftp", "globus"]

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
                           aspera_maximum_bandwidth):
                attempted_protocols.append(protocol)
                if protocol == "aspera":
                    with open(local_path, "wb") as handle:
                        handle.write(b"")
                elif protocol == "s3":
                    with open(local_path, "wb") as handle:
                        handle.write(b"abc")

            with patch.object(Files, "_batch_download_by_protocol", side_effect=fake_batch):
                success = Files._download_with_fallback(
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
                           aspera_maximum_bandwidth):
                with open(local_path, "wb") as handle:
                    handle.write(b"data")

            with patch.object(Files, "_batch_download_by_protocol", side_effect=fake_batch) as batch_mock, \
                 patch.object(Files, "_download_with_fallback") as fallback_mock:
                Files.download_files(
                    file_list_json=[file_record],
                    accession="PXD000000",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                )

            assert batch_mock.call_count == 1
            assert batch_mock.call_args.args[2] == "ftp"
            fallback_mock.assert_not_called()

    def test_download_files_raises_when_any_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_list = [{"fileName": "missing.raw"}]

            with patch.object(Files, "_batch_download_by_protocol"), \
                 patch.object(Files, "_download_with_fallback", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "missing.raw"):
                    Files.download_files(
                        file_list_json=file_list,
                        accession="PXD000000",
                        output_folder=tmp_dir,
                        skip_if_downloaded_already=False,
                        protocol="ftp",
                    )
