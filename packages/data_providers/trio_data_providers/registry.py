from __future__ import annotations

from .base import DataProvider, ProviderError
from .bloomberg_provider import BloombergProvider
from .i3investor_provider import I3InvestorProvider
from .tradingview_provider import TradingViewProvider
from .yfinance_provider import YFinanceProvider

_PROVIDERS: dict[str, type[DataProvider]] = {
    "yfinance": YFinanceProvider,
    "tradingview": TradingViewProvider,
    "i3investor": I3InvestorProvider,
    "bloomberg": BloombergProvider,
}


def get_provider(name: str) -> DataProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(f"unknown provider: {name}")
    return cls()


def list_providers() -> list[dict[str, str]]:
    return [
        {"name": name, "label": cls().label}
        for name, cls in _PROVIDERS.items()
    ]
