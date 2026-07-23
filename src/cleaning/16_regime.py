#!/usr/bin/env python3
"""Build the country-year regime / democracy table (V-Dem + Polity5).

Purpose
-------
Tidy V-Dem v16 and Polity5 into one (iso3, year) regime table (see
docs/CODEBOOK.md, "Regime & democracy"). Country-year -> iso3_broadcast,
TIME-VARYING. V-Dem also supplies `vdem_terr_control` (state authority over
territory), the coercive/territorial complement to the fiscal state-capacity
layer.

Inputs
------
    data/raw/vdem/vdem.RData            (V-Dem v16; read via pyreadr)
    data/raw/polity5/p5v2018.sav        (Polity5; read via pyreadstat)
    data/raw/legal_origins/qog_std_cs_jan22.csv  (ccodecow<->iso3 bridge for Polity)

Output
------
    data/interim/regime.parquet   one row per (iso3, year), 1989-2025

Run
---
    .venv/bin/python src/cleaning/16_regime.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyreadr
import pyreadstat

ROOT = Path(__file__).resolve().parents[2]
VDEM = ROOT / "data" / "raw" / "vdem" / "vdem.RData"
POLITY = ROOT / "data" / "raw" / "polity5" / "p5v2018.sav"
QOG = ROOT / "data" / "raw" / "legal_origins" / "qog_std_cs_jan22.csv"
OUT = ROOT / "data" / "interim" / "regime.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("regime")

YMIN, YMAX = 1989, 2025
VDEM_COLS = {
    "v2x_polyarchy": "vdem_polyarchy",       # electoral democracy 0-1
    "v2x_libdem": "vdem_libdem",             # liberal democracy 0-1
    "v2x_rule": "vdem_rule_of_law",          # rule of law 0-1
    "v2xnp_regcorr": "vdem_corruption",      # political corruption 0-1 (HIGH = MORE corrupt)
    "v2x_regime": "vdem_regime",             # Regimes of the World 0=closed-aut..3=lib-dem
    "v2svstterr": "vdem_terr_control",       # state authority over territory (%)
}


def load_vdem() -> pd.DataFrame:
    v = pyreadr.read_r(str(VDEM))["vdem"]
    v = v[["country_text_id", "year"] + list(VDEM_COLS)].rename(columns={"country_text_id": "iso3", **VDEM_COLS})
    v["year"] = v["year"].astype(int)
    return v[v["year"].between(YMIN, YMAX)]


def load_polity() -> pd.DataFrame:
    pol, _ = pyreadstat.read_sav(str(POLITY))
    pol = pol[["ccode", "year", "polity2"]].copy()
    pol["year"] = pol["year"].astype(int)
    pol = pol[pol["year"].between(YMIN, YMAX)]
    # COW-style ccode -> iso3 via the QoG cross-section bridge (same as COW states).
    q = pd.read_csv(QOG, low_memory=False)[["ccodecow", "ccodealp"]].dropna()
    q["ccodecow"] = q["ccodecow"].astype(int)
    bridge = dict(zip(q["ccodecow"], q["ccodealp"]))
    cc = pol["ccode"].astype("Int64")
    pol["iso3"] = cc.map(bridge)
    # Polity uses its own post-split COW codes that the single-vintage QoG bridge
    # gets wrong: 626 = "Sudan-North" (modern Sudan, bridge sends it to SSD), 525 =
    # real South Sudan (no bridge row), 529 = post-1993 Ethiopia (no bridge row).
    # Override the bridge for these; FIX-mapped rows win the overlap years (1993 ETH,
    # 2011 SDN) via the priority sort below.
    POLITY_CCODE_FIX = {626: "SDN", 525: "SSD", 529: "ETH"}
    fix_iso = cc.map(POLITY_CCODE_FIX)
    pol["_fix_prio"] = fix_iso.notna().astype(int)
    pol["iso3"] = fix_iso.fillna(pol["iso3"])
    pol = (pol.dropna(subset=["iso3"])
              .sort_values(["iso3", "year", "_fix_prio"])
              .drop_duplicates(["iso3", "year"], keep="last")
              .drop(columns="_fix_prio"))
    pol["anocracy_flag"] = (pol["polity2"].abs() <= 5).astype("float")
    pol.loc[pol["polity2"].isna(), "anocracy_flag"] = pd.NA
    return pol[["iso3", "year", "polity2", "anocracy_flag"]]


def main() -> None:
    v = load_vdem()
    p = load_polity()
    df = v.merge(p, on=["iso3", "year"], how="outer")
    df = df[df["year"].between(YMIN, YMAX)].sort_values(["iso3", "year"]).reset_index(drop=True)
    assert df.duplicated(["iso3", "year"]).sum() == 0, "duplicate (iso3, year) in regime"
    df.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    ours = set(cw[cw["kept"]]["iso3"])
    log.info("wrote %s: %d country-years, %d countries", OUT.name, len(df), df["iso3"].nunique())
    log.info("V-Dem covers %d/%d study countries; Polity covers %d/%d",
             len(ours & set(v["iso3"])), len(ours), len(ours & set(p["iso3"])), len(ours))
    log.info("V-Dem year range %d-%d | Polity year range %d-%d",
             int(v["year"].min()), int(v["year"].max()), int(p["year"].min()), int(p["year"].max()))
    log.info("study countries missing V-Dem: %s", sorted(ours - set(v["iso3"])))


if __name__ == "__main__":
    main()
