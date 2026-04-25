"""Abstract data-provider interface.

A provider's job is to turn a list of tickers into a list of dicts whose keys
match the canonical fields each scoring engine expects (see contracts.py +
docs/algorithms/*.md). The scoring engine never sees the provider — keeping
/score universe-blind is a load-bearing invariant.

Coverage is best-effort: providers fill what they can, leave the rest as None,
and surface unsupported fields in `coverage()` so callers can warn upfront.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a provider cannot fulfil a request (network, auth, missing creds)."""


@dataclass
class ProviderResult:
    rows: list[dict[str, Any]]
    universe: str
    provider: str
    warnings: list[str] = field(default_factory=list)


class DataProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def coverage(self, model: str) -> set[str]:
        """Return canonical fields this provider can populate for the given model."""

    @abstractmethod
    def fetch(self, tickers: list[str], *, model: str) -> ProviderResult:
        """Pull rows for these tickers, mapped to canonical scoring fields."""
