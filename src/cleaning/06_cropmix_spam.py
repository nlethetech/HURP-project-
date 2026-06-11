#!/usr/bin/env python3
"""Aggregate SPAM 2020 harvested-area pixels to per-district crop mix.

Purpose
-------
Turn the SPAM 2020 v2.0 Release 2 GLOBAL harvested-area grid (all technologies)
into a tidy per-district crop-mix table: for each admin-2 spine unit, the
harvested area (ha) of each of the 46 SPAM crops and that crop's share of the
district's total harvested area. These shares are the time-invariant local
crop-mix weights used to combine crop-specific exposure across the panel
(see docs/DATA_SOURCES.md, "SPAM / MapSPAM").

Method: each SPAM pixel carries the longitude/latitude of its cell centroid and
one harvested-area column per crop. Pixels are turned into points, spatially
joined to the spine polygons (point-in-polygon), and each crop's area is summed
within each district. Shares are computed per district over its own total.

Variable / technology choice
----------------------------
The harvested-area zip contains three technology splits: H_TA (all
technologies / complete crop), H_TI (irrigated), H_TR (rainfed, = TA - TI).
This script uses H_TA, the all-technologies layer, per the task spec.

Note on the "*_A" wording: in SPAM file naming the variable code for harvested
area is "H" (the README's variable table uses "A" for *physical* area and "H"
for harvested area). The all-technologies harvested-area file is therefore
spam2020V2r2_global_H_TA.csv, which is the file loaded here.

Inputs
------
    data/raw/spam2020/spam2020V2r2_global_harvested_area.csv.zip
        (produced by src/acquisition/06_download_spam.py; the member
         spam2020V2r2_global_harvested_area/spam2020V2r2_global_H_TA.csv is
         read. Columns: grid_code, x, y, FIPS0/1/2, ADM0/1/2_NAME, + 46 crop
         harvested-area columns in hectares.)
    data/raw/spam2020/Readme_SPAM2020V2r2.txt
        (the release ReadMe; its crop lookup table maps the 4-letter SPAM codes
         to full crop names. Parsed at runtime — crop names are NOT hardcoded.)
    data/interim/spine.gpkg  (layer "spine"; admin-2 polygons, EPSG:4326)

Outputs
-------
    data/interim/cropmix_spam2020.parquet
        One row per (district_id, crop) with nonzero harvested area:
            district_id   (str)    spine shapeID
            crop          (str)    SPAM 4-letter code + " " + full name
                                   e.g. "whea Wheat"
            harv_area_ha  (float)  summed harvested area (ha) in the district
            crop_share    (float)  harv_area_ha / district total harvested area
    Sorted by (district_id, crop) for byte-stable re-runs.

Row-level handling (logged; thresholds as constants below)
----------------------------------------------------------
  * Pixels that fall outside every spine polygon (e.g. small coastline/centroid
    offsets, or land the spine does not resolve to admin-2) are counted and
    their harvested area is reported as an unmatched share, then dropped.
  * (district, crop) pairs with zero summed harvested area are dropped (the long
    table keeps only crops actually grown in the district).

Runtime
-------
~2-6 minutes (reading ~965k-row CSV, building points, spatial join, aggregate).

How to run
----------
    .venv/bin/python src/cleaning/06_cropmix_spam.py

Idempotent: the output parquet is rewritten in full each run from the immutable
raw zip and spine.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import points as shapely_points

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "spam2020"
HARV_ZIP = RAW_DIR / "spam2020V2r2_global_harvested_area.csv.zip"
README = RAW_DIR / "Readme_SPAM2020V2r2.txt"
SPINE_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
SPINE_LAYER = "spine"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "cropmix_spam2020.parquet"

# Member CSV inside the zip: harvested area, all technologies (complete crop).
CSV_MEMBER = (
    "spam2020V2r2_global_harvested_area/spam2020V2r2_global_H_TA.csv"
)

# Non-crop identifier columns at the front of the SPAM CSV.
ID_COLS = ["grid_code", "x", "y", "FIPS0", "FIPS1", "FIPS2",
           "ADM0_NAME", "ADM1_NAME", "ADM2_NAME"]
LON_COL = "x"
LAT_COL = "y"

# Expected number of SPAM crops in the 2020 release (sanity guard).
EXPECTED_N_CROPS = 46

# Spatial-join predicate: a pixel centroid is assigned to the polygon it lies in.
SJOIN_PREDICATE = "within"

FINAL_COLS = ["district_id", "crop", "harv_area_ha", "crop_share"]
SORT_COLS = ["district_id", "crop"]


def log(msg: str) -> None:
    print(msg, flush=True)


def parse_crop_lookup(readme_path: Path) -> dict[str, str]:
    """Parse the ReadMe crop table -> {4-letter SPAM code: full crop name}.

    Lines look like: '1\twhea\tWheat' (numeric id, code, name). Crop names are
    taken verbatim from the authoritative ReadMe (never hardcoded here).
    """
    if not readme_path.exists():
        raise FileNotFoundError(
            f"ReadMe missing: {readme_path}\n"
            "Run: .venv/bin/python src/acquisition/06_download_spam.py"
        )
    txt = readme_path.read_text(encoding="utf-8")
    pat = re.compile(r"^\s*(\d{1,2})\s+([a-z]{4})\s+(.+?)\s*$")
    lookup: dict[str, str] = {}
    for line in txt.splitlines():
        m = pat.match(line)
        if m:
            code, name = m.group(2), m.group(3)
            lookup[code] = name
    if len(lookup) != EXPECTED_N_CROPS:
        raise ValueError(
            f"Parsed {len(lookup)} crops from ReadMe, expected "
            f"{EXPECTED_N_CROPS}; the ReadMe layout may have changed."
        )
    return lookup


def main() -> int:
    if not HARV_ZIP.exists():
        raise FileNotFoundError(
            f"Raw input missing: {HARV_ZIP}\n"
            "Run: .venv/bin/python src/acquisition/06_download_spam.py"
        )
    if not SPINE_GPKG.exists():
        raise FileNotFoundError(f"Spine missing: {SPINE_GPKG}")

    crop_lookup = parse_crop_lookup(README)
    log(f"Parsed {len(crop_lookup)} SPAM crop codes from ReadMe")

    # --- Load the harvested-area CSV (all technologies) from inside the zip ---
    log(f"Reading {CSV_MEMBER} from {HARV_ZIP.name}")
    with zipfile.ZipFile(HARV_ZIP) as zf:
        names = zf.namelist()
        if CSV_MEMBER not in names:
            raise FileNotFoundError(
                f"Expected member not in zip: {CSV_MEMBER}\n"
                f"Zip contains: {names}"
            )
        with zf.open(CSV_MEMBER) as fh:
            df = pd.read_csv(fh)
    log(f"  pixels (rows): {len(df):,}; columns: {len(df.columns)}")

    # Guard the schema.
    missing_id = [c for c in ID_COLS if c not in df.columns]
    if missing_id:
        raise ValueError(f"SPAM CSV missing identifier columns: {missing_id}")

    crop_cols = [c for c in df.columns if c not in ID_COLS]
    if len(crop_cols) != EXPECTED_N_CROPS:
        raise ValueError(
            f"Found {len(crop_cols)} crop columns, expected {EXPECTED_N_CROPS}: "
            f"{crop_cols}"
        )
    unknown = [c for c in crop_cols if c not in crop_lookup]
    if unknown:
        raise ValueError(
            f"Crop columns not in ReadMe lookup: {unknown}; cannot label."
        )

    # SPAM harvested area is in hectares (ReadMe + SPAM convention).
    for c in crop_cols:
        df[c] = pd.to_numeric(df[c], errors="raise")

    global_totals = {c: float(df[c].sum()) for c in crop_cols}

    # --- Build points and spatially join to the spine -----------------------
    log("Building pixel-centroid points (EPSG:4326)")
    geom = shapely_points(df[LON_COL].to_numpy(), df[LAT_COL].to_numpy())
    pts = gpd.GeoDataFrame(
        df[[*crop_cols]].copy(),
        geometry=geom,
        crs="EPSG:4326",
    )
    pts["pixel_idx"] = range(len(pts))

    log(f"Loading spine polygons from {SPINE_GPKG.name}")
    spine = gpd.read_file(SPINE_GPKG, layer=SPINE_LAYER)[["district_id", "geometry"]]
    if spine.crs is None or spine.crs.to_epsg() != 4326:
        raise ValueError(f"Spine CRS is {spine.crs}; expected EPSG:4326.")
    log(f"  spine polygons: {len(spine):,}")

    log(f"Spatial join (predicate='{SJOIN_PREDICATE}') ...")
    joined = gpd.sjoin(pts, spine, how="left", predicate=SJOIN_PREDICATE)

    # A pixel centroid can sit exactly on a shared border and match >1 polygon;
    # keep one deterministic match per pixel (lowest district_id) so a pixel's
    # area is never double-counted.
    joined = joined.sort_values(["pixel_idx", "district_id"], kind="mergesort")
    joined = joined.drop_duplicates(subset="pixel_idx", keep="first")

    matched_mask = joined["district_id"].notna()
    n_total = len(joined)
    n_unmatched = int((~matched_mask).sum())

    # Report unmatched both as a pixel count and as a share of total harv area.
    total_harv_all = float(sum(global_totals.values()))
    unmatched_harv = float(
        joined.loc[~matched_mask, crop_cols].to_numpy().sum()
    )
    unmatched_pixel_share = n_unmatched / n_total if n_total else 0.0
    unmatched_area_share = (
        unmatched_harv / total_harv_all if total_harv_all else 0.0
    )
    log(
        f"  pixels matched to a district: {int(matched_mask.sum()):,} / {n_total:,}"
    )
    log(
        f"  pixels UNMATCHED (outside every spine polygon): {n_unmatched:,} "
        f"({unmatched_pixel_share:.4%} of pixels; "
        f"{unmatched_area_share:.4%} of total harvested area)"
    )

    matched = joined.loc[matched_mask].copy()

    # --- Sum each crop's harvested area per district ------------------------
    log("Aggregating harvested area per district x crop")
    grouped = (
        matched.groupby("district_id", observed=True)[crop_cols].sum()
    )
    log(f"  districts with any matched pixel: {len(grouped):,}")

    # Wide -> long; label crops; drop zero-area (district, crop) pairs.
    long = grouped.reset_index().melt(
        id_vars="district_id",
        value_vars=crop_cols,
        var_name="crop_code",
        value_name="harv_area_ha",
    )
    long = long.loc[long["harv_area_ha"] > 0].copy()

    long["crop"] = long["crop_code"].map(
        lambda c: f"{c} {crop_lookup[c]}"
    )

    # District totals over matched harvested area -> per-crop share.
    dist_tot = long.groupby("district_id", observed=True)["harv_area_ha"].transform(
        "sum"
    )
    long["crop_share"] = long["harv_area_ha"] / dist_tot

    n_nonzero_cropland_districts = long["district_id"].nunique()

    # --- Deterministic output -----------------------------------------------
    out = long[FINAL_COLS].sort_values(SORT_COLS, kind="mergesort").reset_index(
        drop=True
    )

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    log(f"Wrote {OUT_PARQUET} ({len(out):,} rows)")

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== SPAM 2020 CROP MIX SUMMARY ===")
    log(f"  pixels processed:           {n_total:,}")
    log(f"  unmatched pixel share:      {unmatched_pixel_share:.4%}")
    log(f"  unmatched harv-area share:  {unmatched_area_share:.4%}")
    log(f"  districts with cropland:    {n_nonzero_cropland_districts:,}")
    log(f"  (district, crop) rows:      {len(out):,}")
    log("  global harvested area (ha), all technologies, by key crop:")
    for code, label in (("whea", "wheat"), ("maiz", "maize"), ("rice", "rice")):
        log(f"      {label:6s} ({code}): {global_totals[code]:,.0f} ha")
    log(f"  total (all crops):          {total_harv_all:,.0f} ha")

    # Internal consistency: per-district shares must sum to 1.
    share_sums = out.groupby("district_id", observed=True)["crop_share"].sum()
    max_dev = float((share_sums - 1.0).abs().max())
    log(f"  max |sum(crop_share)-1| per district: {max_dev:.3e}")
    if max_dev > 1e-6:
        raise AssertionError(
            f"crop_share does not sum to 1 within tolerance (max dev {max_dev});"
            " aborting."
        )
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
