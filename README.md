# pridepy

[![Python package](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml/badge.svg)](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/pridepy.svg)](https://badge.fury.io/py/pridepy)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pridepy)

`pridepy` is a Python client and CLI for the PRIDE Archive API.

You can:
- download public and private PRIDE files
- download by category (`RAW`, `SEARCH`, `RESULT`, etc.)
- stream project and file metadata
- search projects by keyword and filters
- download raw files from ProteomeXchange XML metadata

The downloader supports `auto`, `aspera`, `s3`, `ftp`, and `globus`.  
With `auto`, it tries multiple protocols with fallback and validates downloaded files (non-empty, and checksum validation when enabled).

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
  -p auto \
  --checksum-check
```

What this does:
- `-p auto` enables protocol fallback (`aspera -> s3 -> ftp -> globus`)
- `--checksum-check` downloads project checksums and validates files
- empty/corrupt files are retried automatically

### 2) Continue interrupted downloads safely

```bash
pridepy download-all-public-raw-files \
  -a PXD008644 \
  -o ./downloads/PXD008644 \
  --skip-if-downloaded-already \
  -p auto \
  --checksum-check
```

### 3) Download only selected categories

```bash
pridepy download-all-public-category-files \
  -a PXD022105 \
  -o ./downloads/PXD022105 \
  -c RAW,SEARCH \
  -p auto
```

### 4) Download one file by name

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/PXD022105 \
  -p auto \
  --checksum-check
```

### 5) Download raw files from ProteomeXchange

```bash
pridepy download-px-raw-files \
  -a PXD039236 \
  -o ./downloads/PXD039236
```

## CLI Command Overview

```bash
pridepy --help
```

Main commands:
- `download-all-public-raw-files`
- `download-all-public-category-files`
- `download-file-by-name`
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

Build PDF with pandoc:

```bash
docker run --rm --platform linux/amd64 \
  -v "$(pwd)/paper:/data" \
  -w /data openjournals/inara:latest paper.md -p -o pdf
```

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
