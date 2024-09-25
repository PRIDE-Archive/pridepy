#!/usr/bin/env python3

import logging
import os
from datetime import datetime

import click
import requests

from authentication.authentication import Authentication
from files.files import Files
from msrun.msrun import MsRun
from project.project import Project
from util.file_handling import FileHanding


@click.group()
def main():
    pass


@main.command()
@click.option('-a', '--accession', required=True, help='PRIDE project accession')
@click.option('-cpf', '--copy_from_file_system', type=bool, default='False',
              help='Copy from file system, If enabled copy from files from local pride file system '
                   '(This is purely for PRIDE internal developers)')
@click.option('-p', '--protocol', default='ftp',
              help='Protocol to be used to download files either by ftp or aspera or from globus. Default is ftp')
@click.option('-i', '--input_folder', required=False, help='Input folder to copy the raw files')
@click.option('-o', '--output_folder', required=True, help='output folder to download or copy raw files')
def download_all_raw_files(accession, copy_from_file_system, protocol, input_folder, output_folder):
    """
    This script download raw files from FTP or copy from the file system
    """

    raw_files = Files()

    logging.info("accession: " + accession)

    if not copy_from_file_system:
        logging.info(f"Data will be downloaded from {protocol}")
        raw_files.download_all_raw_files(accession, output_folder, protocol)
    else:
        logging.info("Data will be copied from file system " + output_folder)
        raw_files.copy_raw_files_from_dir(accession, input_folder)


@main.command()
@click.option('-a', '--accession', required=True, help='PRIDE project accession')
@click.option('-cpf', '--copy_from_file_system', type=bool, default=False, required=False,
              help='Copy from file system, If enabled copy from files from local pride file system '
                   '(This is purely for PRIDE internal developers)')
@click.option('-p', '--protocol', default='ftp',
              help='Protocol to be used to download files either by ftp or aspera or from globus. Default is ftp')
@click.option('-f', '--file_name', required=True, help='fileName to be downloaded')
@click.option('-i', '--input_folder', required=False, help='Input folder to copy the files')
@click.option('-o', '--output_folder', required=True, help='output folder to download or copy files')
def download_files_by_name(accession, copy_from_file_system, protocol, file_name, input_folder, output_folder):
    """
    This script download single file from servers or copy from the file system
    """

    raw_files = Files()

    logging.info("accession: " + accession)

    if not copy_from_file_system:
        logging.info(f"Data will be downloaded from {protocol}")
        raw_files.download_file_by_name(accession, file_name, output_folder, protocol)
    else:
        logging.info("Data will be copied from file system " + output_folder)
        raw_files.copy_file_from_dir_by_name(accession, file_name, input_folder)

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
    file_handling = FileHanding()
    file_handling.wrap_with_ms_run_metadata(filename)

    # Update msrun metatdata
    msrun = MsRun()
    msrun.update_msrun_metadata(filename, token)


@main.command()
@click.option('-k', '--keyword', required=False, help='The entered word will be searched among the fields to fetch '
                                                      'matching pride. The structure of the keyword is : *:*')
