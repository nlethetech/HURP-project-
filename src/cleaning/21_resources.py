#!/usr/bin/env python3
"""Aggregate oil/gas + diamond + mineral deposits to district-constant flags.

Purpose
-------
Spatial-join PRIO PETRODATA (onshore oil/gas), PRIO DIADATA (diamonds, with the
primary/secondary=lootable split) and USGS MRDS (mineral deposits) to the admin-2
spine (see docs/CODEBOOK.md, "Natural resources"). Static geological endowment ->
ONE row per district, broadcast to all panel years at merge. The lootable-
resource / "greed" channel.

Masking: PETRODATA and DIADATA are global compilations, so within their scope a
district with no intersecting deposit is a TRUE zero -> count columns are
zero-filled across all spine districts. Caveat (documented): PETRODATA's 2003
vintage misses the post-2003 East-African oil frontier (Uganda 2006, Kenya 2012)
-> those are false zeros. MRDS is USGS and US-biased; `n_mineral_deposits` is
informational and undercounts outside North America.

Inputs
------
    data/raw/petrodata/Petrodata_Onshore_V1.2.shp
    data/raw/diadata/DIADATA.shp
    data/raw/mrds/mrds.csv
    data/interim/spine.gpkg  (layer "spine"; EPSG:4326)

Output
------
    data/interim/resources.parquet   one row per district_id (no year)

Run
---
    .venv/bin/python src/cleaning/21_resources.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PETRO = ROOT / "data" / "raw" / "petrodata" / "Petrodata_Onshore_V1.2.shp"
DIA = ROOT / "data" / "raw" / "diadata" / "DIADATA.shp"
MRDS = ROOT / "data" / "raw" / "mrds" / "mrds.csv"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "resources.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("resources")

# DIADATA low-precision location codes to drop (country/region centroids etc.):
# they would point-in-polygon into an arbitrary district and inflate it.
DIA_LOWPREC = {"D1", "D2", "E1", "E2", "F", "G"}


def sjoin_counts(geom: gpd.GeoDataFrame, spine: gpd.GeoDataFrame, predicate: str = "within") -> gpd.GeoDataFrame:
    # points -> "within"; polygon footprints (PETRODATA fields) -> "intersects".
    return gpd.sjoin(geom.to_crs(4326), spine, how="inner", predicate=predicate)


def main() -> None:
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "geometry"]].to_crs(4326)
    out = spine[["district_id"]].copy()

    # --- PETRODATA onshore oil/gas ---
    petro = gpd.read_file(PETRO)
    j = sjoin_counts(petro, spine, predicate="intersects")  # oil/gas FIELD POLYGONS
    ri = j["RESINFO"].astype(str).str.lower()
    j["_oil"] = ri.isin(["oil", "oil and gas"]).astype(int)
    j["_gas"] = ri.isin(["gas", "oil and gas"]).astype(int)
    j["_disc"] = pd.to_numeric(j["DISC"], errors="coerce").where(lambda s: s > 0)
    g = j.groupby("district_id")
    petro_agg = pd.DataFrame({
        "n_oil_gas_fields": g.size(),
        "has_oil": (g["_oil"].sum() > 0).astype(int),
        "has_gas": (g["_gas"].sum() > 0).astype(int),
        "oil_gas_first_discovery_year": g["_disc"].min(),
    })
    out = out.merge(petro_agg, on="district_id", how="left")
    out["n_oil_gas_fields"] = out["n_oil_gas_fields"].fillna(0).astype(int)
    out["has_oil_gas"] = (out["n_oil_gas_fields"] > 0).astype(int)
    out["has_oil"] = out["has_oil"].fillna(0).astype(int)
    out["has_gas"] = out["has_gas"].fillna(0).astype(int)

    # --- DIADATA diamonds (drop low-precision points) ---
    dia = gpd.read_file(DIA)
    # LOCDER can be compound (e.g. "D2; F"); drop if ANY component is low-precision.
    lp = dia["LOCDER"].astype(str).str.upper().str.split(r"[;,]")
    dia = dia[~lp.apply(lambda ps: any(p.strip() in DIA_LOWPREC for p in ps))]
    jd = sjoin_counts(dia, spine)
    di = jd["DIAINFO"].astype(str).str.upper()
    jd["_sec"] = (di == "S").astype(int)
    jd["_pri"] = (di == "P").astype(int)
    jd["_mix"] = (di == "M").astype(int)   # mixed primary+secondary (has an alluvial component)
    gd = jd.groupby("district_id")
    dia_agg = pd.DataFrame({
        "n_diamond_deposits": gd.size(),
        "n_diamond_secondary": gd["_sec"].sum(),
        "n_diamond_primary": gd["_pri"].sum(),
        "n_diamond_mixed": gd["_mix"].sum(),
    })
    out = out.merge(dia_agg, on="district_id", how="left")
    for c in ["n_diamond_deposits", "n_diamond_secondary", "n_diamond_primary", "n_diamond_mixed"]:
        out[c] = out[c].fillna(0).astype(int)
    out["has_diamond"] = (out["n_diamond_deposits"] > 0).astype(int)
    # Lootable = alluvial: secondary OR mixed (mixed deposits include an alluvial component).
    out["has_lootable_diamond"] = ((out["n_diamond_secondary"] + out["n_diamond_mixed"]) > 0).astype(int)

    # --- USGS MRDS mineral deposits (US-biased; informational) ---
    m = pd.read_csv(MRDS, low_memory=False, usecols=["latitude", "longitude"])
    m = m.dropna(subset=["latitude", "longitude"])
    mp = gpd.GeoDataFrame(m, geometry=gpd.points_from_xy(m["longitude"], m["latitude"]), crs="EPSG:4326")
    jm = sjoin_counts(mp, spine)
    out = out.merge(jm.groupby("district_id").size().rename("n_mineral_deposits"), on="district_id", how="left")
    out["n_mineral_deposits"] = out["n_mineral_deposits"].fillna(0).astype(int)

    out = out.sort_values("district_id").reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    log.info("wrote %s: %d districts", OUT.name, len(out))
    log.info("has_oil_gas=1: %d | has_diamond=1: %d | has_lootable_diamond=1: %d | any mineral: %d",
             int(out["has_oil_gas"].sum()), int(out["has_diamond"].sum()),
             int(out["has_lootable_diamond"].sum()), int((out["n_mineral_deposits"] > 0).sum()))


if __name__ == "__main__":
    main()
