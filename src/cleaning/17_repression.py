#!/usr/bin/env python3
"""Build the country-year state-repression table (Political Terror Scale).

Purpose
-------
Tidy the Political Terror Scale (PTS-2025) into one (iso3, year) table (see
docs/CODEBOOK.md, "State repression"). Country-year -> iso3_broadcast,
TIME-VARYING. PTS gives three 1-5 physical-integrity/repression scores from
Amnesty (A), US State Dept (S) and HRW (H); we keep all three and a coalesced
`pts_score` (S -> A -> H, State Dept being the most complete series).

WARNING (design): repression is BOTH a driver and a consequence of conflict — a
mediator to lag (t-1), not a clean exogenous cause.

Inputs
------
    data/raw/pts/PTS-2025.csv   (Latin-1 encoded; iso3 in WordBank_Code_A)

Output
------
    data/interim/repression.parquet   one row per (iso3, year), 1989-2025

Run
---
    .venv/bin/python src/cleaning/17_repression.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "pts" / "PTS-2025.csv"
OUT = ROOT / "data" / "interim" / "repression.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("repression")

YMIN, YMAX = 1989, 2025


def main() -> None:
    p = pd.read_csv(SRC, encoding="latin-1")
    p = p.rename(columns={"WordBank_Code_A": "iso3", "Year": "year"})
    p["year"] = pd.to_numeric(p["year"], errors="coerce")
    p = p.dropna(subset=["iso3", "year"])
    p["year"] = p["year"].astype(int)
    p = p[p["year"].between(YMIN, YMAX)].copy()

    for c in ["PTS_A", "PTS_S", "PTS_H"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")  # non-numeric NA_Status -> NaN

    # PTS uses legacy World Bank codes for a few states (DR Congo = ZAR, not COD).
    WB_CODE_FIX = {"ZAR": "COD"}
    iso3 = p["iso3"].astype(str).str.strip().replace(WB_CODE_FIX)
    out = pd.DataFrame({
        "iso3": iso3,
        "year": p["year"],
        "pts_amnesty": p["PTS_A"],
        "pts_state": p["PTS_S"],
        "pts_hrw": p["PTS_H"],
    })
    # Coalesce S -> A -> H (State Dept most complete); record which source supplied it.
    out["pts_score"] = out["pts_state"].combine_first(out["pts_amnesty"]).combine_first(out["pts_hrw"])
    src = np.where(out["pts_state"].notna(), "S",
                   np.where(out["pts_amnesty"].notna(), "A",
                            np.where(out["pts_hrw"].notna(), "H", None)))
    out["pts_source"] = src

    # The source has a few disagreeing duplicate (iso3, year) rows (some all-NaN);
    # keep the most-informative one (non-null pts_score wins) deterministically.
    out["_has_score"] = out["pts_score"].notna().astype(int)
    out = (out.dropna(subset=["iso3"])
              .sort_values(["iso3", "year", "_has_score"])
              .drop_duplicates(["iso3", "year"], keep="last")
              .drop(columns="_has_score"))
    out = out.sort_values(["iso3", "year"]).reset_index(drop=True)
    assert out.duplicated(["iso3", "year"]).sum() == 0
    out.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    ours = set(cw[cw["kept"]]["iso3"])
    log.info("wrote %s: %d country-years, %d countries, %d-%d",
             OUT.name, len(out), out["iso3"].nunique(), int(out["year"].min()), int(out["year"].max()))
    log.info("study coverage: %d/%d | pts_score non-null: %.0f%%",
             len(ours & set(out["iso3"])), len(ours), 100 * out["pts_score"].notna().mean())
    log.info("pts_source mix: %s", pd.Series(out["pts_source"]).value_counts(dropna=False).to_dict())
    log.info("study countries missing PTS: %s", sorted(ours - set(out["iso3"])))


if __name__ == "__main__":
    main()
