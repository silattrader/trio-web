import clsx from "clsx";
import type { Recommendation } from "@/lib/api";

const STYLES: Record<Recommendation, string> = {
  "BUY-BUY": "bg-q-buybuy text-white",
  BUY: "bg-q-buy text-white",
  SELL: "bg-q-sell text-white",
  "SELL-SELL": "bg-q-sellsell text-white",
  UNRANKED: "bg-slate-200 text-slate-700",
};

export function QuartileChip({ rec }: { rec: Recommendation }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        STYLES[rec]
      )}
    >
      {rec}
    </span>
  );
}
