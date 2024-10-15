#!/usr/bin/env python3
import asyncio
import logging
import click
from pridepy.files.files import Files
from pridepy.project.project import Project


@click.group()
def main():
    pass


@main.command(
    "download-all-public-raw-files",
    help="Download all public raw files from a given PRIDE public project",
)
@click.option("-a", "--accession", required=True, help="PRIDE project accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    help="Protocol to be used to download files either by ftp or aspera or from globus. Default is ftp",
)
@click.option(
    "-o",
    "--output_folder",
    required=True,
    help="output folder to download or copy raw files",
)
@click.option(
    "-skip",
    "--skip_if_downloaded_already",
    required=False,
    default=True,
    help="Boolean value to skip the download if the file has already been downloaded.",
)
@click.option(
    "--aspera_maximum_bandwidth",
    required=False,
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M",
    default="100M",
)
@click.option(
    "--checksum_check",
    required=False,
    help="Download checksum file for project",
    is_flag=True,
    default=False,
)
def download_all_public_raw_files(
    accession,
    protocol,
    output_folder,
    skip_if_downloaded_already,
    aspera_maximum_bandwidth: str = "50M",
    checksum_check: bool = False,
):
    """
    This script download raw files from FTP or copy from the file system
    """

    raw_files = Files()
    logging.info("accession: " + accession)
    logging.info(f"Data will be downloaded from {protocol}")

    if protocol == "aspera":
        logging.info(f"Aspera maximum bandwidth: {aspera_maximum_bandwidth}")

    raw_files.download_all_raw_files(
        accession,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        checksum_check=checksum_check,
    )


@main.command(
    "download-file-by-name",
    help="Download a single file from a given PRIDE project (public or private)",
)
@click.option("-a", "--accession", required=True, help="PRIDE project accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    help="Protocol to be used to download files either by ftp or aspera or from globus. Default is ftp",
)
@click.option("-f", "--file_name", required=True, help="fileName to be downloaded")
@click.option(
    "-o",
    "--output_folder",
    required=True,
    help="output folder to download or copy files",
)
@click.option(
    "-skip",
    "--skip_if_downloaded_already",
    required=False,
    default=True,
    help="Boolean value to skip the download if the file has already been downloaded.",
)
@click.option(
    "--username", required=False, help="PRIDE login username for private files"
)
@click.option(
    "--password", required=False, help="PRIDE login password for private files"
)
@click.option(
    "--aspera_maximum_bandwidth",
    required=False,
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M",
    default="100M",
)
@click.option(
    "--checksum_check",
    required=False,
    help="Download checksum file for project",
    is_flag=True,
    default=False,
)
def download_file_by_name(
    accession,
    protocol,
    file_name,
    output_folder,
    skip_if_downloaded_already: bool,
    username: str = None,
    password: str = None,
    aspera_maximum_bandwidth: str = "50M",
    checksum_check: bool = False,
):
    """
    This script download single file from servers or copy from the file system
    :param accession: PRIDE project accession
    :param protocol: Protocol to be used to download files either by ftp or aspera or from globus. Default is ftp
    :param file_name: fileName to be downloaded
    :param output_folder: output folder to download or copy files
    :param skip_if_downloaded_already: Boolean value to skip the download if the file has already been downloaded.
    :param username: PRIDE login username for private files
    :param password: PRIDE login password for private files
    :param aspera_maximum_bandwidth: Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M
    :param checksum_check: Download checksum file for project.
    """

    file_handler = Files()

    logging.info("accession: " + accession)
    logging.info(f"Data will be downloaded from {protocol}")
    if protocol == "aspera":
        logging.info(f"Aspera maximum bandwidth: {aspera_maximum_bandwidth}")

    file_handler.download_file_by_name(
        accession=accession,
        file_name=file_name,
        output_folder=output_folder,
        skip_if_downloaded_already=skip_if_downloaded_already,
        protocol=protocol,
        username=username,
        password=password,
        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        checksum_check=checksum_check,
    )


@main.command("get-private-files", help="Get private files by project accession")
@click.option("-a", "--accession", required=True, help="accession of the project")
@click.option("-u", "--user", required=True, help="PRIDE login username")
@click.option("-p", "--password", required=True, help="PRiDE login password")
def get_private_files(accession, user, password):
    """
    get files by project accession
    :return:
    """
    project = Project()
    list_files = project.get_private_files_by_accession(accession, user, password)
    if list_files:
        logging.info("File Name\tFile Size\tCategory")
        for f in list_files:
            # Get file size in MB from bytes
            file_size = f["fileSizeBytes"] / (1024 * 1024)
            file_category = f["fileCategory"]["value"]
            logging.info(
                f["fileName"] + "\t" + str(file_size) + " MB\t" + file_category
            )


@main.command()
@click.option(
    "-k",
    "--keyword",
    required=False,
    help="The entered word will be searched among the fields to fetch "
    "matching pride. The structure of the keyword is : *:*",
)
@click.option(
    "-f",
    "--filter",
    required=False,
    help="Parameters to filter the search results. The structure of the "
    "filter is: field1==value1, field2==value2. Example "
    "accession==PRD000001",
)
@click.option(
    "-ps",
    "--page_size",
    required=False,
    default=100,
    help="Number of results to fetch in a page",
)
@click.option(
    "-p",
    "--page",
    required=False,
    default=0,
    help="Identifies which page of results to fetch",
)
@click.option(
    "-dg",
    "--date_gap",
    required=False,
    help="A date range field with possible values of +1MONTH, +1YEAR",
)
@click.option(
    "-sd",
    "--sort_direction",
    required=False,
    default="DESC",
    help="Sorting direction: ASC or DESC",
)
@click.option(
    "-sf",
    "--sort_fields",
    required=False,
    default="submission_date",
    help="Field(s) for sorting the results on. Default for this "
    "request is submission_date. More fields can be separated by "
    "comma and passed. Example: submission_date,project_title",
)
def search_projects_by_keywords_and_filters(
    keyword, filter, page_size, page, date_gap, sort_direction, sort_fields
):
    """
    search public pride with keywords and filters
    :return:
    """
    project = Project()
    logging.info(
        project.search_by_keywords_and_filters(
            keyword, filter, page_size, page, date_gap, sort_direction, sort_fields
        )
    )


