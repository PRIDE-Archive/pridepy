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
    Command to download all public raw files from a specified PRIDE project.

    Parameters:
        accession (str): PRIDE project accession.
        protocol (str): Protocol for downloading files (ftp, aspera, globus). Default is ftp.
        output_folder (str): Directory to save downloaded raw files.
        skip_if_downloaded_already (bool): Skip download if files already exist. Default is True.
        aspera_maximum_bandwidth (str): Maximum bandwidth for Aspera protocol. Default is 100M.
        checksum_check (bool): Flag to download checksum file for the project. Default is False.
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
    "download-all-public-category-files",
    help="Download all public files of specific category from a given PRIDE public project",
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
@click.option(
    "-c",
    "--category",
    required=True,
    help="Category of the files to be downloaded",
    type=click.Choice("RAW,PEAK,SEARCH,RESULT,SPECTRUM_LIBRARY,OTHER,FASTA".split(",")),
)
def download_all_public_category_files(
    accession: str,
    protocol: str,
    output_folder: str,
    skip_if_downloaded_already: bool,
    aspera_maximum_bandwidth: str = "50M",
    checksum_check: bool = False,
    category: str = "RAW",
):
    """
    Command to download all public files of a specified category from a given PRIDE public project.

    Parameters:
        accession (str): The PRIDE project accession identifier.
        protocol (str): The protocol to use for downloading files (ftp, aspera, globus).
        output_folder (str): The directory where the files will be downloaded.
        skip_if_downloaded_already (bool): If True, skips downloading files that already exist.
        aspera_maximum_bandwidth (str): Maximum bandwidth for Aspera transfers.
        checksum_check (bool): If True, downloads the checksum file for the project.
        category (str): The category of files to download.
    """

    raw_files = Files()
    logging.info("accession: " + accession)
    logging.info(f"Data will be downloaded from {protocol}")

    if protocol == "aspera":
        logging.info(f"Aspera maximum bandwidth: {aspera_maximum_bandwidth}")

    raw_files.download_all_category_files(
        accession,
        output_folder,
        skip_if_downloaded_already,
        protocol,
        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        checksum_check=checksum_check,
        category=category,
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
@click.option("--username", required=False, help="PRIDE login username for private files")
@click.option("--password", required=False, help="PRIDE login password for private files")
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


@main.command("list-private-files", help="List private files by project accession")
@click.option("-a", "--accession", required=True, help="accession of the project")
@click.option("-u", "--user", required=True, help="PRIDE login username")
@click.option("-p", "--password", required=True, help="PRIDE login password")
def list_private_files(accession, user, password):
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
            logging.info(f["fileName"] + "\t" + str(file_size) + " MB\t" + file_category)


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
    "-k",
    "--keyword",
    required=True,
    help="The entered word will be searched among the fields to fetch " "matching pride.",
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
    type=click.IntRange(min=1, max=1000),
    help="Number of results to fetch in a page",
)
@click.option(
    "-p",
    "--page",
    required=False,
    default=0,
    type=click.IntRange(min=0),
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
    "-sf",
    "--sort_fields",
    required=False,
    default=["submission_date"],
    multiple=True,
    help="Field(s) for sorting the results on. Default for this "
    "request is submission_date. More fields can be separated by "
    "comma and passed. Example: submissionDate,accession",
    type=click.Choice(
        "accession,submissionDate,diseases,organismsPart,organisms,instruments,softwares,"
        "avgDownloadsPerFile,downloadCount,publicationDate".split(",")
    ),
)
def search_projects_by_keywords_and_filters(
    keyword, filter, page_size, page, sort_direction, sort_fields
):
    """
    Search all projects by keywords and filters
    Parameters:
        keyword (str): keyword to search in entire project.
        filter (str): filter the search results. field1==value1
        page_size (int): no of records or projects per page
        page (int): Page number
        sort_direction (str): sort direction of the results based on sortfield
        sort_fields (str): field to sort the results by.
    """
    project = Project()
    sf = ", ".join(sort_fields)
    logging.info(
        project.search_by_keywords_and_filters(
            keyword, filter, page_size, page, sort_direction, sf
        )
    )


if __name__ == "__main__":
    main()
