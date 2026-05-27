"""Accession-to-provider resolution.

Providers are tried in priority order; direct-download repositories
(MassIVE / JPOST / iProX) are tried first because their accession patterns
are unambiguous. PRIDE is tried last and acts as the catch-all for
``PXD\\d+`` / ``PRD\\d+`` accessions.
"""
from typing import List, Type

from pridepy.providers.base import Provider

_PROVIDERS: List[Type[Provider]] = []  # populated by individual provider modules


def register(provider_cls: Type[Provider]) -> Type[Provider]:
    """Register a provider class. Usable as a decorator."""
    if provider_cls not in _PROVIDERS:
        _PROVIDERS.append(provider_cls)
    return provider_cls


def resolve(accession: str) -> Provider:
    """Return a provider instance that matches ``accession``.

    :raises ValueError: when no registered provider matches.
    """
    for cls in _PROVIDERS:
        if cls.matches(accession):
            return cls()
    raise ValueError(f"No provider registered for accession {accession!r}")


def is_known(accession: str) -> bool:
    """Return True if any registered provider matches ``accession``."""
    for cls in _PROVIDERS:
        if cls.matches(accession):
            return True
    return False
