"""iProX direct-download support.

iProX publishes the ProteomeXchange XML for each dataset at a deterministic
path on its anonymous HTTPS download server::

    http://download.iprox.org/<accession>/PX_<accession>.xml

The referenced files are served from the same host over HTTPS with byte-range
support, so resume and parallel downloads use the same plumbing as PRIDE
HTTP(S) transfers.
"""
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

from pridepy.files.files import Files
from pridepy.download import transport
from pridepy.download.iprox import IproxProvider
from pridepy.download.pride import PrideProvider


IPROX_XML_FIXTURE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ProteomeXchangeDataset id="PXD000001" formatVersion="1.4.0">
  <DatasetIdentifierList>
    <DatasetIdentifier>
      <cvParam cvRef="MS" accession="MS:1002836" name="iProX dataset identifier" value="IPX0017413000"/>
    </DatasetIdentifier>
  </DatasetIdentifierList>
  <DatasetFileList>
    <DatasetFile id="FILE_0" name="sample1.raw">
      <cvParam cvRef="MS" accession="MS:1002846" name="Associated raw file URI"
        value="http://download.iprox.org/IPX0017413000/IPX0017413001/sample1.raw"/>
    </DatasetFile>
    <DatasetFile id="FILE_1" name="sample2.raw">
      <cvParam cvRef="MS" accession="MS:1002846" name="Associated raw file URI"
        value="http://download.iprox.org/IPX0017413000/IPX0017413001/sample2.raw"/>
    </DatasetFile>
    <DatasetFile id="FILE_2" name="results.tsv">
      <cvParam cvRef="MS" accession="MS:1002849" name="Search engine output file URI"
        value="http://download.iprox.org/IPX0017413000/IPX0017413001/results.tsv"/>
    </DatasetFile>
    <DatasetFile id="FILE_3" name="ignored.txt">
      <cvParam cvRef="MS" accession="MS:9999999" name="Other URI"
        value="ftp://example.org/should-be-ignored"/>
    </DatasetFile>
  </DatasetFileList>
</ProteomeXchangeDataset>
""".encode("utf-8")


class TestIProXFiles(TestCase):
    def test_is_iprox_accession_matches_ipx_format(self):
        assert Files.is_iprox_accession("IPX0000123")
        assert Files.is_iprox_accession("IPX0000123000")
        assert Files.is_iprox_accession("ipx1234567")
        assert not Files.is_iprox_accession("PXD000012")
        assert not Files.is_iprox_accession("MSV000012345")
        assert not Files.is_iprox_accession("JPST000001")
        assert not Files.is_iprox_accession("IPX12")
        assert not Files.is_iprox_accession("")
        assert not Files.is_iprox_accession(None)

    def test_iprox_is_a_direct_download_accession(self):
        assert Files.is_direct_download_accession("IPX0017413000")

    def test_build_iprox_file_record_maps_px_cv_to_category(self):
        record = IproxProvider._build_file_record(
            "IPX0017413000",
            "http://download.iprox.org/IPX0017413000/IPX0017413001/sample.raw",
            category_from_px="Associated raw file URI",
        )
        assert record["fileName"] == "sample.raw"
        assert record["fileCategory"]["value"] == "RAW"
        assert record["source"] == "iProX"
        # _download_direct_download_records dispatches by URL scheme, so the
        # publicFileLocations URL must still be the HTTPS download URL.
        assert record["publicFileLocations"][0]["value"].startswith("http://")

    def test_list_iprox_public_files_parses_px_xml(self):
        fake_response = MagicMock()
        fake_response.content = IPROX_XML_FIXTURE
        fake_response.raise_for_status = MagicMock()
        with patch(
            "pridepy.download.iprox.requests.get", return_value=fake_response
        ) as req_mock:
            records = IproxProvider().list_files("IPX0017413000")

        # The fetch hits the deterministic PX XML URL.
        req_mock.assert_called_once()
        called_url = req_mock.call_args[0][0]
        assert called_url == (
            "http://download.iprox.org/IPX0017413000/PX_IPX0017413000.xml"
        )

        # 3 valid HTTPS records; the ftp:// "Other URI" cvParam was filtered out.
        assert len(records) == 3
        cats = {r["fileName"]: r["fileCategory"]["value"] for r in records}
        assert cats == {
            "sample1.raw": "RAW",
            "sample2.raw": "RAW",
            "results.tsv": "SEARCH",
        }
        for r in records:
            assert r["source"] == "iProX"
            assert r["publicFileLocations"][0]["value"].startswith("http://")

    def test_get_all_raw_file_list_filters_iprox_records(self):
        files = Files()
        fake_response = MagicMock()
        fake_response.content = IPROX_XML_FIXTURE
        fake_response.raise_for_status = MagicMock()
        with patch(
            "pridepy.download.iprox.requests.get", return_value=fake_response
        ), patch.object(PrideProvider, "stream_all_files_by_project") as pride_mock:
            raw_files = files.get_all_raw_file_list("IPX0017413000")

        pride_mock.assert_not_called()
        assert {r["fileName"] for r in raw_files} == {"sample1.raw", "sample2.raw"}

    def test_download_file_by_name_routes_iprox_to_http_urls(self):
        files = Files()
        fake_response = MagicMock()
        fake_response.content = IPROX_XML_FIXTURE
        fake_response.raise_for_status = MagicMock()
        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "pridepy.download.iprox.requests.get", return_value=fake_response
        ), patch.object(transport, "download_http_urls") as http_mock, patch.object(
            transport, "download_ftp_urls"
        ) as ftp_mock:
            files.download_file_by_name(
                accession="IPX0017413000",
                file_name="results.tsv",
                output_folder=tmp_dir,
                skip_if_downloaded_already=False,
                protocol="ftp",
                username=None,
                password=None,
                aspera_maximum_bandwidth="100M",
                checksum_check=False,
            )

        # iProX is HTTPS, not FTP — FTP path must not be called.
        ftp_mock.assert_not_called()
        http_mock.assert_called_once()
        kwargs = http_mock.call_args.kwargs
        assert kwargs["http_urls"] == [
            "http://download.iprox.org/IPX0017413000/IPX0017413001/results.tsv"
        ]
        assert kwargs["parallel_files"] == 1
        assert kwargs["skip_if_downloaded_already"] is False
