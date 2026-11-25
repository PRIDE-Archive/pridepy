"""iProX direct-download provider.

iProX publishes the ProteomeXchange XML for each dataset at a
deterministic path on its anonymous HTTP download server::

    http://download.iprox.org/<accession>/PX_<accession>.xml

We fetch the XML, walk every ``<DatasetFile>``'s ``cvParam`` entries, and
turn each ``Associated raw file URI`` (and sibling URIs for search-engine
output, result files, etc.) into a pridepy file record. File downloads
themselves go through plain HTTP on the same host, which supports
``Range`` requests for resume.
"""
import logging
import os
import re
import subprocess
import tempfile
import defusedxml.ElementTree as ET
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

import requests

from pridepy.download import registry
from pridepy.download.base import Provider
from pridepy.download.jpost import JpostProvider


@registry.register
class IproxProvider(Provider):
    name: ClassVar[str] = "iprox"
    use_tls: ClassVar[bool] = False  # download.iprox.org serves over plain HTTP

    DOWNLOAD_BASE_URL: ClassVar[str] = "http://download.iprox.org/"
    PX_XML_URL_TEMPLATE: ClassVar[str] = (
        "http://download.iprox.org/{accession}/PX_{accession}.xml"
    )
    ASPERA_HOST: ClassVar[str] = "download.iprox.org"
    ASPERA_PORT: ClassVar[str] = "33001"
    # iProX PX XML uses the same PSI-MS cvParam "name" values as JPOST PROXI,
    # so we reuse JpostProvider's category map.
    PX_CATEGORY_MAP: ClassVar[Dict[str, str]] = JpostProvider.PROXI_CATEGORY_MAP

    @staticmethod
    def matches(accession: str) -> bool:
        """Return True when ``accession`` looks like an iProX dataset accession."""
        if not accession:
            return False
        return bool(re.fullmatch(r"IPX\d{7,10}", accession.upper()))

    @staticmethod
    def _ascp_binary() -> str:
        # Reuse PRIDE's bundled ascp binary resolution.
        from pridepy.download.pride import PrideProvider
        return PrideProvider.get_ascp_binary()

    @classmethod
    def aspera_download(
        cls,
        urls: List[str],
        output_folder: str,
        user: Optional[str],
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        maximum_bandwidth: str = "500M",
    ) -> None:
        """Download iProX-hosted URLs in one batched ``ascp --file-list`` session.

        Auth resolution is fail-fast and never lets ``ascp`` fall back to an
        interactive ``Password:`` prompt (which would hang a batch/sbatch
        job): pass ``key_path`` for key-based auth (``-i <key_path>``), or
        ``password`` for password auth (via the ``ASPERA_SCP_PASS``
        env var — iProX's own account password, not a key). Exactly one of
        the two must be supplied by the caller. ``ascp --mode recv
        --file-list`` always recreates the remote ``/IPX.../IPX.../`` source
        tree under ``output_folder`` — this transfer path does not support
        flattening.
        """
        if not user:
            raise ValueError(
                "iProX Aspera requires --iprox-user (your registered iProX "
                "username)."
            )
        env = dict(os.environ)
        if key_path:
            if not os.path.isfile(key_path):
                raise ValueError(
                    f"iProX Aspera key not found: {key_path}. Pass "
                    "--aspera-key <path> to your registered Aspera private "
                    "key, or use the default HTTP transport."
                )
        elif password:
            env["ASPERA_SCP_PASS"] = password
        else:
            raise ValueError(
                "iProX Aspera needs a credential: set IPROX_ASPERA_PASSWORD "
                "(your iProX account password) or pass --aspera-key <path>. "
                "HTTP is the default alternative."
            )
        ascp = cls._ascp_binary()
        remote_paths = [urlparse(u).path for u in urls]
        os.makedirs(output_folder, exist_ok=True)
        fd, list_path = tempfile.mkstemp(prefix="iprox_aspera_", suffix=".txt", text=True)
        try:
            with os.fdopen(fd, "w") as fh:
                for path in remote_paths:
                    fh.write(path + "\n")
            argv = [
                ascp, "-T", "-l", maximum_bandwidth, "-P", cls.ASPERA_PORT,
                "-k", "1",
            ] + (["-i", key_path] if key_path else []) + [
                "--mode", "recv",
                "--host", cls.ASPERA_HOST, "--file-list", list_path,
                "--user", user, output_folder,
            ]
            logging.info(
                "iProX Aspera: transferring %d file(s) via ascp --file-list",
                len(remote_paths),
            )
            try:
                subprocess.run(argv, check=True, env=env, stdin=subprocess.DEVNULL)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"iProX Aspera transfer failed (exit {e.returncode})"
                ) from e
        finally:
            os.remove(list_path)

    @staticmethod
    def _get_public_root(accession: str) -> str:
        return f"/{accession.upper()}"

    @classmethod
    def _get_public_ftp_url(cls, accession: str, remote_path: str) -> str:
        # NOTE: name kept as `_get_public_ftp_url` for parity with other providers,
        # but iProX URLs are http(s) not ftp. The dispatcher routes by scheme.
        root_path = cls._get_public_root(accession).rstrip("/")
        relative_path = remote_path
        if remote_path.startswith(root_path):
            relative_path = remote_path[len(root_path):].lstrip("/")
        return f"{cls.DOWNLOAD_BASE_URL}{accession.upper()}/{relative_path}"

    @classmethod
    def _build_file_record(
        cls, accession: str, file_url: str, category_from_px: Optional[str] = None
    ) -> Dict:
        """Build a pridepy file record for an iProX file.

        ``file_url`` is the file URI from the PX XML (``http://`` on
        download.iprox.org; ``https://`` is also accepted if present).
        ``category_from_px`` is the ``cvParam`` ``name`` from the dataset's
        ProteomeXchange XML (e.g. ``"Associated raw file URI"``).
        """
        from pridepy.download.massive import MassiveProvider
        parsed = urlparse(file_url)
        root_prefix = f"/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix):]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        if category_from_px and category_from_px in cls.PX_CATEGORY_MAP:
            category = cls.PX_CATEGORY_MAP[category_from_px]
        else:
            category = MassiveProvider._map_collection_to_category(collection)
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": category},
            # "FTP Protocol" is the existing label the download dispatcher uses
            # to locate a file URL; here it actually points at HTTP
            # (download.iprox.org). Provider.download_files routes by URL scheme.
            "publicFileLocations": [{"name": "FTP Protocol", "value": file_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "iProX",
        }

    def list_files(self, accession: str) -> List[Dict]:
        normalized = accession.upper()
        xml_url = self.PX_XML_URL_TEMPLATE.format(accession=normalized)
        logging.info(f"Fetching iProX PX XML: {xml_url}")
        response = requests.get(xml_url, timeout=30)
        response.raise_for_status()
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as parse_error:
            raise RuntimeError(
                f"Unable to parse iProX PX XML for {normalized}: {parse_error}"
            ) from parse_error

        records: List[Dict] = []
        for dataset_file in root.iter("DatasetFile"):
            for cv in dataset_file.findall("cvParam"):
                name = cv.attrib.get("name")
                value = cv.attrib.get("value")
                if not value or not name or not name.endswith("URI"):
                    continue
                if not value.lower().startswith(("http://", "https://")):
                    continue
                records.append(
                    self._build_file_record(
                        normalized,
                        value,
                        category_from_px=name,
                    )
                )
        if not records:
            raise RuntimeError(
                f"iProX PX XML for {normalized} contained no downloadable "
                f"HTTP/HTTPS URIs"
            )
        return records
