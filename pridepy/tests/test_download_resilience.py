import hashlib
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from pridepy.files.files import Files


class TestDownloadResilience(TestCase):
    def test_read_checksum_file_parses_common_formats(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            checksum_path = os.path.join(tmp_dir, "checksums.tsv")
            with open(checksum_path, "w", encoding="utf-8") as handle:
                handle.write("900150983cd24fb0d6963f7d28e17f72 fileA.raw\n")
                handle.write("fileB.raw\t900150983cd24fb0d6963f7d28e17f72\n")
                handle.write("900150983cd24fb0d6963f7d28e17f72\t/path/to/fileC.raw\n")

            checksum_map = Files.read_checksum_file(checksum_path)

            assert checksum_map["fileA.raw"] == "900150983cd24fb0d6963f7d28e17f72"
            assert checksum_map["fileB.raw"] == "900150983cd24fb0d6963f7d28e17f72"
            assert checksum_map["fileC.raw"] == "900150983cd24fb0d6963f7d28e17f72"

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
        assert Files._protocol_sequence("auto") == ["aspera", "s3", "ftp", "globus"]
        assert Files._protocol_sequence("ftp") == ["ftp", "aspera", "s3", "globus"]

    def test_download_with_fallback_switches_protocol_after_invalid_file(self):
        handler = Files()
        file_record = {
            "fileName": "sample.raw",
            "publicFileLocations": [{"name": "FTP Protocol", "value": "ftp://ftp.pride.ebi.ac.uk/p.raw"}],
        }
        expected_checksum = hashlib.md5(b"abc").hexdigest()

        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, "p.raw")

            def fake_download(record, output_folder, protocol, aspera_bandwidth):
                if protocol == "aspera":
                    with open(local_path, "wb") as handle:
                        handle.write(b"")
                elif protocol == "s3":
                    with open(local_path, "wb") as handle:
                        handle.write(b"abc")

            with patch.object(Files, "_download_one_file_by_protocol", side_effect=fake_download):
                success = handler._download_with_fallback(
                    file_record=file_record,
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol_sequence=["aspera", "s3"],
                    expected_checksum=expected_checksum,
                    aspera_maximum_bandwidth="100M",
                    max_protocol_retries=1,
                )

            assert success is True
