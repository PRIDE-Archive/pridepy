# pridepy

[![Python package](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml/badge.svg)](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/pridepy.svg)](https://badge.fury.io/py/pridepy)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pridepy)

`pridepy` is a Python client and CLI for the PRIDE Archive API.

You can:
- download public and private PRIDE files
- download public MassIVE (`MSV...`), JPOST (`JPST...`), and iProX (`IPX...`) datasets directly. MassIVE goes through FTPS at `massive-ftp.ucsd.edu`; JPOST uses the JSON PROXI endpoint at `repository.jpostdb.org` for listings and `ftp.jpostdb.org` for transfers; iProX fetches the dataset's ProteomeXchange XML from `download.iprox.org` and downloads files over anonymous HTTPS
- download by category (`RAW`, `SEARCH`, `RESULT`, etc.)
- stream project and file metadata
- search projects by keyword and filters
- download raw files from ProteomeXchange XML metadata

The downloader supports `ftp`, `aspera`, `s3`, and `globus`.  
By default it starts with FTP, falls back across the remaining protocols when needed, and validates downloaded files (non-empty, and checksum validation when enabled).

## Requirements

- Python `>=3.9`

## Installation

### Option 1: Install from PyPI with uv (recommended)

Install as a CLI tool:

```bash
uv tool install pridepy
pridepy --help
```

Or run without installing globally:

```bash
uvx pridepy --help
```

### Option 2: Install from PyPI with pip

```bash
pip install --upgrade pridepy
pridepy --help
```

### Option 3: Install from source (development)

```bash
git clone https://github.com/PRIDE-Archive/pridepy
cd pridepy
uv sync --extra dev
uv run pridepy --help
```

## Quick Start (New Users)

### 1) Download all raw files for a project (robust mode)

```bash
pridepy download-all-public-raw-files \
  -a PXD008644 \
  -o ./downloads/PXD008644 \
  --checksum-check
```

What this does:
- default `ftp` starts with FTP and falls back (`ftp -> aspera -> s3 -> globus`)
- `--checksum-check` downloads project checksums and validates files
- empty/corrupt files are retried automatically

### 2) Continue interrupted downloads safely

```bash
pridepy download-all-public-raw-files \
  -a PXD008644 \
  -o ./downloads/PXD008644 \
  --skip-if-downloaded-already \
  --checksum-check
```

### 3) Download a public MassIVE, JPOST, or iProX dataset directly

```bash
# MassIVE
pridepy download-all-public-raw-files \
  -a MSV000082297 \
  -o ./downloads/MSV000082297

# JPOST
pridepy download-all-public-raw-files \
  -a JPST002311 \
  -o ./downloads/JPST002311

# iProX
pridepy download-all-public-raw-files \
  -a IPX0017413000 \
  -o ./downloads/IPX0017413000
```

For these direct downloads, `pridepy` enumerates the dataset from the repository:
- **MassIVE** lists files by walking the FTPS tree at `massive-ftp.ucsd.edu` (TLS is required by the server).
- **JPOST** lists files through the JSON PROXI endpoint at `https://repository.jpostdb.org/proxi/datasets/<JPSTxxxxxx>` and downloads them from `ftp.jpostdb.org` over plain FTP. The PROXI listing avoids the source-IP connection limit JPOST enforces on FTP.
- **iProX** fetches the dataset's ProteomeXchange XML from `http://download.iprox.org/<accession>/PX_<accession>.xml`, then downloads each referenced file from the same host over anonymous HTTPS. iProX exposes Aspera (`faspe://`) with username/password for very large bulk transfers; `pridepy` uses the public HTTPS endpoint instead so no iProX credentials are required.

Raw downloads follow each repository's own collection layout, so `download-all-public-raw-files` downloads the files stored under the dataset's `raw/` collection. Direct downloads support resume (REST for FTP, byte-Range for HTTPS), per-file retries, parallel workers (`-w N` up to 3), and post-transfer size verification against the server-reported size.

### 4) Download only selected categories

```bash
pridepy download-all-public-category-files \
  -a PXD022105 \
  -o ./downloads/PXD022105 \
  -c RAW,SEARCH
```

You can also request a specific MassIVE / JPOST / iProX collection through the same category interface:

```bash
pridepy download-all-public-category-files \
  -a MSV000082297 \
  -o ./downloads/MSV000082297-results \
  -c RESULT
```

### 5) Download one file by name

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/PXD022105 \
  --checksum-check
```

### 6) Download raw files from ProteomeXchange

```bash
pridepy download-px-raw-files \
  -a PXD039236 \
  -o ./downloads/PXD039236
```

### 6) Download a named subset of files (manifest)

```bash
pridepy download-files-by-list \
  -a PXD001819 \
  -F files.txt \
  -o ./downloads/PXD001819 \
  --checksum-check
```

`files.txt` is one filename per line (blank lines and `#` comments are
ignored). Internally each filename is resolved against the project metadata
API and downloaded via the same batch + protocol-fallback engine as
`download-all-public-raw-files`. Use `-f a.raw,b.raw,c.raw` instead of
`-F` for a small inline list.

