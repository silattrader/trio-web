"""i3investor scraper — KLCI / Bursa Malaysia partial enrichment.

Resurrected from notebooks/i3investor_scraper.ipynb of trio-mvp.

Coverage: target_return + analyst_sent ONLY. i3investor's analyst price-target
page does not surface volume, dividend yield, or Altman Z, so KLCI users still
need a CSV upload (or Bloomberg) for full BOS scoring. We document this
explicitly and emit a warning per request.

URL pattern: https://klse.i3investor.com/web/stock/analysis-price-target/{ticker}
where {ticker} is the 4-character KLSE code (e.g. '1155' for Maybank).

Sentiment encoding: i3investor exposes analyst counts (sell, hold, buy).
We map to the 1..5 BOS scale via:
    sentiment = 1 + 4 * buy / max(buy + hold + sell, 1)
i.e. 100% buy -> 5.0, 100% sell -> 1.0, balanced -> ~3.0.

Politeness: 5-second sleep between requests (matches legacy notebook).
Set TRIO_I3_RATE_LIMIT=0 in tests / dev to disable.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from .base import DataProvider, ProviderError, ProviderResult

log = logging.getLogger(__name__)

BASE_URL = "https://klse.i3investor.com/web/stock/analysis-price-target/{ticker}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _sentiment(buy: int, hold: int, sell: int) -> float | None:
    total = buy + hold + sell
    if total <= 0:
        return None
    return round(1 + 4 * buy / total, 2)


def _parse_target_page(html: str, ticker: str) -> dict[str, Any]:
    from bs4 import BeautifulSoup  # local import — heavy

    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {"ticker": ticker, "name": None}

    name_el = soup.find("h5", id="stock-heading")
    if name_el and name_el.find("strong"):
        out["name"] = name_el.find("strong").text.strip()

    info_el = soup.find("div", id="stock-price-info")
    if info_el:
        strongs = info_el.find_all("strong")
        if strongs:
            try:
                out["px_last"] = float(strongs[0].text.replace(",", ""))
            except ValueError:
                pass

    cols = soup.find_all("div", {"class": "col-sm-3 col-6"})
    if len(cols) > 1 and cols[1].find("strong"):
        try:
            out["best_target_price"] = float(cols[1].find("strong").text.replace(",", ""))
        except ValueError:
            pass

    if isinstance(out.get("px_last"), float) and isinstance(out.get("best_target_price"), float) and out["px_last"]:
        out["target_return"] = round(
            ((out["best_target_price"] - out["px_last"]) / out["px_last"]) * 100, 2
        )

    anr_cols = soup.find_all("div", {"class": "col-4"})
    if len(anr_cols) >= 3:
        try:
            sell = int(anr_cols[0].find("strong").text)
            hold = int(anr_cols[1].find("strong").text)
            buy = int(anr_cols[2].find("strong").text)
            out["analyst_sent"] = _sentiment(buy, hold, sell)
        except (AttributeError, ValueError):
            pass

    return out


class I3InvestorProvider(DataProvider):
    name = "i3investor"
    label = "i3investor (KLSE) — partial enrichment"

    def coverage(self, model: str) -> set[str]:
        if model == "bos":
            return {"target_return", "analyst_sent", "px_last", "best_target_price"}
        if model == "mos":
            return {"px_last", "best_target_price"}
        if model == "four_factor":
            return set()
        return set()

    def fetch(self, tickers: list[str], *, model: str) -> ProviderResult:
        try:
            import requests  # local import — only when used
        except ImportError as e:
            raise ProviderError("requests not installed") from e

        rate = float(os.environ.get("TRIO_I3_RATE_LIMIT", "5"))
        rows: list[dict[str, Any]] = []
        warnings: list[str] = [
            "i3investor only provides target price + analyst sentiment. "
            "For full BOS scoring on KLCI, supplement with a CSV upload or Bloomberg.",
        ]

        for i, raw in enumerate(tickers):
            t = raw.strip()
            if not t:
                continue
            url = BASE_URL.format(ticker=t)
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                row = _parse_target_page(resp.text, t)
                rows.append(row)
            except Exception as e:
                warnings.append(f"{t}: {type(e).__name__}: {e}")
                rows.append({"ticker": t, "name": None})
            if rate > 0 and i < len(tickers) - 1:
                time.sleep(rate)

        return ProviderResult(rows=rows, universe="KLCI", provider=self.name, warnings=warnings)
