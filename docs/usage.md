# pridepy usage guide

This guide covers how to download data and query metadata with `pridepy`. For
installation, see the [README](../README.md#installation).

`pridepy` works with PRIDE accessions and, transparently, with native MassIVE
(`MSV…`), JPOST (`JPST…`), and iProX (`IPX…`) accessions. The downloader
supports `ftp`, `aspera`, `s3`, and `globus`: by default it starts with FTP,
falls back across the remaining protocols when a transfer fails, and validates
downloaded files (non-empty, and checksum validation when enabled).

## Contents

- [Command overview](#command-overview)
- [PRIDE file downloads](#pride-file-downloads)
- [Metadata and search](#metadata-and-search)
- [Download from ProteomeXchange and other repositories](#download-from-proteomexchange-and-other-repositories)
- [Download CPTAC/PDC files](#download-cptacpdc-files)
- [Python API examples](#python-api-examples)

## Command overview

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
| `download-pdc-files` | Download PDC/CPTAC files via PDC GraphQL signed HTTPS URLs |
| `list-private-files` | List files of a private project (needs credentials) |
| `stream-files-metadata` | Stream file metadata (one project or all) to JSON |
| `stream-projects-metadata` | Stream all project metadata to JSON |
| `search-projects-by-keywords-and-filters` | Search projects by keyword and filters |

The download commands work for PRIDE accessions and, transparently, for native
MassIVE (`MSV…`), JPOST (`JPST…`), and iProX (`IPX…`) accessions — see
[Download from ProteomeXchange and other repositories](#download-from-proteomexchange-and-other-repositories).

## PRIDE file downloads

PRIDE downloads start with FTP and fall back across the remaining protocols
(`ftp -> aspera -> s3 -> globus`) when a transfer fails. They support resume,
per-file retries, parallel workers, and optional checksum validation. Empty or
corrupt files are retried automatically.

### Common download options

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
| `--preserve-structure` | Recreate the dataset's subdirectory layout (e.g. `raw/…/`) under the output folder instead of downloading flat | off |

By default, files are downloaded **flat** into the output folder (no
`raw/…/` subdirectories). When two files would collapse to the same name,
later ones get a numeric suffix (`run.raw`, `run_1.raw`). Pass
`--preserve-structure` to keep the dataset's original directory layout.

### Download all raw files (robust mode)

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

### Download only selected categories

```bash
pridepy download-all-public-category-files \
  -a PXD022105 \
  -o ./downloads/PXD022105 \
  -c RAW,SEARCH
```

`-c, --category` takes one or more comma-separated categories. Valid values:
`RAW`, `PEAK`, `SEARCH`, `RESULT`, `SPECTRUM_LIBRARY`, `OTHER`, `FASTA`.

### Download one file by name

```bash
pridepy download-file-by-name \
  -a PXD022105 \
  -f checksum.txt \
  -o ./downloads/PXD022105 \
  --checksum-check
```

`-f, --file-name` is the file to download.

### Download a named subset of files (manifest)

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

### Download files from raw URLs

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

### Private (restricted) files

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

## Metadata and search

### Stream all project metadata to JSON

```bash
pridepy stream-projects-metadata -o all_pride_projects.json
```

| Option | Description | Default |
| --- | --- | --- |
| `-o, --output-file` | JSON file to write all project metadata to | required |

### Stream file metadata

```bash
# All file metadata for one accession
pridepy stream-files-metadata -a PXD005011 -o PXD005011_files.json
```

| Option | Description | Default |
| --- | --- | --- |
| `-o, --output-file` | JSON file to write file metadata to | required |
| `-a, --accession` | Limit to one project (omit to stream all files) | optional |

### Search projects by keywords and filters

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

## Download from ProteomeXchange and other repositories

A ProteomeXchange (`PXD…` / `PRD…`) accession is a cross-repository identifier:
the dataset may be hosted at PRIDE, MassIVE, JPOST, iProX, or elsewhere.
`pridepy` lets you start from the ProteomeXchange accession, or go straight to
the hosting repository using its **native** accession.

### Start from a ProteomeXchange accession

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

### Go directly to the hosting repository (native MassIVE / JPOST / iProX accessions)

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

- **MassIVE** walks the FTPS tree at `massive-ftp.ucsd.edu` (the server requires TLS). MassIVE distributes datasets across versioned root directories (`/v01`–`/vNN`); `pridepy` discovers the correct root automatically. If FTP/FTPS is blocked by the network, `pridepy` falls back to HTTPS: it lists the dataset from the GNPS2 file index (`datasetcache.gnps2.org`) and downloads each file from the ProteoSAFe endpoint at `massive.ucsd.edu` (byte-identical to the FTPS copy).
- **JPOST** lists files through the JSON PROXI endpoint at `https://repository.jpostdb.org/proxi/datasets/<JPSTxxxxxx>` and downloads from `ftp.jpostdb.org` over plain FTP. The PROXI listing avoids the source-IP connection limit JPOST enforces on FTP.
- **iProX** fetches the dataset's ProteomeXchange XML from `http://download.iprox.org/<accession>/PX_<accession>.xml`, then downloads each referenced file from the same host over anonymous HTTP (with `Range` support for resume). iProX also exposes Aspera (`faspe://`) with username/password for very large bulk transfers; `pridepy` uses the public HTTP endpoint so no iProX credentials are required.

`download-all-public-raw-files` retrieves the files stored under the dataset's
`raw/` collection. These direct downloads support resume (REST for FTP,
byte-Range for HTTP), per-file retries, parallel workers (`-w` up to 3), and
post-transfer size verification against the server-reported size. By default
files are written flat into the output folder; pass `--preserve-structure` to
keep the dataset's sub-directory layout.

You can also request a specific collection from these repositories through the
same category interface:

```bash
pridepy download-all-public-category-files \
  -a MSV000082297 \
  -o ./downloads/MSV000082297-results \
  -c RESULT
```

## Download CPTAC/PDC files

The [Proteomic Data Commons (PDC)](https://pdc.cancer.gov/) hosts CPTAC (Clinical
Proteomic Tumor Analysis Consortium) mass-spectrometry datasets. `pridepy` can
enumerate and download PDC files via the PDC GraphQL API, which issues short-lived
signed HTTPS URLs for each file. Files are organised by **PDC study ID**
(e.g. `PDC000109`).

### Download all files for a study

Omit `--file-type` to download every file available in the study:

```bash
pridepy download-pdc-files \
  -a PDC000109 \
  -o ./downloads/PDC000109
```

Files are placed under `<output-folder>/<PDC study ID>/<file name>`.

### Download a specific file type

Pass `--file-type` to restrict the download to one category:

```bash
# mzIdentML peptide-spectral-match files
pridepy download-pdc-files \
  -a PDC000109 \
  --file-type mzid \
  -o ./downloads/PDC000109

# PSM TSV files
pridepy download-pdc-files \
  -a PDC000109 \
  --file-type psm \
  -o ./downloads/PDC000109

# Vendor RAW files
pridepy download-pdc-files \
  -a PDC000109 \
  --file-type raw \
  -o ./downloads/PDC000109

# Processed mzML files
pridepy download-pdc-files \
  -a PDC000109 \
  --file-type mzml \
  -o ./downloads/PDC000109
```

### Download multiple studies at once

Pass a comma-separated list of study IDs or a CSV file:

```bash
# Comma-separated list — downloads all files for each study
pridepy download-pdc-files \
  -a PDC000109,PDC000110,PDC000111 \
  -o ./downloads/pdc-batch

# CSV with a pdc_id column — downloads all files for each row
# studies.csv:  pdc_id
#               PDC000109
#               PDC000110
pridepy download-pdc-files \
  -a studies.csv \
  -o ./downloads/pdc-batch
```

When the CSV includes a `file-type` (or `filetype`) column, each row's file type
is used independently, allowing mixed-type batch downloads in a single command:

```csv
pdc_id,file-type
PDC000109,raw
PDC000110,mzml
PDC000111,psm
```

```bash
pridepy download-pdc-files \
  -a studies.csv \
  -o ./downloads/pdc-batch
```

### Resume an interrupted download

```bash
pridepy download-pdc-files \
  -a PDC000109 \
  -o ./downloads/PDC000109 \
  --skip-if-downloaded-already
```

### Validate checksums

PDC-provided `md5sum` values are checked automatically. To disable:

```bash
pridepy download-pdc-files \
  -a PDC000109 \
  -o ./downloads/PDC000109 \
  --no-checksum-check
```

### Speed up large files with parallel HTTP Range threads

Use `-t / --threads` (1–32) to split each file into parallel byte-range requests:

```bash
pridepy download-pdc-files \
  -a PDC000109 \
  --file-type raw \
  -o ./downloads/PDC000109 \
  --threads 8
```

### Retry failed files (including 403 signed-URL refresh)

Signed URLs expire after a short time. `--retry` re-fetches a fresh URL before
each retry attempt when a `403 Forbidden` is received:

```bash
pridepy download-pdc-files \
  -a PDC000109 \
  -o ./downloads/PDC000109 \
  --retry
```

### Full option reference

| Option | Description | Default |
| --- | --- | --- |
| `-a, --accession` | PDC study ID, comma-separated IDs, or a CSV with `pdc_id`/`pdc_study_id` and optional `file-type`/`filetype` column | required |
| `--file-type` | Restrict to one type: `mzid`, `psm`, `raw`, or `mzml`. Omit to download all file types. Overrides the CSV `file-type` column. | all types |
| `-o, --output-folder` | Destination directory; files are written as `<output>/<study ID>/<file name>` | required |
| `--skip-if-downloaded-already` | Skip files that already exist locally and match PDC size/checksum | off |
| `--checksum-check / --no-checksum-check` | Validate downloads against PDC `md5sum` values | on |
| `-t, --threads` | Parallel HTTP Range threads per file (1–32) | `1` |
| `--retry` | Retry failed files; HTTP 403 retries refresh the PDC signed URL first | off |

## Python API examples

> **Breaking change (0.0.16):** the legacy `pridepy.files.files.Files` class has been
> removed. Replace `from pridepy.files.files import Files` with
> `from pridepy.download.client import Client`; `Client` exposes the same public
> methods (`get_all_raw_file_list`, `download_all_raw_files`,
> `get_submitted_file_path_prefix`, `download_file_by_name`,
> `download_all_category_files`, `download_px_raw_files`, …).

### Get raw files for a project

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

### Download all raw files for a project

```python
from pridepy.download.client import Client

client = Client()
client.download_all_raw_files(
    accession="PXD008644",
    output_folder="./downloads/PXD008644",
    skip_if_downloaded_already=True,
    protocol="ftp",
    aspera_maximum_bandwidth="100M",
    checksum_check=True,
)
```

### Search projects

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
