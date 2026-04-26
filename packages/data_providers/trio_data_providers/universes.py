"""Curated equity universes for the demo + MLA training.

Three groups:

- ``SP500_TOP_100`` — the largest 100 S&P 500 names by market cap (snapshot
  early 2024). Covers ~75% of the index by weight and is small enough that
  the FMP free tier (250 req/day) can refresh it daily.
- ``KLCI_30`` — the 30 components of FBM KLCI. PIT data coverage is *limited*
  for these (no EDGAR for Malaysian issuers; Wikipedia EN has patchy
  coverage). Documented in `docs/algorithms/universes.md`.
- ``CURATED_DEMO`` — the 28-name US large-cap basket used for the original
  MLA training and gate runs. Kept as a baseline for reproducing existing
  results.

The UI exposes these as preset buttons in `LiveUniverseCard`. The API
exposes them via ``GET /universes``. Lists are intentionally hand-curated
and dated — refresh annually, document the snapshot date.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Universe:
    id: str
    label: str
    snapshot: str          # ISO date the list was last verified
    coverage: str          # "us" or "my" — drives provider selection
    tickers: list[str]


# The 28-name US large-cap basket used in the original MLA gate run.
# Kept verbatim so existing artifacts and walk-forward results reproduce.
CURATED_DEMO: Universe = Universe(
    id="curated_demo",
    label="Curated demo (28 US large caps)",
    snapshot="2026-04-26",
    coverage="us",
    tickers=[
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "ORCL", "CRM", "ADBE",
        "AMZN", "WMT", "COST", "MCD", "KO", "PEP", "PG", "NKE",
        "BA", "CAT", "DE", "HON", "XOM", "CVX",
        "JNJ", "PFE", "MRK", "ABBV", "LLY", "UNH",
    ],
)


# S&P 500 top 100 by market capitalisation, snapshot February 2024.
# Updated annually; verify against https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
SP500_TOP_100: Universe = Universe(
    id="sp500_top_100",
    label="S&P 500 — top 100 by market cap",
    snapshot="2024-02-01",
    coverage="us",
    tickers=[
        # Mega-cap tech (~30% of index weight)
        "MSFT", "AAPL", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "ORCL",
        "ADBE", "CRM", "AMD", "QCOM", "INTU", "CSCO", "ACN", "TXN", "INTC", "IBM",
        # Financials
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK", "AXP",
        "C", "SCHW", "SPGI", "PGR", "PYPL", "USB",
        # Healthcare
        "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "PFE", "DHR", "AMGN",
        "ISRG", "MDT", "ELV", "BMY", "GILD", "VRTX",
        # Consumer
        "WMT", "PG", "HD", "COST", "KO", "PEP", "MCD", "PM", "NKE", "TJX",
        "LOW", "SBUX", "MDLZ", "BKNG", "MO", "DIS", "CMCSA", "NFLX",
        # Energy / Industrials / Materials
        "XOM", "CVX", "COP", "BA", "CAT", "GE", "HON", "RTX", "UNP", "DE",
        "LMT", "UPS", "LIN", "ETN", "ADP",
        # Utilities / Real Estate / Comms
        "NEE", "SO", "DUK", "PLD", "AMT",
        # Other large-caps
        "T", "VZ", "TMUS", "CI", "NOW",
    ],
)


# FBM KLCI 30 — Malaysian large caps as of early 2026.
# Verify via Bursa Malaysia: https://www.bursamalaysia.com/market_information/equities_prices?b=AC
# Tickers use Bloomberg-style "<symbol> MK" suffix (used by i3investor + bloomberg providers).
KLCI_30: Universe = Universe(
    id="klci_30",
    label="FBM KLCI 30 (limited PIT coverage)",
    snapshot="2026-04-01",
    coverage="my",
    tickers=[
        "MAYBANK MK", "PBBANK MK", "TENAGA MK", "CIMB MK", "PCHEM MK",
        "PETDAG MK", "PETGAS MK", "AXIATA MK", "DIGI MK", "MAXIS MK",
        "GENTING MK", "GENM MK", "KLK MK", "IOICORP MK", "SDPL MK",
        "HLBANK MK", "RHBBANK MK", "AMMB MK", "MISC MK", "SIME MK",
        "TM MK", "YTL MK", "YTLPOWR MK", "PMETAL MK", "MRDIY MK",
        "CDB MK", "QL MK", "NESTLE MK", "TOPGLOV MK", "HARTA MK",
    ],
)


ALL: dict[str, Universe] = {
    u.id: u for u in (CURATED_DEMO, SP500_TOP_100, KLCI_30)
}


def get_universe(universe_id: str) -> Universe:
    if universe_id not in ALL:
        raise KeyError(f"unknown universe: {universe_id}; have {sorted(ALL)}")
    return ALL[universe_id]


__all__ = [
    "ALL",
    "CURATED_DEMO",
    "KLCI_30",
    "SP500_TOP_100",
    "Universe",
    "get_universe",
]
