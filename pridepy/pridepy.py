#!/usr/bin/env python3
import asyncio
import logging
import click
from pridepy.download.client import Client as Files
from pridepy.pdc import download_pdc_files as run_pdc_download
from pridepy.project.project import Project

PROTOCOL_CHOICES = click.Choice(["ftp", "aspera", "globus", "s3"], case_sensitive=False)


@click.group()
@click.version_option(package_name="pridepy")
def main():
    pass


@main.command(
    "download-all-public-raw-files",
    help="Download all public raw files from a PRIDE or MassIVE public dataset",
)
@click.option("-a", "--accession", required=True, help="PRIDE or MassIVE accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    type=PROTOCOL_CHOICES,
    help="Protocol to use for download: ftp, aspera, globus, s3. Default is ftp with fallback enabled.",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download or copy raw files",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip the download if the file has already been downloaded.",
)
@click.option(
    "--aspera-maximum-bandwidth",
    required=False,
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M",
    default="100M",
)
@click.option(
    "--checksum-check",
    required=False,
    help="Download checksum file for project and validate downloads",
    is_flag=True,
    default=False,
)
@click.option(
    "-t",
    "--threads",
    "download_threads",
    default=1,
    type=click.IntRange(1, 32),
    help="Number of threads for each file download. Default is 1.",
)
@click.option(
    "--preserve-structure",
    is_flag=True,
    default=False,
    help="Recreate the dataset's subdirectory layout under the output folder. "
    "By default files are downloaded flat into the output folder.",
)
def download_all_public_raw_files(
    accession,
    protocol,
    output_folder,
    skip_if_downloaded_already,
    aspera_maximum_bandwidth: str = "50M",
    checksum_check: bool = False,
    download_threads: int = 1,
    preserve_structure: bool = False,
):
    """
    Command to download all public raw files from a specified PRIDE or MassIVE dataset.

    Parameters:
        accession (str): PRIDE or MassIVE accession.
        protocol (str): Protocol for downloading files (ftp, aspera, globus, s3). Default is ftp.
        output_folder (str): Directory to save downloaded raw files.
        skip_if_downloaded_already (bool): Skip download if files already exist. Default is False.
        aspera_maximum_bandwidth (str): Maximum bandwidth for Aspera protocol. Default is 100M.
        checksum_check (bool): Flag to download checksum file for the project. Default is False.
        download_threads (int): Number of threads for each file download. Default is 1.
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
        download_threads=download_threads,
        flatten=not preserve_structure,
    )


@main.command(
    "download-all-public-category-files",
    help="Download all public files of specific category from a PRIDE or MassIVE public dataset",
)
@click.option("-a", "--accession", required=True, help="PRIDE or MassIVE accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    type=PROTOCOL_CHOICES,
    help="Protocol to use for download: ftp, aspera, globus, s3. Default is ftp with fallback enabled.",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download or copy raw files",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip the download if the file has already been downloaded.",
)
@click.option(
    "--aspera-maximum-bandwidth",
    required=False,
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M",
    default="100M",
)
@click.option(
    "--checksum-check",
    required=False,
    help="Download checksum file for project and validate downloads",
    is_flag=True,
    default=False,
)
@click.option(
    "-c",
    "--category",
    required=True,
    help="Comma-separated categories of files to download (e.g. RAW or RAW,SEARCH). "
    "Valid values: RAW, PEAK, SEARCH, RESULT, SPECTRUM_LIBRARY, OTHER, FASTA",
)
@click.option(
    "-t",
    "--threads",
    "download_threads",
    default=1,
    type=click.IntRange(1, 32),
    help="Number of threads for each file download. Default is 1.",
)
@click.option(
    "--preserve-structure",
    is_flag=True,
    default=False,
    help="Recreate the dataset's subdirectory layout under the output folder. "
    "By default files are downloaded flat into the output folder.",
)
def download_all_public_category_files(
    accession: str,
    protocol: str,
    output_folder: str,
    skip_if_downloaded_already: bool,
    aspera_maximum_bandwidth: str = "50M",
    checksum_check: bool = False,
    category: str = "RAW",
    download_threads: int = 1,
    preserve_structure: bool = False,
):
    """
    Command to download all public files of a specified category from a given PRIDE or MassIVE dataset.

    Parameters:
        accession (str): The PRIDE or MassIVE dataset accession identifier.
        protocol (str): The protocol to use for downloading files (ftp, aspera, globus, s3).
        output_folder (str): The directory where the files will be downloaded.
        skip_if_downloaded_already (bool): If True, skips downloading files that already exist. Default is False.
        aspera_maximum_bandwidth (str): Maximum bandwidth for Aspera transfers.
        checksum_check (bool): If True, downloads the checksum file for the project.
        category (str): Comma-separated categories of files to download (e.g. RAW or RAW,SEARCH).
        download_threads (int): Number of threads for each file download. Default is 1.
    """

    valid_categories = {"RAW", "PEAK", "SEARCH", "RESULT", "SPECTRUM_LIBRARY", "OTHER", "FASTA"}
    categories = [c.strip().upper() for c in category.split(",")]
    invalid = set(categories) - valid_categories
    if invalid:
        raise click.BadParameter(
            f"Invalid category: {', '.join(invalid)}. "
            f"Valid values: {', '.join(sorted(valid_categories))}"
        )

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
        categories=categories,
        download_threads=download_threads,
        flatten=not preserve_structure,
    )


@main.command(
    "download-file-by-name",
    help="Download a single file from a PRIDE dataset or a public MassIVE dataset",
)
@click.option("-a", "--accession", required=True, help="PRIDE or MassIVE accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    type=PROTOCOL_CHOICES,
    help="Protocol to use for download: ftp, aspera, globus, s3. Default is ftp with fallback enabled.",
)
@click.option("-f", "--file-name", required=True, help="fileName to be downloaded")
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download or copy files",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip the download if the file has already been downloaded.",
)
@click.option("--username", required=False, help="PRIDE login username for private files")
@click.option("--password", required=False, help="PRIDE login password for private files")
@click.option(
    "--aspera-maximum-bandwidth",
    required=False,
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M), depending on the user's network bandwidth, default is 100M",
    default="100M",
)
@click.option(
    "--checksum-check",
    required=False,
    help="Download checksum file for project and validate downloads",
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
    :param accession: PRIDE or MassIVE accession
    :param protocol: Protocol to use for download: ftp, aspera, globus, s3. Default is ftp.
    :param file_name: fileName to be downloaded
    :param output_folder: output folder to download or copy files
    :param skip_if_downloaded_already: Boolean value to skip the download if the
        file has already been downloaded. Default is False.
    :param username: PRIDE login username for private files
    :param password: PRIDE login password for private files
    :param aspera_maximum_bandwidth: Aspera maximum bandwidth (e.g 50M, 100M,
        200M), depending on the user's network bandwidth, default is 100M
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


@main.command(
    "download-px-raw-files",
    help="Download all raw files referenced by a ProteomeXchange dataset (PX URL or accession)",
)
@click.option(
    "-a",
    "--accession",
    "--px",
    "accession",
    required=True,
    help="ProteomeXchange accession (e.g. PXD039236). --px is deprecated.",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download files",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip the download if the file has already been downloaded.",
)
@click.option(
    "--preserve-structure",
    is_flag=True,
    default=False,
    help="Recreate the dataset's subdirectory layout under the output folder. "
    "By default files are downloaded flat into the output folder.",
)
def download_px_raw_files(
    accession: str,
    output_folder: str,
    skip_if_downloaded_already: bool,
    preserve_structure: bool = False,
):
    """CLI wrapper to download raw files via ProteomeXchange XML."""
    files = Files()
    logging.info(f"PX accession/URL: {accession}")
    files.download_px_raw_files(
        accession,
        output_folder,
        skip_if_downloaded_already,
        flatten=not preserve_structure,
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
    "--output-file",
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
    "--output-file",
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
    "--filters",
    required=False,
    help="Parameters to filter the search results. The structure of the "
    "filter is: field1==value1, field2==value2. Example "
    "accession==PRD000001",
)
@click.option(
    "-ps",
    "--page-size",
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
    "--sort-direction",
    required=False,
    default="DESC",
    help="Sorting direction: ASC or DESC",
)
@click.option(
    "-sf",
    "--sort-fields",
    required=False,
    default=["submissionDate"],
    multiple=True,
    help="Field(s) for sorting the results on. Default for this "
    "request is submissionDate. More fields can be separated by "
    "comma and passed. Example: submissionDate,accession",
    type=click.Choice(
        "accession,submissionDate,diseases,organismsPart,organisms,instruments,softwares,"
        "avgDownloadsPerFile,downloadCount,publicationDate".split(",")
    ),
)
def search_projects_by_keywords_and_filters(
    keyword, filters, page_size, page, sort_direction, sort_fields
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
            keyword, filters, page_size, page, sort_direction, sf
        )
    )


def _parse_text_manifest(path, *, take_first_column=False):
    """Read a text manifest, skipping blank lines and ``#``-prefixed comments.

    When ``take_first_column`` is True, each line is split on tabs and only
    the first cell is kept (used by the filename-list manifest).
    """
    if not path:
        return []
    items = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if take_first_column:
                line = line.split("\t")[0].strip()
            items.append(line)
    return items


def _read_filename_arguments(file_list_path, files_csv):
    """Build a deduplicated filename list from a manifest path and/or CSV string.

    The manifest takes one filename per line (additional tab-separated columns
    are ignored); blank lines and ``#``-prefixed comments are skipped.
    """
    if not file_list_path and not files_csv:
        raise click.BadParameter("Provide either --file-list or --files")
    names = list(_parse_text_manifest(file_list_path, take_first_column=True))
    if files_csv:
        names.extend(part.strip() for part in files_csv.split(",") if part.strip())
    deduped = list(dict.fromkeys(names))
    if not deduped:
        raise click.BadParameter("No filenames found in the provided inputs")
    return deduped


def _read_url_arguments(url_list_path, urls_csv=None):
    """Build a deduplicated URL list from a manifest path and/or a CSV string.

    Manifest format: one URL per line; blank lines and ``#``-prefixed comments
    are skipped. ``urls_csv`` is split on ``,``; URLs containing literal
    commas should be provided via a manifest file instead.
    """
    if not url_list_path and not urls_csv:
        raise click.BadParameter("Provide --url-list or --urls")
    urls = list(_parse_text_manifest(url_list_path))
    if urls_csv:
        urls.extend(part.strip() for part in urls_csv.split(",") if part.strip())
    deduped = list(dict.fromkeys(urls))
    if not deduped:
        raise click.BadParameter("No URLs found in the provided inputs")
    return deduped


@main.command(
    "download-files-by-list",
    help="Download a subset of files from a PRIDE project, given a filename list",
)
@click.option("-a", "--accession", required=True, help="PRIDE project accession")
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    type=PROTOCOL_CHOICES,
    help="Protocol to use for download: ftp, aspera, globus, s3. Default is ftp with fallback enabled.",
)
@click.option(
    "-F",
    "--file-list",
    "file_list_path",
    required=False,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a manifest file with one filename per line.",
)
@click.option(
    "-f",
    "--files",
    "files_csv",
    required=False,
    help="Comma-separated filenames. Use this OR --file-list (or both).",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download files",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip the download if the file has already been downloaded.",
)
@click.option(
    "--aspera-maximum-bandwidth",
    required=False,
    default="100M",
    help="Aspera maximum bandwidth (e.g 50M, 100M, 200M).",
)
@click.option(
    "--checksum-check",
    is_flag=True,
    default=False,
    help="Download project checksums and validate downloaded files.",
)
@click.option(
    "-t",
    "--threads",
    "download_threads",
    default=1,
    type=click.IntRange(1, 32),
    help="Number of threads for each file download. Default is 1.",
)
@click.option(
    "--preserve-structure",
    is_flag=True,
    default=False,
    help="Recreate the dataset's subdirectory layout under the output folder. "
    "By default files are downloaded flat into the output folder.",
)
def download_files_by_list(
    accession,
    protocol,
    file_list_path,
    files_csv,
    output_folder,
    skip_if_downloaded_already,
    aspera_maximum_bandwidth,
    checksum_check,
    download_threads,
    preserve_structure: bool = False,
):
    """Download a named subset of files from a PRIDE project."""
    file_names = _read_filename_arguments(file_list_path, files_csv)
    files_obj = Files()
    logging.info("accession: %s", accession)
    logging.info("Downloading %d file(s) via %s", len(file_names), protocol)
    files_obj.download_files_by_list(
        accession=accession,
        file_names=file_names,
        output_folder=output_folder,
        skip_if_downloaded_already=skip_if_downloaded_already,
        protocol=protocol,
        aspera_maximum_bandwidth=aspera_maximum_bandwidth,
        checksum_check=checksum_check,
        download_threads=download_threads,
        flatten=not preserve_structure,
    )


@main.command(
    "download-files-by-url",
    help="Download files from a list of raw URLs (http/https/ftp)",
)
@click.option(
    "-F",
    "--url-list",
    "url_list_path",
    required=False,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a manifest file with one URL per line.",
)
@click.option(
    "-u",
    "--urls",
    "urls_csv",
    required=False,
    help="One or more comma-separated URLs. Use this OR --url-list (or both).",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="output folder to download files into",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip URLs whose target file already exists locally.",
)
@click.option(
    "-p",
    "--protocol",
    default="ftp",
    type=click.Choice(["ftp", "globus"], case_sensitive=False),
    help="Download strategy. ftp (default): single-connection per URL scheme. "
         "globus: resume-capable http/https downloads (single-connection stream).",
)
@click.option(
    "--checksum-check",
    is_flag=True,
    default=False,
    help="Validate downloaded files against PRIDE checksums. "
         "Accessions are inferred from PRIDE URL paths (only PRIDE URLs supported).",
)
@click.option(
    "-t",
    "--threads",
    "download_threads",
    default=1,
    type=click.IntRange(1, 32),
    help="Number of threads for each file download. Default is 1.",
)
def download_files_by_url(
    url_list_path,
    urls_csv,
    output_folder,
    skip_if_downloaded_already,
    protocol,
    checksum_check,
    download_threads,
):
    """Download files from raw URLs (http/https/ftp), dispatched by scheme."""
    urls = _read_url_arguments(url_list_path, urls_csv)
    logging.info("Downloading %d URL(s) [protocol=%s]", len(urls), protocol)
    Files.download_files_by_url(
        urls=urls,
        output_folder=output_folder,
        skip_if_downloaded_already=skip_if_downloaded_already,
        protocol=protocol,
        download_threads=download_threads,
        checksum_check=checksum_check,
    )


@main.command(
    "download-pdc-files",
    help="Download files from PDC/CPTAC studies via PDC signed HTTPS URLs",
)
@click.option(
    "-a",
    "--accession",
    required=True,
    help="PDC study ID, comma-separated PDC study IDs, or a CSV with pdc_id/pdc_study_id and optional file-type/filetype.",
)
@click.option(
    "--file-type",
    required=False,
    type=click.Choice(["mzid", "psm", "raw", "mzml"], case_sensitive=False),
    help="PDC file type to download: mzid, psm, raw, or mzml. Omit to download all file types. Overrides CSV file-type/filetype values.",
)
@click.option(
    "-o",
    "--output-folder",
    required=True,
    help="Output folder. Files are written as <output>/<PDC study ID>/<file name>.",
)
@click.option(
    "--skip-if-downloaded-already",
    is_flag=True,
    default=False,
    help="Skip files that already exist locally and match PDC size/checksum metadata.",
)
@click.option(
    "--checksum-check/--no-checksum-check",
    "checksum_check",
    default=True,
    help="Validate downloads against PDC md5sum values. Enabled by default.",
)
@click.option(
    "-t",
    "--threads",
    "download_threads",
    default=1,
    type=click.IntRange(1, 32),
    help="Number of parallel HTTP Range threads per file (1-32). Default is 1.",
)
@click.option(
    "--retry",
    is_flag=True,
    default=False,
    help="Retry failed files; HTTP 403 retries refresh the PDC signed URL first.",
)
def download_pdc_files(
    accession,
    file_type,
    output_folder,
    skip_if_downloaded_already,
    checksum_check,
    download_threads,
    retry,
):
    """Download PDC/CPTAC files with PDC GraphQL metadata and signed HTTPS URLs."""
    try:
        stats = run_pdc_download(
            accession=accession,
            file_type=file_type,
            output_folder=output_folder,
            skip_if_downloaded_already=skip_if_downloaded_already,
            checksum_check=checksum_check,
            download_threads=download_threads,
            retry=retry,
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    logging.info(
        "PDC download completed: studies=%d total=%d downloaded=%d skipped=%d failed=%d",
        stats.studies,
        stats.total_files,
        stats.downloaded,
        stats.skipped,
        stats.failed,
    )


if __name__ == "__main__":
    main()
