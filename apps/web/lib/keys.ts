// BYOK — store user-supplied API keys in localStorage and inject them as
// X-TRIO-* headers on every /api fetch. No server-side persistence;
// keys never leave the user's browser except in the request to /api.

export interface UserKeys {
  sec_ua: string;
  fmp_key: string;
  wiki_ua: string;
}

const KEYS_STORAGE = "trio.byok.keys.v1";

export const EMPTY_KEYS: UserKeys = { sec_ua: "", fmp_key: "", wiki_ua: "" };

export function loadKeys(): UserKeys {
  if (typeof window === "undefined") return { ...EMPTY_KEYS };
  try {
    const raw = window.localStorage.getItem(KEYS_STORAGE);
    if (!raw) return { ...EMPTY_KEYS };
    const parsed = JSON.parse(raw) as Partial<UserKeys>;
    return {
      sec_ua: (parsed.sec_ua || "").trim(),
      fmp_key: (parsed.fmp_key || "").trim(),
      wiki_ua: (parsed.wiki_ua || "").trim(),
    };
  } catch {
    return { ...EMPTY_KEYS };
  }
}

export function saveKeys(keys: UserKeys): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEYS_STORAGE, JSON.stringify(keys));
  // Notify listeners (other tabs / cross-component) without a router reload.
  window.dispatchEvent(new CustomEvent("trio-keys-changed"));
}

export function clearKeys(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEYS_STORAGE);
  window.dispatchEvent(new CustomEvent("trio-keys-changed"));
}

/** Build HTTP headers that include the user's keys, if any. */
export function keyHeaders(keys?: UserKeys): Record<string, string> {
  const k = keys ?? loadKeys();
  const out: Record<string, string> = {};
  if (k.sec_ua) out["X-TRIO-SEC-UA"] = k.sec_ua;
  if (k.fmp_key) out["X-TRIO-FMP-KEY"] = k.fmp_key;
  if (k.wiki_ua) out["X-TRIO-WIKI-UA"] = k.wiki_ua;
  return out;
}

export function hasAnyKey(keys?: UserKeys): boolean {
  const k = keys ?? loadKeys();
  return Boolean(k.sec_ua || k.fmp_key || k.wiki_ua);
}

/** Coverage summary for the Settings UI badge — what factors are reachable. */
export interface CoverageSummary {
  altman_z: boolean;
  dvd_yld_ind: boolean;
  vol_avg_3m: boolean;        // always true (yfinance, no key)
  target_return: boolean;
  analyst_sent: boolean;
  insider_flow: boolean;
  retail_flow: boolean;
}

export function coverageFromKeys(keys: UserKeys): CoverageSummary {
  const sec = Boolean(keys.sec_ua);
  const fmp = Boolean(keys.fmp_key);
  const wiki = Boolean(keys.wiki_ua);
  return {
    altman_z: sec,
    dvd_yld_ind: sec,
    vol_avg_3m: true,
    target_return: fmp,
    analyst_sent: fmp,
    insider_flow: sec,
    retail_flow: wiki,
  };
}
