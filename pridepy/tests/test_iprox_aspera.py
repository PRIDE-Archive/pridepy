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

    def test_skip_if_downloaded_already_does_not_skip_when_only_dir_exists(self):
        """Regression: when relpath is missing, dest used to resolve to the
        output DIRECTORY, so os.path.exists(dest) was always True and every
        such file was wrongly skipped."""
        url = "http://download.iprox.org/IPX0003578000/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            run.return_value = MagicMock(returncode=0)
            IproxProvider.aspera_download(
                urls=[url],
                output_folder=tmp,
                relative_paths=[None],
                user="bob",
                password="secret",
                maximum_bandwidth="100M",
                skip_if_downloaded_already=True,
            )
        run.assert_called_once()

    def test_skip_if_downloaded_already_does_not_skip_zero_byte_file(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            dest_dir = os.path.join(tmp, "IPX0003578001")
            os.makedirs(dest_dir, exist_ok=True)
            dest_file = os.path.join(dest_dir, "a.raw")
            open(dest_file, "w").close()  # 0-byte partial file
            run.return_value = MagicMock(returncode=0)

            IproxProvider.aspera_download(
                urls=[url],
                output_folder=tmp,
                relative_paths=["IPX0003578001/a.raw"],
                user="bob",
                password="secret",
                maximum_bandwidth="100M",
                skip_if_downloaded_already=True,
            )
        run.assert_called_once()

    def test_traversal_relpath_does_not_escape_output_folder(self):
        """A relativePath like '../../etc/x' must not write outside output_folder."""
        url = "http://download.iprox.org/IPX0003578000/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            run.return_value = MagicMock(returncode=0)
            IproxProvider.aspera_download(
                urls=[url],
                output_folder=tmp,
                relative_paths=["../../etc/x"],
                user="bob",
                password="secret",
                maximum_bandwidth="100M",
            )
        args, kwargs = run.call_args
        argv = args[0]
        dest = argv[-1]
        out_abs = os.path.abspath(tmp)
        dest_abs = os.path.abspath(dest)
        assert dest_abs == out_abs or dest_abs.startswith(out_abs + os.sep)

    def test_parallel_files_downloads_all_and_aggregates_failures(self):
        urls = [
            "http://download.iprox.org/IPX0003578000/a.raw",
            "http://download.iprox.org/IPX0003578000/b.raw",
            "http://download.iprox.org/IPX0003578000/c.raw",
        ]
        rels = ["a.raw", "b.raw", "c.raw"]

        def fake_run(argv, check, env):
            if argv[-1].endswith("b.raw"):
                raise subprocess.CalledProcessError(1, argv)
            return MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run", side_effect=fake_run) as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            with pytest.raises(RuntimeError, match="b.raw"):
                IproxProvider.aspera_download(
                    urls=urls,
                    output_folder=tmp,
                    relative_paths=rels,
                    user="bob",
                    password="secret",
                    maximum_bandwidth="100M",
                    parallel_files=2,
                )
        assert run.call_count == 3


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

    def test_px_aspera_rejects_spoofed_host(self):
        """A URL on a lookalike host (substring match, not exact) must NOT be
        routed to iProX Aspera."""
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        rec = {
            "publicFileLocations": [
                {"name": "FTP Protocol",
                 "value": "http://download.iprox.org.evil.example/IPX1/a.raw"}
            ],
            "relativePath": "a.raw",
        }
        with patch.object(prov, "list_files", return_value=[rec]), \
             patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp:
            with pytest.raises(ValueError, match="no iProX-hosted files"):
                prov.download_from_accession_or_url(
                    "PXD000001", "/tmp/x", protocol="aspera",
                    iprox_user="bob", iprox_password="secret",
                )
        asp.assert_not_called()

    def test_px_aspera_warns_on_mixed_dataset(self):
        """Non-iProX files in a mixed dataset are dropped from the aspera
        transfer; a warning should be logged naming how many were skipped."""
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        records = [
            {
                "publicFileLocations": [
                    {"name": "FTP Protocol",
                     "value": "http://download.iprox.org/IPX1/a.raw"}
                ],
                "relativePath": "a.raw",
            },
            {
                "publicFileLocations": [
                    {"name": "FTP Protocol",
                     "value": "ftp://massive-ftp.ucsd.edu/MSV1/b.raw"}
                ],
                "relativePath": "b.raw",
            },
        ]
        with patch.object(prov, "list_files", return_value=records), \
             patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp, \
             self.assertLogs(level="WARNING") as log_ctx:
            prov.download_from_accession_or_url(
                "PXD000001", "/tmp/x", protocol="aspera",
                iprox_user="bob", iprox_password="secret",
            )
        asp.assert_called_once()
        assert any("not" in m.lower() and "iprox" in m.lower() for m in log_ctx.output)

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