@click.option('-f', '--filter', required=False, help='Parameters to filter the search results. The structure of the '
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
def search_projects_by_keywords_and_filters(keyword, filter, page_size, page, date_gap, sort_direction, sort_fields):
    """
    search public pride with keywords and filters
    :return:
    """
    project = Project()
    print(project.search_by_keywords_and_filters(keyword, filter, page_size, page, date_gap, sort_direction,
                                                 sort_fields))


@main.command()
@click.option('-k', '--keyword', required=False, help='The entered word will be searched among the fields to fetch '
                                                      'matching pride. The structure of the keyword is : *:*')
@click.option('-f', '--filter', required=False, help='Parameters to filter the search results. The structure of the '
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
def search_projects_by_keywords_and_filters(keyword, filter, page_size, page, date_gap, sort_direction, sort_fields):
    """
    search public pride with keywords and filters
    :return:
    """
    project = Project()
    print(project.search_by_keywords_and_filters(keyword, filter, page_size, page, date_gap, sort_direction,
                                                 sort_fields))


@main.command()
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sc', '--sort_conditions', required=False, default='projectAccession',
              help='Field(s) for sorting the results on. Default for this '
                   'request is project_accession. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def get_projects(page_size, page, sort_direction, sort_conditions):
    """
    get paged projects
    :return:
    """
    project = Project()
    print(project.get_projects(page_size, page, sort_direction, sort_conditions))


@main.command()
@click.option('-a', '--accession', required=False, help='accession of the project')
def get_projects_by_accession(accession):
    """
    get projects by accession
    :return:
    """
    project = Project()
    print(project.get_by_accession(accession))


@main.command()
@click.option('-a', '--accession', required=False, help='accession of the project')
def get_reanalysis_projects_by_accession(accession):
    """
    get reanalysis projects by accession
    :return:
    """
    project = Project()
    print(project.get_reanalysis_projects_by_accession(accession))


@main.command()
@click.option('-a', '--accession', required=False, help='accession of the project')
def get_similar_projects_by_accession(accession):
    """
    get similar projects by accession
    :return:
    """
    project = Project()
    print(project.get_similar_projects_by_accession(accession))


@main.command()
@click.option('-a', '--accession', required=False, help='accession of the project')
@click.option('-f', '--filter', required=False, help='Parameters to filter the search results. The structure of the '
                                                     'filter is: field1==value1, field2==value2. Example '
                                                     'accession==PRD000001')
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sc', '--sort_conditions', required=False, default='projectAccession',
              help='Field(s) for sorting the results on. Default for this '
                   'request is project_accession. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def get_files_by_project_accession(accession, filter, page_size, page, sort_direction, sort_conditions):
    """
    get files by project accession
    :return:
    """
    project = Project()
    print(project.get_files_by_accession(accession, filter, page_size, page, sort_direction, sort_conditions))

# @main.command()
# @click.option('-usi', '--usi', required=False, help='usi, Provide multiple values separated by \n')
# @click.option('-pa', '--project_accession', required=False, help='projectAccession')
# @click.option('-aa', '--assay_accession', required=False, help='assayAccession')
# @click.option('-pepSeq', '--peptide_sequence', required=False, help='peptideSequence')
# @click.option('-modSeq', '--modified_sequence', required=False, help='peptideSequence')
# @click.option('-rt', '--result_type', required=False, default='COMPACT', help='peptideSequence')
# @click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
# @click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
# @click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
# @click.option('-sc', '--sort_conditions', required=False, default='projectAccession',
#               help='Field(s) for sorting the results on. Default for this '
#                    'request is project_accession. More fields can be separated by '
#                    'comma and passed. Example: submission_date,project_title')
# def search_spectra_evidences(usi, project_accession, assay_accession, peptide_sequence, modified_sequence,
#                              result_type, page_size, page, sort_direction, sort_conditions):
#     """
#     search public pride spectra with keywords and filters
#     :return:
#     """
#     spectra = Spectra()
#     print(spectra.spectra_evidences(usi, project_accession, assay_accession, peptide_sequence, modified_sequence,
#                                     result_type, page_size, page, sort_direction, sort_conditions))


@main.command()
@click.option('-f', '--filter', required=False, help='Parameters to filter the search results. The structure of the '
                                                     'filter is: field1==value1, field2==value2. Example '
                                                     'fileCategory.value==RAW')
@click.option('-ps', '--page_size', required=False, default=100, help='Number of results to fetch in a page')
@click.option('-p', '--page', required=False, default=0, help='Identifies which page of results to fetch')
@click.option('-sd', '--sort_direction', required=False, default='DESC', help='Sorting direction: ASC or DESC')
@click.option('-sc', '--sort_conditions', required=False, default='submissionDate',
              help='Field(s) for sorting the results on. Default for this '
                   'request is submissionDate. More fields can be separated by '
                   'comma and passed. Example: submission_date,project_title')
def get_files_by_filter(filter, page_size, page, sort_direction, sort_conditions):
    """
    get paged files
    :return:
    """
    files = Files()
    print(files.get_all_paged_files(filter, page_size, page, sort_direction, sort_conditions))


@main.command()
@click.option('-a', '--accession', required=True, help='accession of the project')
@click.option('-u', '--user', required=True, help='PRIDE login username')
@click.option('-p', '--password', required=True, help='PRiDE login password')
def get_private_files(accession, user, password):
    """
    get files by project accession
    :return:
    """
    project = Project()
    return project.get_private_files_by_accession(accession, user, password)

@main.command()
@click.option('-a', '--accession', required=True, help='accession of the project')
@click.option('-u', '--user', required=True, help='PRIDE login username')
@click.option('-p', '--password', required=True, help='PRiDE login password')
@click.option('-l', '--location', required=True, help='location to save files')
def download_private_files(accession, user, password, location):
    """
    get files by project accession
    :return:
    """
    project = Project()
    files_list = project.get_private_files_by_accession(accession, user, password)
    for f in files_list:
        url = f['_links']['download']['href']
        local_dir = os.path.join(location, accession)
        local_filename = os.path.join(local_dir, f['fileName'])
        os.mkdir(local_dir)
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    # If you have chunk encoded response uncomment if
                    # and set chunk_size parameter to None.
                    # if chunk:
                    f.write(chunk)


if __name__ == '__main__':
    main()
