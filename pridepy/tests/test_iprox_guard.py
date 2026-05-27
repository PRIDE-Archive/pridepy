"""iProX accession recognition and unsupported-accession guard.

iProX direct downloads are not implemented (the iProX REST API gates listing
behind CAS authentication and files are served over Aspera with per-session
tokens). pridepy still recognises the accession format so the user gets a
clear ``NotImplementedError`` instead of a confusing PRIDE-API 404.
"""
import tempfile
from unittest import TestCase

import pytest

from pridepy.files.files import Files


class TestIProXGuard(TestCase):
    def test_is_iprox_accession_matches_ipx_format(self):
        assert Files.is_iprox_accession("IPX0000123")
        assert Files.is_iprox_accession("IPX0000123000")
        assert Files.is_iprox_accession("ipx1234567")
        assert not Files.is_iprox_accession("PXD000012")
        assert not Files.is_iprox_accession("MSV000012345")
        assert not Files.is_iprox_accession("JPST000001")
        assert not Files.is_iprox_accession("IPX12")
        assert not Files.is_iprox_accession("")
        assert not Files.is_iprox_accession(None)

    def test_iprox_is_not_a_direct_download_accession(self):
        assert Files.is_direct_download_accession("IPX0000123000") is False

    def test_get_all_raw_file_list_raises_for_iprox(self):
        files = Files()
        with pytest.raises(NotImplementedError, match="iProX"):
            files.get_all_raw_file_list("IPX0006033000")

    def test_download_file_by_name_raises_for_iprox(self):
        files = Files()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(NotImplementedError, match="iProX"):
                files.download_file_by_name(
                    accession="IPX0006033000",
                    file_name="foo.raw",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                    username=None,
                    password=None,
                    aspera_maximum_bandwidth="100M",
                    checksum_check=False,
                )

    def test_download_all_raw_files_raises_for_iprox(self):
        files = Files()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(NotImplementedError, match="iProX"):
                files.download_all_raw_files(
                    accession="IPX0006033000",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=False,
                    protocol="ftp",
                    aspera_maximum_bandwidth="100M",
                )
