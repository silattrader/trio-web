// Mirror of packages/algorithms/trio_algorithms/contracts.py — keep in sync.

import { keyHeaders } from "./keys";

/** Inject BYOK headers into a fetch init. */
function withKeys(init: RequestInit = {}): RequestInit {
  const userHeaders = keyHeaders();
  return {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...userHeaders,
    },
  };
}

export type Recommendation =
  | "BUY-BUY"
  | "BUY"
  | "SELL"
  | "SELL-SELL"
  | "UNRANKED";

export type Band = "BUY" | "NEUTRAL" | "SELL" | "N/A";

export interface FactorBreakdown {
  id: string;
  label: string;
  raw: number | null;
  band: Band;
  sub_score: number;
  weight: number;
  contribution: number;
  flags: string[];
}

export interface StockResult {
  ticker: string;
  name: string | null;
  final_score: number | null;
  quartile: number | null;
  recommendation: Recommendation;
  factors: FactorBreakdown[];
  explanation: string | null;
  flags: string[];
}

export interface ScoreResponse {
  model_version: string;
  as_of: string;
  universe: string;
  n_rows: number;
  n_scored: number;
  results: StockResult[];
  warnings: string[];
}

export type ModelId = "bos" | "bos_flow" | "mos" | "four_factor" | "mla_v0";

export interface BosWeights {
  f1_volume: number;
  f2_target: number;
  f3_dvd_yld: number;
  f4_altman_z: number;
  f5_analyst_sent: number;
}

export const CANONICAL_BOS_WEIGHTS: BosWeights = {
  f1_volume: 0.20,
  f2_target: 0.20,
  f3_dvd_yld: 0.20,
  f4_altman_z: 0.30,
  f5_analyst_sent: 0.10,
};

export interface BosFlowWeights {
  f1_volume: number;
  f2_target: number;
  f3_dvd_yld: number;
  f4_altman_z: number;
  f5_analyst_sent: number;
  f6_insider_flow: number;
  f7_retail_flow: number;
}

export const CANONICAL_BOS_FLOW_WEIGHTS: BosFlowWeights = {
  f1_volume: 0.15,
  f2_target: 0.15,
  f3_dvd_yld: 0.15,
  f4_altman_z: 0.20,
  f5_analyst_sent: 0.10,
  f6_insider_flow: 0.15,
  f7_retail_flow: 0.10,
};

export type ProviderId = "yfinance" | "tradingview" | "i3investor" | "bloomberg";

export interface UniverseResponse {
  provider: string;
  universe: string;
  rows: Record<string, unknown>[];
  warnings: string[];
  coverage: string[];
}

export async function fetchUniverse(
  provider: ProviderId,
  tickers: string[],
  model: ModelId
): Promise<UniverseResponse> {
  const res = await fetch(`/api/universe/${provider}?model=${model}`, withKeys({
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tickers }),
  }));
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Provider ${provider} ${res.status}: ${text}`);
  }
  return res.json();
}

export type StrategyId = "sma" | "rba_snapshot" | "rba_pit";

export interface EquityPoint {
  date: string;
  value: number;
  benchmark: number | null;
}

export interface BacktestMetrics {
  cagr: number;
  sharpe: number;
  max_drawdown: number;
  total_return: number;
  n_trades: number;
  win_rate: number | null;
}

export interface BacktestResponse {
  strategy: StrategyId;
  universe_size: number;
  start: string;
  end: string;
  equity_curve: EquityPoint[];
  metrics: BacktestMetrics;
  benchmark_metrics: BacktestMetrics | null;
  warnings: string[];
}

export interface BacktestRequest {
  tickers: string[];
  start: string;
  end: string;
  initial_capital?: number;
  fast?: number;
  slow?: number;
  model?: ModelId;
  top_n?: number;
  rebalance_days?: number;
  fee_bps?: number;
}

export async function backtest(
  strategy: StrategyId,
  body: BacktestRequest
): Promise<BacktestResponse> {
  const res = await fetch(`/api/backtest?strategy=${strategy}`, withKeys({
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }));
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Backtest ${res.status}: ${text}`);
  }
  return res.json();
}

export interface WalkForwardWindow {
  index: number;
  start: string;
  end: string;
  metrics: BacktestMetrics;
  benchmark_metrics: BacktestMetrics | null;
  beat_benchmark: boolean;
}

export interface WalkForwardAggregate {
  n_windows: number;
  mean_sharpe: number;
  median_total_return: number;
  total_return_std: number;
  pct_windows_beating_benchmark: number;
  pct_windows_positive: number;
}

export interface WalkForwardResponse {
  strategy: StrategyId;
  universe_size: number;
  start: string;
  end: string;
  windows: WalkForwardWindow[];
  aggregate: WalkForwardAggregate;
  warnings: string[];
}

export async function walkForward(
  strategy: StrategyId,
  nWindows: number,
  body: BacktestRequest
): Promise<WalkForwardResponse> {
  const res = await fetch(
    `/api/backtest/walk_forward?strategy=${strategy}&n_windows=${nWindows}`,
    withKeys({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Walk-forward ${res.status}: ${text}`);
  }
  return res.json();
}

export async function score(
  model: ModelId,
  universe: string,
  rows: Record<string, unknown>[],
  opts: {
    legacy?: boolean;
    bosWeights?: BosWeights;
    bosFlowWeights?: BosFlowWeights;
  } = {}
): Promise<ScoreResponse> {
  const qs = new URLSearchParams({ model });
  if (opts.legacy) qs.set("legacy", "true");

  const body: Record<string, unknown> = { universe, rows };
  if (opts.bosWeights && model === "bos") body.bos_weights = opts.bosWeights;
  if (opts.bosFlowWeights && model === "bos_flow")
    body.bos_flow_weights = opts.bosFlowWeights;

  const res = await fetch(`/api/score?${qs.toString()}`, withKeys({
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }));
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}
