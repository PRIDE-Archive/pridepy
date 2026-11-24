"""PRIDE Aspera key/binary resolution.

EBI's Aspera server no longer accepts the bundled DSA key, so the RSA key is
the default. ``PRIDEPY_ASPERA_KEY`` / ``PRIDEPY_ASCP`` let users supply their own.
"""
import os
from unittest.mock import patch

import pytest

from pridepy.download.pride import PrideProvider


def test_default_key_is_bundled_rsa_key(monkeypatch):
    monkeypatch.delenv("PRIDEPY_ASPERA_KEY", raising=False)
    key = PrideProvider.get_aspera_key()
    assert key.endswith(os.path.join("aspera", "key", "aspera_tokenauth_id_rsa"))
    assert os.path.isfile(key)


def test_key_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "my_key"
    custom.write_text("dummy")
    monkeypatch.setenv("PRIDEPY_ASPERA_KEY", str(custom))
    assert PrideProvider.get_aspera_key() == str(custom)


def test_ascp_env_override(monkeypatch):
    monkeypatch.setenv("PRIDEPY_ASCP", "/opt/ibm/ascp")
    assert PrideProvider.get_ascp_binary() == "/opt/ibm/ascp"


def test_ascp_defaults_to_bundled_binary(monkeypatch):
    monkeypatch.delenv("PRIDEPY_ASCP", raising=False)
    assert os.path.isfile(PrideProvider.get_ascp_binary())


@pytest.mark.parametrize(
    "system,expected",
    [
        ("Linux", os.path.join("linux-x86_64", "bin", "ascp")),
        ("Darwin", os.path.join("macos-universal", "bin", "ascp")),
    ],
)
def test_bundled_ascp_4x_layout(monkeypatch, system, expected):
    monkeypatch.delenv("PRIDEPY_ASCP", raising=False)
    with patch("pridepy.download.pride.platform.system", return_value=system), patch(
        "pridepy.download.pride.platform.architecture", return_value=("64bit", "")
    ):
        path = PrideProvider.get_ascp_binary()
    assert path.endswith(expected)
    assert os.path.isfile(path)
    # ascp 4.x refuses to start without its license at ../etc.
    assert os.path.isfile(os.path.join(os.path.dirname(path), "..", "etc", "aspera-license"))


def test_aspera_download_uses_resolved_binary_and_key(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIDEPY_ASCP", "/opt/ibm/ascp")
    monkeypatch.setenv("PRIDEPY_ASPERA_KEY", str(tmp_path / "k"))
    records = [
        {
            "fileName": "a.raw",
            "accession": "PXD000001",
            "publicFileLocations": [
                {"name": "Aspera Protocol", "value": "prd_ascp@fasp.ebi.ac.uk:pride/a.raw"}
            ],
        }
    ]
    with patch("pridepy.download.pride.subprocess.run") as run:
        PrideProvider.download_files_from_aspera(
            records, str(tmp_path), skip_if_downloaded_already=False
        )
    argv = run.call_args[0][0]
    assert argv[0] == "/opt/ibm/ascp"
    assert argv[argv.index("-i") + 1] == str(tmp_path / "k")
