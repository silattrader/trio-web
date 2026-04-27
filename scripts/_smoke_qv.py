"""Live QV-extension smoke test — fetches real EDGAR + yfinance data and
prints the 6 QV factors per ticker.
"""
from datetime import date
from trio_backtester.data import fetch_history, fetch_volume_history
from trio_data_providers import EdgarPitProvider

TICKERS = ["AAPL", "MSFT", "JNJ", "XOM", "WMT"]


def _fmt(v, w=7, p=2):
    if v is None:
        return f"{'N/A':>{w}}"
    return f"{v:>{w}.{p}f}"


def main() -> None:
    print("Fetching prices+volumes...")
    _, prices = fetch_history(TICKERS, date(2023, 1, 1), date(2023, 12, 31))
    volumes = fetch_volume_history(TICKERS, date(2023, 1, 1), date(2023, 12, 31))

    p = EdgarPitProvider()
    res = p.fetch_as_of(TICKERS, as_of=date(2023, 6, 1), model="qv",
                        prices=prices, volumes=volumes)
    print()
    print(f"{'Ticker':<7s} {'ROE%':>7s}  {'GP/A':>5s}  {'D/E':>6s}  {'EY%':>7s}  {'B/M':>5s}  {'FCF%':>7s}  {'MCap':>9s}")
    print("-" * 78)
    for r in res.rows:
        mc = r.get("market_cap")
        mc_str = f"${mc/1e9:>6.1f}B" if mc else "      N/A"
        print(
            f"{r['ticker']:<7s} "
            f"{_fmt(r.get('roe'))}  "
            f"{_fmt(r.get('gross_profit_to_assets'), 5, 3)}  "
            f"{_fmt(r.get('debt_to_equity'), 6)}  "
            f"{_fmt(r.get('earnings_yield'))}  "
            f"{_fmt(r.get('book_to_market'), 5, 3)}  "
            f"{_fmt(r.get('fcf_yield'))}  {mc_str}"
        )

    print()
    for w in res.warnings:
        print(" -", w[:100])


if __name__ == "__main__":
    main()
