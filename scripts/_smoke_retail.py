"""Live smoke test for RetailFlowPitProvider — real Wikipedia pageviews."""
from datetime import date

from trio_data_providers import RetailFlowPitProvider

# Mix: mega-caps + meme-stocks. Expect divergent attention z-scores.
TICKERS = ["AAPL", "MSFT", "GME", "AMC", "TSLA", "NVDA", "JNJ", "PLTR"]


def main() -> None:
    print("Pulling Wikipedia pageviews (cold cache ~ 60s)...")
    p = RetailFlowPitProvider(recent_days=30, baseline_days=365)
    res = p.fetch_as_of(TICKERS, as_of=date(2023, 6, 1), model="bos")
    print()
    print(f"{'Ticker':6s}  {'Score':>5s}  {'Z':>6s}  {'Recent':>10s}  {'Baseline':>10s}")
    for r in res.rows:
        z = r.get("_retail_attention_z")
        recent = r.get("_retail_recent_mean")
        baseline = r.get("_retail_baseline_mean")
        z_s = f"{z:>6.2f}" if z is not None else "   N/A"
        rs = f"{recent:>10,.0f}" if recent is not None else "       N/A"
        bs = f"{baseline:>10,.0f}" if baseline is not None else "       N/A"
        print(
            f"{r['ticker']:6s}  {str(r['retail_flow']):>5s}  {z_s}  {rs}  {bs}"
        )
    print()
    for w in res.warnings:
        print(" -", w[:120].replace("→", "->"))


if __name__ == "__main__":
    main()
