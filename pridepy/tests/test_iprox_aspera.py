"""iProX Aspera command construction + credential handling."""
import os
import re
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import patch, MagicMock

import pytest

from pridepy.download.iprox import IproxProvider


class TestIproxAspera(TestCase):
    def test_builds_ascp_source_and_env(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            run.return_value = MagicMock(returncode=0)
            IproxProvider.aspera_download(
                urls=[url],
                output_folder=tmp,
                relative_paths=["IPX0003578001/a.raw"],
                user="bob",
                password="secret",
                maximum_bandwidth="100M",
            )
        args, kwargs = run.call_args
        argv = args[0]
        assert argv[0] == "/bin/ascp"
        assert "33001" in argv
        assert "bob@download.iprox.org:/data/iprox/IPX0003578000/IPX0003578001/a.raw" in argv
        # password only via env, never argv
        assert "secret" not in argv
        assert kwargs["env"]["ASPERA_SCP_PASS"] == "secret"

    def test_missing_credentials_raises(self):
        with pytest.raises(ValueError, match="credentials"):
            IproxProvider.aspera_download(
                urls=["http://download.iprox.org/IPX1/a.raw"],
                output_folder="/tmp/x",
                relative_paths=["a.raw"],
                user=None,
                password=None,
            )

    def test_failed_transfer_raises_runtime_error(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            run.side_effect = subprocess.CalledProcessError(1, ["ascp"])
            with pytest.raises(RuntimeError, match=re.escape(url)):
                IproxProvider.aspera_download(
                    urls=[url],
                    output_folder=tmp,
                    relative_paths=["IPX0003578001/a.raw"],
                    user="bob",
                    password="secret",
                    maximum_bandwidth="100M",
                )

    def test_skip_if_downloaded_already_skips_existing_file(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            dest_dir = os.path.join(tmp, "IPX0003578001")
            os.makedirs(dest_dir, exist_ok=True)
            dest_file = os.path.join(dest_dir, "a.raw")
            with open(dest_file, "w") as f:
                f.write("already here")

            IproxProvider.aspera_download(
                urls=[url],
                output_folder=tmp,
                relative_paths=["IPX0003578001/a.raw"],
                user="bob",
                password="secret",
                maximum_bandwidth="100M",
                skip_if_downloaded_already=True,
            )
        run.assert_not_called()


class TestPxAsperaRouting(TestCase):
    def test_px_aspera_routes_to_iprox(self):
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        rec = {
            "publicFileLocations": [
                {"name": "FTP Protocol",
                 "value": "http://download.iprox.org/IPX1/IPX2/a.raw"}
            ],
            "relativePath": "IPX2/a.raw",
        }
        with patch.object(prov, "list_files", return_value=[rec]), \
             patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp:
            prov.download_from_accession_or_url(
                "PXD000001", "/tmp/x", protocol="aspera",
                iprox_user="bob", iprox_password="secret",
            )
        asp.assert_called_once()
        assert asp.call_args.kwargs["user"] == "bob"

    def test_px_aspera_flattens_relative_paths_by_default(self):
        """Aspera branch should honor flatten=True like the HTTP/FTP path:
        dataset subtree paths collapse to deduplicated basenames."""
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        records = [
            {
                "publicFileLocations": [
                    {"name": "FTP Protocol",
                     "value": "http://download.iprox.org/IPX1/run1/a.raw"}
                ],
                "relativePath": "run1/a.raw",
            },
            {
                "publicFileLocations": [
                    {"name": "FTP Protocol",
                     "value": "http://download.iprox.org/IPX1/run2/a.raw"}
                ],
                "relativePath": "run2/a.raw",
            },
        ]
        with patch.object(prov, "list_files", return_value=records), \
             patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp:
            prov.download_from_accession_or_url(
                "PXD000001", "/tmp/x", protocol="aspera", flatten=True,
                iprox_user="bob", iprox_password="secret",
            )
        asp.assert_called_once()
        rels = asp.call_args.kwargs["relative_paths"]
        # Flattened + de-duped basenames, no subdirectories preserved.
        assert set(rels) == {"a.raw", "a_1.raw"}

    def test_px_aspera_preserves_structure_when_not_flattened(self):
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        rec = {
            "publicFileLocations": [
                {"name": "FTP Protocol",
                 "value": "http://download.iprox.org/IPX1/IPX2/a.raw"}
            ],
            "relativePath": "IPX2/a.raw",
        }
        with patch.object(prov, "list_files", return_value=[rec]), \
             patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp:
            prov.download_from_accession_or_url(
                "PXD000001", "/tmp/x", protocol="aspera", flatten=False,
                iprox_user="bob", iprox_password="secret",
            )
        asp.assert_called_once()
        assert asp.call_args.kwargs["relative_paths"] == ["IPX2/a.raw"]