Useful options:

- `-p globus` — use the globus download strategy (HTTP Range + resume)
- `-w 3` — download up to 3 files in parallel (globus only, max 3)
- `--checksum-check` — validate files against PRIDE checksums after download

### 7) Download files from raw URLs

```bash
pridepy download-files-by-url \
  -F urls.txt \
  -o ./downloads/urls
```

`urls.txt` is one fully-qualified URL per line. Schemes `http`, `https`, and
`ftp` are dispatched to the matching downloader. Use `-u/--urls` for one or
more comma-separated URLs, e.g. `--urls https://a.com/x.raw,ftp://b.com/y.raw`.
Note: URLs containing literal commas are not supported with `--urls`; use a
manifest file (`-F`) instead.

Useful options:

- `-p globus` — use globus download strategy for http/https URLs (resume-capable)
- `-w 3` — download up to 3 files in parallel (globus only, max 3)
- `--checksum-check` — validate against PRIDE checksums (accession inferred
  from PRIDE URL paths; only PRIDE archive URLs are supported)

## CLI Command Overview

```bash
pridepy --help
```

Main commands:
- `download-all-public-raw-files`
- `download-all-public-category-files`
- `download-file-by-name`
- `download-files-by-list`
- `download-files-by-url`
- `download-px-raw-files`
- `list-private-files`
- `stream-files-metadata`
- `stream-projects-metadata`
- `search-projects-by-keywords-and-filters`

## More CLI Examples

### Search projects

```bash
pridepy search-projects-by-keywords-and-filters \
  -k human \
  -f projectTags==ProteomeTools,organismsPart==Pancreas \
  -sd DESC \
  -sf accession \
  -sf submissionDate
```

### Stream all project metadata to JSON

```bash
pridepy stream-projects-metadata -o all_pride_projects.json
```

### Stream all file metadata for one accession

```bash
pridepy stream-files-metadata -a PXD005011 -o PXD005011_files.json
```

### Download private files

List files:

```bash
pridepy list-private-files -a PXD022105 -u YOUR_USER -p YOUR_PASSWORD
```

Download a private file:

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/private \
  --username YOUR_USER \
  --password YOUR_PASSWORD
```

## Python API Examples

### Example: get raw files for a project

```python
from pridepy.files.files import Files

files = Files()
raw_files = files.get_all_raw_file_list("PXD008644")
print(f"RAW files: {len(raw_files)}")
print(raw_files[0]["fileName"])
```

For MassIVE / JPOST / iProX accessions, the same method returns the files found under the dataset's `raw/` collection:

```python
from pridepy.files.files import Files

files = Files()
for accession in ("MSV000082297", "JPST002311", "IPX0017413000"):
    raw_files = files.get_all_raw_file_list(accession)
    print(f"{accession} raw files: {len(raw_files)}")
```

### Example: search projects

```python
from pridepy.project.project import Project

project = Project()
results = project.search_by_keywords_and_filters(
    keyword="PXD009476",
    query_filter="",
    page_size=25,
    page=0,
    sort_direction="DESC",
    sort_fields="accession",
)
print(f"Hits: {len(results)}")
```

## Development and Release (uv)

Run tests:

```bash
uv run pytest
```

Lint:

```bash
uv run flake8 .
```

Build distributions:

```bash
uv build
```

`pridepy` is published via GitHub Actions (`.github/workflows/python-publish.yml`) using `uv build` and a PyPI API token secret (`PYPI_API_TOKEN`).

## White Paper

A white paper is available in [paper/paper.md](paper/paper.md).

## Contributing

1. Fork the repository
2. Create a branch (`git checkout -b feature/my-change`)
3. Install dev dependencies (`uv sync --extra dev`)
4. Run tests and lint (`uv run pytest`, `uv run flake8 .`)
5. Commit and push your branch
6. Open a pull request

## Citation

Kamatchinathan, S., Hewapathirana, S., Bandla, C., Insua, S., Vizcaíno, J. A., & Perez-Riverol, Y. (2025). pridepy: A Python package to download and search data from PRIDE database. Journal of Open Source Software, 10(107), 7563. doi:10.21105/joss.07563

[![Zenodo](https://zenodo.org/badge/DOI/10.5281/zenodo.4475414.svg)](https://doi.org/10.5281/zenodo.4475414)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.07563/status.svg)](https://doi.org/10.21105/joss.07563)
