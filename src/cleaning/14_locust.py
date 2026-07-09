#!/usr/bin/env python3
"""Aggregate desert-locust swarm + hopper-band observations to district-year.

Purpose
-------
Spatial-join the georeferenced gregarious-phase locust observations (swarms +
hopper bands) to the admin-2 spine and aggregate to district-year (see
docs/CODEBOOK.md, "Pest layer — Africa"). This is SURVEY/observation data, not a
census: it is populated only where locust survey teams operate (the desert-locust
belt: Sahel, Horn, N. Africa). Absence of a row is NOT locust-free — it is
not-surveyed — so the merge leaves non-belt district-years NaN, never zero.

Inputs
------
    data/raw/locust_hub/locust_swarms.csv
    data/raw/locust_hub/locust_bands.csv
    data/interim/spine.gpkg

Output
------
    data/interim/locust_district_year.parquet
        One row per observed (district_id, year).

Run
---
    .venv/bin/python src/cleaning/14_locust.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SWARMS = ROOT / "data" / "raw" / "locust_hub" / "locust_swarms.csv"
BANDS = ROOT / "data" / "raw" / "locust_hub" / "locust_bands.csv"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "locust_district_year.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("locust")


def main() -> None:
    df = pd.concat([pd.read_csv(SWARMS, low_memory=False),
                    pd.read_csv(BANDS, low_memory=False)], ignore_index=True)
    for c in ["lat", "lon", "area_treated_in_ha"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["year"] = pd.to_datetime(df["start_date"], errors="coerce").dt.year
    df = df.dropna(subset=["lat", "lon", "year"])
    df["year"] = df["year"].astype(int)
    df["area_treated_in_ha"] = df["area_treated_in_ha"].fillna(0.0)
    n_raw = len(df)

    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
    spine = gpd.read_file(SPINE)[["district_id", "iso3", "geometry"]].to_crs(4326)
    j = gpd.sjoin(pts, spine, how="inner", predicate="within")
    log.info("locust points joined to a district: %d/%d (%.1f%%)", len(j), n_raw, 100 * len(j) / n_raw)

    j["is_swarm"] = (j["category"] == "SWARM").astype(int)
    j["is_band"] = (j["category"] == "BAND").astype(int)
    g = j.groupby(["district_id", "iso3", "year"])
    dy = g.agg(
        dl_swarm_obs=("is_swarm", "sum"),
        dl_band_obs=("is_band", "sum"),
        dl_area_treated_ha=("area_treated_in_ha", "sum"),
    ).reset_index()
    dy["dl_gregarious_obs"] = dy["dl_swarm_obs"] + dy["dl_band_obs"]
    dy["dl_present_flag"] = 1  # every row is an observed presence

    # District-level outbreak timing: first year a gregarious swarm/band was seen.
    first = dy.groupby("district_id")["year"].min()
    dy["dl_first_gregarious_year"] = dy["district_id"].map(first)

    dy = dy.sort_values(["district_id", "year"]).reset_index(drop=True)
    dy.to_parquet(OUT, index=False)

    log.info("wrote %s: %d district-year rows", OUT.name, len(dy))
    log.info("districts: %d | countries: %d | years: %d-%d",
             dy["district_id"].nunique(), dy["iso3"].nunique(),
             int(dy["year"].min()), int(dy["year"].max()))
    log.info("total swarm obs: %d | band obs: %d", int(dy["dl_swarm_obs"].sum()), int(dy["dl_band_obs"].sum()))
    log.info("rows by year (top upsurge yrs):\n%s",
             dy.groupby("year")["dl_gregarious_obs"].sum().sort_values(ascending=False).head(8).to_string())
    log.info("top countries by district-years:\n%s", dy["iso3"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
