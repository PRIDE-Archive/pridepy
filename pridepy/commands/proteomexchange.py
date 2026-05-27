"""ProteomeXchange XML download command.

Given a PXD accession or a ProteomeXchange XML URL, parse the XML for
``Associated raw file URI`` cvParams and download each one over its
native scheme (ftp:// via FTP, http(s):// via HTTPS).
"""
import logging
import os
import xml.etree.ElementTree as ET
from typing import List
from urllib.parse import urlparse

from pridepy.util.api_handling import Util


def _normalize_px_xml_url(px_id_or_url: str) -> str:
    """
    Build the ProteomeXchange XML endpoint from a dataset accession or a dataset web URL.
    Examples accepted:
      - PXD039236
      - https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236
      - https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD039236&anything
    """
    if px_id_or_url.startswith("http://") or px_id_or_url.startswith("https://"):
        parsed = urlparse(px_id_or_url)
        # keep the ID param value if present; otherwise fallback to the path tail
        query = parsed.query or ""
        if "ID=" in query:
            id_value = [q.split("=", 1)[1] for q in query.split("&") if q.startswith("ID=")]
            if id_value:
                return (
                    f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={id_value[0]}&outputMode=XML&test=no"
                )
        # If the input URL already requests XML, just ensure flags
        if parsed.path.endswith("/cgi/GetDataset"):
            return (
                f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?{query}&outputMode=XML&test=no"
            )
    # Assume it's a plain accession if not a URL
    return (
        f"https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID={px_id_or_url}&outputMode=XML&test=no"
    )


def _parse_px_xml_for_raw_file_urls(px_xml_url: str) -> List[str]:
    """
    Parse the PX XML and return a list of associated raw file URIs.
    We extract cvParam with name "Associated raw file URI" under each DatasetFile.
    """
    headers = {"Accept": "application/xml"}
    response = Util.get_api_call(px_xml_url, headers)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    urls: List[str] = []
    # The XML namespace is often absent in PX XML; access elements directly
    for dataset_file in root.iter("DatasetFile"):
        for cv in dataset_file.findall("cvParam"):
            name = cv.attrib.get("name")
            value = cv.attrib.get("value")
            if name == "Associated raw file URI" and value:
                urls.append(value)
    return urls


def download_px_raw_files(
    px_id_or_url: str,
    output_folder: str,
    skip_if_downloaded_already: bool = True,
) -> None:
    """Download all raw files referenced by a ProteomeXchange dataset.

    Prefers FTP when the URL is ftp://, otherwise uses HTTP(S). Supports
    resume and skip.
    """
    from pridepy.files.files import Files  # lazy: avoid module-load cycle

    if not os.path.isdir(output_folder):
        os.makedirs(output_folder, exist_ok=True)

    px_xml_url = _normalize_px_xml_url(px_id_or_url)
    logging.info(f"Fetching PX XML: {px_xml_url}")
    urls = _parse_px_xml_for_raw_file_urls(px_xml_url)
    if not urls:
        logging.info("No Associated raw file URIs found in PX XML")
        return

    ftp_urls = [u for u in urls if u.lower().startswith("ftp://")]
    http_urls = [u for u in urls if u.lower().startswith(("http://", "https://"))]

    if ftp_urls:
        Files.download_ftp_urls(ftp_urls, output_folder, skip_if_downloaded_already)
    if http_urls:
        Files.download_http_urls(http_urls, output_folder, skip_if_downloaded_already)
