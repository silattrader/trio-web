"use client";

import { useState } from "react";
import {
  fetchUniverse,
  score,
  type ModelId,
  type ProviderId,
  type ScoreResponse,
} from "@/lib/api";

interface Props {
  onResult: (
    resp: ScoreResponse,
    modelId: ModelId,
    rows: Record<string, unknown>[],
    universe: string,
  ) => void;
}

const PRESETS: Record<ProviderId, string> = {
  yfinance: "AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, JPM",
  tradingview: "NASDAQ:AAPL, NASDAQ:MSFT, NASDAQ:NVDA, NYSE:JPM, MYX:1155",
  i3investor: "1155, 1023, 5347, 6012, 3182, 1295, 5168, 1066",
  bloomberg: "MAYBANK MK, CIMB MK, TENAGA MK, PCHEM MK",
};

export function LiveUniverseCard({ onResult }: Props) {
  const [model, setModel] = useState<ModelId>("bos");
  const [provider, setProvider] = useState<ProviderId>("yfinance");
  const [tickers, setTickers] = useState(PRESETS.yfinance);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  async function run() {
    const list = tickers
      .split(/[,\s]+/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (list.length === 0) {
      setError("Enter at least one ticker.");
      return;
    }
    setBusy(true);
    setError(null);
    setWarnings([]);
    try {
      const uni = await fetchUniverse(provider, list, model);
      setWarnings(uni.warnings);
      const resp = await score(model, uni.universe, uni.rows);
      onResult(resp, model, uni.rows, uni.universe);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onProviderChange(p: ProviderId) {
    setProvider(p);
    setTickers(PRESETS[p]);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-ink">Or fetch a live universe</h2>
        <span className="text-xs text-slate-500">
          yfinance: SP500 · tradingview: US+MY (unofficial) · i3investor: KLCI partial · bloomberg: stub
        </span>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Provider</span>
          <select
            value={provider}
            onChange={(e) => onProviderChange(e.target.value as ProviderId)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="yfinance">yfinance — Yahoo Finance (US)</option>
            <option value="tradingview">TradingView — Scanner (US + MY, unofficial)</option>
            <option value="i3investor">i3investor — KLSE (partial)</option>
            <option value="bloomberg">Bloomberg — credentials required</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Model</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value as ModelId)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="bos">BOS — 5-Factor</option>
            <option value="bos_flow">BOS-Flow — 7-Factor (BOS + flow)</option>
            <option value="mos">MOS — Margin-of-Safety</option>
            <option value="four_factor">4-Factor — Legacy</option>
            <option value="mla_v0">MLA v0 — Gradient-Boosted (preview)</option>
          </select>
        </label>
      </div>

      <label className="mt-4 block text-sm">
        <span className="block font-medium text-slate-700">
          Tickers <span className="font-normal text-slate-500">(comma- or space-separated)</span>
        </span>
        <textarea
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          rows={2}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm"
        />
      </label>

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="rounded-md border border-trust bg-trust px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Fetching & scoring…" : "Fetch & score"}
        </button>
        {provider === "i3investor" && (
          <span className="text-xs text-amber-700">
            Politeness sleep: 5 s between tickers
          </span>
        )}
      </div>

      {warnings.length > 0 && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <strong className="mr-1">Provider warnings:</strong>
          <ul className="ml-4 list-disc">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}
    </section>
  );
}
