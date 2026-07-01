"""ProteomeXchange provider.

ProteomeXchange is a meta-repository: a PXD/PRD accession routes through
the cross-repository XML at ``proteomecentral.proteomexchange.org``, and
the XML's ``Associated raw file URI`` cvParams point at the actual hosting
repository (PRIDE / MassIVE / JPOST / iProX / etc.).

Unlike the other providers in this package, ``ProteomeXchangeProvider`` is
NOT auto-registered with :mod:`pridepy.download.registry`. PXD/PRD
accessions would otherwise be ambiguous between PRIDE's V3 API listing and
ProteomeXchange's XML listing; the registry continues to route PXD/PRD via
:class:`pridepy.download.pride.PrideProvider`. ``ProteomeXchangeProvider``
is the explicit gateway invoked by the ``download-px-raw-files`` CLI
command and by ``Client.download_px_raw_files`` — callers who specifically
want the cross-repository XML view.

The class accepts either:

- a plain accession (``PXD039236``)
- a ProteomeCentral dataset URL (``https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=...``)

…and resolves it to the XML endpoint via :meth:`_normalize_px_xml_url`.
"""
import logging
import os
import posixpath
import re
import defusedxml.ElementTree as ET
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

from pridepy.download.base import Provider
from pridepy.download.util import flatten_relative_paths
from pridepy.util.api_handling import Util


