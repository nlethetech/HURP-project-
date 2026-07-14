#!/usr/bin/env python3
"""Build the complete FAOSTAT agricultural-output layer for the study countries.

Purpose
-------
Turn the FAOSTAT "Production: Crops and livestock products" (QCL) bulk download
into (a) a COMPLETE tidy country-year long table for the 79 study countries
(every crop/livestock item x {Production, Area harvested, Yield}) and (b) a
panel-ready WIDE country-year table of headline agricultural-output measures
that merges onto the study panel by iso3 (see docs/CODEBOOK.md, "Agriculture —
FAOSTAT"). This is the agricultural-OUTPUT side of the two-way conflict <->
agriculture question. Country-year -> iso3_broadcast, TIME-VARYING; NaN where a
country-year-item is not reported (never zero-filled). FAOSTAT ends 2024 -> 2025
is NaN.

Inputs
------
    data/raw/faostat_qcl/Production_Crops_Livestock_E_All_Data_(Normalized).zip
        (downloaded by src/acquisition/04_download_faostat_qcl.py)
    reference/iso3_region_crosswalk.csv

Outputs
-------
    data/interim/faostat_ag_long.parquet   COMPLETE: one row per
        (iso3, year, item_code, item, element); Production(t)/Area(ha)/Yield(kg/ha);
        `is_aggregate` flags the FAO group totals (do not sum with their members).
    data/interim/faostat_ag.parquet        WIDE panel-ready country-year table.

Run
---
    .venv/bin/python src/cleaning/24_faostat_ag.py
"""
from __future__ import annotations

import glob
import logging
import zipfile

import country_converter as coco
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_GLOB = str(ROOT / "data" / "raw" / "faostat_qcl" / "*Normalized*.zip")
OUT_LONG = ROOT / "data" / "interim" / "faostat_ag_long.parquet"
OUT_WIDE = ROOT / "data" / "interim" / "faostat_ag.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("faostat_ag")

# Elements kept (code -> (name, unit)).
ELEMENTS = {5510: ("Production", "t"), 5312: ("Area harvested", "ha"), 5412: ("Yield", "kg/ha")}
# FAO group-total items (used for the aggregate columns; flagged in the long table
# so a user does not double-count them against their member crops). NB: the
# "Oilcrops Primary" (1730) and "Crops primary" (1714) totals are defined in the
# item list but carry NO data rows in the QCL bulk snapshot, so they are excluded.
AGG_ITEMS = {1717: "cereal", 1720: "roots_tubers", 1726: "pulses",
             1738: "fruit", 1735: "vegetables", 1765: "meat_total", 1780: "milk_total"}
# Headline individual staples for the panel (production + yield).
STAPLE_ITEMS = {56: "maize", 27: "rice", 15: "wheat", 83: "sorghum", 79: "millet",
                125: "cassava", 176: "beans", 242: "groundnuts"}
# FAOSTAT area-code quirk: pre-split "former entity" M49 codes that coco cannot map
# but which carry a study country's back-series. Each pairs with its successor's
# code over a DISJOINT year range (no overlap -> no double-count):
#   736 "Sudan (former)"  1961-2011  -> SDN  (successor 729 from 2012)
#   230 "Ethiopia PDR"    1961-1992  -> ETH  (successor 231 from 1993)
M49_OVERRIDE = {736: "SDN", 230: "ETH"}


