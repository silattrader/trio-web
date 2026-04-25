"use client";

import { useEffect, useRef, useState } from "react";
import {
  CANONICAL_BOS_WEIGHTS,
  score,
  type BosWeights,
  type ScoreResponse,
} from "@/lib/api";

interface Props {
  rows: Record<string, unknown>[];
  universe: string;
  onRescore: (resp: ScoreResponse) => void;
}

const FACTORS: { key: keyof BosWeights; label: string; hint: string }[] = [
  { key: "f1_volume",      label: "F1 — Volume Avg 3M",     hint: "Liquidity floor" },
  { key: "f2_target",      label: "F2 — Target Return %",   hint: "Analyst upside" },
  { key: "f3_dvd_yld",     label: "F3 — Dividend Yield %",  hint: "Income tilt" },
  { key: "f4_altman_z",    label: "F4 — Altman Z-Score",    hint: "Bankruptcy risk" },
  { key: "f5_analyst_sent", label: "F5 — Analyst Sentiment", hint: "Consensus call" },
];

function normalise(w: BosWeights): BosWeights {
  const total =
    w.f1_volume + w.f2_target + w.f3_dvd_yld + w.f4_altman_z + w.f5_analyst_sent;
  if (total <= 0) return { ...CANONICAL_BOS_WEIGHTS };
  return {
    f1_volume: w.f1_volume / total,
    f2_target: w.f2_target / total,
    f3_dvd_yld: w.f3_dvd_yld / total,
    f4_altman_z: w.f4_altman_z / total,
    f5_analyst_sent: w.f5_analyst_sent / total,
  };
}

export function WeightSliders({ rows, universe, onRescore }: Props) {
  const [weights, setWeights] = useState<BosWeights>({ ...CANONICAL_BOS_WEIGHTS });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCanonical =
    JSON.stringify(weights) === JSON.stringify(CANONICAL_BOS_WEIGHTS);

  useEffect(() => {
    if (isCanonical) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const resp = await score("bos", universe, rows, { bosWeights: weights });
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
  }, [weights, rows, universe, onRescore, isCanonical]);

  const normalised = normalise(weights);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-ink">
          Tune factor weights <span className="font-normal text-slate-500">(BOS only)</span>
        </h2>
        <button
          type="button"
          onClick={async () => {
            setWeights({ ...CANONICAL_BOS_WEIGHTS });
            setBusy(true);
            setError(null);
            try {
              const resp = await score("bos", universe, rows);
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
        always sum to 100%. {busy && <span className="ml-1 text-trust">Re-scoring…</span>}
      </p>

      <div className="mt-4 space-y-3">
        {FACTORS.map((f) => {
          const raw = weights[f.key];
          const pct = normalised[f.key] * 100;
          return (
            <div key={f.key}>
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
                  setWeights((w) => ({ ...w, [f.key]: Number(e.target.value) }))
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
