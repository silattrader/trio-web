"use client";

import { useEffect, useState } from "react";
import { hasAnyKey, loadKeys } from "@/lib/keys";

/** Top-of-page banner that adapts based on whether the user has set keys.
 *
 * Anonymous (demo mode): explain BYOK + audience framing.
 * Live mode: brief reminder that costs/limits are on their account.
 *
 * Listens for the `trio-keys-changed` custom event so saving keys flips
 * the banner without a router reload.
 */
export function BYOKBanner() {
  const [live, setLive] = useState<boolean | null>(null);

  useEffect(() => {
    const sync = () => setLive(hasAnyKey(loadKeys()));
    sync();
    window.addEventListener("trio-keys-changed", sync);
    return () => window.removeEventListener("trio-keys-changed", sync);
  }, []);

  if (live === null) return null;  // SSR placeholder

  if (!live) {
    return (
      <section className="rounded-lg border border-trust/30 bg-blue-50 p-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 inline-flex h-6 w-6 items-center justify-center rounded-full bg-trust text-white text-xs font-semibold">
            i
          </span>
          <div>
            <h2 className="text-sm font-semibold text-ink">
              Demo mode · for retail traders + institutional fund managers
            </h2>
            <p className="mt-1 text-sm text-slate-700">
              You can browse the engine, upload a CSV, and run backtests on
              static price history right now. To pull <em>live</em> point-in-time
              fundamentals, insider flow, and analyst consensus, click{" "}
              <strong>BYOK · demo mode</strong> in the header and paste your
              own free API keys. The keys never leave your browser — TRIO
              calls third-party providers as you, on your quota.
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Required for live mode: SEC EDGAR contact email (free), Wikipedia
              contact email (free), Financial Modeling Prep API key (free
              tier — 250 requests/day).
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
      <p className="text-xs text-emerald-900">
        <strong>Live mode active.</strong> Provider rate limits, costs, and
        data licensing apply to your accounts. Open the BYOK panel to clear
        keys at any time.
      </p>
    </section>
  );
}
