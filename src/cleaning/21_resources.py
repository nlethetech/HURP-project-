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
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "iso3", "geometry"]].to_crs(4326)
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

    # --- Gold: USGS Africa GIS (3 mineral point layers) for Africa + MRDS for the Americas ---
    # MRDS badly undercounts African artisanal gold, so Africa uses the USGS Africa
    # compilation (Facilities + Deposits + Exploration) and the Americas keep MRDS.
    afr_iso = set(pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv").query("region == 'Africa'")["iso3"])
    gdb = ROOT / "data" / "raw" / "usgs_africa_gis" / "Africa_GIS.gdb"
    parts = []
    for lyr in ["AFR_Mineral_Facilities", "AFR_Mineral_Deposits", "AFR_Mineral_Exploration"]:
        gl = gpd.read_file(gdb, layer=lyr)
        dsg = [c for c in gl.columns if c.startswith("DsgAttr")]
        is_gold = gl[dsg].apply(lambda r: r.astype(str).str.fullmatch("Gold").any(), axis=1)
        parts.append(gl.loc[is_gold, ["geometry"]])
    usgs_gold = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    usgs_gold["geometry"] = usgs_gold.geometry.force_2d()   # Point Z -> Point
    # A mine can appear in >1 USGS layer (Deposits + Exploration); de-dup by ~100 m
    # location so n_gold_deposits does not double-count it.
    usgs_gold["_rx"] = usgs_gold.geometry.x.round(3)
    usgs_gold["_ry"] = usgs_gold.geometry.y.round(3)
    usgs_gold = usgs_gold.drop_duplicates(["_rx", "_ry"]).drop(columns=["_rx", "_ry"])
    u_ct = sjoin_counts(usgs_gold, spine).groupby("district_id").size()
    gm = pd.read_csv(MRDS, low_memory=False, usecols=["latitude", "longitude", "commod1", "commod2", "commod3"]).dropna(subset=["latitude", "longitude"])
    gm = gm[gm[["commod1", "commod2", "commod3"]].apply(lambda r: r.astype(str).str.contains("Gold", case=False, na=False).any(), axis=1)]
    gmp = gpd.GeoDataFrame(gm, geometry=gpd.points_from_xy(gm["longitude"], gm["latitude"]), crs="EPSG:4326")
    m_ct = sjoin_counts(gmp, spine).groupby("district_id").size()
    gold = spine[["district_id", "iso3"]].copy()
    gold["_afr"] = gold["iso3"].isin(afr_iso)
    gold = gold.merge(u_ct.rename("_u"), on="district_id", how="left").merge(m_ct.rename("_m"), on="district_id", how="left")
    # n_gold_deposits stays region-specific (USGS for Africa, MRDS elsewhere) so the
    # count is internally consistent within a region; has_gold is the UNION of both
    # sources so a district with gold in EITHER source is flagged (recovers African
    # districts where only MRDS has a record).
    gold["n_gold_deposits"] = np.where(gold["_afr"], gold["_u"].fillna(0), gold["_m"].fillna(0)).astype(int)
    gold["has_gold"] = ((gold["_u"].fillna(0) > 0) | (gold["_m"].fillna(0) > 0)).astype(int)
    out = out.merge(gold[["district_id", "n_gold_deposits", "has_gold"]], on="district_id", how="left")

    out = out.sort_values("district_id").reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    log.info("wrote %s: %d districts", OUT.name, len(out))
    log.info("has_oil_gas=1: %d | has_diamond=1: %d | has_lootable_diamond=1: %d | has_gold=1: %d | any mineral: %d",
             int(out["has_oil_gas"].sum()), int(out["has_diamond"].sum()), int(out["has_lootable_diamond"].sum()),
             int(out["has_gold"].sum()), int((out["n_mineral_deposits"] > 0).sum()))


if __name__ == "__main__":
    main()
