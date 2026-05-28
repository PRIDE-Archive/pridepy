"""MassIVE direct-download provider.

Primary path: list files by walking the FTPS tree at massive-ftp.ucsd.edu
(TLS is required by the server) and download them over FTPS.

HTTPS fallback: some networks block FTP/FTPS entirely. When the FTPS
listing fails, fall back to the HTTPS file index at datasetcache.gnps2.org
and download each file from the ProteoSAFe HTTPS endpoint at
massive.ucsd.edu (same bytes as FTPS, verified by checksum). The fallback
keeps everything over HTTPS so it works on FTPS-blocked networks.
"""
import logging
import os
import re
from typing import ClassVar, Dict, List
from urllib.parse import quote, urlparse

import requests

from pridepy.download import registry
from pridepy.download.base import Provider


MASSIVE_CATEGORY_MAP = {
    "raw": "RAW",
    "peak": "PEAK",
    "ccms_peak": "PEAK",
    "search": "SEARCH",
    "result": "RESULT",
    "ccms_result": "RESULT",
    "quant": "RESULT",
    "fasta": "FASTA",
    "spectrum_library": "SPECTRUM_LIBRARY",
    "library": "SPECTRUM_LIBRARY",
}


@registry.register
class MassiveProvider(Provider):
    name: ClassVar[str] = "massive"
    use_tls: ClassVar[bool] = True

    ARCHIVE_FTP: ClassVar[str] = "massive-ftp.ucsd.edu"
    ARCHIVE_FTP_URL_PREFIX: ClassVar[str] = "ftp://massive-ftp.ucsd.edu/v01/"

    # HTTPS fallback for FTPS-blocked networks.
    HTTPS_DOWNLOAD_URL: ClassVar[str] = (
        "https://massive.ucsd.edu/ProteoSAFe/DownloadResultFile"
    )
    # GNPS2 dataset cache: HTTPS file index (datasette CSV stream).
    HTTPS_FILE_INDEX_URL: ClassVar[str] = (
        "https://datasetcache.gnps2.org/datasette/database/filename.csv"
    )

    @staticmethod
    def matches(accession: str) -> bool:
        """Return True when ``accession`` is a MassIVE dataset accession."""
        if not accession:
            return False
        return bool(re.fullmatch(r"R?MSV\d{9}", accession.upper()))

    @staticmethod
    def _get_public_root(accession: str) -> str:
        return f"/v01/{accession.upper()}"

    @classmethod
    def _get_public_ftp_url(cls, accession: str, remote_path: str) -> str:
        root_path = cls._get_public_root(accession).rstrip("/")
        relative_path = remote_path
        if remote_path.startswith(root_path):
            relative_path = remote_path[len(root_path):].lstrip("/")
        return f"{cls.ARCHIVE_FTP_URL_PREFIX}{accession.upper()}/{relative_path}"

    @staticmethod
    def _map_collection_to_category(collection: str) -> str:
        return MASSIVE_CATEGORY_MAP.get(collection.lower(), "OTHER")

    @classmethod
    def _build_file_record(cls, accession: str, ftp_url: str) -> Dict:
        """Build a pridepy file record from an FTP URL inside the dataset."""
        parsed = urlparse(ftp_url)
        root_prefix = f"/v01/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix):]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": cls._map_collection_to_category(collection)},
            "publicFileLocations": [{"name": "FTP Protocol", "value": ftp_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "MassIVE",
        }

    @classmethod
    def _get_https_url(cls, accession: str, relative_path: str) -> str:
        """ProteoSAFe HTTPS download URL for a dataset-relative file path.

        Mirrors the FTPS file: ``f.<ACCESSION>/<relative_path>`` in the
        ProteoSAFe ftp file-space. Verified to return byte-identical content
        to the FTPS copy.
        """
        file_param = f"f.{accession.upper()}/{relative_path.lstrip('/')}"
        return (
            f"{cls.HTTPS_DOWNLOAD_URL}?forceDownload=true"
            f"&file={quote(file_param, safe='/.')}"
        )

    @classmethod
    def _build_https_file_record(cls, accession: str, relative_path: str) -> Dict:
        """Build a file record whose download location is the HTTPS endpoint."""
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(relative_path),
            "fileCategory": {"value": cls._map_collection_to_category(collection)},
            # base.Provider.download_files routes by URL scheme; an https://
            # value here sends the file through the HTTPS transport.
            "publicFileLocations": [
                {"name": "HTTPS", "value": cls._get_https_url(accession, relative_path)}
            ],
            "relativePath": relative_path,
            "collection": collection,
            "source": "MassIVE",
        }

    def _list_via_https(self, accession: str) -> List[Dict]:
        """List dataset files over HTTPS via the GNPS2 dataset cache.

        Used when FTPS is unavailable (blocked network). Streams the file
        index as CSV and builds HTTPS-download records.
        """
        import csv
        normalized = accession.upper()
        logging.info(f"Listing MassIVE dataset {normalized} via HTTPS file index")
        response = requests.get(
            self.HTTPS_FILE_INDEX_URL,
            params={"dataset__exact": normalized, "_stream": "on", "_col": "filepath"},
            timeout=60,
            stream=True,
        )
        response.raise_for_status()
        lines = (line.decode("utf-8") for line in response.iter_lines() if line)
        records: List[Dict] = []
        for row in csv.DictReader(lines):
            file_path = (row.get("filepath") or "").strip()
            if file_path:
                records.append(self._build_https_file_record(normalized, file_path))
        if not records:
            raise RuntimeError(
                f"No files found via HTTPS file index for MassIVE dataset {normalized}"
            )
        return records

    def list_files(self, accession: str) -> List[Dict]:
        from pridepy.download import transport
        normalized = accession.upper()
        remote_root = self._get_public_root(normalized)
        try:
            remote_files = transport._list_ftp_repo_files(
                host=self.ARCHIVE_FTP,
                remote_root=remote_root,
                error_label=f"MassIVE dataset {normalized}",
                use_tls=True,
            )
        except Exception as ftps_error:
            logging.warning(
                "MassIVE FTPS listing failed for %s (%s); "
                "falling back to the HTTPS file index.",
                normalized,
                ftps_error,
            )
            return self._list_via_https(normalized)
        return [
            self._build_file_record(
                normalized,
                self._get_public_ftp_url(normalized, remote_file),
            )
            for remote_file in remote_files
        ]
