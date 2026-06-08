import hashlib
import os
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

import pytest
import requests

from pridepy.pdc.client import PDCFile
from pridepy.pdc.downloader import download_pdc_files


ABC_MD5 = hashlib.md5(b"abc").hexdigest()


def _pdc_file(name="sample.psm", url="https://example.org/sample.psm", md5sum=ABC_MD5, study_id="PDC000109"):
    return PDCFile(
        study_id=study_id,
        file_id="file-1",
        file_name=name,
        file_format="tsv",
        file_size=3,
        data_category="Peptide Spectral Matches",
        file_type="Text",
        file_location="s3://bucket/key",
        md5sum=md5sum,
        url=url,
    )


def _fetcher(files):
    def fetch_files(study_id, file_type):
        assert study_id == "PDC000109"
        assert file_type == "psm"
        return files

    return fetch_files


def _all_files_fetcher(files):
    def fetch_files(study_id, file_type):
        assert study_id == "PDC000109"
        assert file_type is None
        return files

    return fetch_files


def _write_data(_url, target):
    with open(target, "wb") as handle:
        handle.write(b"abc")


class TestPDCDownloader(TestCase):
    def test_skip_existing_file_with_matching_checksum(self):
        pdc_file = _pdc_file()
        with tempfile.TemporaryDirectory() as tmp_dir:
            study_dir = os.path.join(tmp_dir, "PDC000109")
            os.makedirs(study_dir)
            target = os.path.join(study_dir, "sample.psm")
            with open(target, "wb") as handle:
                handle.write(b"abc")

            with patch("pridepy.pdc.downloader.transport._parallel_download") as mock_download:
                stats = download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    skip_if_downloaded_already=True,
                    checksum_check=True,
                    fetch_files=_fetcher([pdc_file]),
                )

            mock_download.assert_not_called()
            assert stats.skipped == 1
            assert stats.downloaded == 0

    def test_download_success_moves_part_to_final_file(self):
        pdc_file = _pdc_file()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                stats = download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    checksum_check=True,
                    fetch_files=_fetcher([pdc_file]),
                )

            target = os.path.join(tmp_dir, "PDC000109", "sample.psm")
            assert stats.downloaded == 1
            assert os.path.exists(target)
            assert not os.path.exists(target + ".part")
            with open(target, "rb") as handle:
                assert handle.read() == b"abc"

    def test_csv_can_download_multiple_file_types(self):
        calls = []

        def fetch_files(study_id, file_type):
            calls.append((study_id, file_type))
            return [_pdc_file(name=f"{study_id}.{file_type}", study_id=study_id)]

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = os.path.join(tmp_dir, "studies.csv")
            with open(csv_path, "w", encoding="utf-8") as handle:
                handle.write("pdc_id,file-type\nPDC000109,psm\nPDC000110,mzid\n")

            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                stats = download_pdc_files(
                    accession=csv_path,
                    file_type=None,
                    output_folder=tmp_dir,
                    checksum_check=True,
                    fetch_files=fetch_files,
                )

            assert calls == [("PDC000109", "psm"), ("PDC000110", "mzid")]
            assert stats.studies == 2
            assert stats.total_files == 2
            assert stats.downloaded == 2
            assert os.path.exists(os.path.join(tmp_dir, "PDC000109", "PDC000109.psm"))
            assert os.path.exists(os.path.join(tmp_dir, "PDC000110", "PDC000110.mzid"))

    def test_threads_use_multipart_downloader(self):
        pdc_file = _pdc_file()
        with tempfile.TemporaryDirectory() as tmp_dir:
            def fake_multipart(_url, target, threads=1):
                assert threads == 4
                _write_data(_url, target)

            with patch(
                "pridepy.pdc.downloader.transport._multipart_download",
                side_effect=fake_multipart,
            ) as mock_multipart:
                download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    checksum_check=True,
                    download_threads=4,
                    fetch_files=_fetcher([pdc_file]),
                )

            mock_multipart.assert_called_once()

    def test_missing_md5_falls_back_to_size_validation(self):
        pdc_file = _pdc_file(md5sum=None)
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                stats = download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    checksum_check=True,
                    fetch_files=_fetcher([pdc_file]),
                )

            assert stats.downloaded == 1

    def test_all_empty_matches_fail_and_write_failed_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(RuntimeError, match="Failed to download 1 PDC file"):
                download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    fetch_files=lambda _study_id, _file_type: [],
                )

            failed_log = os.path.join(tmp_dir, "failed_files.txt")
            with open(failed_log, "r", encoding="utf-8") as handle:
                content = handle.read()
            assert "PDC000109\t<psm>\tNo PDC files matched file_type=psm" in content

    def test_partial_empty_matches_warn_and_continue(self):
        pdc_file = _pdc_file()

        def fetch_files(study_id, file_type):
            assert file_type == "psm"
            if study_id == "PDC_EMPTY":
                return []
            assert study_id == "PDC000109"
            return [pdc_file]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                stats = download_pdc_files(
                    accession="PDC000109,PDC_EMPTY",
                    file_type="psm",
                    output_folder=tmp_dir,
                    checksum_check=True,
                    fetch_files=fetch_files,
                )

            assert stats.studies == 2
            assert stats.total_files == 1
            assert stats.downloaded == 1
            assert stats.failed == 0
            assert not os.path.exists(os.path.join(tmp_dir, "failed_files.txt"))

    def test_checksum_failure_writes_failed_files(self):
        pdc_file = _pdc_file(md5sum="ffffffffffffffffffffffffffffffff")
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                with pytest.raises(RuntimeError, match="Failed to download 1 PDC file"):
                    download_pdc_files(
                        accession="PDC000109",
                        file_type="psm",
                        output_folder=tmp_dir,
                        checksum_check=True,
                        fetch_files=_fetcher([pdc_file]),
                    )

            failed_log = os.path.join(tmp_dir, "failed_files.txt")
            with open(failed_log, "r", encoding="utf-8") as handle:
                content = handle.read()
            assert "PDC000109\tsample.psm\tchecksum mismatch" in content

    def test_403_retry_refreshes_signed_url(self):
        pdc_file = _pdc_file(url="https://example.org/old")
        response = Mock()
        response.status_code = 403
        http_error = requests.HTTPError("403 Client Error")
        http_error.response = response
        seen_urls = []

        def fake_download(url, target):
            seen_urls.append(url)
            if url == "https://example.org/old":
                raise http_error
            _write_data(url, target)

        refresh = Mock(return_value="https://example.org/new")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=fake_download,
            ), patch("pridepy.pdc.downloader.time.sleep"):
                stats = download_pdc_files(
                    accession="PDC000109",
                    file_type="psm",
                    output_folder=tmp_dir,
                    checksum_check=True,
                    retry=True,
                    fetch_files=_fetcher([pdc_file]),
                    refresh_url=refresh,
                )

        assert stats.downloaded == 1
        assert seen_urls == ["https://example.org/old", "https://example.org/new"]
        refresh.assert_called_once_with("PDC000109", "sample.psm", "psm")

    def test_no_file_type_downloads_all_files(self):
        psm_file = _pdc_file(name="sample.psm")
        raw_file = _pdc_file(name="sample.raw")
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch(
                "pridepy.pdc.downloader.transport._parallel_download",
                side_effect=_write_data,
            ):
                stats = download_pdc_files(
                    accession="PDC000109",
                    file_type=None,
                    output_folder=tmp_dir,
                    checksum_check=True,
                    fetch_files=_all_files_fetcher([psm_file, raw_file]),
                )

            assert stats.downloaded == 2
            assert stats.total_files == 2
            assert os.path.exists(os.path.join(tmp_dir, "PDC000109", "sample.psm"))
            assert os.path.exists(os.path.join(tmp_dir, "PDC000109", "sample.raw"))
