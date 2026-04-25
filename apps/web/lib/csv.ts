import Papa from "papaparse";
import type { ModelId } from "./api";

// Maps incoming CSV header (Bloomberg-style or canonical) -> canonical field used by the API.
// Canonical names match what packages/algorithms/.../rba/*.py reads from each row dict.

const ALIASES: Record<ModelId, Record<string, string>> = {
  bos: {
    VOLUME_AVG_3M: "vol_avg_3m",
    RETURN: "target_return",
    EQY_DVD_YLD_IND: "dvd_yld_ind",
    ALTMAN_Z_SCORE: "altman_z",
    EQY_REC_CONS: "analyst_sent",
    LONG_COMP_NAME: "name",
  },
  mos: {
    BS_CASH_NEAR_CASH_ITEM: "cash_near_cash",
    BS_ACCT_NOTE_RCV: "accounts_receivable",
    BS_INVENTORIES: "inventories",
    BS_OTHER_CUR_ASSET: "other_current_assets",
    BS_ACCT_PAYABLE: "accounts_payable",
    BS_OTHER_ST_LIAB: "other_st_liab",
    BS_ST_BORROW: "st_borrow",
    NON_CUR_LIAB: "non_current_liab",
    EQY_SH_OUT: "shares_out",
    PX_LAST: "px_last",
    BEST_TARGET_PRICE: "best_target_price",
    LONG_COMP_NAME: "name",
  },
  four_factor: {
    ALTMAN_Z_SCORE: "altman_z",
    EQY_DVD_YLD_EST: "dvd_yld_est",
    "3YR_AVG_RETURN_ON_EQUITY": "roe_3yr_avg",
    PE_RATIO: "pe_ratio",
    FIVE_YR_AVG_PRICE_EARNINGS: "pe_5yr_avg",
    LONG_COMP_NAME: "name",
  },
};

export function parseCsv(text: string, model: ModelId): Record<string, unknown>[] {
  const parsed = Papa.parse<Record<string, unknown>>(text, {
    header: true,
    skipEmptyLines: true,
    delimitersToGuess: [",", ";", "\t"],
  });
  if (parsed.errors.length > 0) {
    console.warn("CSV parse warnings:", parsed.errors.slice(0, 3));
  }
  const aliasMap = ALIASES[model];
  return parsed.data.map((raw) => {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(raw)) {
      out[k] = v;
      const canonical = aliasMap[k];
      if (canonical && out[canonical] === undefined) out[canonical] = v;
    }
    if (out.ticker === undefined) {
      out.ticker = raw["KLCI_INDEX_NAME"] ?? raw["TICKER"] ?? raw["Ticker"] ?? "?";
    }
    return out;
  });
}
