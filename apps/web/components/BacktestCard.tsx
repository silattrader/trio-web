"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from "recharts";
import {
  backtest,
  type BacktestResponse,
  type ModelId,
  type StrategyId,
} from "@/lib/api";

const STRATEGIES: { id: StrategyId; label: string; blurb: string }[] = [
  { id: "sma", label: "SMA crossover (price-only)", blurb: "Fast/slow moving-average crossover. No fundamentals → no lookahead bias." },
  { id: "rba_snapshot", label: "RBA snapshot (lookahead-flagged)", blurb: "Top-N by today's RBA score, equal-weight, periodic rebalance. Demo-only — uses today's fundamentals against historical prices." },
];

function fmtPct(x: number): string {
  return `${(x * 100).toFixed(2)}%`;
}

function fmtSigned(x: number): string {
  return `${x >= 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;
}

export interface BacktestCardHandle {
  prefillAndScroll: (tickers: string[], modelHint?: ModelId) => void;
}

export const BacktestCard = forwardRef<BacktestCardHandle, object>(function BacktestCard(_, ref) {
  const [strategy, setStrategy] = useState<StrategyId>("sma");
  const [tickers, setTickers] = useState("AAPL, MSFT, NVDA, GOOGL, AMZN, JPM, JNJ, XOM");
  const [start, setStart] = useState("2020-01-02");
  const [end, setEnd] = useState("2024-12-31");
  const [fast, setFast] = useState(50);
  const [slow, setSlow] = useState(200);
  const [model, setModel] = useState<ModelId>("bos");
  const [topN, setTopN] = useState(3);
  const [rebal, setRebal] = useState(21);
  const [feeBps, setFeeBps] = useState(5);

  const [busy, setBusy] = useState(false);
  const [resp, setResp] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLElement>(null);

  useImperativeHandle(ref, () => ({
    prefillAndScroll: (newTickers, modelHint) => {
      setTickers(newTickers.join(", "));
      if (modelHint) setModel(modelHint);
      setStrategy("rba_snapshot");
      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  }));

  useEffect(() => {
    setResp(null);
  }, [strategy, model]);

  async function run() {
    const list = tickers.split(/[,\s]+/).map((t) => t.trim()).filter(Boolean);
    if (list.length === 0) {
      setError("Enter at least one ticker.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await backtest(strategy, {
        tickers: list,
        start,
        end,
        fast,
        slow,
        model,
        top_n: topN,
        rebalance_days: rebal,
        fee_bps: feeBps,
      });
      setResp(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const stratMeta = STRATEGIES.find((s) => s.id === strategy)!;

  return (
    <section ref={cardRef} className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-ink">4. Backtest</h2>
        <span className="text-xs text-slate-500">P4 · pure-price + RBA-snapshot</span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm sm:col-span-2">
          <span className="block font-medium text-slate-700">Strategy</span>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as StrategyId)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {STRATEGIES.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-slate-500">{stratMeta.blurb}</span>
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Start</span>
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">End</span>
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
      </div>

      <label className="mt-4 block text-sm">
        <span className="block font-medium text-slate-700">
          Tickers <span className="font-normal text-slate-500">(yfinance symbols)</span>
        </span>
        <textarea
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          rows={2}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
        />
      </label>

      {strategy === "sma" ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <NumField label="Fast SMA" value={fast} setValue={setFast} min={2} max={200} />
          <NumField label="Slow SMA" value={slow} setValue={setSlow} min={5} max={400} />
          <NumField label="Fee (bps)" value={feeBps} setValue={setFeeBps} min={0} max={100} />
        </div>
      ) : (
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          <label className="text-sm">
            <span className="block font-medium text-slate-700">Model</span>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value as ModelId)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="bos">BOS</option>
              <option value="mos">MOS</option>
              <option value="four_factor">4-Factor</option>
            </select>
          </label>
          <NumField label="Top N" value={topN} setValue={setTopN} min={1} max={20} />
          <NumField label="Rebal (days)" value={rebal} setValue={setRebal} min={1} max={252} />
          <NumField label="Fee (bps)" value={feeBps} setValue={setFeeBps} min={0} max={100} />
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="rounded-md border border-trust bg-trust px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Backtesting…" : "Run backtest"}
        </button>
        <span className="text-xs text-slate-500">Live data via yfinance — initial run may take ~10 s.</span>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}

      {resp && (
        <div className="mt-6 space-y-4">
          {resp.warnings.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <strong className="mr-1">Backtest notes:</strong>
              <ul className="ml-4 list-disc">
                {resp.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Total return" v={fmtSigned(resp.metrics.total_return)} bench={resp.benchmark_metrics ? fmtSigned(resp.benchmark_metrics.total_return) : null} />
            <Stat label="CAGR" v={fmtSigned(resp.metrics.cagr)} bench={resp.benchmark_metrics ? fmtSigned(resp.benchmark_metrics.cagr) : null} />
            <Stat label="Sharpe" v={resp.metrics.sharpe.toFixed(2)} bench={resp.benchmark_metrics?.sharpe.toFixed(2) ?? null} />
            <Stat label="Max DD" v={fmtPct(resp.metrics.max_drawdown)} bench={resp.benchmark_metrics ? fmtPct(resp.benchmark_metrics.max_drawdown) : null} />
          </div>

          <div className="h-72 rounded-md border border-slate-200 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={resp.equity_curve} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" name="Strategy" stroke="#1d4ed8" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="benchmark" name="Equal-weight buy & hold" stroke="#94a3b8" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
});

function NumField({ label, value, setValue, min, max }: { label: string; value: number; setValue: (v: number) => void; min: number; max: number }) {
  return (
    <label className="text-sm">
      <span className="block font-medium text-slate-700">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(e) => setValue(Number(e.target.value))}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />
    </label>
  );
}

function Stat({ label, v, bench }: { label: string; v: string; bench: string | null }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-base font-semibold text-ink">{v}</div>
      {bench && <div className="text-xs text-slate-400">B&H: {bench}</div>}
    </div>
  );
}
