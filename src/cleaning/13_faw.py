#!/usr/bin/env python3
"""Aggregate FAMEWS fall-armyworm trap records to a district-year table.

Purpose
-------
Spatial-join the georeferenced FAMEWS trap checks to the admin-2 spine and
aggregate to district-year (see docs/CODEBOOK.md, "Pest layer — Africa"). This
is MONITORING data, not damage: it is populated only where FAMEWS traps were
run (Africa, ~2018-2023). Absence of a row is NOT pest-free — it is not-observed
— so the merge leaves non-monitored district-years NaN, never zero-filled.

Inputs
------
    data/raw/famews_faw/famews_traps.csv   (dated georeferenced trap checks)
    data/interim/spine.gpkg                (CGAZ admin-2 polygons, EPSG:4326)

Output
------
    data/interim/faw_district_year.parquet
        One row per observed (district_id, year); columns documented in codebook.

Run
---
    .venv/bin/python src/cleaning/13_faw.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FAW = ROOT / "data" / "raw" / "famews_faw" / "famews_traps.csv"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "faw_district_year.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("faw")


def main() -> None:
    faw = pd.read_csv(FAW)
    faw.columns = [c.strip() for c in faw.columns]
    for c in ["lat", "long", "faw_confirmed_count", "faw_suspected_plus_confirmed_count"]:
        faw[c] = pd.to_numeric(faw[c], errors="coerce")
    faw["date"] = pd.to_datetime(faw["date"], errors="coerce")
    faw["year"] = faw["date"].dt.year
    faw = faw.dropna(subset=["lat", "long", "year"])
    faw["year"] = faw["year"].astype(int)
    n_raw = len(faw)

    pts = gpd.GeoDataFrame(faw, geometry=gpd.points_from_xy(faw["long"], faw["lat"]), crs="EPSG:4326")
    spine = gpd.read_file(SPINE)[["district_id", "iso3", "geometry"]].to_crs(4326)
    j = gpd.sjoin(pts, spine, how="inner", predicate="within")
    log.info("FAW points joined to a district: %d/%d (%.1f%%)", len(j), n_raw, 100 * len(j) / n_raw)

    # District-year aggregation.
    g = j.groupby(["district_id", "iso3", "year"])
    dy = g.agg(
        faw_n_trap_checks=("id", "size"),
        faw_confirmed_sum=("faw_confirmed_count", "sum"),
        faw_suspconf_sum=("faw_suspected_plus_confirmed_count", "sum"),
    ).reset_index()
    dy["faw_present"] = (dy["faw_confirmed_sum"] > 0).astype(int)
    dy["faw_catch_rate"] = dy["faw_confirmed_sum"] / dy["faw_n_trap_checks"]

    # District-level invasion-front timing: first year with a confirmed detection.
    det = dy[dy["faw_confirmed_sum"] > 0].groupby("district_id")["year"].min()
    dy["faw_first_detection_year"] = dy["district_id"].map(det)

    dy = dy.sort_values(["district_id", "year"]).reset_index(drop=True)
    dy.to_parquet(OUT, index=False)

    log.info("wrote %s: %d district-year rows", OUT.name, len(dy))
    log.info("districts: %d | countries: %d | years: %d-%d",
             dy["district_id"].nunique(), dy["iso3"].nunique(),
             int(dy["year"].min()), int(dy["year"].max()))
    log.info("district-years with a confirmed detection: %d", int((dy["faw_present"] == 1).sum()))
    log.info("districts that ever detected FAW: %d", int(det.notna().sum()))
    log.info("top countries by rows:\n%s", dy["iso3"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
