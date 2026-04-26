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
  walkForward,
  type BacktestResponse,
  type ModelId,
  type StrategyId,
  type WalkForwardResponse,
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
  const [wfResp, setWfResp] = useState<WalkForwardResponse | null>(null);
  const [walkForwardOn, setWalkForwardOn] = useState(false);
  const [nWindows, setNWindows] = useState(4);
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
    setWfResp(null);
  }, [strategy, model]);

  async function run() {
    const list = tickers.split(/[,\s]+/).map((t) => t.trim()).filter(Boolean);
    if (list.length === 0) {
      setError("Enter at least one ticker.");
      return;
    }
    setBusy(true);
    setError(null);
    const body = {
      tickers: list,
      start,
      end,
      fast,
      slow,
      model,
      top_n: topN,
      rebalance_days: rebal,
      fee_bps: feeBps,
    };
    try {
      if (walkForwardOn) {
        const w = await walkForward(strategy, nWindows, body);
        setWfResp(w);
        setResp(null);
      } else {
        const r = await backtest(strategy, body);
        setResp(r);
        setWfResp(null);
      }
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

      <div className="mt-4 flex flex-wrap items-center gap-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={walkForwardOn}
            onChange={(e) => setWalkForwardOn(e.target.checked)}
            className="h-4 w-4 accent-trust"
          />
          <span className="font-medium text-slate-700">Walk-forward</span>
          <span className="text-xs text-slate-500">
            Split the range into N non-overlapping windows — checks consistency, not luck.
          </span>
        </label>
        {walkForwardOn && (
          <label className="inline-flex items-center gap-2 text-sm">
            <span className="text-slate-700">N windows</span>
            <input
              type="number"
              min={2}
              max={12}
              value={nWindows}
              onChange={(e) => setNWindows(Number(e.target.value))}
              className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
        )}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="rounded-md border border-trust bg-trust px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? (walkForwardOn ? "Walk-forward running…" : "Backtesting…") : (walkForwardOn ? "Run walk-forward" : "Run backtest")}
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

      {wfResp && (
        <div className="mt-6 space-y-4">
          {wfResp.warnings.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <strong className="mr-1">Walk-forward notes:</strong>
              <ul className="ml-4 list-disc">
                {wfResp.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat label="Windows" v={String(wfResp.aggregate.n_windows)} bench={null} />
            <Stat label="Mean Sharpe" v={wfResp.aggregate.mean_sharpe.toFixed(2)} bench={null} />
            <Stat label="Median return" v={fmtSigned(wfResp.aggregate.median_total_return)} bench={null} />
            <Stat label="Beat B&H" v={`${(wfResp.aggregate.pct_windows_beating_benchmark * 100).toFixed(0)}%`} bench={null} />
            <Stat label="Positive" v={`${(wfResp.aggregate.pct_windows_positive * 100).toFixed(0)}%`} bench={null} />
          </div>

          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Window</th>
                  <th className="px-3 py-2 text-left">Range</th>
                  <th className="px-3 py-2 text-right">Strategy</th>
                  <th className="px-3 py-2 text-right">B&amp;H</th>
                  <th className="px-3 py-2 text-right">Sharpe</th>
                  <th className="px-3 py-2 text-right">Max DD</th>
                  <th className="px-3 py-2 text-center">Beat?</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {wfResp.windows.map((w) => (
                  <tr key={w.index}>
                    <td className="px-3 py-2 font-medium text-slate-700">#{w.index + 1}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{w.start} → {w.end}</td>
                    <td className={`px-3 py-2 text-right tabular-nums ${w.metrics.total_return >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                      {fmtSigned(w.metrics.total_return)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                      {w.benchmark_metrics ? fmtSigned(w.benchmark_metrics.total_return) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{w.metrics.sharpe.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-500">{fmtPct(w.metrics.max_drawdown)}</td>
                    <td className="px-3 py-2 text-center">
                      {w.beat_benchmark ? <span className="text-emerald-700">✓</span> : <span className="text-slate-400">·</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
