"use client";

import { useRef, useState } from "react";
import type { ModelId, ScoreResponse, StockResult } from "@/lib/api";
import { UploadCard } from "@/components/UploadCard";
import { LiveUniverseCard } from "@/components/LiveUniverseCard";
import { ResultsTable } from "@/components/ResultsTable";
import { StockDetail } from "@/components/StockDetail";
import { BacktestCard, type BacktestCardHandle } from "@/components/BacktestCard";
import { WeightSliders } from "@/components/WeightSliders";

export default function Home() {
  const [resp, setResp] = useState<ScoreResponse | null>(null);
  const [modelId, setModelId] = useState<ModelId>("bos");
  const [picked, setPicked] = useState<StockResult | null>(null);
  const [lastRows, setLastRows] = useState<Record<string, unknown>[]>([]);
  const [lastUniverse, setLastUniverse] = useState<string>("CSV");
  const backtestRef = useRef<BacktestCardHandle>(null);

  const handleResult = (
    r: ScoreResponse,
    m: ModelId,
    rows: Record<string, unknown>[],
    universe: string,
  ) => {
    setResp(r);
    setModelId(m);
    setLastRows(rows);
    setLastUniverse(universe);
    setPicked(null);
  };

  return (
    <div className="space-y-8">
      <div className="grid gap-6 lg:grid-cols-2">
        <UploadCard onResult={handleResult} />
        <LiveUniverseCard onResult={handleResult} />
      </div>

      {resp && (modelId === "bos" || modelId === "bos_flow") && lastRows.length > 0 && (
        <WeightSliders
          rows={lastRows}
          universe={lastUniverse}
          modelId={modelId}
          onRescore={(r) => {
            setResp(r);
            setPicked(null);
          }}
        />
      )}

      {resp && (
        <section>
          <h2 className="mb-3 text-base font-semibold text-ink">3. Ranked watchlist</h2>
          <ResultsTable
            resp={resp}
            onPick={setPicked}
            onBacktestTopN={(tickers) => backtestRef.current?.prefillAndScroll(tickers, modelId)}
          />
        </section>
      )}

      {picked && (
        <StockDetail stock={picked} modelId={modelId} onClose={() => setPicked(null)} />
      )}

      <BacktestCard ref={backtestRef} />
    </div>
  );
}
