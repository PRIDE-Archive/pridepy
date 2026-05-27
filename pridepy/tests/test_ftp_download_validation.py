"""Coverage for the size-mismatch detection added to ``_download_one_ftp_path``.

The FTP server's ``SIZE`` reply is the only integrity signal direct downloads
have (MassIVE/JPOST don't publish per-file MD5 manifests like PRIDE). After
``retrbinary`` returns, we re-check the local size against the server-reported
size and treat a mismatch as a retryable failure.
"""
import os
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock

import pytest

from pridepy.files.files import Files


def _make_fake_ftp(expected_size, write_bytes_per_call):
    """Return a MagicMock FTP that writes ``write_bytes_per_call`` bytes per call.

    ``retrbinary`` is invoked once per attempt; we record how many attempts
    happened by counting calls and produce a different payload size for each.
    """
    fake = MagicMock()
    fake.size.return_value = expected_size
    fake.sendcmd = MagicMock()
    fake._call_count = 0

    def retrbinary(cmd, callback):
        idx = fake._call_count
        fake._call_count += 1
        payload = b"x" * write_bytes_per_call[idx]
        callback(payload)

    fake.retrbinary.side_effect = retrbinary
    return fake


class TestSizeMismatchValidation(TestCase):
    def test_size_mismatch_is_retried_then_succeeds(self):
        """First attempt returns 50 bytes (expected 100) -> retry, second yields 50 more -> 100, OK."""
        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "f.bin")
            ftp = _make_fake_ftp(expected_size=100, write_bytes_per_call=[50, 50])

            Files._download_one_ftp_path(
                ftp=ftp,
                ftp_path="/JPST000001/f.bin",
                local_path=local_path,
                skip_if_downloaded_already=False,
                max_download_retries=3,
            )

            assert os.path.getsize(local_path) == 100
            assert ftp.retrbinary.call_count == 2
            # First attempt: file empty, no REST. Second: file has 50 bytes, REST 50 issued.
            sendcmd_args = [call.args[0] for call in ftp.sendcmd.call_args_list]
            assert sendcmd_args == ["REST 50"]

    def test_size_mismatch_after_retries_raises(self):
        """Three attempts all undersize -> RuntimeError after giving up."""
        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "f.bin")
            ftp = _make_fake_ftp(expected_size=100, write_bytes_per_call=[10, 10, 10])

            with pytest.raises(RuntimeError, match="Giving up"):
                Files._download_one_ftp_path(
                    ftp=ftp,
                    ftp_path="/JPST000001/f.bin",
                    local_path=local_path,
                    skip_if_downloaded_already=False,
                    max_download_retries=3,
                )

            assert ftp.retrbinary.call_count == 3

    def test_correct_size_returns_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_path = os.path.join(tmp, "f.bin")
            ftp = _make_fake_ftp(expected_size=50, write_bytes_per_call=[50])

            Files._download_one_ftp_path(
                ftp=ftp,
                ftp_path="/JPST000001/f.bin",
                local_path=local_path,
                skip_if_downloaded_already=False,
                max_download_retries=3,
            )

            assert os.path.getsize(local_path) == 50
            assert ftp.retrbinary.call_count == 1
