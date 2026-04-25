import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "TRIO Web",
  description:
    "Transparent factor-based equity scoring. Decision-support only — not investment advice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-ink">TRIO Web</h1>
              <p className="text-xs text-slate-500">
                Rule-based equity scoring · BOS · MOS · 4-Factor
              </p>
            </div>
            <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
              Decision-support only — not investment advice
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
