#!/usr/bin/env python3
"""Parse World Bank WDI indicator JSON into a tidy (iso3, year) covariate table.

Purpose
-------
Turn the per-indicator WB WDI JSON (raw, downloaded by
src/acquisition/11_download_wb_wdi.py) into one wide, deterministic
country-year table of socioeconomic & agricultural covariates for the panel
(see docs/DATA_SOURCES.md, "World Bank World Development Indicators (WDI)").

Inputs
------
    data/raw/wb_wdi/<CODE>.json   (one per curated indicator; each has
        {code, column, indicator_name, data:[{countryiso3code, date, value}]})

Output
------
    data/interim/wb_wdi.parquet
        One row per (iso3, year) with one column per indicator (wb_*). Values
        are float; NaN where the World Bank has no observation (NOT zero --
        these are continuous measures). Only rows with a real 3-letter
        countryiso3code are kept; WB regional aggregates (WLD, ARB, ...) are
        dropped (they never join to a spine district anyway). Sorted by
        (iso3, year).

Runtime
-------
A few seconds (15 small JSON files).

How to run
----------
    .venv/bin/python src/cleaning/11_wb_wdi.py

Idempotent: rewritten in full from the immutable raw JSON, fixed sort order.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

# Mirror the acquisition script's curated set (code -> column).
INDICATORS = {
    "SL.UEM.TOTL.ZS": "wb_unemployment",
    "SL.UEM.1524.ZS": "wb_unemployment_youth",
    "NY.GDP.PCAP.KD": "wb_gdp_pc",
    "NY.GDP.MKTP.KD.ZG": "wb_gdp_growth",
    "FP.CPI.TOTL.ZG": "wb_inflation",
    "SP.POP.TOTL": "wb_population",
    "SP.POP.GROW": "wb_pop_growth",
    "SP.POP.0014.TO.ZS": "wb_pop_0_14",
    "SP.URB.TOTL.IN.ZS": "wb_urban_pct",
    "NV.AGR.TOTL.ZS": "wb_ag_valueadd_pct",
    "SL.AGR.EMPL.ZS": "wb_ag_employment_pct",
    "AG.LND.AGRI.ZS": "wb_ag_land_pct",
    "AG.YLD.CREL.KG": "wb_cereal_yield",
    "AG.PRD.FOOD.XD": "wb_food_prod_index",
    "AG.LND.ARBL.ZS": "wb_arable_land_pct",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "wb_wdi"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "wb_wdi.parquet"

ISO3_RE = re.compile(r"^[A-Z]{3}$")
YEAR_MIN, YEAR_MAX = 1989, 2025

# World Bank regional / income / lending AGGREGATES. These carry real 3-letter
# `countryiso3code` values (so the ISO3 regex does not exclude them) but are not
# countries. They would never join to a spine district, but are dropped here so
# the interim country-year table contains only economies. (Standard WB v2
# aggregate code set; an unseen new aggregate would still fail to join.)
WB_AGGREGATES = frozenset({
    "WLD", "ARB", "CSS", "CEB", "EAR", "EAS", "EAP", "TEA", "EMU", "ECS",
    "ECA", "TEC", "EUU", "FCS", "HPC", "HIC", "IBD", "IBT", "IDB", "IDX",
    "IDA", "LTE", "LCN", "LAC", "TLA", "LDC", "LMY", "LIC", "LMC", "MEA",
    "MNA", "TMN", "MIC", "NAC", "INX", "OED", "OSS", "PSS", "PST", "PRE",
    "SST", "SAS", "TSA", "SSF", "SSA", "TSS", "UMC", "AFE", "AFW",
})


def log(msg: str) -> None:
    print(msg, flush=True)


def load_indicator(code: str, col: str) -> pd.DataFrame:
    path = RAW_DIR / f"{code}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}; run src/acquisition/11_download_wb_wdi.py")
    payload = json.loads(path.read_text())
    rows = payload["data"]
    recs = []
    for r in rows:
        iso3 = (r.get("countryiso3code") or "").strip()
        val = r.get("value")
        year = r.get("date")
        if val is None or not ISO3_RE.match(iso3) or iso3 in WB_AGGREGATES:
            continue  # drop nulls, malformed codes, and WB regional aggregates
        recs.append((iso3, int(year), float(val)))
    df = pd.DataFrame(recs, columns=["iso3", "year", col])
    df = df[(df["year"] >= YEAR_MIN) & (df["year"] <= YEAR_MAX)]
    # Guard: (iso3, year) unique within an indicator.
    if df.duplicated(["iso3", "year"]).any():
        raise AssertionError(f"{code}: duplicate (iso3, year) rows.")
    return df


def main() -> int:
    merged: pd.DataFrame | None = None
    n_obs = {}
    for code, col in INDICATORS.items():
        df = load_indicator(code, col)
        n_obs[col] = len(df)
        log(f"  {col:24s} {len(df):6,} obs  ({df['iso3'].nunique()} countries, "
            f"{int(df['year'].min())}-{int(df['year'].max())})")
        merged = df if merged is None else merged.merge(
            df, on=["iso3", "year"], how="outer")

    assert merged is not None
    cols = ["iso3", "year"] + list(INDICATORS.values())
    merged = merged[cols]
    merged["year"] = merged["year"].astype("int64")
    for c in INDICATORS.values():
        merged[c] = merged[c].astype("float64")

    if merged.duplicated(["iso3", "year"]).any():
        raise AssertionError("Final table has duplicate (iso3, year).")
    merged = merged.sort_values(["iso3", "year"], kind="mergesort").reset_index(drop=True)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT_PARQUET, index=False)
    log(f"Wrote {OUT_PARQUET} ({len(merged):,} rows x {len(INDICATORS)} indicators)")

    log("")
    log("=== WB WDI CLEANING SUMMARY ===")
    log(f"  country-year rows:   {len(merged):,}")
    log(f"  distinct countries:  {merged['iso3'].nunique()}")
    log(f"  year range:          {int(merged['year'].min())}-{int(merged['year'].max())}")
    log("  non-null per indicator:")
    for c in INDICATORS.values():
        log(f"      {c:24s} {int(merged[c].notna().sum()):6,} "
            f"({100*merged[c].notna().mean():.0f}%)")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
