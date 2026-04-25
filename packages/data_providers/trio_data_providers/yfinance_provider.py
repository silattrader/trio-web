"""yfinance adapter — primary live source for US equities (S&P 500).

Field mapping (BOS):
  vol_avg_3m   <- 3-month mean of daily Volume
  target_return <- (targetMeanPrice - currentPrice) / currentPrice * 100
  dvd_yld_ind  <- info['dividendYield'] * 100
  altman_z     <- computed from balance sheet when fields are present, else None
  analyst_sent <- 6 - info['recommendationMean']
                  (yfinance: 1=strongBuy ... 5=strongSell;
                   TRIO BOS rule expects high = bullish, so we invert)

For MOS (balance-sheet model) we map the relevant `BS_*` fields out of
`Ticker.balance_sheet`. yfinance's row labels are stable; missing rows -> None.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import DataProvider, ProviderError, ProviderResult

log = logging.getLogger(__name__)

# yfinance balance-sheet row labels we care about (left = label in DataFrame index)
BS_LABEL_MAP = {
    "Cash And Cash Equivalents": "cash_near_cash",
    "Receivables": "accounts_receivable",
    "Inventory": "inventories",
    "Other Current Assets": "other_current_assets",
    "Accounts Payable": "accounts_payable",
    "Other Current Liabilities": "other_st_liab",
    "Current Debt": "st_borrow",
    "Total Non Current Liabilities Net Minority Interest": "non_current_liab",
}


def _altman_z_public(info: dict, bs: dict | None) -> float | None:
    """Public-firm Altman Z (manufacturing). Returns None if any input missing."""
    try:
        if not bs:
            return None
        ta = bs.get("Total Assets")
        tl = bs.get("Total Liabilities Net Minority Interest")
        ca = bs.get("Current Assets")
        cl = bs.get("Current Liabilities")
        re_ = bs.get("Retained Earnings")
        if not all(isinstance(v, (int, float)) for v in (ta, tl, ca, cl, re_)):
            return None
        if ta == 0:
            return None
        wc = ca - cl
        ebit = info.get("ebitda") or info.get("operatingIncome")
        sales = info.get("totalRevenue")
        mv_eq = info.get("marketCap")
        if not all(isinstance(v, (int, float)) and v is not None for v in (ebit, sales, mv_eq)):
            return None
        z = (
            1.2 * (wc / ta)
            + 1.4 * (re_ / ta)
            + 3.3 * (ebit / ta)
            + 0.6 * (mv_eq / tl if tl else 0)
            + 1.0 * (sales / ta)
        )
        return round(z, 3)
    except Exception:
        log.debug("altman_z compute failed", exc_info=True)
        return None


class YFinanceProvider(DataProvider):
    name = "yfinance"
    label = "Yahoo Finance (yfinance)"

    def coverage(self, model: str) -> set[str]:
        if model == "bos":
            return {"vol_avg_3m", "target_return", "dvd_yld_ind", "altman_z", "analyst_sent"}
        if model == "mos":
            return set(BS_LABEL_MAP.values()) | {"shares_out", "px_last", "best_target_price"}
        if model == "four_factor":
            return {"altman_z", "dvd_yld_est", "pe_ratio"}  # pe_5yr_avg & ROE 3yr not on yf info
        return set()

    def fetch(self, tickers: list[str], *, model: str) -> ProviderResult:
        try:
            import yfinance as yf  # local import — heavy
        except ImportError as e:
            raise ProviderError("yfinance not installed") from e

        rows: list[dict[str, Any]] = []
        warnings: list[str] = []

        for raw in tickers:
            t = raw.strip().upper()
            if not t:
                continue
            try:
                tk = yf.Ticker(t)
                info = tk.info or {}
                hist = tk.history(period="3mo", auto_adjust=False)
                vol_avg = float(hist["Volume"].mean()) if not hist.empty else None
                px_last = info.get("currentPrice") or info.get("regularMarketPrice")
                tgt = info.get("targetMeanPrice")
                target_return = (
                    ((tgt - px_last) / px_last) * 100
                    if (isinstance(tgt, (int, float)) and isinstance(px_last, (int, float)) and px_last)
                    else None
                )
                dvd_yld = info.get("dividendYield")
                dvd_pct = dvd_yld * 100 if isinstance(dvd_yld, (int, float)) else None
                rec_mean = info.get("recommendationMean")
                analyst_sent = (6 - rec_mean) if isinstance(rec_mean, (int, float)) else None

                bs_dict: dict[str, float] = {}
                try:
                    bs_df = tk.balance_sheet
                    if bs_df is not None and not bs_df.empty:
                        latest_col = bs_df.columns[0]
                        for label in bs_df.index:
                            v = bs_df.at[label, latest_col]
                            if v is not None and v == v:  # not NaN
                                bs_dict[label] = float(v)
                except Exception:
                    log.debug("balance_sheet pull failed for %s", t, exc_info=True)

                row: dict[str, Any] = {
                    "ticker": t,
                    "name": info.get("longName") or info.get("shortName"),
                    # BOS fields
                    "vol_avg_3m": vol_avg,
                    "target_return": target_return,
                    "dvd_yld_ind": dvd_pct,
                    "altman_z": _altman_z_public(info, bs_dict),
                    "analyst_sent": analyst_sent,
                    # MOS fields
                    "px_last": px_last,
                    "best_target_price": tgt,
                    "shares_out": info.get("sharesOutstanding"),
                    # 4-factor extras
                    "dvd_yld_est": dvd_pct,
                    "pe_ratio": info.get("trailingPE"),
                }
                for label, canonical in BS_LABEL_MAP.items():
                    if label in bs_dict:
                        row[canonical] = bs_dict[label]
                rows.append(row)
            except Exception as e:
                warnings.append(f"{t}: {type(e).__name__}: {e}")
                rows.append({"ticker": t, "name": None})

        if not rows:
            warnings.append("No tickers resolved.")

        return ProviderResult(rows=rows, universe="SP500", provider=self.name, warnings=warnings)
