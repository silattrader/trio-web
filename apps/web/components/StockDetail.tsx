"use client";

import type { ModelId, StockResult } from "@/lib/api";
import { FactorRadar } from "./FactorRadar";
import { QuartileChip } from "./QuartileChip";

interface Props {
  stock: StockResult;
  modelId: ModelId;
  onClose: () => void;
}

const BAND_COLOR: Record<string, string> = {
  BUY: "text-blue-700",
  NEUTRAL: "text-amber-700",
  SELL: "text-red-700",
  "N/A": "text-slate-400",
};

export function StockDetail({ stock, modelId, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-30 flex items-start justify-center bg-slate-900/40 p-6">
      <div className="w-full max-w-3xl rounded-lg bg-white p-6 shadow-xl ring-1 ring-slate-200">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-ink">{stock.ticker}</h2>
              <QuartileChip rec={stock.recommendation} />
            </div>
            {stock.name && <p className="text-sm text-slate-500">{stock.name}</p>}
            {stock.final_score !== null && (
              <p className="mt-1 text-sm text-slate-700">
                Score: <span className="font-semibold">{stock.final_score.toFixed(2)}</span>
                {stock.quartile && ` · Quartile ${stock.quartile}`}
              </p>
            )}
            {stock.explanation && (
              <p className="mt-2 max-w-prose text-sm text-slate-600">{stock.explanation}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {(modelId === "bos" || modelId === "bos_flow" || modelId === "mla_v0") &&
          stock.factors.length > 0 && (
          <div className="mt-6 rounded-md border border-slate-200 bg-slate-50 p-4">
            <FactorRadar factors={stock.factors} />
          </div>
        )}

        <table className="mt-6 w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="py-2">Factor</th>
              <th>Raw</th>
              <th>Band</th>
              <th>Sub-score</th>
              <th>Weight</th>
              <th>Contribution</th>
            </tr>
          </thead>
          <tbody>
            {stock.factors.map((f) => (
              <tr key={f.id} className="border-t border-slate-100">
                <td className="py-2 font-medium text-slate-700">
                  {f.id} · {f.label}
                </td>
                <td>{f.raw === null ? "—" : f.raw.toFixed(2)}</td>
                <td className={BAND_COLOR[f.band]}>{f.band}</td>
                <td>{f.sub_score.toFixed(2)}</td>
                <td>{f.weight.toFixed(2)}</td>
                <td className="font-medium">{f.contribution.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {stock.flags.length > 0 && (
          <p className="mt-4 text-xs text-amber-700">
            Flags: {stock.flags.join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
