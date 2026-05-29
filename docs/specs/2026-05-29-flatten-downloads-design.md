# Flatten downloads into the output folder — design

Date: 2026-05-29
Status: Approved (pending spec review)

## Problem

When downloading from the direct-download repositories (MassIVE, JPOST, iProX),
pridepy recreates the dataset's subdirectory tree under the output folder, e.g.:

```
./downloads/MSV000088302/raw/.../sample.raw
./downloads/MSV000088302/ccms_peak/.../sample.mzML
```

Many users want the files dropped directly into the folder they pass with `-o`,
without the intermediate `raw/`, `ccms_peak/`, … directories.

The subdirectory layout was introduced deliberately (PRs #98 / #100 / #105) to
stop identically-named files in different collections from overwriting each
other. Flattening reintroduces that collision risk, so it must be paired with a
collision-safe naming scheme.

## Current behavior

- Direct-download providers (MassIVE/JPOST/iProX) thread each file's
  `relativePath` through `base.Provider.download_files` into
  `transport.download_ftp_urls` / `download_http_urls`, where
  `transport._dest_path` / `_safe_join` join it under the output folder,
  preserving the tree.
- PRIDE downloads are **already flat**: `PrideProvider.get_output_file_name`
  uses only the URL basename, so PRIDE files land directly in the output folder
  today (with no collision handling — last write wins).

## Decision

Make **flatten the default** behavior for all repositories, with an opt-out to
preserve the directory tree. Flattening is made collision-safe with
deterministic auto-rename.

### Behavior

- **Default: flatten.** Each file is written directly into `output_folder` by
  its basename.
- **Opt-out: `--preserve-structure`** keeps the dataset subdirectory tree
  (the current behavior).
- **Collision handling (auto-rename).** When two or more files in the same
  download set collapse to the same basename, the first (by sorted source
  relative path) keeps the basename; subsequent ones get a numeric suffix
  inserted before the final extension: `run.raw`, `run_1.raw`, `run_2.raw`.
  - The mapping is computed over the **full file list** for the download, not
    from what is already on disk, so it is deterministic across runs. This
    keeps `--skip-if-downloaded-already` and FTP `REST` resume stable (the same
    source file always maps to the same flat name).
  - Extension splitting uses `os.path.splitext` (so `a.tar.gz` → `a.tar_1.gz`).

## Architecture

Approach A (chosen): thread a `flatten` flag into `base.Provider.download_files`
and, when set, replace each record's `relativePath` with a flat de-duplicated
name passed through the existing `relative_paths` plumbing. Because a relative
path with no slash already lands directly in `output_folder` via
`transport._safe_join`, **no change to the transport layer is required**.

Rejected alternatives:
- **B.** Add `flatten` to `transport.download_ftp_urls` / `download_http_urls`.
  Spreads naming policy across two transport signatures and mixes "how to
  transfer" with "where to name"; no upside over A.
- **C.** Download with structure, then move files to a flat layout. Wastes
  work, breaks resume, fragile.

### Components

1. **`flatten_relative_paths(relative_paths: List[str]) -> List[str]`** — new
   pure helper (in `pridepy/download/util.py`). Maps a list of dataset-relative
   paths to flat, de-duplicated basenames using the deterministic auto-rename
   rule above. Order of the returned list matches the order of the input
   (suffix assignment is decided by sorted source path, but the output aligns
   positionally with the input so callers can zip it back to records).

2. **`base.Provider.download_files(..., flatten: bool = True)`** — when
   `flatten` is True, build `relative_paths` from
   `flatten_relative_paths([r.get("relativePath") or basename(url) for r in records])`;
   when False, use each record's `relativePath` as today.

3. **Flag threading.** Add `flatten: bool = True` to the relevant `Client`
   facade methods and the provider `download_by_*` methods so the value flows
   CLI → `Client` → provider → `download_files`:
   - `Client.download_all_raw_files`
   - `Client.download_all_category_files`
   - `Client.download_by_filenames` (download-files-by-list)
   - `Client.download_px_raw_files`

4. **CLI.** Add a `--preserve-structure` flag (Click `is_flag`, default False →
   flatten on) to the multi-file download commands:
   - `download-all-public-raw-files`
   - `download-all-public-category-files`
   - `download-files-by-list`
   - `download-px-raw-files`

   `download-file-by-name` (single file) and `download-files-by-url` (already
   basename-flat, no dataset structure) do not get the flag.

### Data flow

```
CLI (--preserve-structure?)
  -> Client.download_*(flatten = not preserve_structure)
    -> provider.download_by_*(flatten=...)
      -> base.Provider.download_files(flatten=...)
        -> relative_paths = flat dedup names (flatten) | original relativePath (preserve)
          -> transport.download_ftp_urls / download_http_urls  (unchanged)
```

### PRIDE note

PRIDE already writes flat via `get_output_file_name`, so the new default does
not change PRIDE behavior. `--preserve-structure` is effectively a no-op for
PRIDE (its records carry no meaningful subtree). Full parity — including
collision auto-rename for PRIDE — arrives when issue #107 routes PRIDE FTP
through the shared `transport` layer; until then PRIDE keeps its existing
flat, last-write-wins behavior. This is called out so the partial coverage is
explicit, not silent.

## Error handling

- Auto-rename never raises; it always produces a usable, unique name.
- `--preserve-structure` falls back to existing behavior, including
  `transport._safe_join`'s defensive guard against `..`/absolute-path escape.

## Testing

- `flatten_relative_paths`:
  - no collisions → basenames unchanged;
  - collisions → deterministic `_1`, `_2` suffixes;
  - ordering determinism (same input in any disk state → same output);
  - multi-dot extensions (`a.tar.gz`), no-extension files, leading-slash paths.
- `base.Provider.download_files`:
  - `flatten=True` passes flat de-duplicated `relative_paths`;
  - `flatten=False` passes original `relativePath` values (existing tests).
- Existing MassIVE/JPOST/iProX structure-preservation tests re-run with
  `flatten=False`.
- CLI: `--preserve-structure` maps to `flatten=False`; default maps to
  `flatten=True` for each affected command.

## Out of scope

- Refactoring PRIDE FTP onto the shared transport (tracked in issue #107).
- Any change to `download-file-by-name` or `download-files-by-url`.
