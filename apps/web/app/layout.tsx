import "./globals.css";
import type { Metadata } from "next";
import { SettingsPanel } from "@/components/SettingsPanel";

export const metadata: Metadata = {
  title: "TRIO Web",
  description:
    "Transparent factor-based equity scoring with PIT-honest data. Decision-support only — not investment advice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/*
        suppressHydrationWarning here silences the React hydration warning
        when browser extensions (Grammarly, ColorZilla, etc.) inject
        attributes like data-gr-ext-installed onto <body> before React
        hydrates. This is the Next.js-documented fix; it does NOT silence
        real hydration errors in our own components.
      */}
      <body suppressHydrationWarning>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-ink">
                TRIO Web
              </h1>
              <p className="text-xs text-slate-500">
                7-factor equity scoring · BOS · BOS-Flow · MLA · point-in-time
              </p>
            </div>
            <div className="flex items-center gap-3">
              <SettingsPanel />
              <span className="hidden rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200 md:inline">
                Decision-support only — not investment advice
              </span>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto mt-12 max-w-6xl border-t border-slate-200 px-6 py-6 text-xs text-slate-500">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>
              Data:{" "}
              <a
                href="https://www.sec.gov/edgar"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                SEC EDGAR
              </a>
              {" · "}
              <a
                href="https://site.financialmodelingprep.com/developer/docs?ref=trio-web"
                target="_blank"
                rel="noopener noreferrer sponsored"
                className="hover:underline"
              >
                Financial Modeling Prep
              </a>
              {" · "}
              <a
                href="https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                Wikimedia
              </a>
              {" · yfinance"}
            </p>
            <p className="text-slate-400">
              Open source ·{" "}
              <a
                href="https://github.com/silattrader/trio-web"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                github.com/silattrader/trio-web
              </a>
            </p>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">
            Some links above are referral / affiliate links — they pay TRIO
            a small commission if you sign up; the price you pay is unchanged.
            TRIO is a research tool, not licensed investment advice.
          </p>
        </footer>
      </body>
    </html>
  );
}
