"use client";

import { useMemo, useState } from "react";
import type { ScoreResponse, StockResult } from "@/lib/api";
import { QuartileChip } from "./QuartileChip";

interface Props {
  resp: ScoreResponse;
  onPick: (s: StockResult) => void;
  onBacktestTopN?: (tickers: string[]) => void;
}

export function ResultsTable({ resp, onPick, onBacktestTopN }: Props) {
  const [filter, setFilter] = useState("");
  const [quartileFilter, setQuartileFilter] = useState<string>("");

  const rows = useMemo(() => {
    return resp.results
      .filter((r) => {
        if (filter && !r.ticker.toLowerCase().includes(filter.toLowerCase())) {
          return r.name?.toLowerCase().includes(filter.toLowerCase()) ?? false;
        }
        return true;
      })
      .filter((r) => !quartileFilter || String(r.quartile ?? "") === quartileFilter)
      .sort((a, b) => {
        // Higher score first; nulls last
        if (a.final_score === null) return 1;
        if (b.final_score === null) return -1;
        return b.final_score - a.final_score;
      });
  }, [resp, filter, quartileFilter]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
        <input
          type="text"
          placeholder="Filter by ticker or name…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
        <select
          value={quartileFilter}
          onChange={(e) => setQuartileFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        >
          <option value="">All quartiles</option>
          <option value="1">Q1 — BUY-BUY</option>
          <option value="2">Q2 — BUY</option>
          <option value="3">Q3 — SELL</option>
          <option value="4">Q4 — SELL-SELL</option>
        </select>
        {onBacktestTopN && rows.length >= 1 && (
          <button
            type="button"
            onClick={() =>
              onBacktestTopN(
                rows
                  .filter((r) => r.final_score !== null)
                  .slice(0, Math.min(5, rows.length))
                  .map((r) => r.ticker)
              )
            }
            className="rounded-md border border-trust px-3 py-1.5 text-xs font-medium text-trust hover:bg-blue-50"
          >
            Backtest top {Math.min(5, rows.filter((r) => r.final_score !== null).length)} ↓
          </button>
        )}
        <span className="ml-auto text-xs text-slate-500">
          {resp.n_scored}/{resp.n_rows} scored · {resp.model_version} ·{" "}
          {new Date(resp.as_of).toLocaleString()}
        </span>
      </div>

      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Ticker</th>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2">Score</th>
            <th className="px-4 py-2">Recommendation</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                No rows match.
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr
              key={r.ticker}
              onClick={() => onPick(r)}
              className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
            >
              <td className="px-4 py-2 font-medium text-ink">{r.ticker}</td>
              <td className="px-4 py-2 text-slate-600">{r.name ?? "—"}</td>
              <td className="px-4 py-2 tabular-nums">
                {r.final_score === null ? "—" : r.final_score.toFixed(2)}
              </td>
              <td className="px-4 py-2">
                <QuartileChip rec={r.recommendation} />
              </td>
              <td className="px-4 py-2 text-right text-xs text-trust">View →</td>
            </tr>
          ))}
        </tbody>
      </table>

      {resp.warnings.length > 0 && (
        <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          {resp.warnings.join(" · ")}
        </div>
      )}
    </div>
  );
}
