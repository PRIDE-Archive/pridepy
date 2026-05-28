"""The pridepy download subsystem.

This package holds everything involved in turning an accession (or URL) into
downloaded files:

- Repository adapters — one module per repository (``pride``, ``massive``,
  ``jpost``, ``iprox``, ``proteomexchange``). Each subclasses
  :class:`pridepy.download.base.Provider` and implements at least ``matches``
  + ``list_files``. Direct-download adapters (MassIVE / JPOST / iProX) inherit
  the whole download workflow from the base; ``PrideProvider`` additionally
  overrides ``get_download_url``, ``download_files``, and ``download_by_name``
  for its multi-protocol fallback and public/private split.
- :mod:`registry` — maps an accession to the right adapter.
- :mod:`transport` — shared FTP/FTPS/HTTPS plumbing (resume, retry, parallel).
- :mod:`util` — checksum and record helpers.
- :mod:`by_url` — cross-cutting download command that takes raw URLs rather
  than an accession.
- :mod:`client` — the :class:`~pridepy.download.client.Client` facade the CLI
  drives; dispatches to adapters via the registry.
"""
