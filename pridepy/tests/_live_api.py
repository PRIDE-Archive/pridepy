"""Helpers for the live PRIDE-API integration tests.

A handful of tests hit ``www.ebi.ac.uk`` directly (no mocking) to validate
real behaviour. That endpoint is occasionally slow or unreachable from CI
runners, which used to fail the build on a transient read timeout. The
:func:`tolerate_api_outage` context manager turns an API outage into a clean
skip instead of a failure, keeping CI deterministic while still exercising the
real API whenever it is available.
"""
import unittest
from contextlib import contextmanager

import requests


@contextmanager
def tolerate_api_outage(testcase: unittest.TestCase):
    """Skip (don't fail) the wrapped block when the live PRIDE API is down.

    Wrap only the live API call(s) and their assertions. An API outage surfaces
    as one of:
      * ``requests.RequestException`` — ``Util.get_api_call`` lets connection
        / read timeouts propagate;
      * ``RuntimeError`` — ``Provider._list_files_checked`` raises when the API
        helper returned ``None``;
      * ``TypeError`` — a helper that returns ``None`` on failure is then
        iterated / measured (e.g. ``len(None)``).
    Genuine assertion failures raise ``AssertionError``, which is *not* caught,
    so real regressions still fail the test.
    """
    try:
        yield
    except (requests.RequestException, RuntimeError, TypeError) as exc:
        testcase.skipTest(f"PRIDE API unavailable: {type(exc).__name__}: {exc}")
