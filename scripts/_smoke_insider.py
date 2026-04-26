"""Quick live smoke test for InsiderFlowPitProvider — real SEC + yfinance."""
from datetime import date

from trio_backtester.data import fetch_history, fetch_volume_history
from trio_data_providers import InsiderFlowPitProvider

TICKERS = ["AAPL", "MSFT", "TSLA", "NVDA", "JNJ"]


def main() -> None:
    print("Fetching prices+volumes...")
    _, prices = fetch_history(TICKERS, date(2023, 1, 1), date(2023, 12, 31))
    volumes = fetch_volume_history(TICKERS, date(2023, 1, 1), date(2023, 12, 31))

    print("Pulling Form 4 filings (cold cache ~ 30s)...")
    p = InsiderFlowPitProvider(lookback_days=90)
    res = p.fetch_as_of(
        TICKERS, as_of=date(2023, 6, 1), model="bos",
        prices=prices, volumes=volumes,
    )
    print()
    for r in res.rows:
        net = r.get("_insider_net_usd", 0) or 0
        kind = r.get("_insider_score_kind", "?")
        print(
            f"{r['ticker']:6s} flow={r['insider_flow']} "
            f"buys={r.get('_insider_n_buys')} sells={r.get('_insider_n_sells')} "
            f"net=${net:,.0f} ({kind})"
        )
    print()
    for w in res.warnings:
        print(" -", w[:120])


if __name__ == "__main__":
    main()
