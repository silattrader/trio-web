"use client";

import { useState } from "react";
import { score, type ModelId, type ScoreResponse } from "@/lib/api";
import { parseCsv } from "@/lib/csv";

interface Props {
  onResult: (
    resp: ScoreResponse,
    modelId: ModelId,
    rows: Record<string, unknown>[],
    universe: string,
  ) => void;
}

const SAMPLE_BOS: Record<string, unknown>[] = [
  { ticker: "MAYBANK MK", name: "Malayan Banking Bhd", vol_avg_3m: 2_000_000, target_return: 18, dvd_yld_ind: 6.4, altman_z: 3.1, analyst_sent: 4.4 },
  { ticker: "TENAGA MK",  name: "Tenaga Nasional",     vol_avg_3m: 800_000,   target_return: 12, dvd_yld_ind: 4.1, altman_z: 2.3, analyst_sent: 4.0 },
  { ticker: "AIRASIA MK", name: "AirAsia Group",       vol_avg_3m: 350_000,   target_return: -8, dvd_yld_ind: 0,   altman_z: 0.8, analyst_sent: 2.5 },
  { ticker: "GENM MK",    name: "Genting Malaysia",    vol_avg_3m: 500_000,   target_return: 5,  dvd_yld_ind: 3.2, altman_z: 1.6, analyst_sent: 3.4 },
  { ticker: "PCHEM MK",   name: "PETRONAS Chemicals",  vol_avg_3m: 1_100_000, target_return: 22, dvd_yld_ind: 5.0, altman_z: 4.2, analyst_sent: 4.5 },
  { ticker: "PBBANK MK",  name: "Public Bank",         vol_avg_3m: 1_400_000, target_return: 15, dvd_yld_ind: 4.5, altman_z: 2.7, analyst_sent: 4.3 },
  { ticker: "AMMB MK",    name: "AMMB Holdings",       vol_avg_3m: 280_000,   target_return: -2, dvd_yld_ind: 3.0, altman_z: 1.4, analyst_sent: 2.9 },
  { ticker: "SIME MK",    name: "Sime Darby",          vol_avg_3m: 600_000,   target_return: 10, dvd_yld_ind: 4.2, altman_z: 2.1, analyst_sent: 3.8 },
];

export function UploadCard({ onResult }: Props) {
  const [model, setModel] = useState<ModelId>("bos");
  const [universe, setUniverse] = useState("KLCI");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);

  async function runScore(rows: Record<string, unknown>[]) {
    setBusy(true);
    setError(null);
    try {
      const resp = await score(model, universe, rows);
      onResult(resp, model, rows, universe);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    const text = await file.text();
    const rows = parseCsv(text, model);
    if (rows.length === 0) {
      setError("CSV parsed to zero rows. Check headers and delimiter.");
      return;
    }
    await runScore(rows);
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h2 className="text-base font-semibold text-ink">1. Choose model & universe</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Model</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value as ModelId)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="bos">BOS — 5-Factor weighted</option>
            <option value="mos">MOS — Margin-of-Safety (Graham)</option>
            <option value="four_factor">4-Factor — Legacy 2019</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Universe label</span>
          <input
            type="text"
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="KLCI / SP500 / CSV"
          />
        </label>
      </div>

      <h2 className="mt-8 text-base font-semibold text-ink">2. Upload CSV</h2>
      <p className="mt-1 text-xs text-slate-500">
        Bloomberg-style headers (e.g. <code>VOLUME_AVG_3M</code>) are auto-mapped to
        canonical fields. Delimiter is auto-detected.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <label className="inline-flex cursor-pointer items-center rounded-md border border-trust bg-trust px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
          <input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} />
          {busy ? "Scoring…" : "Choose CSV file"}
        </label>
        <button
          type="button"
          onClick={() => runScore(SAMPLE_BOS)}
          disabled={busy || model !== "bos"}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          title={model !== "bos" ? "Sample data is BOS-only" : "Use built-in 8-stock KLCI sample"}
        >
          Try sample (BOS)
        </button>
        {filename && <span className="text-xs text-slate-500">{filename}</span>}
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}
    </section>
  );
}
