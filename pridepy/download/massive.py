"""MassIVE direct-download provider.

Lists files by walking the FTPS tree at massive-ftp.ucsd.edu (TLS is
required by the server). Downloads files via the shared transport layer
with ``use_tls=True``.
"""
import os
import re
from typing import ClassVar, Dict, List
from urllib.parse import urlparse

from pridepy.download import registry
from pridepy.download.base import BaseDirectDownloadProvider


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
class MassiveProvider(BaseDirectDownloadProvider):
    name: ClassVar[str] = "massive"
    use_tls: ClassVar[bool] = True

    ARCHIVE_FTP: ClassVar[str] = "massive-ftp.ucsd.edu"
    ARCHIVE_FTP_URL_PREFIX: ClassVar[str] = "ftp://massive-ftp.ucsd.edu/v01/"

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

    def list_files(self, accession: str) -> List[Dict]:
        from pridepy.download import transport
        normalized = accession.upper()
        remote_root = self._get_public_root(normalized)
        remote_files = transport._list_ftp_repo_files(
            host=self.ARCHIVE_FTP,
            remote_root=remote_root,
            error_label=f"MassIVE dataset {normalized}",
            use_tls=True,
        )
        return [
            self._build_file_record(
                normalized,
                self._get_public_ftp_url(normalized, remote_file),
            )
            for remote_file in remote_files
        ]
