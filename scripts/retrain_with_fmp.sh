#!/usr/bin/env bash
# Wire FmpPitProvider into MLA training and unlock the 2 dead-weight features.
#
# Pre-req: set TRIO_FMP_KEY (free tier 250 req/day at financialmodelingprep.com).
#   export TRIO_FMP_KEY="your_key_here"
#   bash scripts/retrain_with_fmp.sh
#
# Network expectation: 28 tickers × 1 fetch each (FMP returns full history per
# ticker, not per as_of). ~28 calls total — well within free-tier daily quota.
# First run takes ~3 minutes; cached runs are instant.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${TRIO_FMP_KEY:-}" ]; then
  echo "ERROR: TRIO_FMP_KEY is not set." >&2
  echo "Get a free key at https://site.financialmodelingprep.com/developer/docs/pricing?ref=trio-web" >&2
  echo "Then: export TRIO_FMP_KEY=\"your_key_here\" && rerun." >&2
  exit 1
fi

# 1. Wipe the cached PIT dataset so the rebuild includes FMP data.
echo "==> Wiping stale cache (built without FMP)..."
rm -f packages/algorithms/trio_algorithms/mla/artifacts/pit_dataset_v2.pkl
rm -f packages/algorithms/trio_algorithms/mla/artifacts/pit_train_2018_2021_v2.pkl

# 2. Retrain on the full 2018–2023 PIT data with FMP wired in.
echo "==> Retraining MLA on 2018–2023 PIT (full FMP-enabled)..."
py -3.12 -m trio_algorithms.mla.train --real \
  --out packages/algorithms/trio_algorithms/mla/artifacts/mla_v0.joblib \
  --cache packages/algorithms/trio_algorithms/mla/artifacts/pit_dataset_v2.pkl

# 3. Run SHAP again to verify target_return and analyst_sent come alive.
echo "==> Running SHAP to confirm previously-dead features now have weight..."
py -3.12 scripts/shap_analysis.py

# 4. Optionally re-run the gate. Comment out if you only want the SHAP signal.
echo "==> Retraining 2018–2021 model (for OOS gate eval)..."
py -3.12 -c "
from datetime import date
from pathlib import Path
from trio_algorithms.mla.data_pipeline import build_pit_dataset, to_xy
from trio_algorithms.mla.model import MlaScorer, TrainingMeta
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score
import numpy as np

samples = build_pit_dataset(
    start=date(2018, 3, 31), end=date(2021, 12, 31),
    cache_path=Path('packages/algorithms/trio_algorithms/mla/artifacts/pit_train_2018_2021_v2.pkl'),
)
X, y, kept = to_xy(samples)
print(f'Train: {len(X)} samples / {len({s.ticker for s in kept})} tickers')
model = GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42)
model.fit(X, y)
preds = model.predict(X)
r2 = float(r2_score(y, preds))
hit = float(np.mean(np.sign(preds) == np.sign(y)))
print(f'2018-2021 r2={r2:.3f}  hit={hit:.3f}')
scorer = MlaScorer(model=model, meta=TrainingMeta(n_samples=len(X), train_r2=r2, rba_corr=hit))
scorer.save(Path('packages/algorithms/trio_algorithms/mla/artifacts/mla_v1_clean.joblib'))
print('Saved mla_v1_clean.joblib')
"

echo "==> Running promotion gate against RBA-BOS-Flow on 2022–2023 OOS..."
py -3.12 -m trio_algorithms.mla.promote \
  --start 2022-01-03 --end 2023-12-29 \
  --artifact packages/algorithms/trio_algorithms/mla/artifacts/mla_v1_clean.joblib \
  --top-n 5 --rebalance-days 63

echo
echo "==> Done. Verify in the SHAP output above:"
echo "    - target_return % of total importance now > 0%"
echo "    - analyst_sent % of total importance now > 0%"
echo "If both are still 0%, FMP returned no data for any ticker (check FMP free-tier"
echo "history limits — older as_of dates may be sparse)."
