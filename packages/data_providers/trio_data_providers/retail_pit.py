"""RetailFlowPitProvider — retail attention factor from Wikipedia pageviews.

The signal: surging retail attention to a stock is *not* a bullish signal in
fundamentals-aware investing. It's a "froth detector". When daily Wikipedia
pageviews for a company spike well above their year-long baseline, retail
flow is piling in — historically a contrarian indicator.

Score interpretation (1–5 BOS scale, 5 = BUY):

    z-score (recent attention vs trailing baseline)
        z >= +2.0   → 1.0  (extreme attention spike — strong contrarian SELL)
        z >= +1.0   → 2.0  (elevated — mild SELL)
        z <  +1.0   → 3.0  (normal — neutral)

Why no upside scoring? Low attention doesn't reliably predict positive
returns; F1 (vol_avg_3m) already penalises illiquidity. Keeping retail_flow
orthogonal — it's purely a "is the crowd already here?" detector.

PIT-honesty: Wikipedia pageview data finalises ~24h after the day in
question and never revises. Filtering to dates ≤ as_of has zero leakage.

Ticker → article mapping is hand-curated for the curated US large-cap
universe. Unknown tickers → None + warning. Extend ``TICKER_TO_ARTICLE``
or pass a custom mapping via constructor.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .pit import PitProvider, PitResult


# Curated ticker → Wikipedia article slug. Articles are case-sensitive in
# URLs; spaces become underscores. Cross-checked against actual Wikipedia.
TICKER_TO_ARTICLE: dict[str, str] = {
    # Tech
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet_Inc.",
    "GOOG": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "NVDA": "Nvidia",
    "ORCL": "Oracle_Corporation",
    "CRM": "Salesforce",
    "ADBE": "Adobe_Inc.",
    "AMZN": "Amazon_(company)",
    "TSLA": "Tesla,_Inc.",
    "NFLX": "Netflix",
    "AMD": "Advanced_Micro_Devices",
    "INTC": "Intel",
    # Consumer
    "WMT": "Walmart",
    "COST": "Costco",
    "MCD": "McDonald's",
    "KO": "The_Coca-Cola_Company",
    "PEP": "PepsiCo",
    "PG": "Procter_&_Gamble",
    "NKE": "Nike,_Inc.",
    "SBUX": "Starbucks",
    "DIS": "The_Walt_Disney_Company",
    # Industrials / Energy
    "BA": "Boeing",
    "CAT": "Caterpillar_Inc.",
    "DE": "John_Deere",
    "HON": "Honeywell",
    "XOM": "ExxonMobil",
    "CVX": "Chevron_Corporation",
    "GE": "General_Electric",
    # Healthcare
    "JNJ": "Johnson_&_Johnson",
    "PFE": "Pfizer",
    "MRK": "Merck_&_Co.",
    "ABBV": "AbbVie",
    "LLY": "Eli_Lilly_and_Company",
    "UNH": "UnitedHealth_Group",
    # Financial
    "JPM": "JPMorgan_Chase",
    "BAC": "Bank_of_America",
    "WFC": "Wells_Fargo",
    "GS": "Goldman_Sachs",
    "MS": "Morgan_Stanley",
    # Notable retail-favourites
    "GME": "GameStop",
    "AMC": "AMC_Theatres",
    "PLTR": "Palantir_Technologies",
    "COIN": "Coinbase",
    "RIVN": "Rivian",
    "NIO": "Nio_Inc.",
    # SP500 top-100 additions (beyond the curated 28-name basket)
    "AVGO": "Broadcom",
    "QCOM": "Qualcomm",
    "INTU": "Intuit",
    "CSCO": "Cisco",
    "ACN": "Accenture",
    "TXN": "Texas_Instruments",
    "IBM": "IBM",
    "BRK-B": "Berkshire_Hathaway",
    "BRK.B": "Berkshire_Hathaway",
    "V": "Visa_Inc.",
    "MA": "Mastercard",
    "BLK": "BlackRock",
    "AXP": "American_Express",
    "C": "Citigroup",
    "SCHW": "Charles_Schwab_Corporation",
    "SPGI": "S%26P_Global",
    "PGR": "Progressive_Corporation",
    "PYPL": "PayPal",
    "USB": "U.S._Bancorp",
    "TMO": "Thermo_Fisher_Scientific",
    "ABT": "Abbott_Laboratories",
    "DHR": "Danaher_Corporation",
    "AMGN": "Amgen",
    "ISRG": "Intuitive_Surgical",
    "MDT": "Medtronic",
    "ELV": "Elevance_Health",
    "BMY": "Bristol_Myers_Squibb",
    "GILD": "Gilead_Sciences",
    "VRTX": "Vertex_Pharmaceuticals",
    "HD": "The_Home_Depot",
    "PM": "Philip_Morris_International",
    "TJX": "TJX_Companies",
    "LOW": "Lowe%27s",
    "MDLZ": "Mondelez_International",
    "BKNG": "Booking_Holdings",
    "MO": "Altria",
    "CMCSA": "Comcast",
    "COP": "ConocoPhillips",
    "RTX": "RTX_Corporation",
    "UNP": "Union_Pacific_Corporation",
    "LMT": "Lockheed_Martin",
    "UPS": "United_Parcel_Service",
    "LIN": "Linde_plc",
    "ETN": "Eaton_Corporation",
    "ADP": "Automatic_Data_Processing",
    "NEE": "NextEra_Energy",
    "SO": "Southern_Company",
    "DUK": "Duke_Energy",
    "PLD": "Prologis",
    "AMT": "American_Tower",
    "T": "AT%26T",
    "VZ": "Verizon",
    "TMUS": "T-Mobile_US",
    "CI": "Cigna",
    "NOW": "ServiceNow",
    # FBM KLCI — best-effort English Wikipedia coverage. Names without
    # English articles return None and the factor is flagged as missing.
    "MAYBANK MK": "Maybank",
    "PBBANK MK": "Public_Bank_Berhad",
    "TENAGA MK": "Tenaga_Nasional",
    "CIMB MK": "CIMB",
    "PCHEM MK": "PETRONAS_Chemicals_Group",
    "PETDAG MK": "Petronas_Dagangan",
    "PETGAS MK": "Petronas_Gas",
    "AXIATA MK": "Axiata",
    "GENTING MK": "Genting_Group",
    "GENM MK": "Genting_Malaysia_Berhad",
    "MISC MK": "MISC_Berhad",
    "SIME MK": "Sime_Darby",
    "TM MK": "Telekom_Malaysia",
    "YTL MK": "YTL_Corporation",
    "NESTLE MK": "Nestl%C3%A9_Malaysia",
    "TOPGLOV MK": "Top_Glove",
    "HARTA MK": "Hartalega",
    "MRDIY MK": "Mr_DIY",
    # KLK, IOICORP, SDPL, HLBANK, RHBBANK, AMMB, YTLPOWR, PMETAL, CDB, QL,
    # MAXIS, DIGI — English Wikipedia coverage is missing or under a
    # disambiguation page; left out so retail_flow gracefully reports None
    # rather than fetching the wrong article.
}


@dataclass
class _AttentionStats:
    z_score: float | None
    recent_mean: float
    baseline_mean: float
    baseline_std: float
    n_recent: int
    n_baseline: int


def _attention_z(
    series: dict[date, int], *, as_of: date,
    recent_days: int = 30, baseline_days: int = 365,
) -> _AttentionStats:
    """Compute z-score of recent mean pageviews vs trailing baseline.

    Recent window: (as_of − recent_days, as_of].
    Baseline window: (as_of − baseline_days, as_of − recent_days].
    """
    recent_start = as_of - timedelta(days=recent_days)
    baseline_start = as_of - timedelta(days=baseline_days)

    recent = [v for d, v in series.items() if recent_start < d <= as_of]
    baseline = [
        v for d, v in series.items()
        if baseline_start < d <= recent_start
    ]
    if not recent or len(baseline) < 30:
        return _AttentionStats(
            z_score=None, recent_mean=0, baseline_mean=0, baseline_std=0,
            n_recent=len(recent), n_baseline=len(baseline),
        )

    recent_mean = sum(recent) / len(recent)
    base_mean = sum(baseline) / len(baseline)
    if len(baseline) > 1:
        var = sum((x - base_mean) ** 2 for x in baseline) / (len(baseline) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
    else:
        std = 0.0
    if std <= 0:
        return _AttentionStats(
            z_score=None, recent_mean=recent_mean, baseline_mean=base_mean,
            baseline_std=0, n_recent=len(recent), n_baseline=len(baseline),
        )
    z = (recent_mean - base_mean) / std
    return _AttentionStats(
        z_score=z, recent_mean=recent_mean, baseline_mean=base_mean,
        baseline_std=std, n_recent=len(recent), n_baseline=len(baseline),
    )


def score_from_attention_z(z: float | None) -> float | None:
    """Map z-score to 1–5 BOS scale. None → None (left as missing factor)."""
    if z is None:
        return None
    if z >= 2.0:
        return 1.0   # extreme attention spike — contrarian sell
    if z >= 1.0:
        return 2.0   # elevated attention
    return 3.0       # normal range — neutral


class RetailFlowPitProvider(PitProvider):
    name = "retail_flow_pit"
    label = "Wikipedia pageviews retail-attention z-score"

    def __init__(
        self,
        *,
        ttl_seconds: int = 7 * 24 * 3600,
        recent_days: int = 30,
        baseline_days: int = 365,
        ticker_to_article: dict[str, str] | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._recent = recent_days
        self._baseline = baseline_days
        self._map = ticker_to_article or TICKER_TO_ARTICLE

    def fetch_as_of(
        self,
        tickers: list[str],
        *,
        as_of: date,
        model: str,
        prices: dict[str, dict[date, float]] | None = None,
        volumes: dict[str, dict[date, float]] | None = None,
    ) -> PitResult:
        del prices, volumes
        from . import _wikipedia_client as wc

        rows: list[dict[str, Any]] = []
        unmapped: list[str] = []
        with_score = 0

        for ticker_raw in tickers:
            ticker = ticker_raw.upper()
            row: dict[str, Any] = {
                "ticker": ticker_raw,
                "name": None,
                "vol_avg_3m": None,
                "target_return": None,
                "analyst_sent": None,
                "altman_z": None,
                "dvd_yld_ind": None,
                "insider_flow": None,
                "retail_flow": None,
            }
            article = self._map.get(ticker)
            if article is None:
                unmapped.append(ticker_raw)
                rows.append(row)
                continue

            try:
                series = wc.fetch_pageviews_window(
                    article, as_of=as_of, lookback_days=self._baseline,
                    ttl_seconds=self._ttl,
                )
            except wc.WikiError:
                rows.append(row)
                continue

            stats = _attention_z(
                series, as_of=as_of,
                recent_days=self._recent, baseline_days=self._baseline,
            )
            row["retail_flow"] = score_from_attention_z(stats.z_score)
            row["_retail_attention_z"] = (
                round(stats.z_score, 3) if stats.z_score is not None else None
            )
            row["_retail_recent_mean"] = round(stats.recent_mean, 1)
            row["_retail_baseline_mean"] = round(stats.baseline_mean, 1)
            row["_retail_n_baseline"] = stats.n_baseline
            if row["retail_flow"] is not None:
                with_score += 1

            rows.append(row)

        warnings = [
            f"retail_flow_pit: retail_flow populated for {with_score}/{len(rows)} "
            f"rows (Wikipedia pageviews z-score, recent {self._recent}d "
            f"vs baseline {self._baseline}d).",
        ]
        if unmapped:
            warnings.append(
                f"retail_flow_pit: no Wikipedia article mapped for "
                f"{len(unmapped)} tickers — extend TICKER_TO_ARTICLE: "
                + ", ".join(unmapped[:8])
                + ("..." if len(unmapped) > 8 else "")
            )
        warnings.append(
            "retail_flow_pit: high z-score → low score (contrarian). "
            "Surging retail attention is a froth signal, not a buy signal, "
            "in a fundamentals-aware framework."
        )

        return PitResult(
            rows=rows, as_of=as_of, provider=self.name, warnings=warnings,
        )


__all__ = [
    "TICKER_TO_ARTICLE",
    "RetailFlowPitProvider",
    "score_from_attention_z",
]
