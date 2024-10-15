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
$ pip install .
```

Install with setup.py: 

```bash
$ git clone https://github.com/PRIDE-Archive/pridepy
$ cd pridepy
$ python setup.py sdist bdist_wheel 
$ pip install dist/pridepy-{version}.tar.gz
```

# Examples

Download all the raw files from a dataset(eg: PXD012353).
Warning: Raw files are generally large in size, so it may take some time to download depending on the number of files and file sizes.

`-p`: in download specifies protocol (ftp default): 
   - **ftp**: FTP protocol
   - **aspera**: using the aspera protocol
   - **globus**: PRIDE globus endpoint (_the data is downloaded through https_)

```bash
$ pridepy download-all-public-raw-files -a PXD012353 -o /Users/yourname/Downloads/foldername/ -p aspera
```

Download single file by name:
```bash
$ pridepy download-file-by-name -a PXD022105 -o /Users/yourname/Downloads/foldername/ -f checksum.txt -p globus
```

>**NOTE**: Currently we use Globus URLs (when `-p globus` is used) via HTTPS, not the Globus protocol. For more information about Globus, see [Globus documentation](https://www.globus.org/data-transfer).

Search projects with keywords and filters
```bash
$ pridepy search-projects-by-keywords-and-filters --keyword accession:PXD012353
```

Search files with filters
```bash
$ pridepy get-files-by-filter --filter fileCategory.value==RAW
```

Stream metadata of all projects as json and write it to a file
```bash
$ pridepy stream-projects-metadata -o all_pride_projects.json
```

Stream metadata of all files as json and write it to a file. Project accession can be specified as an optional parameter
```bash
$ pridepy stream-files-metadata -o all_pride_files.json
OR
$ pridepy stream-files-metadata -o PXD005011_files.json -a PXD005011
```

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
    
```
# NOTE

Please make sure you are using Python3, not Python 2.7 version.

# White paper

A white paper is available at [here](paper/paper.md). We can build it as PDF using pandoc.

```bash
$docker run --rm --platform linux/amd64 -v /Users/yperez/work/pridepy/paper/:/data -w /data openjournals/inara:latest paper.md -p -o pdf
```

# Citation

Selvakumar Kamatchinathan, Suresh Hewapathirana, Chakradhar Bandla, Yasset Perez-Riverol. (2021, January 28). pridepy: A Python package to download and search data from PRIDE database (Version v0.0.3). 

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4475414.svg)](https://doi.org/10.5281/zenodo.4475414)
