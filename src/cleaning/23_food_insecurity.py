#!/usr/bin/env python3
"""Aggregate FEWS NET IPC phase polygons to a district-year food-insecurity table.

Purpose
-------
Overlay the FEWS NET IPC-phase polygons (one geojson per country-date) with the
admin-2 spine and aggregate to district-year (see docs/CODEBOOK.md, "Food
insecurity"). The literal bridge between agricultural output and conflict:
subnational acute food stress. Coverage-masked (NaN where not monitored — never
zero-filled); Africa-heavy with Haiti the only strong Americas reach; ~2011+.

Method
------
Concatenate all geojsons into one GeoDataFrame (phase `value` + `year` from the
reporting date), reproject to equal-area, overlay with study districts, and take
the WORST (max) phase per district-year plus the area share in Crisis+ (phase>=3).

Inputs
------
    data/raw/fews/*.geojson  (per country-date, scenario=CS)
    data/interim/spine.gpkg (layer "spine"; EPSG:4326)

Output
------
    data/interim/food_insecurity.parquet   one row per observed (district_id, year)

Run
---
    .venv/bin/python src/cleaning/23_food_insecurity.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import country_converter as coco
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fews"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "food_insecurity.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("food_insecurity")

YMIN, YMAX = 1989, 2025
EQUAL_AREA = "EPSG:6933"


def load_all() -> gpd.GeoDataFrame:
    files = sorted(RAW.glob("*.geojson"))
    iso2s = sorted({f.stem.split("_")[0] for f in files})
    iso3_of = dict(zip(iso2s, coco.CountryConverter().convert(iso2s, src="ISO2", to="ISO3", not_found=None)))
    frames = []
    for f in files:
        try:
            g = gpd.read_file(f)
        except Exception:
            continue
        if not len(g) or "value" not in g.columns:
            continue
        date = g.get("reporting_date")
        if date is None:
            date = g.get("projection_start")
        g["year"] = pd.to_datetime(date, errors="coerce").dt.year
        g["phase"] = pd.to_numeric(g["value"], errors="coerce")  # "Not Mapped"/"Missing" -> NaN
        g["fews_iso3"] = iso3_of.get(f.stem.split("_")[0])       # source country (from filename)
        frames.append(g[["year", "phase", "fews_iso3", "geometry"]].dropna(subset=["year", "phase", "fews_iso3"]))
    if not frames:
        raise SystemExit(f"no usable FEWS geojsons in {RAW} — run src/acquisition/22_download_fews.py")
    out = pd.concat(frames, ignore_index=True)
    out = out[out["phase"].between(1, 5)]
    return gpd.GeoDataFrame(out, geometry="geometry", crs=frames[0].crs)


def main() -> None:
    ours = set(pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv").query("kept").iso3)
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "iso3", "geometry"]]
    spine = spine[spine["iso3"].isin(ours)].to_crs(EQUAL_AREA)
    spine["geometry"] = spine.geometry.make_valid()
    spine["district_area"] = spine.geometry.area

    fews = load_all().to_crs(EQUAL_AREA)
    fews["geometry"] = fews.geometry.make_valid()
    # make_valid can yield GeometryCollections -> explode to a uniform Polygon type
    # (overlay rejects mixed geometry); drop non-polygonal (zero-area) parts.
    fews = fews.explode(index_parts=False).reset_index(drop=True)
    fews = fews[fews.geom_type == "Polygon"].copy()
    fews["year"] = fews["year"].astype(int)
    fews = fews[fews["year"].between(YMIN, YMAX)]
    log.info("overlaying %d FEWS phase polygons x %d study districts...", len(fews), len(spine))

    inter = gpd.overlay(spine[["district_id", "iso3", "district_area", "geometry"]],
                        fews, how="intersection", keep_geom_type=True)
    # Keep only same-country overlaps (drop border slivers of a neighbour's FEWS unit).
    inter = inter[inter["iso3"] == inter["fews_iso3"]].copy()
    inter["area"] = inter.geometry.area

    g = inter.groupby(["district_id", "iso3", "year"])
    out = g.agg(ipc_phase_max=("phase", "max"),
                ipc_n_reports=("phase", "size"),
                _tot=("area", "sum")).reset_index()
    # Crisis(>=3) share of the district's MONITORED area (normalize by total overlap
    # area, NOT district_area: a district gets several FEWS reports per year whose
    # areas would otherwise sum past the district and push the share above 1).
    inter["_crisis_area"] = np.where(inter["phase"] >= 3, inter["area"], 0.0)
    crisis = inter.groupby(["district_id", "year"]).apply(
        lambda d: d["_crisis_area"].sum() / d["area"].sum(), include_groups=False
    ).rename("ipc_phase3plus_area_share").reset_index()
    modal = (inter.groupby(["district_id", "year", "phase"])["area"].sum().reset_index()
                  .sort_values("area").groupby(["district_id", "year"]).tail(1)
                  .rename(columns={"phase": "ipc_phase_modal"})[["district_id", "year", "ipc_phase_modal"]])
    out = out.merge(crisis, on=["district_id", "year"], how="left").merge(modal, on=["district_id", "year"], how="left")
    out["ipc_crisis_flag"] = (out["ipc_phase_max"] >= 3).astype(int)
    out["fews_covered"] = 1
    out = out.drop(columns="_tot").sort_values(["district_id", "year"]).reset_index(drop=True)
    out["ipc_phase_max"] = out["ipc_phase_max"].astype(int)
    out["ipc_phase_modal"] = out["ipc_phase_modal"].astype(int)
    out.to_parquet(OUT, index=False)

    log.info("wrote %s: %d district-years, %d districts, %d countries, %d-%d",
             OUT.name, len(out), out["district_id"].nunique(), out["iso3"].nunique(),
             int(out["year"].min()), int(out["year"].max()))
    log.info("crisis (phase>=3) district-years: %d | countries incl. Haiti: %s",
             int(out["ipc_crisis_flag"].sum()), "HTI" in set(out["iso3"]))


if __name__ == "__main__":
    main()
