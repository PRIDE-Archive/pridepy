import click
from files.raw import RawFiles


@click.command()
@click.option('-a', '--accession', required=True, default='PXD008644', help='PRIDE accession')
@click.option('-f', '--ftp_download_enabled', type=bool, default='True', help='If enabled, files will be downloaded from FTP, otherwise copy from file system')
@click.option('-i', '--input_folder', required=False, help='Input folder to copy the raw files')
@click.option('-o', '--output_folder', required=True, help='output folder to download or copy raw files')
def main(accession, ftp_download_enabled, input_folder, output_folder):

    raw_files = RawFiles()

    print("accession: " + accession)

    if ftp_download_enabled:
        print("Data will be download from ftp")
        raw_files.download_raw_files_from_ftp(accession, output_folder)
    else:
        print("Data will be copied from file system " + output_folder)


if __name__ == '__main__':
    main()