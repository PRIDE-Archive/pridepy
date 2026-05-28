"""Backward-compatibility shim.

The download facade moved to :mod:`pridepy.download.client` and the class
was renamed ``Files`` -> ``Client``. This module re-exports it under the old
name so ``from pridepy.files.files import Files`` keeps working, along with
``Progress``.
"""
from pridepy.download.client import Client, Progress  # noqa: F401

Files = Client  # legacy alias

__all__ = ["Client", "Files", "Progress"]
