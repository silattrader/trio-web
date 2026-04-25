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

export function FactorRadar({ factors }: { factors: FactorBreakdown[] }) {
  const data = factors.map((f) => ({ factor: f.label, score: f.sub_score }));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="75%">
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
          <Radar
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
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
