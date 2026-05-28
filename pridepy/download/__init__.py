"""The pridepy download subsystem.

This package holds everything involved in turning an accession (or URL) into
downloaded files:

- Repository adapters — one module per repository (``pride``, ``massive``,
  ``jpost``, ``iprox``, ``proteomexchange``). Each subclasses
  :class:`pridepy.download.base.Provider` and implements ``matches`` +
  ``list_files``; the download workflow itself is inherited from the base.
- :mod:`registry` — maps an accession to the right adapter.
- :mod:`transport` — shared FTP/FTPS/HTTPS plumbing (resume, retry, parallel).
- :mod:`util` — checksum and record helpers.
- :mod:`by_url`, :mod:`by_list` — cross-cutting download commands that take
  URLs or filename lists rather than an accession.
- :mod:`client` — the :class:`~pridepy.download.client.Client` facade the CLI
  drives; dispatches to adapters via the registry.
"""
