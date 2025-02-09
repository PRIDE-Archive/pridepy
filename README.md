# pridepy: A Python package to download and search data from PRIDE database

[![Python package](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml/badge.svg)](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/pridepy.svg)](https://badge.fury.io/py/pridepy)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pridepy)

Python Client library for PRIDE Rest API

# Installation

## From PyPI

To install, simply use `pip`:

```bash
$ pip install --upgrade pridepy
```

## From Source

First, clone the repository on your local machine and then install the package using `pip`:

```bash
$ git clone https://github.com/PRIDE-Archive/pridepy
$ cd pridepy
$ poetry build
$ pip install dist/*.whl
```

Install with setup.py: 

```bash
$ git clone https://github.com/PRIDE-Archive/pridepy
$ cd pridepy
$ poetry build
$ pip install dist/pridepy-{version}.tar.gz
```
# Usage and Documentation

This Python CLI tool, built using the Click module, 
already provides detailed usage instructions for each command. To avoid redundancy and potential clutter in this README, you can access the usage instructions directly from the CLI
Use the below command to view a list of commands available:

```bash
$ pridepy --help
Usage: pridepy [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  download-all-public-raw-files   Download all public raw files...
  download-file-by-name           Download a single file from a...
  get-files-by-filter             get paged files :return:
  get-files-by-project-accession  get files by project accession...
  get-private-files               Get private files by project...
  get-projects                    get paged projects :return:
  get-projects-by-accession       get projects by accession... 
  stream-files-metadata           Stream all files metadata in...
  stream-projects-metadata        Stream all projects metadata...
  search-projects-by-keywords-and-filters Search all projects by keywords...
    
```
> [!NOTE]
> Please make sure you are using Python3, not Python 2.7 version.

## Downloading a project from PRIDE Archive

The main purpose of this tool is to download data from the PRIDE Archive. Here, how to download all the raw files from a dataset(eg: PXD012353).

```bash
$ pridepy download-all-public-raw-files -a PXD012353 -o /Users/yourname/Downloads/foldername/ -p aspera
```
- `-a` flag is used to specify the project accession number.
- `-o` flag is used to specify the output directory. 
- `-p` flag is used to specify the protocol (**aspera, ftp, globus**)

> [!IMPORTANT]
> Currently, pridepy supports multiple protocols for downloading including ftp, aspera, globus, s3. ftp, aspera uses those protocols to download the files; the pridepy includes the aspera client. For globus and s3, the tool uses https of both services endpoints. Read the whitepaper to know more about the performance of each protocol.

Additional options: 

- `-skip` flag is used to skip the download of files that already exist in the output directory.
- `--aspera_maximum_bandwidth` flag is used to specify the maximum bandwidth for the Aspera download. The default value is 100M.
- `--checksum_check` flag is used to check the checksum of the downloaded files. The default value is False.

## Download single file by name

Users instead of downloading an entire project files may be interested in downloading a single file if they know it by name. Here is how to download a single file by name.

```bash
$ pridepy download-file-by-name -a PXD022105 -o /Users/yourname/Downloads/foldername/ -f checksum.txt -p globus
```

Please be aware that the additional parameters are the same as the previous command [Downloading a project from PRIDE Archive](#downloading-a-project-from-pride-archive).

## Download project files by category

Users may be interested in downloading files by category. Here is how to download files by category. The different categories are available in the PRIDE Archive: 

- RAW: Raw data files  
- PEAK: Peak list files 
- SEARCH: Search engine output files 
- OTHER: Other files
- RESULT: Result files
- SPECTRUM LIBRARIES: Spectrum libraries
- FASTA: FASTA files

```bash
$ pridepy download-files-by-category -a PXD022105 -o /Users/yourname/Downloads/foldername/ -c RAW -p ftp
```

Please be aware that the additional parameters are the same as the previous command [Downloading a project from PRIDE Archive](#downloading-a-project-from-pride-archive).

>[!IMPORTANT]
> We also implemented a direct command to download RAW files from a project which is the most common use case.

## Download private files

Users and especially reviewers may be interested in downloading private files. Here is how to download private files. 

First, the user can list the private files of a project:

```bash
$ pridepy list-private-files -a PXD022105 -u yourusername -p yourpassword
```

This command will list the private files of the project PXD022105. Including the file name, file size, and download link.

Then the user can download the private files:

```bash
$ pridepy download-file-by-name -a PXD022105 -o /Users/yourname/Downloads/foldername/ --username yourusername --password yourpassword -f checksum.txt 
```

>[!WARNING]
> To download preivate files, the user should use the same command as downloading a single file by name. The only difference is that the user should provide the username and password. However, protocol in this case is unnecessary as the tool will use the https protocol to download the files. At the moment we only allow this protocol because of the infrastructure of PRIDE private files (read the whitepaper for more information).

## Streaming metadata

One of the great features of PRIDE and pridepy is the ability to stream metadata of all projects and files. This is useful for users who want to analyze the metadata of all projects and files locally.

Stream metadata of all projects as JSON and write it to a file: 

```bash
$ pridepy stream-projects-metadata -o all_pride_projects.json
```

Stream all files metadata in a specific project as JSON and write it to a file: 

```bash
$ pridepy stream-files-metadata -o all_pride_files_metadata.json
```
Stream the files metadata of a specific project as JSON and write it to a file: 

```bash
$ pridepy stream-files-metadata -o PXD005011_files.json -a PXD005011
```

## Search projects by keywords and filters

Get the Project metadata by keywords and filters

```bash
$  python -m pridepy.pridepy search-projects-by-keywords-and-filters -f projectTags==Proteometools,organismsPart==Pancreas -k human -sd DESC -sf accession -sf submissionDate
```

# White paper

A white paper is available at [here](paper/paper.md). We can build it as PDF using pandoc.

```bash
$docker run --rm --platform linux/amd64 -v /Users/yperez/work/pridepy/paper/:/data -w /data openjournals/inara:latest paper.md -p -o pdf
```

# Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

# Citation

Selvakumar Kamatchinathan, Suresh Hewapathirana, Chakradhar Bandla, Juan Antonio Vizcaíno, Yasset Perez-Riverol. (2021, January 28). pridepy: A Python package to download and search data from PRIDE database (Version v0.0.3). 

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4475414.svg)](https://doi.org/10.5281/zenodo.4475414)
