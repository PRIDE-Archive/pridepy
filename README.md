# pridepy: Python client for PRIDE Archive database

[![Python package](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml/badge.svg)](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/pridepy.svg)](https://badge.fury.io/py/pridepy)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pridepy)

Python Client library for PRIDE Rest API

# Installation
To install, simply use `pip`:

```bash
$ pip install --upgrade pridepy
```

# Examples

Download all the raw files from a dataset(eg: PXD012353).
Warning: Raw files are generally large in size, so it may take some time to download depending on the number of files and file sizes.
-p in download specifies protocol , Available protocols nows are ftp, aspera, s3 and globus. Default is ftp.

```python
$ pridepy download-all-raw-files -a PXD012353 -o /Users/yourname/Downloads/foldername/ -p aspera
```

Download single file by name

```python
$ pridepy download-files-by-name -a PXD022105 -o /Users/yourname/Downloads/foldername/ -f checksum.txt -p s3
```

```python
$ pridepy download-files-by-name -a PXD022105 -o /Users/yourname/Downloads/foldername/ -f checksum.txt -p globus
```

Please note : Currently we use globus urls ( when -p globus is used) via https not globus protocol.

Search projects with keywords and filters

```python
$ pridepy search-projects-by-keywords-and-filters --keyword accession:PXD012353
```

Search files with filters

```python
$ pridepy get-files-by-filter --filter fileCategory.value==RAW
```

Search protein-evidences with keywords and filters

```python
$ pridepy search-protein-evidences --project_accession PXD012353
```

Search spectra-evidences with keywords and filters

```python
$ pridepy search-spectra-evidences --usi "mzspec:PXD019317:sh_5282_HYK_101018_Mac_D_25mM.mzML:scan:10138:YAAMVTC[UNIMOD:4]MDEAVRNITWALKR/3"
```

Use below command to view list of commands available
```python
$ python3 pridepy.py --help

  download-all-raw-files          
  download-files-by-name          
  get-files-by-filter             
  get-files-by-project-accession  
  get-projects                    
  get-projects-by-accession       
  get-reanalysis-projects-by-accession
  get-similar-projects-by-accession
  search-projects-by-keywords-and-filters                 

```

# NOTE

Please make sure you are using Python3, not Python 2.7 version.

# Citation

Selvakumar Kamatchinathan, Suresh Hewapathirana, Yasset Perez-Riverol. (2021, January 28). pridepy: python client for the PRIDE Archive database (Version v0.0.2). 

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4475414.svg)](https://doi.org/10.5281/zenodo.4475414)
