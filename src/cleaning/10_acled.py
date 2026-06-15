#!/usr/bin/env python3
"""Aggregate ACLED events to district-year by event type (admin-2 spatial join).

Purpose
-------
Turn the raw ACLED event parquet files (per year, downloaded by
src/acquisition/10_download_acled.py) into the ACLED layer of the panel:
geolocated events spatially joined to the admin-2 spine and summed to
district x year, split by ACLED event_type. Unlike UCDP GED (fatal events
only), ACLED captures NON-LETHAL unrest -- protests, riots, and violence
against civilians that caused no deaths -- which is the point of adding it.
See docs/DATA_SOURCES.md, "ACLED".

Inputs
------
    data/raw/acled/acled_<YEAR>.parquet  (all years; produced by acquisition)
    data/interim/spine.gpkg  (layer "spine"; EPSG:4326; key district_id, iso3)

Outputs
-------
    data/interim/acled_district_year.parquet
        Wide, one row per (district_id, iso3, year) that has >=1 matched event:
            district_id, iso3, year,
            acled_events_total,
            acled_events_battles, _protests, _riots, _vac, _explosions, _strategic,
            acled_fatalities    (sum of ACLED fatalities; ACLED is conservative)
    data/interim/acled_coverage.parquet
        One row per iso3 (spine country) observed in the matched ACLED data:
            iso3, acled_first_year, acled_last_year
        (the OBSERVED data span; the merge combines this with the authoritative
         per-country coverage-start reference to build the zero-fill mask.)

Row-level filter (logged)
-------------------------
  * GEO_PRECISION_MAX = 2: keep events with geo_precision in {1, 2}
    (1 = exact coordinates, 2 = coordinates near the event / small area).
    geo_precision 3 means only the region/admin1 is known and the coordinates
    are an admin centroid; a naive polygon join would fabricate concentration
    in centroid districts, so level-3 events are dropped (mirrors the UCDP GED
    where_prec<=3 logic, adapted to ACLED's 3-level scale). Dropped count logged.
  * Points outside every spine polygon (sjoin 'within' miss) are reported and
    excluded (cannot be assigned a district_id).

Runtime
-------
Several minutes (reading the spine + the within-join over millions of points).

How to run
----------
    .venv/bin/python src/cleaning/10_acled.py

Idempotent: outputs rewritten in full each run from the raw parquet + spine,
with a fixed sort order, so re-runs are byte-stable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import country_converter as coco
import geopandas as gpd
import pandas as pd

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "acled"
SPINE_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
SPINE_LAYER = "spine"
OUT_WIDE = REPO_ROOT / "data" / "interim" / "acled_district_year.parquet"
OUT_COVERAGE = REPO_ROOT / "data" / "interim" / "acled_coverage.parquet"

# Keep events whose coordinates are point-accurate enough for an admin-2 join.
GEO_PRECISION_MAX = 2

# ACLED event_type -> short suffix used in the wide output columns. The six
# canonical 2025 event types; any unseen value fails loudly (schema guard).
EVENT_TYPE_SUFFIX = {
    "Battles": "battles",
    "Protests": "protests",
    "Riots": "riots",
    "Violence against civilians": "vac",
    "Explosions/Remote violence": "explosions",
    "Strategic developments": "strategic",
}
SUFFIXES = list(EVENT_TYPE_SUFFIX.values())


def log(msg: str) -> None:
    print(msg, flush=True)


def load_events() -> pd.DataFrame:
    """Read and concatenate every acled_<year>.parquet; coerce dtypes."""
    files = sorted(RAW_DIR.glob("acled_*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No ACLED raw parquet in {RAW_DIR}.\n"
            "Run: .venv/bin/python src/acquisition/10_download_acled.py"
        )
    log(f"Reading {len(files)} ACLED year files ...")
    frames = []
    for f in files:
        df = pd.read_parquet(f)
        if not df.empty:
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    log(f"  raw events: {len(df):,} ({files[0].stem}..{files[-1].stem})")

    # Coerce types (the API returns lat/lon and some numerics as strings).
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["geo_precision"] = pd.to_numeric(df["geo_precision"], errors="coerce").astype("Int64")
    df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0).astype("int64")
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype("int64")

    if df["latitude"].isna().any() or df["longitude"].isna().any():
        n = int(df["latitude"].isna().sum() + df["longitude"].isna().sum())
        raise ValueError(f"{n} ACLED rows with unpar-seable latitude/longitude; aborting.")

    # Guard: every event_type is one of the six documented values.
    bad = set(df["event_type"].unique()) - set(EVENT_TYPE_SUFFIX)
    if bad:
        raise ValueError(
            f"Unexpected event_type values {sorted(bad)}; ACLED taxonomy may "
            "have changed -- update EVENT_TYPE_SUFFIX. Aborting."
        )
    # De-duplicate on the stable event id (a re-pull could overlap years).
    before = len(df)
    df = df.drop_duplicates(subset="event_id_cnty", keep="first")
    if len(df) != before:
        log(f"  dropped {before - len(df):,} duplicate event_id_cnty rows")
    return df


def compute_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country ACLED coverage window from ACLED's OWN country coding.

    Coverage answers "in which years did ACLED monitor country C?", which must
    come from ACLED's `iso` field (numeric ISO 3166-1, mapped to ISO3), NOT from
    which spine polygon an event falls in. Otherwise a handful of border /
    disputed-territory events (e.g. a 2010 Kashmir event ACLED codes as Pakistan
    but whose coordinates sit inside India's polygon) would make a country look
    "covered" years before ACLED actually began monitoring it -- fabricating
    leading-edge zeros across that country's interior districts. Uses ALL events
    (any geo_precision) so coverage is not narrowed by the admin-2 geo filter.
    Returns iso3, acled_first_year, acled_last_year.
    """
    isos = sorted(int(i) for i in pd.unique(df["iso"].dropna()))
    cc = coco.CountryConverter()
    mapped = cc.convert(isos, src="ISOnumeric", to="ISO3", not_found=None)
    num_to_iso3 = {n: m for n, m in zip(isos, mapped) if m is not None}
    unmapped = [n for n in isos if n not in num_to_iso3]
    if unmapped:
        log(f"  coverage: {len(unmapped)} ACLED numeric iso codes did not map to "
            f"ISO3 and are excluded from the coverage table: {unmapped}")
    acled_iso3 = df["iso"].map(lambda v: num_to_iso3.get(int(v)) if pd.notna(v) else None)
    cov_src = df.assign(_iso3=acled_iso3).dropna(subset=["_iso3"])
    coverage = (
        cov_src.groupby("_iso3")["year"]
        .agg(acled_first_year="min", acled_last_year="max")
        .reset_index().rename(columns={"_iso3": "iso3"})
        .sort_values("iso3", kind="mergesort").reset_index(drop=True)
    )
    coverage["acled_first_year"] = coverage["acled_first_year"].astype("int64")
    coverage["acled_last_year"] = coverage["acled_last_year"].astype("int64")
    return coverage


