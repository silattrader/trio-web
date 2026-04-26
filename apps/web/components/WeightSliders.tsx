"use client";

import { useEffect, useRef, useState } from "react";
import {
  CANONICAL_BOS_FLOW_WEIGHTS,
  CANONICAL_BOS_WEIGHTS,
  score,
  type BosFlowWeights,
  type BosWeights,
  type ModelId,
  type ScoreResponse,
} from "@/lib/api";

interface Props {
  rows: Record<string, unknown>[];
  universe: string;
  modelId: ModelId;     // "bos" or "bos_flow"
  onRescore: (resp: ScoreResponse) => void;
}

const BOS_FACTORS: { key: keyof BosWeights; label: string; hint: string }[] = [
  { key: "f1_volume",       label: "F1 — Volume Avg 3M",     hint: "Liquidity floor" },
  { key: "f2_target",       label: "F2 — Target Return %",   hint: "Analyst upside" },
  { key: "f3_dvd_yld",      label: "F3 — Dividend Yield %",  hint: "Income tilt" },
  { key: "f4_altman_z",     label: "F4 — Altman Z-Score",    hint: "Bankruptcy risk" },
  { key: "f5_analyst_sent", label: "F5 — Analyst Sentiment", hint: "Consensus call" },
];

const FLOW_FACTORS: { key: keyof BosFlowWeights; label: string; hint: string }[] = [
  ...BOS_FACTORS,
  { key: "f6_insider_flow", label: "F6 — Insider Flow",      hint: "Form 4 net buying" },
  { key: "f7_retail_flow",  label: "F7 — Retail Flow",       hint: "Wikipedia attention (contrarian)" },
];

function sumWeights(w: Record<string, number>): number {
  return Object.values(w).reduce((acc, v) => acc + v, 0);
}

function normalise<T extends Record<string, number>>(w: T, fallback: T): T {
  const total = sumWeights(w);
  if (total <= 0) return { ...fallback };
  const out: Record<string, number> = {};
  for (const k of Object.keys(w)) out[k] = w[k] / total;
  return out as T;
}

export function WeightSliders({ rows, universe, modelId, onRescore }: Props) {
  const isFlow = modelId === "bos_flow";
  const canonical = isFlow ? CANONICAL_BOS_FLOW_WEIGHTS : CANONICAL_BOS_WEIGHTS;
  const factors = isFlow ? FLOW_FACTORS : BOS_FACTORS;

  const [weights, setWeights] = useState<Record<string, number>>({ ...canonical });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset weights to the model's canonical defaults when the model changes.
  useEffect(() => {
    setWeights({ ...canonical });
  }, [modelId]); // eslint-disable-line react-hooks/exhaustive-deps

  const isCanonical = JSON.stringify(weights) === JSON.stringify(canonical);

  useEffect(() => {
    if (isCanonical) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const opts = isFlow
          ? { bosFlowWeights: weights as unknown as BosFlowWeights }
          : { bosWeights: weights as unknown as BosWeights };
        const resp = await score(modelId, universe, rows, opts);
        onRescore(resp);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    }, 350);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [weights, rows, universe, onRescore, isCanonical, isFlow, modelId]);

  const normalised = normalise(weights, canonical as unknown as Record<string, number>);
  const label = isFlow ? "BOS-Flow (7 factors)" : "BOS (5 factors)";

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-ink">
          Tune factor weights{" "}
          <span className="font-normal text-slate-500">— {label}</span>
        </h2>
        <button
          type="button"
          onClick={async () => {
            setWeights({ ...canonical });
            setBusy(true);
            setError(null);
            try {
              const resp = await score(modelId, universe, rows);
              onRescore(resp);
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
          disabled={busy || isCanonical}
          className="rounded-md border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Reset to canonical
        </button>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Drag any slider to re-weight the engine. Raw values are normalised so they
        always sum to 100%.{" "}
        {busy && <span className="ml-1 text-trust">Re-scoring…</span>}
      </p>

      <div className="mt-4 space-y-3">
        {factors.map((f) => {
          const raw = weights[f.key as string] ?? 0;
          const pct = (normalised[f.key as string] ?? 0) * 100;
          return (
            <div key={f.key as string}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-medium text-slate-700">
                  {f.label}{" "}
                  <span className="font-normal text-slate-400">— {f.hint}</span>
                </span>
                <span className="font-mono tabular-nums text-slate-600">
                  {pct.toFixed(1)}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={raw}
                onChange={(e) =>
                  setWeights((w) => ({ ...w, [f.key as string]: Number(e.target.value) }))
                }
                className="mt-1 w-full accent-trust"
              />
            </div>
          );
        })}
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}
    </section>
  );
}
