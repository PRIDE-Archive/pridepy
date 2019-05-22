#!/usr/bin/env python3

import click
import logging

from authentication.authentication import Authentication
from files.raw import RawFiles
from msrun.msrun import MsRun
from util.file_handling import FileHanding


@click.group()
def main():
    pass


@main.command()
@click.option('-a', '--accession', required=True, help='PRIDE project accession')
@click.option('-f', '--ftp_download_enabled', type=bool, default='True', help='If enabled, files will be downloaded from FTP, otherwise copy from file system')
@click.option('-i', '--input_folder', required=False, help='Input folder to copy the raw files')
@click.option('-o', '--output_folder', required=True, help='output folder to download or copy raw files')
def download(accession, ftp_download_enabled, input_folder, output_folder):
    """
    This script download raw files from FTP or copy from the file system
    """

    raw_files = RawFiles()

    logging.info("accession: " + accession)

    if ftp_download_enabled:
        logging.info("Data will be download from ftp")
        raw_files.download_raw_files_from_ftp(accession, output_folder)
    else:
        logging.info("Data will be copied from file system " + output_folder)
        raw_files.copy_raw_files_from_dir(accession,input_folder)


@main.command()
@click.option('-f', '--filename', required=True, help='Metadata file')
@click.option('-u', '--username', required=True, help='PRIDE account username')
@click.option('-p', '--password', required=True, help='PRIDE account password')
def update_metadata(filename, username, password):
    """
    Update extracted metadata from raw files into MongoDB
    :return:
    """

    # Get user token to make calls with PRIDE API
    authentication = Authentication()
    token = authentication.get_token(username, password)

    # Format extracted metadata to compatible with PRIDE API endpoint
    fileHandling = FileHanding()
    fileHandling.wrap_with_ms_run_metadata(filename)

    # Update msrun metatdata
    msrun = MsRun()
    msrun.update_msrun_metadata(filename, token)


if __name__ == '__main__':
    main()