class ProteomeXchangeProvider(Provider):
    name: ClassVar[str] = "proteomexchange"

    @staticmethod
    def matches(accession: str) -> bool:
        """Return True for PXD/PRD accessions or ProteomeCentral URLs.

        Not used by :mod:`pridepy.download.registry` (this provider is
        deliberately not auto-registered). Provided for parity with the
        ``Provider`` interface and so direct callers can introspect whether
        a given input looks like something ProteomeXchange knows how to
        handle.
        """
        if not accession:
            return False
        if accession.lower().startswith(("http://", "https://")):
            return "proteomexchange" in accession.lower() or "cgi/GetDataset" in accession
        return bool(re.fullmatch(r"(?:PXD|PRD)\d+", accession.upper()))

    @staticmethod
    def _normalize_px_xml_url(px_id_or_url: str) -> str:
        """Build the ProteomeXchange XML endpoint URL from an accession or URL.

        Examples accepted:
          - ``PXD039236``
          - ``https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236``
          - ``https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236&anything``
        """
        if px_id_or_url.startswith("http://") or px_id_or_url.startswith("https://"):
            parsed = urlparse(px_id_or_url)
            query = parsed.query or ""
            if "ID=" in query:
                id_value = [
                    q.split("=", 1)[1] for q in query.split("&") if q.startswith("ID=")
                ]
                if id_value:
                    return (
                        "https://proteomecentral.proteomexchange.org/cgi/GetDataset"
                        f"?ID={id_value[0]}&outputMode=XML&test=no"
                    )
            if parsed.path.endswith("/cgi/GetDataset"):
                return (
                    "https://proteomecentral.proteomexchange.org/cgi/GetDataset"
                    f"?{query}&outputMode=XML&test=no"
                )
        return (
            "https://proteomecentral.proteomexchange.org/cgi/GetDataset"
            f"?ID={px_id_or_url}&outputMode=XML&test=no"
        )

    @staticmethod
    def _parse_px_xml_for_raw_file_urls(px_xml_url: str) -> List[str]:
        """Fetch the PX XML and return every ``Associated raw file URI`` value."""
        headers = {"Accept": "application/xml"}
        response = Util.get_api_call(px_xml_url, headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        urls: List[str] = []
        for dataset_file in root.iter("DatasetFile"):
            for cv in dataset_file.findall("cvParam"):
                name = cv.attrib.get("name")
                value = cv.attrib.get("value")
                if name == "Associated raw file URI" and value:
                    urls.append(value)
        return urls

    @staticmethod
    def _relative_paths_for_urls(urls: List[str]) -> List[str]:
        """Compute a dataset-relative destination path for each URL.

        The PX XML's raw-file URIs point at arbitrary directories on the
        hosting repository, so flattening to the URL basename would let
        same-named files in different directories overwrite each other.
        Strip the common parent directory shared by all URIs and keep the
        remainder, so e.g. ``.../run1/x.raw`` and ``.../run2/x.raw`` become
        ``run1/x.raw`` and ``run2/x.raw``. A single file (or one with no
        shared prefix) falls back to its basename.
        """
        paths = [urlparse(url).path for url in urls]
        if not paths:
            return []
        dirs = [posixpath.dirname(p) for p in paths]
        try:
            common = dirs[0] if len(paths) == 1 else posixpath.commonpath(dirs)
        except ValueError:
            common = ""
        rels: List[str] = []
        for path in paths:
            # ``common`` is the shared ancestor of every path's directory, so
            # each path starts with it; strip it to keep the disambiguating
            # remainder. ``common`` can legitimately be ``"/"`` (files in
            # different top-level dirs) — handle that by stripping it too,
            # rather than collapsing to the (colliding) basename.
            if common:
                rel = path[len(common):].lstrip("/")
            else:
                rel = posixpath.basename(path)
            rels.append(rel or posixpath.basename(path))
        return rels

    def list_files(self, accession: str) -> List[Dict]:
        """Return the dataset's raw-file URIs as minimal file records.

        The PX XML doesn't expose checksums or rich category labels, so
        each record carries just enough to drive the downloader. A
        ``relativePath`` is derived per file (see
        :meth:`_relative_paths_for_urls`) so the transport layer preserves
        directory structure instead of colliding on duplicate basenames.
        """
        px_xml_url = self._normalize_px_xml_url(accession)
        logging.info(f"Fetching PX XML: {px_xml_url}")
        urls = self._parse_px_xml_for_raw_file_urls(px_xml_url)
        relative_paths = self._relative_paths_for_urls(urls)
        records: List[Dict] = []
        for url, relative_path in zip(urls, relative_paths):
            parsed = urlparse(url)
            records.append(
                {
                    "accession": accession,
                    "fileName": os.path.basename(parsed.path),
                    "fileCategory": {"value": "RAW"},
                    "publicFileLocations": [
                        {"name": "FTP Protocol", "value": url}
                    ],
                    "relativePath": relative_path,
                    "source": "ProteomeXchange",
                }
            )
        return records

    def download_from_accession_or_url(
        self,
        px_id_or_url: str,
        output_folder: str,
        skip_if_downloaded_already: bool = True,
        flatten: bool = True,
        parallel_files: int = 1,
        download_threads: int = 1,
        protocol: str = "ftp",
        iprox_user: Optional[str] = None,
        iprox_password: Optional[str] = None,
    ) -> None:
        """End-to-end: resolve XML, list files, partition by scheme, download.

        Convenience for the ``download-px-raw-files`` CLI command — combines
        :meth:`list_files` and :meth:`download_files` with the original
        ``download_px_raw_files`` defaults (skip-if-downloaded-already
        defaults to ``True``). ``parallel_files`` controls across-file
        concurrency and ``download_threads`` controls per-file HTTP Range
        segments; ``protocol`` flows into :meth:`download_files` (ftp/http(s)
        are handled directly today).

        When ``protocol == "aspera"``, iProX-hosted files are routed through
        :meth:`IproxProvider.aspera_download` instead of the HTTP/FTP path
        (opt-in, requires ``iprox_user``/``iprox_password``).
        """
        records = self.list_files(px_id_or_url)
        if not records:
            logging.info("No Associated raw file URIs found in PX XML")
            return

        if protocol.lower() == "aspera":
            from pridepy.download.iprox import IproxProvider
            iprox_urls, rels = [], []
            for r in records:
                loc = self.get_download_url(r, protocol)
                host = (urlparse(loc).hostname or "").lower()
                if host == "download.iprox.org":
                    iprox_urls.append(loc)
                    rels.append(r.get("relativePath"))
            if not iprox_urls:
                raise ValueError(
                    "Aspera requested but no iProX-hosted files found in this dataset."
                )
            if len(iprox_urls) < len(records):
                logging.warning(
                    "%d of %d file(s) are NOT hosted on iProX and were NOT "
                    "downloaded: --protocol aspera only handles iProX-hosted "
                    "files. Use the default HTTP transport (omit --protocol, "
                    "or pass --protocol ftp) to download the full set.",
                    len(records) - len(iprox_urls),
                    len(records),
                )
            if flatten:
                sources = [
                    rel if rel else urlparse(url).path
                    for url, rel in zip(iprox_urls, rels)
                ]
                dest_rels: List[Optional[str]] = flatten_relative_paths(sources)
            else:
                dest_rels = rels
            IproxProvider.aspera_download(
                urls=iprox_urls,
                output_folder=output_folder,
                relative_paths=dest_rels,
                user=iprox_user,
                password=iprox_password,
                skip_if_downloaded_already=skip_if_downloaded_already,
                parallel_files=parallel_files,
            )
            return

        self.download_files(
            accession=px_id_or_url,
            records=records,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            protocol=protocol,
            flatten=flatten,
            parallel_files=parallel_files,
            download_threads=download_threads,
        )
