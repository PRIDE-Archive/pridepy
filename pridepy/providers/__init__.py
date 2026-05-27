"""Per-repository provider classes used by :class:`pridepy.files.files.Files`.

Each module under this package owns the listing, transport choice, and
record-construction logic for one repository: PRIDE, MassIVE, JPOST, iProX.
The :mod:`registry` module maps an accession to the right provider; the
:mod:`transport` module hosts the shared FTP/FTPS/HTTPS download plumbing.
"""
