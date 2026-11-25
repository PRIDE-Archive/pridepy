"""iProX Aspera command construction + credential handling."""
import os
import re
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import patch, MagicMock

import pytest

from pridepy.download.iprox import IproxProvider


def _make_key_file(tmp):
    key_path = os.path.join(tmp, "aspera.key")
    with open(key_path, "w") as f:
        f.write("fake-private-key")
    return key_path


class TestIproxAspera(TestCase):
    def test_builds_ascp_key_based_file_list_argv(self):
        urls = [
            "http://download.iprox.org/IPX0003474000/IPX0003474001/a.raw",
            "http://download.iprox.org/IPX0002031000/IPX0002031001/b.raw",
        ]
        captured_list_contents = {}

        def fake_run(argv, **kwargs):
            list_idx = argv.index("--file-list") + 1
            list_path = argv[list_idx]
            with open(list_path) as f:
                captured_list_contents["lines"] = f.read().splitlines()
            return MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run", side_effect=fake_run) as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            key_path = _make_key_file(tmp)
            output_folder = os.path.join(tmp, "out")
            IproxProvider.aspera_download(
                urls=urls,
                output_folder=output_folder,
                user="daicx",
                key_path=key_path,
                maximum_bandwidth="500M",
            )

        args, kwargs = run.call_args
        argv = args[0]

        assert argv[0] == "/bin/ascp"
        assert "-T" in argv
        assert argv[argv.index("-l") + 1] == "500M"
        assert argv[argv.index("-P") + 1] == "33001"
        assert argv[argv.index("-k") + 1] == "1"
        assert argv[argv.index("-i") + 1] == key_path
        assert argv[argv.index("--mode") + 1] == "recv"
        assert argv[argv.index("--host") + 1] == "download.iprox.org"
        assert argv[argv.index("--user") + 1] == "daicx"
        assert argv[-1] == output_folder

        # key-based auth: no ASPERA_SCP_PASS set in the subprocess env
        assert "ASPERA_SCP_PASS" not in kwargs.get("env", {})
        assert "ASPERA_SCP_PASS" not in argv
        assert not any("secret" in str(a) for a in argv)

        # stdin is always closed so a rejected/missing credential errors
        # instead of blocking on an interactive Password: prompt
        assert kwargs.get("stdin") == subprocess.DEVNULL

        # file-list contains exactly the URL paths, one per line
        assert captured_list_contents["lines"] == [
            "/IPX0003474000/IPX0003474001/a.raw",
            "/IPX0002031000/IPX0002031001/b.raw",
        ]

    def test_builds_ascp_password_based_file_list_argv(self):
        urls = ["http://download.iprox.org/IPX0003474000/IPX0003474001/a.raw"]

        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            run.return_value = MagicMock(returncode=0)
            output_folder = os.path.join(tmp, "out")
            IproxProvider.aspera_download(
                urls=urls,
                output_folder=output_folder,
                user="daicx",
                password="secret",
                maximum_bandwidth="500M",
            )

        args, kwargs = run.call_args
        argv = args[0]

        # password auth: no -i flag at all
        assert "-i" not in argv
        assert argv[argv.index("--mode") + 1] == "recv"
        assert argv[argv.index("--host") + 1] == "download.iprox.org"
        assert argv[argv.index("--user") + 1] == "daicx"
        assert argv[-1] == output_folder

        # credential goes through the env, never on argv
        assert kwargs.get("env", {}).get("ASPERA_SCP_PASS") == "secret"
        assert not any("secret" in str(a) for a in argv)

        # stdin closed so ascp can't fall back to an interactive prompt
        assert kwargs.get("stdin") == subprocess.DEVNULL

    def test_temp_file_list_is_removed_after_run(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        captured = {}

        def fake_run(argv, **kwargs):
            captured["list_path"] = argv[argv.index("--file-list") + 1]
            return MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run", side_effect=fake_run), \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            key_path = _make_key_file(tmp)
            IproxProvider.aspera_download(
                urls=[url],
                output_folder=os.path.join(tmp, "out"),
                user="daicx",
                key_path=key_path,
            )
        assert not os.path.exists(captured["list_path"])

    def test_missing_user_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = _make_key_file(tmp)
            with pytest.raises(ValueError, match="--iprox-user"):
                IproxProvider.aspera_download(
                    urls=["http://download.iprox.org/IPX1/a.raw"],
                    output_folder=os.path.join(tmp, "out"),
                    user=None,
                    key_path=key_path,
                )

    def test_missing_credential_raises(self):
        """Neither key nor password supplied: fail fast, never call ascp."""
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run:
            with pytest.raises(ValueError, match="IPROX_ASPERA_PASSWORD"):
                IproxProvider.aspera_download(
                    urls=["http://download.iprox.org/IPX1/a.raw"],
                    output_folder=os.path.join(tmp, "out"),
                    user="daicx",
                )
            run.assert_not_called()

    def test_nonexistent_key_path_raises(self):
        with pytest.raises(ValueError, match="--aspera-key"):
            IproxProvider.aspera_download(
                urls=["http://download.iprox.org/IPX1/a.raw"],
                output_folder="/tmp/x",
                user="daicx",
                key_path="/no/such/key/file",
            )

    def test_failed_transfer_raises_runtime_error(self):
        url = "http://download.iprox.org/IPX0003578000/IPX0003578001/a.raw"
        with tempfile.TemporaryDirectory() as tmp, \
             patch("pridepy.download.iprox.subprocess.run") as run, \
             patch.object(IproxProvider, "_ascp_binary", return_value="/bin/ascp"):
            key_path = _make_key_file(tmp)
            run.side_effect = subprocess.CalledProcessError(1, ["ascp"])
            with pytest.raises(RuntimeError, match=re.escape("exit 1")):
                IproxProvider.aspera_download(
                    urls=[url],
                    output_folder=os.path.join(tmp, "out"),
                    user="daicx",
                    key_path=key_path,
                )


class TestPxAsperaRouting(TestCase):
    def test_px_aspera_routes_to_iprox_with_key(self):
        from pridepy.download.proteomexchange import ProteomeXchangeProvider
        prov = ProteomeXchangeProvider()
        rec = {
            "publicFileLocations": [
                {"name": "FTP Protocol",
                 "value": "http://download.iprox.org/IPX1/IPX2/a.raw"}
            ],
            "relativePath": "IPX2/a.raw",
        }
        with tempfile.TemporaryDirectory() as tmp:
            key_path = _make_key_file(tmp)
            with patch.object(prov, "list_files", return_value=[rec]), \
                 patch("pridepy.download.iprox.IproxProvider.aspera_download") as asp:
                prov.download_from_accession_or_url(
                    "PXD000001", "/tmp/x", protocol="aspera",
                    iprox_user="daicx", aspera_key=key_path,
                )
            asp.assert_called_once()
            assert asp.call_args.kwargs["user"] == "daicx"
            assert asp.call_args.kwargs["key_path"] == key_path
            assert asp.call_args.kwargs["password"] is None

    def test_px_aspera_routes_to_iprox_with_password(self):
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
                iprox_user="daicx", aspera_password="secret",
            )
        asp.assert_called_once()
        assert asp.call_args.kwargs["user"] == "daicx"
        assert asp.call_args.kwargs["key_path"] is None
        assert asp.call_args.kwargs["password"] == "secret"

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
                    iprox_user="daicx", aspera_key="/some/key",
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
                iprox_user="daicx", aspera_key="/some/key",
            )
        asp.assert_called_once()
        assert any("not" in m.lower() and "iprox" in m.lower() for m in log_ctx.output)
