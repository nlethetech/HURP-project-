#!/usr/bin/env python3
"""Parse the GRD "Merged" sheet into a tidy country-year fiscal-capacity table.

Purpose
-------
Turn the UNU-WIDER Government Revenue Dataset (GRD 2025, sheet "Merged" -- one
row per country-year, the recommended series) into a tidy (iso3, year) fiscal
state-capacity table (see docs/CODEBOOK.md, "State capacity"). Values in GRD are
FRACTIONS of GDP; we multiply by 100 to store percentages. Country-year ->
broadcast onto every district at merge (iso3_broadcast). TIME-VARYING.

Inputs
------
    data/raw/grd/UNUWIDERGRD_2025.xlsx  (sheet "Merged")

Output
------
    data/interim/state_capacity.parquet   one row per (iso3, year)

Run
---
    .venv/bin/python src/cleaning/15_state_capacity.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "grd" / "UNUWIDERGRD_2025.xlsx"
OUT = ROOT / "data" / "interim" / "state_capacity.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("state_capacity")

# GRD source column -> our column (values are fractions of GDP; *100 -> percent).
PCT_COLS = {
    "Taxes": "grd_tax_pct_gdp",                        # PRIMARY fiscal-capacity measure
    "Non-Resource Tax": "grd_nonresource_tax_pct_gdp",  # least price-endogenous extractive proxy
    "Total Revenue": "grd_totrev_pct_gdp",              # fallback (broader coverage)
    "Total Resource Revenue": "grd_resource_rev_pct_gdp",
}
CAUTION_COLS = [
    "Caution1 Accuracy, Quality or Comparability of data is questionable",
    "Caution2 Un-excluded resource revenues / taxes are significant but cannot be isolated from total revenues / taxes",
    "Caution3 Un-excluded Resource Revenues/Taxes are Marginal, but Non-Negligible and cannot be isolated from total revenue / taxes",
    "Caution 4 Inconsistencies with Social Contributions",
]


def main() -> None:
    m = pd.read_excel(SRC, sheet_name="Merged")
    m = m.dropna(subset=["ISO", "Year"]).copy()
    # Source data-entry typo: Estonia's 1980 row is mislabeled ISO=ETH (Ethiopia).
    # Harmless in the 1989+ window but drop it defensively (Estonia is also under EST).
    m = m[~((m["ISO"] == "ETH") & (m["Country"].astype(str).str.strip() == "Estonia"))]
    m["iso3"] = m["ISO"].astype(str).str.strip()
    m["year"] = m["Year"].astype(int)
    m["grd_gov_level"] = m["General (=1 if General)"].fillna(0).map({1.0: "general", 0.0: "central"})

    out = m[["iso3", "year", "grd_gov_level"]].copy()
    for src, dst in PCT_COLS.items():
        out[dst] = pd.to_numeric(m[src], errors="coerce") * 100.0

    # Quality flag: any GRD caution set for this observation (data-quality caveat).
    caution = pd.DataFrame({c: pd.to_numeric(m.get(c), errors="coerce").fillna(0) for c in CAUTION_COLS})
    out["grd_quality_flag"] = (caution.sum(axis=1) > 0).astype(int)

    # One row per (iso3, year) already in the Merged sheet; assert it.
    assert out.duplicated(["iso3", "year"]).sum() == 0, "GRD Merged had duplicate (iso3, year)"
    out = out.sort_values(["iso3", "year"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    log.info("wrote %s: %d country-years, %d countries, %d-%d",
             OUT.name, len(out), out["iso3"].nunique(), int(out["year"].min()), int(out["year"].max()))
    log.info("tax %%GDP non-null: %.0f%% | nonresource-tax: %.0f%% | totrev: %.0f%%",
             100 * out["grd_tax_pct_gdp"].notna().mean(),
             100 * out["grd_nonresource_tax_pct_gdp"].notna().mean(),
             100 * out["grd_totrev_pct_gdp"].notna().mean())
    log.info("gov level: %s", out["grd_gov_level"].value_counts().to_dict())


if __name__ == "__main__":
    main()
