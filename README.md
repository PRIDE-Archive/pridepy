# pridepy

[![Python package](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml/badge.svg)](https://github.com/PRIDE-Archive/pridepy/actions/workflows/python-package.yml)
[![PyPI version](https://badge.fury.io/py/pridepy.svg)](https://badge.fury.io/py/pridepy)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pridepy)

`pridepy` is a Python client and CLI for the PRIDE Archive API.

You can:
- download public and private PRIDE files
- download public MassIVE (`MSV...`), JPOST (`JPST...`), and iProX (`IPX...`) datasets directly. MassIVE goes through FTPS at `massive-ftp.ucsd.edu`, with an automatic HTTPS fallback (via the GNPS2 file index and the `massive.ucsd.edu` ProteoSAFe endpoint) for networks that block FTP/FTPS; JPOST uses the JSON PROXI endpoint at `repository.jpostdb.org` for listings and `ftp.jpostdb.org` for transfers; iProX fetches the dataset's ProteomeXchange XML from `download.iprox.org` and downloads files over anonymous HTTP
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

## Command Overview

```bash
pridepy --help
```

| Command | Purpose |
| --- | --- |
| `download-all-public-raw-files` | Download every public RAW file of a dataset |
| `download-all-public-category-files` | Download files of one or more categories (RAW, SEARCH, …) |
| `download-file-by-name` | Download a single file (public or private) |
| `download-files-by-list` | Download a named subset of files from a manifest/CSV |
| `download-files-by-url` | Download files from raw `http`/`https`/`ftp` URLs |
| `download-px-raw-files` | Download RAW files resolved from a ProteomeXchange accession |
| `list-private-files` | List files of a private project (needs credentials) |
| `stream-files-metadata` | Stream file metadata (one project or all) to JSON |
| `stream-projects-metadata` | Stream all project metadata to JSON |
| `search-projects-by-keywords-and-filters` | Search projects by keyword and filters |

The download commands work for PRIDE accessions and, transparently, for native
MassIVE (`MSV…`), JPOST (`JPST…`), and iProX (`IPX…`) accessions — see
[Download from ProteomeXchange and other repositories](#download-from-proteomexchange-and-other-repositories).

## PRIDE File Downloads

PRIDE downloads start with FTP and fall back across the remaining protocols
(`ftp -> aspera -> s3 -> globus`) when a transfer fails. They support resume,
per-file retries, parallel workers, and optional checksum validation. Empty or
corrupt files are retried automatically.

<details>
<summary><strong>Common download options</strong> (shared across the download commands)</summary>

These options are shared by `download-all-public-raw-files`,
`download-all-public-category-files`, `download-file-by-name`, and
`download-files-by-list`:

| Option | Description | Default |
| --- | --- | --- |
| `-a, --accession` | Dataset accession (e.g. `PXD008644`) | required |
| `-o, --output-folder` | Destination directory | required |
| `-p, --protocol` | Transfer protocol: `ftp`, `aspera`, `globus`, `s3` (FTP-first with fallback) | `ftp` |
| `-w, --parallel-files` | Download 1–3 files concurrently — primarily for `globus`; not available on `download-file-by-name` | `1` |
| `--skip-if-downloaded-already` | Resume: skip files already present locally | off |
| `--checksum-check` | Download PRIDE checksums and validate each file | off |
| `--aspera-maximum-bandwidth` | Aspera cap, e.g. `50M`, `100M`, `200M` (Aspera only) | `100M` |

</details>

<details>
<summary><strong>Download all raw files</strong> (robust mode)</summary>

```bash
pridepy download-all-public-raw-files \
  -a PXD008644 \
  -o ./downloads/PXD008644 \
  --checksum-check
```

Continue an interrupted download safely by adding `--skip-if-downloaded-already`:

```bash
pridepy download-all-public-raw-files \
  -a PXD008644 \
  -o ./downloads/PXD008644 \
  --skip-if-downloaded-already \
  --checksum-check
```

</details>

<details>
<summary><strong>Download only selected categories</strong></summary>

```bash
pridepy download-all-public-category-files \
  -a PXD022105 \
  -o ./downloads/PXD022105 \
  -c RAW,SEARCH
```

`-c, --category` takes one or more comma-separated categories. Valid values:
`RAW`, `PEAK`, `SEARCH`, `RESULT`, `SPECTRUM_LIBRARY`, `OTHER`, `FASTA`.

</details>

<details>
<summary><strong>Download one file by name</strong></summary>

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/PXD022105 \
  --checksum-check
```

`-f, --file-name` is the file to download.

</details>

<details>
<summary><strong>Download a named subset of files</strong> (manifest)</summary>

```bash
pridepy download-files-by-list \
  -a PXD001819 \
  -F files.txt \
  -o ./downloads/PXD001819 \
  --checksum-check
```

`files.txt` is one filename per line (blank lines and `#` comments are
ignored). Each filename is resolved against the project metadata and downloaded
via the same batch + protocol-fallback engine as `download-all-public-raw-files`.
Use `-f a.raw,b.raw,c.raw` instead of `-F` for a small inline list (you can
combine both).

</details>

<details>
<summary><strong>Download files from raw URLs</strong></summary>

```bash
pridepy download-files-by-url \
  -F urls.txt \
  -o ./downloads/urls
```

`urls.txt` is one fully-qualified URL per line. Schemes `http`, `https`, and
`ftp` are dispatched to the matching downloader. Use `-u, --urls` for one or
more comma-separated URLs, e.g. `--urls https://a.com/x.raw,ftp://b.com/y.raw`
(URLs containing literal commas must use a manifest file instead).

Command-specific options:

| Option | Description | Default |
| --- | --- | --- |
| `-F, --url-list` | Manifest file, one URL per line | — |
| `-u, --urls` | Comma-separated URL(s) | — |
| `-p, --protocol` | `ftp` (per-scheme) or `globus` (resume-capable http/https) | `ftp` |
| `-w, --parallel-files` | Download 1–3 files concurrently (any scheme) | `1` |
| `--checksum-check` | Validate against PRIDE checksums (accession inferred from PRIDE URL paths; only PRIDE archive URLs supported) | off |

</details>

<details>
<summary><strong>Private (restricted) files</strong></summary>

List the files of a private project with your PRIDE credentials:

```bash
pridepy list-private-files -a PXD022105 -u YOUR_USER -p YOUR_PASSWORD
```

Download a private file by passing `--username`/`--password` to
`download-file-by-name`:

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/private \
  --username YOUR_USER \
  --password YOUR_PASSWORD
```

</details>

## Metadata and Search

<details>
<summary><strong>Stream all project metadata to JSON</strong></summary>

```bash
pridepy stream-projects-metadata -o all_pride_projects.json
```

| Option | Description | Default |
| --- | --- | --- |
| `-o, --output-file` | JSON file to write all project metadata to | required |

</details>

<details>
<summary><strong>Stream file metadata</strong></summary>

```bash
# All file metadata for one accession
pridepy stream-files-metadata -a PXD005011 -o PXD005011_files.json
```

| Option | Description | Default |
| --- | --- | --- |
| `-o, --output-file` | JSON file to write file metadata to | required |
| `-a, --accession` | Limit to one project (omit to stream all files) | optional |

</details>

<details>
<summary><strong>Search projects by keywords and filters</strong></summary>

```bash
pridepy search-projects-by-keywords-and-filters \
  -k human \
  -f projectTags==ProteomeTools,organismsPart==Pancreas \
  -sd DESC \
  -sf accession \
  -sf submissionDate
```

| Option | Description | Default |
| --- | --- | --- |
| `-k, --keyword` | Keyword searched across project fields | required |
| `-f, --filters` | `field==value` filters, comma-separated (e.g. `accession==PRD000001`) | — |
| `-ps, --page-size` | Results per page (1–1000) | `100` |
| `-p, --page` | Page number (0-based) | `0` |
| `-sd, --sort-direction` | `ASC` or `DESC` | `DESC` |
| `-sf, --sort-fields` | Sort field(s), repeatable. One of: `accession`, `submissionDate`, `diseases`, `organismsPart`, `organisms`, `instruments`, `softwares`, `avgDownloadsPerFile`, `downloadCount`, `publicationDate` | `submissionDate` |

</details>

## Download from ProteomeXchange and other repositories

A ProteomeXchange (`PXD…` / `PRD…`) accession is a cross-repository identifier:
the dataset may be hosted at PRIDE, MassIVE, JPOST, iProX, or elsewhere.
`pridepy` lets you start from the ProteomeXchange accession, or go straight to
the hosting repository using its **native** accession.

<details>
<summary><strong>Start from a ProteomeXchange accession</strong></summary>

`download-px-raw-files` resolves the dataset's ProteomeXchange XML and downloads
the RAW files it references, regardless of which repository hosts them:

```bash
pridepy download-px-raw-files \
  -a PXD039236 \
  -o ./downloads/PXD039236
```

| Option | Description | Default |
| --- | --- | --- |
| `-a, --accession` | ProteomeXchange accession (e.g. `PXD039236`). `--px` is a deprecated alias | required |
| `-o, --output-folder` | Destination directory | required |
| `--skip-if-downloaded-already` | Skip files already present locally | off |

</details>

<details>
<summary><strong>Go directly to the hosting repository</strong> (native MassIVE / JPOST / iProX accessions)</summary>

Datasets that do not have a ProteomeXchange accession — or where you already
know the native accession — can be downloaded directly. The standard download
commands accept MassIVE, JPOST, and iProX accessions transparently:

```bash
# MassIVE (FTPS at massive-ftp.ucsd.edu)
pridepy download-all-public-raw-files \
  -a MSV000082297 \
  -o ./downloads/MSV000082297

# JPOST (PROXI listing + ftp.jpostdb.org)
pridepy download-all-public-raw-files \
  -a JPST002311 \
  -o ./downloads/JPST002311

# iProX (ProteomeXchange XML + anonymous HTTP at download.iprox.org)
pridepy download-all-public-raw-files \
  -a IPX0017413000 \
  -o ./downloads/IPX0017413000
```

How each repository is enumerated:

- **MassIVE** walks the FTPS tree at `massive-ftp.ucsd.edu` (the server requires TLS). If FTP/FTPS is blocked by the network, `pridepy` automatically falls back to HTTPS: it lists the dataset from the GNPS2 file index (`datasetcache.gnps2.org`) and downloads each file from the ProteoSAFe endpoint at `massive.ucsd.edu` (byte-identical to the FTPS copy).
- **JPOST** lists files through the JSON PROXI endpoint at `https://repository.jpostdb.org/proxi/datasets/<JPSTxxxxxx>` and downloads from `ftp.jpostdb.org` over plain FTP. The PROXI listing avoids the source-IP connection limit JPOST enforces on FTP.
- **iProX** fetches the dataset's ProteomeXchange XML from `http://download.iprox.org/<accession>/PX_<accession>.xml`, then downloads each referenced file from the same host over anonymous HTTP (with `Range` support for resume). iProX also exposes Aspera (`faspe://`) with username/password for very large bulk transfers; `pridepy` uses the public HTTP endpoint so no iProX credentials are required.

`download-all-public-raw-files` retrieves the files stored under the dataset's
`raw/` collection, saving them under `output_folder` with the dataset's
sub-directory layout preserved (so identically-named files in different
collections don't overwrite each other). These direct downloads support resume
(REST for FTP, byte-Range for HTTP), per-file retries, parallel workers (`-w`
up to 3), and post-transfer size verification against the server-reported size.

You can also request a specific collection from these repositories through the
same category interface:

```bash
pridepy download-all-public-category-files \
  -a MSV000082297 \
  -o ./downloads/MSV000082297-results \
  -c RESULT
```

</details>

## Python API Examples

<details>
<summary><strong>Get raw files for a project</strong></summary>

```python
from pridepy.download.client import Client

client = Client()
raw_files = client.get_all_raw_file_list("PXD008644")
print(f"RAW files: {len(raw_files)}")
print(raw_files[0]["fileName"])
```

For MassIVE / JPOST / iProX accessions, the same method returns the files found under the dataset's `raw/` collection:

```python
from pridepy.download.client import Client

client = Client()
for accession in ("MSV000082297", "JPST002311", "IPX0017413000"):
    raw_files = client.get_all_raw_file_list(accession)
    print(f"{accession} raw files: {len(raw_files)}")
```

</details>

<details>
<summary><strong>Search projects</strong></summary>

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

</details>

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
