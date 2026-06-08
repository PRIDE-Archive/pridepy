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

### Option 3: Install the latest code directly from GitHub

To get features that have not been released to PyPI yet, install straight from a
branch. `master` holds the latest stable code; `dev` holds the newest (and
potentially unstable) development work.

With `uv`:

```bash
# Latest stable (master)
uv tool install "git+https://github.com/PRIDE-Archive/pridepy@master"

# Bleeding edge (dev)
uv tool install "git+https://github.com/PRIDE-Archive/pridepy@dev"
```

Or with `pip`:

```bash
# Latest stable (master)
pip install --upgrade "git+https://github.com/PRIDE-Archive/pridepy@master"

# Bleeding edge (dev)
pip install --upgrade "git+https://github.com/PRIDE-Archive/pridepy@dev"
```

You can pin to any branch, tag, or commit by changing the part after `@` (e.g.
`@v0.0.16` or `@<commit-sha>`).

### Option 4: Install from source (development)

```bash
git clone https://github.com/PRIDE-Archive/pridepy
cd pridepy
uv sync --extra dev
uv run pridepy --help
```

## Usage

See the **[usage guide](docs/usage.md)** for detailed instructions and examples:
downloading data (PRIDE, MassIVE, JPOST, iProX, ProteomeXchange), category and
manifest downloads, private files, streaming metadata, searching projects, and
the Python API.

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
| `download-pdc-files` | Download PDC/CPTAC files via PDC signed HTTPS URLs |
| `download-px-raw-files` | Download RAW files resolved from a ProteomeXchange accession |
| `list-private-files` | List files of a private project (needs credentials) |
| `stream-files-metadata` | Stream file metadata (one project or all) to JSON |
| `stream-projects-metadata` | Stream all project metadata to JSON |
| `search-projects-by-keywords-and-filters` | Search projects by keyword and filters |

Quick examples:

```bash
# Download all public RAW files of a dataset (any repository)
pridepy download-all-public-raw-files -a PXD008644 -o ./downloads/PXD008644 --checksum-check

# Download a ProteomeXchange dataset by its PXD accession
pridepy download-px-raw-files -a PXD039236 -o ./downloads/PXD039236

# Download a native MassIVE / JPOST / iProX dataset
pridepy download-all-public-raw-files -a MSV000082297 -o ./downloads/MSV000082297

# Download PDC/CPTAC files for a study (all types, or restrict with --file-type)
pridepy download-pdc-files -a PDC000109 -o ./downloads/pdc
pridepy download-pdc-files -a PDC000109 --file-type psm -o ./downloads/pdc
```

Full option tables and more examples are in [docs/usage.md](docs/usage.md).

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
