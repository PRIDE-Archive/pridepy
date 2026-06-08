from unittest import TestCase
from unittest.mock import Mock, patch

from click.testing import CliRunner

from pridepy.pdc.downloader import PDCDownloadStats
from pridepy.pridepy import main


class TestPDCCli(TestCase):
    def test_help_exposes_pdc_options_without_pride_protocol_options(self):
        result = CliRunner().invoke(main, ["download-pdc-files", "--help"])

        assert result.exit_code == 0
        assert "--accession" in result.output
        assert "--file-type" in result.output
        assert "--output-folder" in result.output
        assert "--skip-if-downloaded-already" in result.output
        assert "--checksum-check / --no-checksum-check" in result.output
        assert "--threads" in result.output
        assert "--retry" in result.output
        assert "--protocol" not in result.output
        assert "--aspera-maximum-bandwidth" not in result.output
        assert "--workers" not in result.output
        assert "--proxy-port" not in result.output

    def test_command_delegates_to_pdc_downloader(self):
        stats = PDCDownloadStats(studies=1, total_files=1, downloaded=1)
        runner = CliRunner()
        with patch("pridepy.pridepy.run_pdc_download", Mock(return_value=stats)) as mock_run:
            result = runner.invoke(
                main,
                [
                    "download-pdc-files",
                    "--accession",
                    "PDC000109",
                    "--file-type",
                    "psm",
                    "--output-folder",
                    "downloads",
                    "--skip-if-downloaded-already",
                    "--no-checksum-check",
                    "--threads",
                    "4",
                    "--retry",
                ],
            )

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            accession="PDC000109",
            file_type="psm",
            output_folder="downloads",
            skip_if_downloaded_already=True,
            checksum_check=False,
            download_threads=4,
            retry=True,
        )

    def test_command_allows_file_type_to_be_omitted_for_csv(self):
        stats = PDCDownloadStats(studies=2, total_files=2, downloaded=2)
        runner = CliRunner()
        with patch("pridepy.pridepy.run_pdc_download", Mock(return_value=stats)) as mock_run:
            result = runner.invoke(
                main,
                [
                    "download-pdc-files",
                    "--accession",
                    "studies.csv",
                    "--output-folder",
                    "downloads",
                ],
            )

        assert result.exit_code == 0
        mock_run.assert_called_once_with(
            accession="studies.csv",
            file_type=None,
            output_folder="downloads",
            skip_if_downloaded_already=False,
            checksum_check=True,
            download_threads=1,
            retry=False,
        )

    def test_root_help_lists_pdc_command(self):
        result = CliRunner().invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "download-pdc-files" in result.output
