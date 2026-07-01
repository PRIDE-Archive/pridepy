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
from concurrent.futures import ThreadPoolExecutor, as_completed
import defusedxml.ElementTree as ET
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

import requests

from pridepy.download import registry
from pridepy.download.base import Provider
from pridepy.download.jpost import JpostProvider
from pridepy.download.transport import _safe_join


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
    ASPERA_ROOT: ClassVar[str] = "/data/iprox"
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
    def _aspera_download_one(
        cls,
        ascp: str,
        url: str,
        relpath: Optional[str],
        output_folder: str,
        user: str,
        password: str,
        maximum_bandwidth: str,
        skip_if_downloaded_already: bool,
        env: Dict[str, str],
    ) -> Optional[str]:
        """Download a single URL via ascp. Returns ``url`` on failure, else None."""
        path = urlparse(url).path.lstrip("/")  # e.g. IPX.../.../a.raw
        source = f"{user}@{cls.ASPERA_HOST}:{cls.ASPERA_ROOT}/{path}"
        if relpath:
            dest = _safe_join(output_folder, relpath)
        else:
            dest = os.path.join(output_folder, os.path.basename(urlparse(url).path))
        dest_parent = os.path.dirname(dest) or output_folder
        os.makedirs(dest_parent, exist_ok=True)
        if (
            skip_if_downloaded_already
            and os.path.isfile(dest)
            and os.path.getsize(dest) > 0
        ):
            logging.info(f"Skipping download as file already exists: {dest}")
            return None
        argv = [
            ascp, "-QT", "-P", cls.ASPERA_PORT, "-l", maximum_bandwidth,
            "-k", "2", source, dest,
        ]
        logging.info(
            "Aspera: %s -> %s", source.replace(password, "***"), dest
        )
        try:
            subprocess.run(argv, check=True, env=env)
            return None
        except subprocess.CalledProcessError as e:
            logging.error(f"iProX Aspera failed for {url}: {e}")
            return url

    @classmethod
    def aspera_download(
        cls,
        urls: List[str],
        output_folder: str,
        relative_paths: List[Optional[str]],
        user: Optional[str],
        password: Optional[str],
        maximum_bandwidth: str = "100M",
        skip_if_downloaded_already: bool = False,
        parallel_files: int = 1,
    ) -> None:
        """Download iProX-hosted URLs via ascp on port 33001.

        Requires iProX account credentials; the password is passed to the
        subprocess through ASPERA_SCP_PASS (never argv). When
        ``parallel_files`` > 1, transfers run concurrently: each ``ascp``
        invocation is its own subprocess writing its own destination file, so
        this is safe.
        """
        if not user or not password:
            raise ValueError(
                "iProX Aspera requires credentials: pass --iprox-user and set "
                "IPROX_ASPERA_PASSWORD (or answer the password prompt), or use "
                "the default parallel HTTP transport instead."
            )
        ascp = cls._ascp_binary()
        env = dict(os.environ)
        env["ASPERA_SCP_PASS"] = password
        os.makedirs(output_folder, exist_ok=True)
        failed: List[str] = []
        workers = max(1, min(parallel_files, len(urls)))
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_url = {
                    executor.submit(
                        cls._aspera_download_one,
                        ascp,
                        url,
                        relative_paths[idx] if idx < len(relative_paths) else None,
                        output_folder,
                        user,
                        password,
                        maximum_bandwidth,
                        skip_if_downloaded_already,
                        env,
                    ): url
                    for idx, url in enumerate(urls)
                }
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        if result is not None:
                            failed.append(result)
                    except Exception as e:
                        logging.error(f"iProX Aspera failed for {url}: {e}")
                        failed.append(url)
        else:
            for idx, url in enumerate(urls):
                relpath = relative_paths[idx] if idx < len(relative_paths) else None
                result = cls._aspera_download_one(
                    ascp,
                    url,
                    relpath,
                    output_folder,
                    user,
                    password,
                    maximum_bandwidth,
                    skip_if_downloaded_already,
                    env,
                )
                if result is not None:
                    failed.append(result)
        if failed:
            raise RuntimeError(
                f"iProX Aspera download failed for {len(failed)} file(s): {failed}"
            )

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
