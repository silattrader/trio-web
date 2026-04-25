"""TradingView Scanner adapter — broad fundamentals + technicals coverage.

⚠️  Unofficial API. TradingView publishes no documented public REST API for
fundamentals; we call the `scanner.tradingview.com/{market}/scan` endpoint that
powers their Screener page. Stable in practice (libraries like
`tradingview-scanner` rely on it) but the contract can change without notice
and TradingView's ToS may restrict heavy programmatic use. Treat coverage
breaks as "expected someday" — every response carries an inline warning.

Markets auto-picked from ticker prefix; default = 'america'.

Field mapping (BOS):
  vol_avg_3m    <- average_volume_90d_calc
  target_return <- (price_target_average / close - 1) * 100
  dvd_yld_ind   <- dividend_yield_recent (already a %)
  analyst_sent  <- Recommend.All mapped from -1..+1 to 1..5

Note: TradingView removed `ALT.Z` (Altman-Z) from the public scanner schema.
For now we drop altman_z from TV coverage; combine TV with yfinance or a CSV
to fill it in. `recommendation_mark` was also reshaped to a non-[-1,+1]
range — we now use the documented `Recommend.All` field instead.

Sentiment normalisation: `Recommend.All` ∈ [-1, +1] where +1 = strong buy.
Remap to BOS 1..5 via `1 + (r + 1) * 2`, so +1 → 5, 0 → 3, -1 → 1. Defensive
clamp to [-1, +1] before the affine transform.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import DataProvider, ProviderError, ProviderResult

log = logging.getLogger(__name__)

SCANNER_URL = "https://scanner.tradingview.com/{market}/scan"

COLUMNS_BOS = [
    "name", "description", "close",
    "average_volume_90d_calc",
    "price_target_average",
    "dividend_yield_recent",
    "Recommend.All",
    "total_shares_outstanding",
]

COLUMNS_MOS = [
    "cash_n_short_term_invest_fy",
    "accounts_receivables_net_fy",
    "total_inventory_fy",
    "other_current_assets_fy",
    "accounts_payable_fy",
    "other_current_liabilities_fy",
    "short_term_debt_fy",
    "total_liabilities_fy",
    "total_current_liabilities_fy",
    "total_shares_outstanding",
    "close",
    "price_target_average",
]

COLUMNS_FOUR_FACTOR = [
    "dividend_yield_recent",
    "return_on_equity",
    "price_earnings_ttm",
]

_BOS_MAP = {
    "average_volume_90d_calc": "vol_avg_3m",
    "dividend_yield_recent": "dvd_yld_ind",
}

_MOS_MAP = {
    "cash_n_short_term_invest_fy": "cash_near_cash",
    "accounts_receivables_net_fy": "accounts_receivable",
    "total_inventory_fy": "inventories",
    "other_current_assets_fy": "other_current_assets",
    "accounts_payable_fy": "accounts_payable",
    "other_current_liabilities_fy": "other_st_liab",
    "short_term_debt_fy": "st_borrow",
    "total_shares_outstanding": "shares_out",
    "close": "px_last",
    "price_target_average": "best_target_price",
}

_FOUR_FACTOR_MAP = {
    "dividend_yield_recent": "dvd_yld_est",
    "return_on_equity": "roe_3yr_avg",
    "price_earnings_ttm": "pe_ratio",
}


def _detect_market(tickers: list[str]) -> str:
    for t in tickers:
        if ":" in t:
            ex = t.split(":", 1)[0].upper()
            if ex in ("MYX", "KLSE", "BURSA"):
                return "malaysia"
            if ex in ("NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "OTC"):
                return "america"
    return "america"


def _normalize_tickers(tickers: list[str], market: str) -> list[str]:
    default = "MYX" if market == "malaysia" else "NASDAQ"
    out: list[str] = []
    for t in tickers:
        s = t.strip().upper()
        if not s:
            continue
        out.append(s if ":" in s else f"{default}:{s}")
    return out


def _analyst_sent_from_rec_mark(rm: float | None) -> float | None:
    if rm is None:
        return None
    try:
        clamped = max(-1.0, min(1.0, float(rm)))
        return round(((clamped + 1) / 2) * 4 + 1, 2)
    except (TypeError, ValueError):
        return None


def _columns_for(model: str) -> list[str]:
    if model == "bos":
        return COLUMNS_BOS
    if model == "mos":
        return COLUMNS_BOS + COLUMNS_MOS
    if model == "four_factor":
        return COLUMNS_BOS + COLUMNS_FOUR_FACTOR
    return COLUMNS_BOS


class TradingViewProvider(DataProvider):
    name = "tradingview"
    label = "TradingView Scanner — unofficial, broad coverage"

    def coverage(self, model: str) -> set[str]:
        if model == "bos":
            return {
                "vol_avg_3m", "target_return", "dvd_yld_ind",
                "analyst_sent", "px_last", "best_target_price",
            }
        if model == "mos":
            return set(_MOS_MAP.values())
        if model == "four_factor":
            return set(_FOUR_FACTOR_MAP.values())
        return set()

    def fetch(self, tickers: list[str], *, model: str) -> ProviderResult:
        try:
            import requests
        except ImportError as e:
            raise ProviderError("requests not installed") from e

        if not tickers:
            return ProviderResult(
                rows=[], universe="?", provider=self.name,
                warnings=["empty ticker list"],
            )

        market = _detect_market(tickers)
        normalized = _normalize_tickers(tickers, market)
        columns = _columns_for(model)

        body = {
            "symbols": {"tickers": normalized},
            "columns": columns,
        }
        try:
            resp = requests.post(
                SCANNER_URL.format(market=market),
                json=body,
                headers={"User-Agent": "trio-web/0.1 (research)"},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            raise ProviderError(f"TradingView scanner request failed: {e}") from e

        warnings: list[str] = [
            "TradingView uses an unofficial scanner endpoint — schema may change without notice.",
        ]
        rows: list[dict[str, Any]] = []
        for item in payload.get("data", []):
            ticker = item.get("s") or "?"
            values = item.get("d") or []
            kv = dict(zip(columns, values, strict=False))

            row: dict[str, Any] = {
                "ticker": ticker.split(":", 1)[-1],
                "name": kv.get("description") or kv.get("name"),
            }

            for tv_key, canonical in _BOS_MAP.items():
                if tv_key in kv and kv[tv_key] is not None:
                    row[canonical] = kv[tv_key]

            close = kv.get("close")
            tgt = kv.get("price_target_average")
            if isinstance(close, (int, float)) and isinstance(tgt, (int, float)) and close:
                row["target_return"] = round(((tgt - close) / close) * 100, 2)
                row["px_last"] = close
                row["best_target_price"] = tgt

            row["analyst_sent"] = _analyst_sent_from_rec_mark(kv.get("Recommend.All"))

            for tv_key, canonical in _MOS_MAP.items():
                if tv_key in kv and kv[tv_key] is not None and canonical not in row:
                    row[canonical] = kv[tv_key]

            for tv_key, canonical in _FOUR_FACTOR_MAP.items():
                if tv_key in kv and kv[tv_key] is not None and canonical not in row:
                    row[canonical] = kv[tv_key]

            rows.append(row)

        if not rows:
            warnings.append("TradingView returned no data for these tickers.")

        universe = "KLCI" if market == "malaysia" else "SP500"
        return ProviderResult(
            rows=rows, universe=universe, provider=self.name, warnings=warnings,
        )
