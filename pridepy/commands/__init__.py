"""Cross-cutting download commands.

Each module under this package owns one user-facing command that doesn't
fit any single provider:

- ``by_url``: download a list of explicit URLs (ftp/http/https)
- ``by_list``: download a subset of a project's files by filename

ProteomeXchange used to live here too but moved to
:class:`pridepy.providers.proteomexchange.ProteomeXchangeProvider` because
it conforms to the ``Provider`` interface (takes an accession or URL and
returns file records). It is deliberately not auto-registered with the
provider registry — PXD/PRD accessions continue to route through
:class:`pridepy.providers.pride.PrideProvider`; ProteomeXchangeProvider is
the explicit gateway for the cross-repository XML view, invoked via the
``download-px-raw-files`` CLI command and ``Files.download_px_raw_files``.

The ``pridepy.files.files.Files`` facade keeps shim methods that
delegate here, so existing test patches on ``Files.X`` keep working.
"""
