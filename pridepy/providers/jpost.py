"""JPOST direct-download provider.

PRIMARY listing: PROXI JSON at repository.jpostdb.org. The PROXI endpoint
returns ``datasetFiles[*].value`` as ``ftp://`` URLs alongside CV labels
(Associated raw file URI, Search engine output file URI, etc.) which map
cleanly to PRIDE file categories.

FALLBACK listing: when PROXI fails, walk the FTP tree at ftp.jpostdb.org.
This is needed because JPOST's FTP server rate-limits aggressively per
source IP (sticky 421-too-many-connections); the PROXI path lets us avoid
walking the FTP tree just for a listing.
"""
import logging
import os
import re
from typing import ClassVar, Dict, List, Optional
from urllib.parse import urlparse

import requests

from pridepy.providers import registry
from pridepy.providers.base import BaseDirectDownloadProvider


@registry.register
class JpostProvider(BaseDirectDownloadProvider):
    name: ClassVar[str] = "jpost"
    use_tls: ClassVar[bool] = False

    ARCHIVE_FTP: ClassVar[str] = "ftp.jpostdb.org"
    ARCHIVE_FTP_URL_PREFIX: ClassVar[str] = "ftp://ftp.jpostdb.org/"
    PROXI_BASE_URL: ClassVar[str] = "https://repository.jpostdb.org/proxi/datasets/"

    PROXI_CATEGORY_MAP: ClassVar[Dict[str, str]] = {
        "Associated raw file URI": "RAW",
        "Result file URI": "RESULT",
        "Search engine output file URI": "SEARCH",
        "Peak list file URI": "PEAK",
        "Spectrum library file URI": "SPECTRUM_LIBRARY",
        "Sequence database URI": "FASTA",
        "Quantification file URI": "RESULT",
    }

    @staticmethod
    def matches(accession: str) -> bool:
        if not accession:
            return False
        return bool(re.fullmatch(r"JPST\d{6}", accession.upper()))

    @staticmethod
    def _get_public_root(accession: str) -> str:
        return f"/{accession.upper()}"

    @classmethod
    def _get_public_ftp_url(cls, accession: str, remote_path: str) -> str:
        root_path = cls._get_public_root(accession).rstrip("/")
        relative_path = remote_path
        if remote_path.startswith(root_path):
            relative_path = remote_path[len(root_path):].lstrip("/")
        return f"{cls.ARCHIVE_FTP_URL_PREFIX}{accession.upper()}/{relative_path}"

    @classmethod
    def _build_file_record(
        cls, accession: str, ftp_url: str, category_from_proxi: Optional[str] = None
    ) -> Dict:
        """Build a pridepy file record from an FTP URL.

        When ``category_from_proxi`` is provided (e.g. ``"Associated raw file URI"``),
        the PROXI CV name takes precedence over the heuristic collection-from-path
        mapping. Falls back to the same path-segment heuristic used for MassIVE
        when the category isn't known.
        """
        # Import the MassIVE collection->category map for the fallback heuristic.
        from pridepy.providers.massive import MassiveProvider
        parsed = urlparse(ftp_url)
        root_prefix = f"/{accession.upper()}/"
        relative_path = parsed.path
        if relative_path.startswith(root_prefix):
            relative_path = relative_path[len(root_prefix):]
        relative_path = relative_path.lstrip("/")
        collection = relative_path.split("/", 1)[0] if relative_path else ""
        if category_from_proxi and category_from_proxi in cls.PROXI_CATEGORY_MAP:
            category = cls.PROXI_CATEGORY_MAP[category_from_proxi]
        else:
            category = MassiveProvider._map_collection_to_category(collection)
        return {
            "accession": accession.upper(),
            "fileName": os.path.basename(parsed.path),
            "fileCategory": {"value": category},
            "publicFileLocations": [{"name": "FTP Protocol", "value": ftp_url}],
            "relativePath": relative_path,
            "collection": collection,
            "source": "JPOST",
        }

    def list_files(self, accession: str) -> List[Dict]:
        """PRIMARY: PROXI JSON. FALLBACK: FTP tree walk."""
        normalized = accession.upper()
        try:
            return self._list_via_proxi(normalized)
        except Exception as proxi_error:
            logging.warning(
                f"JPOST PROXI listing failed for {normalized} "
                f"({proxi_error}); falling back to FTP tree walk."
            )
            from pridepy.providers import transport
            remote_root = self._get_public_root(normalized)
            remote_files = transport._list_ftp_repo_files(
                host=self.ARCHIVE_FTP,
                remote_root=remote_root,
                error_label=f"JPOST dataset {normalized}",
            )
            return [
                self._build_file_record(
                    normalized,
                    self._get_public_ftp_url(normalized, remote_file),
                )
                for remote_file in remote_files
            ]

    def _list_via_proxi(self, accession: str) -> List[Dict]:
        """Fetch JPOST PROXI dataset metadata and turn each datasetFiles entry into a file record."""
        import json as _json
        proxi_url = f"{self.PROXI_BASE_URL}{accession}"
        logging.info(f"Fetching JPOST PROXI metadata: {proxi_url}")
        response = requests.get(
            proxi_url,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        data = _json.loads(response.content)
        dataset_files = data.get("datasetFiles") or []
        records: List[Dict] = []
        for entry in dataset_files:
            value = (entry or {}).get("value")
            if not value or not value.startswith("ftp://"):
                continue
            records.append(
                self._build_file_record(
                    accession,
                    value,
                    category_from_proxi=(entry or {}).get("name"),
                )
            )
        if not records:
            raise RuntimeError(
                f"JPOST PROXI returned no FTP file URIs for {accession}"
            )
        return records
