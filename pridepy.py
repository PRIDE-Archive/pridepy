#!/usr/bin/env python3

import logging

import click

from authentication.authentication import Authentication
from files.raw import RawFiles
from msrun.msrun import MsRun
from pride.search import Search
from util.file_handling import FileHanding


@click.group()
def main():
    pass


@main.command()
@click.option('-a', '--accession', required=True, help='PRIDE project accession')
@click.option('-f', '--ftp_download_enabled', type=bool, default='True',
              help='If enabled, files will be downloaded from FTP, otherwise copy from file system')
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
        raw_files.copy_raw_files_from_dir(accession, input_folder)


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


@main.command()
@click.option('-k', '--keywords', required=False, help='The entered word will be searched among the fields to fetch '
                                                       'matching pride. The structure of the keywords is : *:*')
@click.option('-f', '--filters', required=False, help='Parameters to filter the search results. The structure of the '
                                                      'filter is: field1==value1, field2==value2. Example '
                                                      'accession==PRD000001')
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-dg', '--date_gap', required=False, help='A date range field with possible values of +1MONTH, +1YEAR')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sf', '--sort_fields', required=False, default='submission_date',
              help='Field(s) for sorting the results on. Default for this '
                   'request is submission_date. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def search_projects(keywords, filters, page_size, page, date_gap, sort_direction, sort_fields):
    """
    search public pride with keywords and filters
    :return:
    """
    search = Search()
    print(search.projects(keywords, filters, page_size, page, date_gap, sort_direction, sort_fields))


@main.command()
@click.option('-pa', '--project_accession', required=False, help='projectAccession')
@click.option('-aa', '--assay_accession', required=False, help='assayAccession')
@click.option('-ra', '--reported_accession', required=False, help='reportedAccession')
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sc', '--sort_conditions', required=False, default='projectAccession',
              help='Field(s) for sorting the results on. Default for this '
                   'request is project_accession. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def search_protein_evidences(project_accession, assay_accession, reported_accession, page_size, page,
                             sort_direction, sort_conditions):
    """
    search public pride protein evidences with keywords and filters
    :return:
    """
    search = Search()
    print(search.protein_evidences(project_accession, assay_accession, reported_accession, page_size, page,
                                   sort_direction, sort_conditions))


@main.command()
@click.option('-usi', '--usi', required=False, help='usi, Provide multiple values separated by \n')
@click.option('-pa', '--project_accession', required=False, help='projectAccession')
@click.option('-aa', '--assay_accession', required=False, help='assayAccession')
@click.option('-pepSeq', '--peptide_sequence', required=False, help='peptideSequence')
@click.option('-modSeq', '--modified_sequence', required=False, help='peptideSequence')
@click.option('-rt', '--result_type', required=False, default='COMPACT', help='peptideSequence')
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sc', '--sort_conditions', required=False, default='projectAccession',
              help='Field(s) for sorting the results on. Default for this '
                   'request is project_accession. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def search_spectra_evidences(usi, project_accession, assay_accession, peptide_sequence, modified_sequence,
                             result_type, page_size, page, sort_direction, sort_conditions):
    """
    search public pride spectra with keywords and filters
    :return:
    """
    search = Search()
    print(search.spectra(usi, project_accession, assay_accession, peptide_sequence, modified_sequence,
                         result_type, page_size, page, sort_direction, sort_conditions))


if __name__ == '__main__':
    main()
