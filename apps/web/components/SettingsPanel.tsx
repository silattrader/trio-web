"use client";

import { useEffect, useState } from "react";
import {
  EMPTY_KEYS,
  clearKeys,
  coverageFromKeys,
  hasAnyKey,
  loadKeys,
  saveKeys,
  type UserKeys,
} from "@/lib/keys";

const PROVIDER_LINKS = {
  // Affiliate slot — replace with your FMP affiliate URL once registered.
  // For now: plain referral link.
  fmp: {
    href: "https://site.financialmodelingprep.com/developer/docs/pricing?ref=trio-web",
    label: "Get a free FMP API key",
    note: "250 requests/day on the free tier — enough for live scoring of a small universe.",
  },
  sec: {
    href: "https://www.sec.gov/about/contact",
    label: "SEC EDGAR usage policy",
    note: "Free, no key. Just provide a contact email per SEC's user-agent rule.",
  },
  wiki: {
    href: "https://wikitech.wikimedia.org/wiki/Robot_policy",
    label: "Wikimedia user-agent policy",
    note: "Free, no key. Provide a contact email so they can throttle bad clients without blocking you.",
  },
};

export function SettingsPanel() {
  const [open, setOpen] = useState(false);
  const [keys, setKeys] = useState<UserKeys>(EMPTY_KEYS);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setKeys(loadKeys());
  }, []);

  const live = hasAnyKey(keys);
  const cov = coverageFromKeys(keys);

  const update = (patch: Partial<UserKeys>) => {
    setKeys((k) => ({ ...k, ...patch }));
    setDirty(true);
  };

  const onSave = () => {
    saveKeys(keys);
    setDirty(false);
  };

  const onClear = () => {
    clearKeys();
    setKeys(EMPTY_KEYS);
    setDirty(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={
          "rounded-md border px-3 py-1.5 text-xs font-medium " +
          (live
            ? "border-emerald-300 bg-emerald-50 text-emerald-800"
            : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50")
        }
      >
        {live ? "BYOK live" : "BYOK • demo mode"}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-40 mt-2 w-[28rem] rounded-lg border border-slate-200 bg-white p-5 shadow-xl ring-1 ring-slate-200">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold text-ink">
              Bring-your-own-keys
            </h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-slate-400 hover:text-slate-700"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <p className="mt-1 text-xs text-slate-500">
            TRIO calls third-party data providers <em>as you</em>. Keys live
            only in your browser (localStorage), are sent on each request as
            HTTP headers, and never persist on our server.
          </p>

          <div className="mt-4 space-y-4">
            <KeyField
              label="SEC EDGAR contact email"
              hint="Required by SEC. Any email works (e.g. you@example.com)."
              link={PROVIDER_LINKS.sec}
              value={keys.sec_ua}
              onChange={(v) => update({ sec_ua: v })}
              placeholder="Mailto you@example.com"
              filled={Boolean(keys.sec_ua)}
            />
            <KeyField
              label="Financial Modeling Prep API key"
              hint={PROVIDER_LINKS.fmp.note}
              link={PROVIDER_LINKS.fmp}
              value={keys.fmp_key}
              onChange={(v) => update({ fmp_key: v })}
              placeholder="sk_..."
              filled={Boolean(keys.fmp_key)}
              type="password"
            />
            <KeyField
              label="Wikimedia contact email"
              hint="Used for retail-attention factor (Wikipedia pageviews)."
              link={PROVIDER_LINKS.wiki}
              value={keys.wiki_ua}
              onChange={(v) => update({ wiki_ua: v })}
              placeholder="Mailto you@example.com"
              filled={Boolean(keys.wiki_ua)}
            />
          </div>

          <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
            <div className="mb-1 font-medium text-slate-700">
              Factor coverage with current keys
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600">
              <Coverage label="Volume Avg 3M" on={cov.vol_avg_3m} />
              <Coverage label="Altman-Z (EDGAR)" on={cov.altman_z} />
              <Coverage label="Dividend Yield (EDGAR)" on={cov.dvd_yld_ind} />
              <Coverage label="Insider Flow (Form 4)" on={cov.insider_flow} />
              <Coverage label="Target Return (FMP)" on={cov.target_return} />
              <Coverage label="Analyst Sentiment (FMP)" on={cov.analyst_sent} />
              <Coverage label="Retail Flow (Wiki)" on={cov.retail_flow} />
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={onSave}
              disabled={!dirty}
              className="rounded-md border border-trust bg-trust px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-40"
            >
              {dirty ? "Save keys" : "Saved"}
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Clear all
            </button>
            <span className="ml-auto text-[11px] text-slate-400">
              Stored: localStorage only · Not synced
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function Coverage({ label, on }: { label: string; on: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        aria-hidden
        className={
          "inline-block h-1.5 w-1.5 rounded-full " +
          (on ? "bg-emerald-500" : "bg-slate-300")
        }
      />
      <span className={on ? "text-slate-700" : "text-slate-400"}>{label}</span>
    </div>
  );
}

interface KeyFieldProps {
  label: string;
  hint: string;
  link: { href: string; label: string };
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  filled: boolean;
  type?: "text" | "password";
}

function KeyField({
  label,
  hint,
  link,
  value,
  onChange,
  placeholder,
  filled,
  type = "text",
}: KeyFieldProps) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label className="text-xs font-medium text-slate-700">
          {label}
          {filled && (
            <span className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 align-middle" />
          )}
        </label>
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer sponsored"
          className="text-[11px] font-medium text-trust hover:underline"
        >
          {link.label} ↗
        </a>
      </div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
        spellCheck={false}
        autoComplete="off"
      />
      <p className="mt-1 text-[11px] text-slate-500">{hint}</p>
    </div>
  );
}
