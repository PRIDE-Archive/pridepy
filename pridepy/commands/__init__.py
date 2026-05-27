"""Cross-cutting download commands.

Each module under this package owns one user-facing command that doesn't
fit any single provider:

- ``by_url``: download a list of explicit URLs (ftp/http/https)
- ``by_list``: download a subset of a project's files by filename
- ``proteomexchange``: download raw files from a ProteomeXchange XML

The ``pridepy.files.files.Files`` facade keeps shim methods that
delegate here, so existing test patches on ``Files.X`` keep working.
"""
