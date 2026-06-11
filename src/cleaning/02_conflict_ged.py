#!/usr/bin/env python3
"""Aggregate UCDP GED 26.1 fatal events to district-year by violence type.

Purpose
-------
Turn the raw UCDP GED 26.1 event CSV into the conflict layer of the panel:
point-located fatal organized-violence events spatially joined to the admin-2
spine and summed to district x year x violence-type counts and death tolls.
See docs/DATA_SOURCES.md, "UCDP Georeferenced Event Dataset".

Each GED row is one fatal event with a point (lat/lon, WGS84), a calendar
`year` (no event spans two years, so year aggregation is clean), a violence
type (1 state-based, 2 non-state, 3 one-sided), and best/low/high fatality
estimates plus a civilian-death count.

Inputs
------
    data/raw/ucdp_ged/ged261-csv.zip
        (produced by src/acquisition/02_download_ucdp_ged.py; inner member
         GEDEvent_v26_1.csv, 417,968 events, 49 columns, years 1989-2025)
    data/interim/spine.gpkg  (layer "spine")
        admin-2 polygon spine, EPSG:4326, key column district_id

Outputs
-------
    data/interim/conflict_ged_long.parquet
        Long form, one row per (district_id, iso3, year, type_of_violence):
            district_id, iso3, year, type_of_violence,
            n_events, deaths_best, deaths_low, deaths_high, deaths_civilians
        (iso3 is the spine's country code for the district the point fell in,
         not GED's event country, so it is consistent with the spine key.)
    data/interim/conflict_ged.parquet
        Wide form, one row per (district_id, iso3, year) with per-type columns
        (sb=state-based, ns=non-state, os=one-sided) plus totals:
            n_events_sb/ns/os/total,
            deaths_best_sb/ns/os/total,
            deaths_low_sb/ns/os/total,
            deaths_high_sb/ns/os/total,
            deaths_civilians_sb/ns/os/total

Both outputs are sorted deterministically (long by district_id, year,
type_of_violence; wide by district_id, year) so re-runs are byte-stable.

Row-level filters (logged, thresholds as constants below)
---------------------------------------------------------
  * WHERE_PREC_MAX = 3: keep events with where_prec in {1,2,3}
    (1 exact, 2 within 25 km, 3 ADM2 representative point). Events with
    where_prec 4-7 sit at ADM1/country/fuzzy/sea-air representative points;
    a naive polygon join would fabricate concentration in centroid districts,
    so they are dropped (registry fit-note + gotcha 1). Dropped count and
    percentage are logged.
  * Points that fall outside every spine polygon (sjoin 'within' miss) are
    reported with their count and share, then excluded from the aggregation
    (they cannot be assigned to a district_id).

Runtime
-------
~1-3 minutes (reading the spine GeoPackage and the within-join dominate).

How to run
----------
    .venv/bin/python src/cleaning/02_conflict_ged.py

Idempotent: outputs are rewritten in full each run from the immutable raw zip
and the spine.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ZIP = REPO_ROOT / "data" / "raw" / "ucdp_ged" / "ged261-csv.zip"
INNER_CSV = "GEDEvent_v26_1.csv"
SPINE_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
SPINE_LAYER = "spine"
OUT_LONG = REPO_ROOT / "data" / "interim" / "conflict_ged_long.parquet"
OUT_WIDE = REPO_ROOT / "data" / "interim" / "conflict_ged.parquet"

# Registry-pinned coverage facts; asserted on load (loud failure if violated).
EXPECTED_N_EVENTS = 417_968
EXPECTED_N_COLS = 49
EXPECTED_YEAR_MIN = 1989
EXPECTED_YEAR_MAX = 2025

# Row-level filter: geo-precision band kept for spatial join.
# where_prec 1=exact, 2=within 25km, 3=ADM2 representative point.
WHERE_PREC_MAX = 3

# Violence-type code -> short suffix used in the wide output.
# 1=state-based, 2=non-state, 3=one-sided (UCDP GED codebook).
VIOLENCE_SUFFIX = {1: "sb", 2: "ns", 3: "os"}

# Columns read from the CSV (subset of the 49) and aggregation measures.
USE_COLS = [
    "id",
    "year",
    "type_of_violence",
    "where_prec",
    "latitude",
    "longitude",
    "best",
    "low",
    "high",
    "deaths_civilians",
]
# Map GED death-estimate columns to the panel's death column names.
DEATH_RENAME = {
    "best": "deaths_best",
    "low": "deaths_low",
    "high": "deaths_high",
    # deaths_civilians already carries its final name.
}
MEASURE_COLS = ["deaths_best", "deaths_low", "deaths_high", "deaths_civilians"]


def log(msg: str) -> None:
    print(msg, flush=True)


def load_events() -> pd.DataFrame:
    """Read the GED CSV from the zip and assert registry coverage facts."""
    if not RAW_ZIP.exists():
        raise FileNotFoundError(
            f"Raw input missing: {RAW_ZIP}\n"
            "Run: .venv/bin/python src/acquisition/02_download_ucdp_ged.py"
        )
    log(f"Reading {RAW_ZIP} :: {INNER_CSV}")
    with zipfile.ZipFile(RAW_ZIP) as zf:
        # First read the header only to assert the 49-column width.
        with zf.open(INNER_CSV) as fh:
            header = pd.read_csv(fh, nrows=0)
        n_cols = len(header.columns)
        if n_cols != EXPECTED_N_COLS:
            raise ValueError(
                f"GED CSV has {n_cols} columns, expected {EXPECTED_N_COLS} "
                "(registry); schema changed, aborting."
            )
        missing = set(USE_COLS) - set(header.columns)
        if missing:
            raise ValueError(f"GED CSV missing expected columns: {sorted(missing)}")
        with zf.open(INNER_CSV) as fh:
            df = pd.read_csv(fh, usecols=USE_COLS)

    n_events = len(df)
    log(f"  events loaded: {n_events:,}")
    if n_events != EXPECTED_N_EVENTS:
        raise ValueError(
            f"GED CSV has {n_events:,} events, expected {EXPECTED_N_EVENTS:,} "
            "(registry); aborting."
        )

    ymin, ymax = int(df["year"].min()), int(df["year"].max())
    log(f"  year range: {ymin}-{ymax}")
    if ymin != EXPECTED_YEAR_MIN or ymax != EXPECTED_YEAR_MAX:
        raise ValueError(
            f"GED year range {ymin}-{ymax} != expected "
            f"{EXPECTED_YEAR_MIN}-{EXPECTED_YEAR_MAX} (registry); aborting."
        )

    # Guard: violence type is one of the three documented codes.
    bad_vt = set(df["type_of_violence"].unique()) - set(VIOLENCE_SUFFIX)
    if bad_vt:
        raise ValueError(
            f"Unexpected type_of_violence values: {sorted(bad_vt)}; "
            f"expected only {sorted(VIOLENCE_SUFFIX)}."
        )
    # Guard: coordinates are present and finite for every event.
    if df["latitude"].isna().any() or df["longitude"].isna().any():
        raise ValueError("GED rows with missing latitude/longitude; aborting.")
    return df


def main() -> int:
    df = load_events()

    # --- Row-level filter: geo-precision band --------------------------------
    n_before = len(df)
    keep_mask = df["where_prec"].between(1, WHERE_PREC_MAX, inclusive="both")
    n_keep = int(keep_mask.sum())
    n_drop = n_before - n_keep
    pct_drop = 100.0 * n_drop / n_before
    log(
        f"  WHERE_PREC filter (keep where_prec in 1..{WHERE_PREC_MAX}): "
        f"dropping {n_drop:,} of {n_before:,} events ({pct_drop:.2f}%); "
        f"keeping {n_keep:,}"
    )
    df = df.loc[keep_mask].copy()

    df = df.rename(columns=DEATH_RENAME)

    # --- Build event points (EPSG:4326) --------------------------------------
    events = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )

    # --- Load spine polygons -------------------------------------------------
    log(f"Reading spine {SPINE_GPKG} (layer '{SPINE_LAYER}')")
    spine = gpd.read_file(SPINE_GPKG, layer=SPINE_LAYER)
    if spine.crs is None or spine.crs.to_epsg() != 4326:
        raise ValueError(f"Spine CRS is {spine.crs}; expected EPSG:4326.")
    spine = spine[["district_id", "iso3", "geometry"]].copy()
    log(f"  spine districts: {len(spine):,}")

    # --- Spatial join: points within polygons --------------------------------
    log("Spatial join (predicate='within') ...")
    joined = gpd.sjoin(
        events,
        spine,
        how="left",
        predicate="within",
    )
    # A point can sit on a shared boundary and match >1 polygon; keep the first
    # match deterministically (by district_id) so each event maps to one unit.
    joined = (
        joined.sort_values(["id", "district_id"], kind="mergesort")
        .drop_duplicates(subset="id", keep="first")
    )
    if len(joined) != len(events):
        raise AssertionError(
            f"Join produced {len(joined):,} rows for {len(events):,} events "
            "after dedup; expected 1:1."
        )

    n_pts = len(joined)
    unmatched_mask = joined["district_id"].isna()
    n_unmatched = int(unmatched_mask.sum())
    pct_unmatched = 100.0 * n_unmatched / n_pts
    log(
        f"  points outside all spine polygons: {n_unmatched:,} of {n_pts:,} "
        f"({pct_unmatched:.2f}%) -- excluded from aggregation"
    )
    matched = joined.loc[~unmatched_mask].copy()
    log(f"  matched events kept: {len(matched):,}")

    # --- Aggregate to district x year x type_of_violence (long) --------------
    matched["n_events"] = 1
    long_df = (
        matched.groupby(["district_id", "iso3", "year", "type_of_violence"], sort=False)
        .agg(
            n_events=("n_events", "sum"),
            deaths_best=("deaths_best", "sum"),
            deaths_low=("deaths_low", "sum"),
            deaths_high=("deaths_high", "sum"),
            deaths_civilians=("deaths_civilians", "sum"),
        )
        .reset_index()
    )
    long_df["year"] = long_df["year"].astype("int64")
    long_df["type_of_violence"] = long_df["type_of_violence"].astype("int64")
    for c in ["n_events", *MEASURE_COLS]:
        long_df[c] = long_df[c].astype("int64")

    long_df = long_df.sort_values(
        ["district_id", "year", "type_of_violence"], kind="mergesort"
    ).reset_index(drop=True)

    long_cols = [
        "district_id",
        "iso3",
        "year",
        "type_of_violence",
        "n_events",
        "deaths_best",
        "deaths_low",
        "deaths_high",
        "deaths_civilians",
    ]
    long_df = long_df[long_cols]

    OUT_LONG.parent.mkdir(parents=True, exist_ok=True)
    long_df.to_parquet(OUT_LONG, index=False)
    log(f"Wrote {OUT_LONG} ({len(long_df):,} rows)")

    # --- Wide form: one row per district-year, columns per violence type -----
    measures = ["n_events", *MEASURE_COLS]
    wide = long_df.copy()
    wide["vt"] = wide["type_of_violence"].map(VIOLENCE_SUFFIX)

    pivot = wide.pivot_table(
        index=["district_id", "iso3", "year"],
        columns="vt",
        values=measures,
        aggfunc="sum",
        fill_value=0,
    )
    # Flatten the (measure, vt) MultiIndex columns to "measure_vt".
    pivot.columns = [f"{measure}_{vt}" for measure, vt in pivot.columns]
    pivot = pivot.reset_index()

    # Ensure every measure x type column exists even if a type never occurs.
    for measure in measures:
        for vt in VIOLENCE_SUFFIX.values():
            col = f"{measure}_{vt}"
            if col not in pivot.columns:
                pivot[col] = 0

    # Totals across violence types.
    for measure in measures:
        type_cols = [f"{measure}_{vt}" for vt in VIOLENCE_SUFFIX.values()]
        pivot[f"{measure}_total"] = pivot[type_cols].sum(axis=1)

    # Deterministic column order: keys, then per measure (sb, ns, os, total).
    ordered_cols = ["district_id", "iso3", "year"]
    for measure in measures:
        for vt in ["sb", "ns", "os", "total"]:
            ordered_cols.append(f"{measure}_{vt}")
    pivot = pivot[ordered_cols]

    for c in ordered_cols:
        if c not in ("district_id", "iso3"):
            pivot[c] = pivot[c].astype("int64")

    pivot = pivot.sort_values(
        ["district_id", "year"], kind="mergesort"
    ).reset_index(drop=True)

    pivot.to_parquet(OUT_WIDE, index=False)
    log(f"Wrote {OUT_WIDE} ({len(pivot):,} rows)")

    # --- Cross-check: total deaths_best by decade ----------------------------
    by_decade = (
        matched.assign(decade=(matched["year"] // 10 * 10))
        .groupby("decade")["deaths_best"]
        .sum()
        .astype("int64")
    )

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== CONFLICT GED SUMMARY ===")
    log(f"  events pre-filter:        {n_before:,}")
    log(f"  events post where_prec:   {n_keep:,} (dropped {n_drop:,}, {pct_drop:.2f}%)")
    log(f"  unmatched points:         {n_unmatched:,} ({pct_unmatched:.2f}%)")
    log(f"  matched events:           {len(matched):,}")
    log(f"  long rows (dist-yr-type): {len(long_df):,}")
    log(f"  wide rows (dist-yr):      {len(pivot):,}")
    log(f"  distinct districts (wide):{pivot['district_id'].nunique():,}")
    log(f"  year range (matched):     {int(matched['year'].min())}-{int(matched['year'].max())}")
    log("  total deaths_best by decade (matched events):")
    for dec, val in by_decade.items():
        log(f"      {int(dec)}s: {int(val):,}")
    log(f"  total deaths_best (matched, all years): {int(by_decade.sum()):,}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
