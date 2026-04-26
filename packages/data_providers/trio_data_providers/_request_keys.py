"""Per-request API key overrides — BYOK plumbing.

Providers read keys via `os.environ` by default (unchanged for CLI/tests).
When the FastAPI middleware sets request-scoped overrides via
``set_request_keys(...)``, the helpers here return those values instead,
isolated to the active asyncio task / thread via ``contextvars``.

Helpers ``request_sec_ua()``, ``request_fmp_key()``, ``request_wiki_ua()``
are the *only* public surface — call them from low-level clients in place
of ``os.environ.get(...)`` reads.
"""
from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from contextlib import contextmanager


@dataclass(frozen=True)
class RequestKeys:
    """A bundle of per-request credentials. None ⇒ fall back to env / default."""

    sec_ua: str | None = None
    fmp_key: str | None = None
    wiki_ua: str | None = None


_current: ContextVar[RequestKeys] = ContextVar(
    "trio_request_keys", default=RequestKeys()
)


@contextmanager
def request_keys(keys: RequestKeys) -> Iterator[None]:
    """Set keys for the duration of the ``with`` block (sync code).

    Usage in tests:
        with request_keys(RequestKeys(fmp_key="abc")):
            # FMP client picks up "abc" instead of TRIO_FMP_KEY env
    """
    token = _current.set(keys)
    try:
        yield
    finally:
        _current.reset(token)


def set_request_keys(keys: RequestKeys) -> None:
    """Set keys for the rest of the current async task. Used by FastAPI
    middleware where the contextmanager pattern is awkward."""
    _current.set(keys)


def reset_request_keys() -> None:
    _current.set(RequestKeys())


def request_sec_ua(default: str) -> str:
    keys = _current.get()
    if keys.sec_ua:
        return keys.sec_ua
    return os.environ.get("TRIO_SEC_UA", default)


def request_fmp_key() -> str | None:
    keys = _current.get()
    if keys.fmp_key:
        return keys.fmp_key
    env = os.environ.get("TRIO_FMP_KEY", "").strip()
    return env or None


def request_wiki_ua(default: str) -> str:
    keys = _current.get()
    if keys.wiki_ua:
        return keys.wiki_ua
    return os.environ.get("TRIO_WIKI_UA", default)


__all__ = [
    "RequestKeys",
    "request_keys",
    "set_request_keys",
    "reset_request_keys",
    "request_sec_ua",
    "request_fmp_key",
    "request_wiki_ua",
]