def load_raw() -> pd.DataFrame:
    zp = glob.glob(RAW_GLOB)
    if not zp:
        raise SystemExit(f"no FAOSTAT raw at {RAW_GLOB} — run src/acquisition/04_download_faostat_qcl.py")
    z = zipfile.ZipFile(zp[0])
    main = [n for n in z.namelist() if n.endswith("(Normalized).csv")][0]
    df = pd.read_csv(z.open(main), encoding="utf-8",
                     usecols=["Area Code (M49)", "Item Code", "Item", "Element Code", "Year", "Unit", "Value"])
    df = df[df["Element Code"].isin(ELEMENTS)].copy()
    # Unit guard: fail loudly if a future FAOSTAT vintage ships different units
    # (e.g. yield in hg/ha instead of kg/ha would silently inflate values 10x).
    for code, (_, unit) in ELEMENTS.items():
        got = set(df.loc[df["Element Code"] == code, "Unit"].unique())
        if got and got != {unit}:
            raise RuntimeError(f"element {code}: expected unit '{unit}', raw has {got} — vintage changed, recheck.")
    # M49 (e.g. "'004") -> ISO3 via country_converter, + Sudan-former override.
    m49 = df["Area Code (M49)"].astype(str).str.replace("'", "", regex=False)
    m49 = pd.to_numeric(m49, errors="coerce")
    df = df[m49.notna()].copy()
    m49 = m49[m49.notna()].astype(int)
    uniq = sorted(m49.unique())
    iso_map = dict(zip(uniq, coco.CountryConverter().convert(uniq, src="ISOnumeric", to="ISO3", not_found=None)))
    iso_map.update(M49_OVERRIDE)
    df["iso3"] = m49.map(iso_map)
    df["year"] = df["Year"].astype(int)
    df = df.rename(columns={"Item Code": "item_code", "Item": "item", "Value": "value"})
    df["element"] = df["Element Code"].map(lambda c: ELEMENTS[c][0])
    df["unit"] = df["Element Code"].map(lambda c: ELEMENTS[c][1])
    return df[["iso3", "year", "item_code", "item", "element", "unit", "value"]]


def main() -> None:
    ours = set(pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv").query("kept").iso3)
    raw = load_raw()
    study = raw[raw["iso3"].isin(ours)].copy()

    missing = ours - set(study["iso3"])
    if missing:
        log.warning("study countries with NO FAOSTAT rows: %s", sorted(missing))

    # --- Complete long companion (dedupe (iso3,year,item,element); flag aggregates) ---
    study = study.drop_duplicates(["iso3", "year", "item_code", "element"], keep="last")
    study["is_aggregate"] = study["item_code"].isin(AGG_ITEMS).astype(int)
    study = study.sort_values(["iso3", "year", "item_code", "element"]).reset_index(drop=True)
    study.to_parquet(OUT_LONG, index=False)

    # --- Wide panel-ready country-year table ---
    prod = study[study["element"] == "Production"]
    area = study[study["element"] == "Area harvested"]
    yld = study[study["element"] == "Yield"]

    def wide(src: pd.DataFrame, items: dict, suffix: str) -> pd.DataFrame:
        s = src[src["item_code"].isin(items)].copy()
        s["col"] = s["item_code"].map(items) + suffix
        return s.pivot_table(index=["iso3", "year"], columns="col", values="value", aggfunc="first")

    w = wide(prod, AGG_ITEMS, "_prod_t")                                   # 9 group totals
    w = w.join(wide(area, {1717: "cereal"}, "_area_ha"), how="outer")     # cereal area
    w = w.join(wide(yld, {1717: "cereal"}, "_yield_kgha"), how="outer")   # cereal yield
    w = w.join(wide(prod, STAPLE_ITEMS, "_prod_t"), how="outer")          # 8 staples production
    w = w.join(wide(yld, STAPLE_ITEMS, "_yield_kgha"), how="outer")       # 8 staples yield
    w = w.add_prefix("fao_").reset_index()
    w.columns = [c.replace("fao_iso3", "iso3").replace("fao_year", "year") for c in w.columns]
    w = w.sort_values(["iso3", "year"]).reset_index(drop=True)
    w.to_parquet(OUT_WIDE, index=False)

    log.info("wrote %s: %d rows (complete long), %d items, %d countries, %d-%d",
             OUT_LONG.name, len(study), study["item_code"].nunique(), study["iso3"].nunique(),
             int(study["year"].min()), int(study["year"].max()))
    log.info("wrote %s: %d country-years x %d cols; study countries %d/79",
             OUT_WIDE.name, len(w), w.shape[1] - 2, len(ours & set(w["iso3"])))
    log.info("wide columns: %s", [c for c in w.columns if c not in ("iso3", "year")])


if __name__ == "__main__":
    main()