def main() -> int:
    df = load_events()

    # --- coverage window per country (from ACLED's own country coding) --------
    coverage = compute_coverage(df)

    # --- geo-precision filter ------------------------------------------------
    n_before = len(df)
    keep = df["geo_precision"].between(1, GEO_PRECISION_MAX, inclusive="both")
    n_keep = int(keep.sum())
    n_drop = n_before - n_keep
    log(f"  GEO_PRECISION filter (keep 1..{GEO_PRECISION_MAX}): dropping "
        f"{n_drop:,} of {n_before:,} ({100*n_drop/n_before:.2f}%); keeping {n_keep:,}")
    df = df.loc[keep].copy()

    # --- build event points (EPSG:4326) --------------------------------------
    events = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )

    # --- spine ---------------------------------------------------------------
    log(f"Reading spine {SPINE_GPKG} (layer '{SPINE_LAYER}') ...")
    spine = gpd.read_file(SPINE_GPKG, layer=SPINE_LAYER)
    if spine.crs is None or spine.crs.to_epsg() != 4326:
        raise ValueError(f"Spine CRS is {spine.crs}; expected EPSG:4326.")
    spine = spine[["district_id", "iso3", "geometry"]].copy()
    log(f"  spine districts: {len(spine):,}")

    # --- spatial join (within) -----------------------------------------------
    log("Spatial join (predicate='within') ...")
    joined = gpd.sjoin(events, spine, how="left", predicate="within")
    # A point on a shared boundary can match >1 polygon; keep the first match
    # deterministically (by district_id) so each event maps to one unit.
    joined = (
        joined.sort_values(["event_id_cnty", "district_id"], kind="mergesort")
        .drop_duplicates(subset="event_id_cnty", keep="first")
    )
    n_pts = len(joined)
    unmatched = joined["district_id"].isna()
    n_un = int(unmatched.sum())
    log(f"  points outside all spine polygons: {n_un:,} of {n_pts:,} "
        f"({100*n_un/n_pts:.2f}%) -- excluded")
    matched = joined.loc[~unmatched].copy()
    log(f"  matched events: {len(matched):,}")

    # --- aggregate to district-year x event_type -----------------------------
    matched["suffix"] = matched["event_type"].map(EVENT_TYPE_SUFFIX)
    matched["one"] = 1

    counts = (
        matched.pivot_table(
            index=["district_id", "iso3", "year"], columns="suffix",
            values="one", aggfunc="sum", fill_value=0,
        )
    )
    counts.columns = [f"acled_events_{c}" for c in counts.columns]
    counts = counts.reset_index()
    # Ensure every event-type column exists even if a type never matched.
    for suf in SUFFIXES:
        col = f"acled_events_{suf}"
        if col not in counts.columns:
            counts[col] = 0

    fatal = (
        matched.groupby(["district_id", "iso3", "year"], as_index=False)["fatalities"]
        .sum().rename(columns={"fatalities": "acled_fatalities"})
    )

    wide = counts.merge(fatal, on=["district_id", "iso3", "year"], validate="1:1")
    type_cols = [f"acled_events_{s}" for s in SUFFIXES]
    wide["acled_events_total"] = wide[type_cols].sum(axis=1)

    ordered = (["district_id", "iso3", "year", "acled_events_total"]
               + type_cols + ["acled_fatalities"])
    wide = wide[ordered]
    for c in ordered:
        if c not in ("district_id", "iso3"):
            wide[c] = wide[c].astype("int64")
    wide = wide.sort_values(["district_id", "year"], kind="mergesort").reset_index(drop=True)

    OUT_WIDE.parent.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(OUT_WIDE, index=False)
    log(f"Wrote {OUT_WIDE} ({len(wide):,} rows)")

    # --- coverage per country (computed above from ACLED's country coding) ---
    coverage.to_parquet(OUT_COVERAGE, index=False)
    log(f"Wrote {OUT_COVERAGE} ({len(coverage):,} countries; "
        f"ACLED-coded coverage windows)")

    # --- summary -------------------------------------------------------------
    log("")
    log("=== ACLED CLEANING SUMMARY ===")
    log(f"  matched events:        {len(matched):,}")
    log(f"  district-years:        {len(wide):,}")
    log(f"  distinct districts:    {wide['district_id'].nunique():,}")
    log(f"  distinct countries:    {wide['iso3'].nunique()}")
    log(f"  year range (matched):  {int(matched['year'].min())}-{int(matched['year'].max())}")
    log("  events by type (matched):")
    for suf in SUFFIXES:
        log(f"      {suf:12s}: {int(wide[f'acled_events_{suf}'].sum()):,}")
    log(f"  total ACLED fatalities: {int(wide['acled_fatalities'].sum()):,}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
