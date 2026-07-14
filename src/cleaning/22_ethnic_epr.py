#!/usr/bin/env python3
"""Build the district-year ethnic-exclusion table (EPR-Core + GeoEPR).

Purpose
-------
Overlay GeoEPR ethnic-group settlement polygons with the admin-2 spine and join
each group's EPR-Core political status per year, to measure how much of a
district is settled by politically EXCLUDED groups (see docs/CODEBOOK.md,
"Ethnic exclusion"). The strongest subnational political driver of civil
conflict; adds within-country variation the (country-level) colonial layer lacks.

Method
------
- Restrict the spine to the 79 study countries (GeoEPR is dense in Africa,
  sparse in the Americas — many countries have no politically-relevant groups).
- Reproject spine + GeoEPR to an equal-area CRS (EPSG:6933) for correct areas.
- Overlay (intersection) → per (district, group-period) area.
- Expand group-periods and EPR-Core status-periods to YEARS, join on
  (gwgroupid, year), aggregate to district-year.
- NaN where no GeoEPR polygon overlaps (never 0-filled); TIME-VARYING via EPR
  periods; post-2021 years NaN (dataset ends 2021).

Inputs
------
    data/raw/epr/EPR-2021.csv, data/raw/epr/GeoEPR-2021.shp
    data/interim/spine.gpkg (layer "spine"; EPSG:4326)
    reference/iso3_region_crosswalk.csv

Output
------
    data/interim/ethnic_epr.parquet   one row per (district_id, year)

Run
---
    .venv/bin/python src/cleaning/22_ethnic_epr.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import country_converter as coco
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "data" / "raw" / "epr" / "EPR-2021.csv"
GEO = ROOT / "data" / "raw" / "epr" / "GeoEPR-2021.shp"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "ethnic_epr.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("ethnic_epr")

YMIN, YMAX = 1989, 2025
EQUAL_AREA = "EPSG:6933"                       # World Cylindrical Equal Area (metres)
EXCLUDED = {"POWERLESS", "DISCRIMINATED", "SELF-EXCLUSION"}


def expand_years(df: pd.DataFrame, lo="from", hi="to") -> pd.DataFrame:
    """Explode [lo, hi] period rows into one row per year within [YMIN, YMAX]."""
    df = df.copy()
    df[lo] = df[lo].clip(lower=YMIN)
    df[hi] = df[hi].clip(upper=YMAX)
    df = df[df[lo] <= df[hi]]
    df["year"] = df.apply(lambda r: range(int(r[lo]), int(r[hi]) + 1), axis=1)
    return df.explode("year").astype({"year": int})


def main() -> None:
    ours = set(pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv").query("kept").iso3)
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "iso3", "geometry"]]
    spine = spine[spine["iso3"].isin(ours)].to_crs(EQUAL_AREA)
    spine["geometry"] = spine.geometry.make_valid()   # GeoEPR/CGAZ have some invalid rings
    spine["district_area"] = spine.geometry.area
    log.info("study districts: %d", len(spine))

    geo = gpd.read_file(GEO).to_crs(EQUAL_AREA)[["gwgroupid", "statename", "from", "to", "geometry"]]
    geo = geo[(geo["to"] >= YMIN) & (geo["from"] <= YMAX)]
    geo["geometry"] = geo.geometry.make_valid()
    # Home country of each GeoEPR group (settlement polygons cross borders).
    cc = coco.CountryConverter()
    geo["group_iso3"] = cc.convert(geo["statename"].tolist(), src="regex", to="ISO3", not_found=None)

    log.info("overlaying %d GeoEPR polygons x %d districts...", len(geo), len(spine))
    inter = gpd.overlay(spine[["district_id", "iso3", "district_area", "geometry"]],
                        geo, how="intersection", keep_geom_type=True)
    # Keep only same-country overlaps: a group's polygon spilling across an
    # international border must NOT inject a neighbour country's EPR status.
    inter = inter[inter["iso3"] == inter["group_iso3"]].copy()
    inter["area"] = inter.geometry.area
    dg = inter[["district_id", "iso3", "district_area", "gwgroupid", "from", "to", "area"]].copy()

    # Expand group-period overlaps to years, then attach EPR-Core status by (gwgroupid, year).
    dgy = expand_years(dg)  # (district_id, iso3, district_area, gwgroupid, area, year)
    core = pd.read_csv(CORE)[["gwgroupid", "from", "to", "status"]]
    core["status"] = core["status"].astype(str).str.upper().str.strip()
    corey = expand_years(core)[["gwgroupid", "year", "status"]]
    dgy = dgy.merge(corey, on=["gwgroupid", "year"], how="left")
    dgy["is_excluded"] = dgy["status"].isin(EXCLUDED)

    # Aggregate to district-year.
    dgy["grp_share"] = dgy["area"] / dgy["district_area"]
    g = dgy.groupby(["district_id", "iso3", "year"])
    out = g.agg(
        n_groups_overlap=("gwgroupid", "nunique"),
        share_area_excluded=("grp_share", lambda s: float(np.clip(s[dgy.loc[s.index, "is_excluded"]].sum(), 0, 1))),
        _tot_area=("area", "sum"),
    ).reset_index()
    # Ethnic fractionalization = 1 - sum(p_g^2), p_g = group area / total group area in district.
    frac = (dgy.assign(a=dgy["area"])
              .groupby(["district_id", "year"])
              .apply(lambda d: 1.0 - ((d.groupby("gwgroupid")["a"].sum() / d["a"].sum()) ** 2).sum(),
                     include_groups=False)
              .rename("ethnic_fractionalization").reset_index())
    out = out.merge(frac, on=["district_id", "year"], how="left").drop(columns="_tot_area")
    out["any_excluded"] = (out["share_area_excluded"] > 0).astype(int)

    out = out.sort_values(["district_id", "year"]).reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    log.info("wrote %s: %d district-years, %d districts, %d countries, %d-%d",
             OUT.name, len(out), out["district_id"].nunique(), out["iso3"].nunique(),
             int(out["year"].min()), int(out["year"].max()))
    log.info("any_excluded=1: %d district-years | mean share_excluded (where >0): %.2f",
             int(out["any_excluded"].sum()), out.loc[out["share_area_excluded"] > 0, "share_area_excluded"].mean())


if __name__ == "__main__":
    main()
