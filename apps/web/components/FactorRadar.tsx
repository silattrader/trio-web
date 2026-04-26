"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { FactorBreakdown } from "@/lib/api";

// Short axis labels — full ones overflow when 7 axes are crammed in.
const SHORT_LABELS: Record<string, string> = {
  "Volume Avg 3M": "Volume",
  "Target Return %": "Target",
  "Dividend Yield %": "Yield",
  "Altman Z-Score": "Altman-Z",
  "Analyst Sentiment": "Analyst",
  "Insider Flow": "Insider",
  "Retail Flow": "Retail",
};

function shortLabel(label: string): string {
  return SHORT_LABELS[label] ?? label;
}

export function FactorRadar({ factors }: { factors: FactorBreakdown[] }) {
  // Two series so we can dim missing factors without changing the polygon shape.
  const data = factors.map((f) => {
    const isMissing = f.flags.includes("missing");
    return {
      factor: shortLabel(f.label),
      score: isMissing ? 0 : f.sub_score,
      missing: isMissing ? 3 : 0,
      raw: f.raw,
      band: f.band,
    };
  });
  const anyMissing = data.some((d) => d.missing > 0);

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis
            dataKey="factor"
            tick={{ fill: "#475569", fontSize: 11 }}
          />
          <PolarRadiusAxis
            domain={[0, 3]}
            tickCount={4}
            tick={{ fill: "#94a3b8", fontSize: 10 }}
          />
          {/* Faint backdrop for missing factors, so the asymmetric polygon
              doesn't look like a real signal. */}
          {anyMissing && (
            <Radar
              name="missing"
              dataKey="missing"
              stroke="#cbd5e1"
              fill="#cbd5e1"
              fillOpacity={0.15}
              strokeDasharray="3 3"
            />
          )}
          <Radar
            name="score"
            dataKey="score"
            stroke="#1d4ed8"
            fill="#1d4ed8"
            fillOpacity={0.35}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#fff",
              borderRadius: 6,
              borderColor: "#cbd5e1",
              fontSize: 12,
            }}
            formatter={(_value, _name, ctx) => {
              const p = (ctx?.payload ?? {}) as Record<string, unknown>;
              const raw = p.raw as number | null | undefined;
              const band = p.band as string | undefined;
              const score = p.score as number | undefined;
              const rawStr = raw == null ? "n/a" : raw.toFixed(2);
              const scoreStr = score == null ? "—" : score.toFixed(2);
              return [`${scoreStr} (raw ${rawStr}, ${band})`, "factor"];
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
      {anyMissing && (
        <p className="mt-1 text-center text-[11px] text-slate-400">
          Dashed area = factor data missing for this row.
        </p>
      )}
    </div>
  );
}
