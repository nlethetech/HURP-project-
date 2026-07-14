#!/usr/bin/env python3
"""Build the country-year forced-displacement table (UNHCR + IDMC).

Purpose
-------
Tidy UNHCR origin totals and IDMC GIDD into one (iso3, year) table (see
docs/CODEBOOK.md, "Displacement"). Country-year -> iso3_broadcast, TIME-VARYING,
NaN where unobserved (NEVER zero-filled: a missing IDMC row is not zero
displacement). Stocks and flows are kept as SEPARATE columns — never sum them.

Inputs
------
    data/raw/unhcr/unhcr_population.json   (origin totals, key coo_iso = ISO3)
    data/raw/idmc/idmc_gidd.xlsx           (sheet 1_Displacement_data, key ISO3)

Output
------
    data/interim/displacement.parquet   one row per (iso3, year), 1989-2025

Run
---
    .venv/bin/python src/cleaning/18_displacement.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
UNHCR = ROOT / "data" / "raw" / "unhcr" / "unhcr_population.json"
IDMC = ROOT / "data" / "raw" / "idmc" / "idmc_gidd.xlsx"
OUT = ROOT / "data" / "interim" / "displacement.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("displacement")

YMIN, YMAX = 1989, 2025


def load_unhcr() -> pd.DataFrame:
    items = json.load(UNHCR.open())["items"]
    u = pd.DataFrame(items)
    u = u.rename(columns={"coo_iso": "iso3"})
    u["year"] = pd.to_numeric(u["year"], errors="coerce")
    ren = {"refugees": "refugees_origin", "asylum_seekers": "asylum_seekers_origin",
           "idps": "idp_stock_unhcr", "returned_refugees": "returned_refugees",
           "returned_idps": "returned_idps"}
    for src in ren:
        u[src] = pd.to_numeric(u[src], errors="coerce")  # "-"/"" -> NaN, keeps reported 0
    u = u.rename(columns=ren)
    u = u.dropna(subset=["iso3", "year"])
    u["year"] = u["year"].astype(int)
    return u[["iso3", "year"] + list(ren.values())]


def load_idmc() -> pd.DataFrame:
    g = pd.read_excel(IDMC, sheet_name="1_Displacement_data")
    ren = {
        "Conflict Stock Displacement": "idp_stock_conflict",
        "Conflict Internal Displacements": "new_disp_conflict",
        "Disaster Stock Displacement": "idp_stock_disaster",
        "Disaster Internal Displacements": "new_disp_disaster",
    }
    g = g.rename(columns={"ISO3": "iso3", "Year": "year", **ren})
    g["year"] = pd.to_numeric(g["year"], errors="coerce")
    for c in ren.values():
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g = g.dropna(subset=["iso3", "year"])
    g["year"] = g["year"].astype(int)
    return g[["iso3", "year"] + list(ren.values())]


def main() -> None:
    u = load_unhcr()
    g = load_idmc()
    df = u.merge(g, on=["iso3", "year"], how="outer")
    df = df[df["year"].between(YMIN, YMAX)].sort_values(["iso3", "year"]).reset_index(drop=True)
    assert df.duplicated(["iso3", "year"]).sum() == 0, "duplicate (iso3, year) in displacement"
    df.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    ours = set(cw[cw["kept"]]["iso3"])
    log.info("wrote %s: %d country-years, %d countries, %d-%d",
             OUT.name, len(df), df["iso3"].nunique(), int(df["year"].min()), int(df["year"].max()))
    log.info("study coverage: UNHCR refugees_origin %d/79 | IDMC conflict-stock %d/79",
             len(ours & set(u[u["refugees_origin"].notna()]["iso3"])),
             len(ours & set(g[g["idp_stock_conflict"].notna()]["iso3"])))
    log.info("IDMC year range: %d-%d | UNHCR idp (starts 1993) min year: %d",
             int(g["year"].min()), int(g["year"].max()),
             int(u[u["idp_stock_unhcr"].notna()]["year"].min()))


if __name__ == "__main__":
    main()