@main.command()
@click.option(
    "-o",
    "--output_file",
    required=True,
    help="output file to save all the projects metadata",
)
def stream_projects_metadata(output_file):
    """
    Stream all projects metadata in JSON format to a file
    :return:
    """
    project = Project()
    asyncio.run(project.stream_all_projects(output_file))


@main.command()
@click.option(
    "-o",
    "--output_file",
    required=True,
    help="output file to save all the files metadata",
)
@click.option(
    "-a",
    "--accession",
    required=False,
    help="project accession",
)
def stream_files_metadata(accession, output_file):
    """
    Stream all files metadata in JSON format and write it to a file
    :return:
    """
    files = Files()
    asyncio.run(files.stream_all_files_metadata(output_file, accession))

@main.command()
@click.option(
    "-ps",
    "--page_size",
    required=False,
    default=100,
    help="Number of results to fetch in a page",
)
@click.option(
    "-p",
    "--page",
    required=False,
    default=0,
    help="Identifies which page of results to fetch",
)
@click.option(
    "-sd",
    "--sort_direction",
    required=False,
    default="DESC",
    help="Sorting direction: ASC or DESC",
)
@click.option(
    "-sc",
    "--sort_conditions",
    required=False,
    default="projectAccession",
    help="Field(s) for sorting the results on. Default for this "
    "request is project_accession. More fields can be separated by "
    "comma and passed. Example: submission_date,project_title",
)
def get_projects(page_size, page, sort_direction, sort_conditions):
    """
    get paged projects
    :return:
    """
    project = Project()
    logging.info(project.get_projects(page_size, page, sort_direction, sort_conditions))


@main.command()
@click.option("-a", "--accession", required=False, help="accession of the project")
def get_projects_by_accession(accession):
    """
    get projects by accession
    :return:
    """
    project = Project()
    logging.info(project.get_by_accession(accession))


@main.command()
@click.option("-a", "--accession", required=False, help="accession of the project")
def get_reanalysis_projects_by_accession(accession):
    """
    get reanalysis projects by accession
    :return:
    """
    project = Project()
    logging.info(project.get_reanalysis_projects_by_accession(accession))


@main.command()
@click.option("-a", "--accession", required=False, help="accession of the project")
def get_similar_projects_by_accession(accession):
    """
    get similar projects by accession
    :return:
    """
    project = Project()
    logging.info(project.get_similar_projects_by_accession(accession))


@main.command()
@click.option("-a", "--accession", required=False, help="accession of the project")
@click.option(
    "-f",
    "--filter",
    required=False,
    help="Parameters to filter the search results. The structure of the "
    "filter is: field1==value1, field2==value2. Example "
    "accession==PRD000001",
)
@click.option(
    "-ps",
    "--page_size",
    required=False,
    default=100,
    help="Number of results to fetch in a page",
)
@click.option(
    "-p",
    "--page",
    required=False,
    default=0,
    help="Identifies which page of results to fetch",
)
@click.option(
    "-sd",
    "--sort_direction",
    required=False,
    default="DESC",
    help="Sorting direction: ASC or DESC",
)
@click.option(
    "-sc",
    "--sort_conditions",
    required=False,
    default="projectAccession",
    help="Field(s) for sorting the results on. Default for this "
    "request is project_accession. More fields can be separated by "
    "comma and passed. Example: submission_date,project_title",
)
def get_files_by_project_accession(
    accession, filter, page_size, page, sort_direction, sort_conditions
):
    """
    get files by project accession
    :return:
    """
    project = Project()
    logging.info(
        project.get_files_by_accession(
            accession, filter, page_size, page, sort_direction, sort_conditions
        )
    )


@main.command()
@click.option(
    "-f",
    "--filter",
    required=False,
    help="Parameters to filter the search results. The structure of the "
    "filter is: field1==value1, field2==value2. Example "
    "fileCategory.value==RAW",
)
@click.option(
    "-ps",
    "--page_size",
    required=False,
    default=100,
    help="Number of results to fetch in a page",
)
@click.option(
    "-p",
    "--page",
    required=False,
    default=0,
    help="Identifies which page of results to fetch",
)
@click.option(
    "-sd",
    "--sort_direction",
    required=False,
    default="DESC",
    help="Sorting direction: ASC or DESC",
)
@click.option(
    "-sc",
    "--sort_conditions",
    required=False,
    default="submissionDate",
    help="Field(s) for sorting the results on. Default for this "
    "request is submissionDate. More fields can be separated by "
    "comma and passed. Example: submission_date,project_title",
)
def get_files_by_filter(filter, page_size, page, sort_direction, sort_conditions):
    """
    get paged files
    :return:
    """
    files = Files()
    logging.info(
        files.get_all_paged_files(
            filter, page_size, page, sort_direction, sort_conditions
        )
    )


if __name__ == "__main__":
    main()
