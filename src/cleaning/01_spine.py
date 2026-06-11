#!/usr/bin/env python3
"""Build the admin-2 panel spine from the geoBoundaries CGAZ ADM2 composite.

Purpose
-------
Turn the raw geoBoundaries CGAZ ADM2 global composite into the fixed,
cross-sectional admin-2 spine that every other layer joins onto. CGAZ is a
COMPOSITE: most countries are represented by their ADM2 units, but countries
that lack an ADM2 level are carried at ADM1 or ADM0. The `admin_level` column
records the level actually represented for each row so downstream users know
the spatial granularity per unit.

Inputs
------
    data/raw/geoboundaries_cgaz/geoBoundariesCGAZ_ADM2.zip
        (produced by src/acquisition/01_download_boundaries.py;
         zipped shapefile, columns shapeName/shapeID/shapeGroup/shapeType,
         EPSG:4326)

Outputs
-------
    data/interim/spine.parquet
        Attribute table only (no geometry), one row per district:
            district_id   (str)  <- shapeID    [primary key, asserted unique]
            iso3          (str)  <- shapeGroup  [3-letter country code]
            district_name (str)  <- shapeName   [may be empty in source; kept]
            admin_level   (str)  <- shapeType   [ADM2 | ADM1 | ADM0]
    data/interim/spine.gpkg
        Same rows + geometry (EPSG:4326), layer "spine".

Both outputs are sorted deterministically by (iso3, admin_level, district_id)
so re-runs are byte-stable.

Row-level filters (logged, thresholds as constants below)
---------------------------------------------------------
  * DROP_DISPUTED: drop CGAZ `shapeType == "DISP"` placeholder polygons.
    These are residual disputed-area markers (e.g. Abyei, Aksai Chin,
    West Bank). They are NOT administrative districts and carry numeric,
    non-ISO3 `shapeGroup` codes (e.g. "111".."129"; one is ESH), which would
    corrupt the `iso3` key. The registry notes CGAZ removes disputed areas;
    these residual placeholders are excluded for the same reason.

Empty district names (source gaps in a handful of CHN/JPN/TKM ADM2 units) are
KEPT: they are valid administrative units with a valid district_id and iso3;
only the human-readable name is missing in the source. The count is logged.

Geometry handling
-----------------
Invalid geometries are repaired with make_valid (count logged). Duplicate
district_id rows are dropped (count logged). district_id uniqueness is asserted.

Runtime
-------
~30-90 s (reading a ~200 MB shapefile and writing a GeoPackage dominate).

How to run
----------
    .venv/bin/python src/cleaning/01_spine.py

Idempotent: outputs are rewritten in full each run from the immutable raw zip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import make_valid

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ZIP = REPO_ROOT / "data" / "raw" / "geoboundaries_cgaz" / "geoBoundariesCGAZ_ADM2.zip"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "spine.parquet"
OUT_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
GPKG_LAYER = "spine"

# Row-level filter: drop disputed-area placeholders (non-administrative, no ISO3).
DROP_DISPUTED = True
DISPUTED_SHAPE_TYPE = "DISP"

# Admin levels we retain (the composite's real administrative units).
KEPT_ADMIN_LEVELS = ("ADM2", "ADM1", "ADM0")

# Source -> spine column mapping.
RENAME = {
    "shapeID": "district_id",
    "shapeGroup": "iso3",
    "shapeName": "district_name",
    "shapeType": "admin_level",
}
FINAL_COLS = ["district_id", "iso3", "district_name", "admin_level"]
SORT_COLS = ["iso3", "admin_level", "district_id"]


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    if not RAW_ZIP.exists():
        raise FileNotFoundError(
            f"Raw input missing: {RAW_ZIP}\n"
            "Run: .venv/bin/python src/acquisition/01_download_boundaries.py"
        )

    log(f"Reading {RAW_ZIP}")
    gdf = gpd.read_file(f"zip://{os.path.abspath(RAW_ZIP)}")
    log(f"  raw rows: {len(gdf):,}")

    expected_cols = {"shapeName", "shapeID", "shapeGroup", "shapeType"}
    missing = expected_cols - set(gdf.columns)
    if missing:
        raise ValueError(f"Source schema changed; missing columns: {sorted(missing)}")

    if gdf.crs is None:
        raise ValueError("Source has no CRS; expected EPSG:4326.")
    if gdf.crs.to_epsg() != 4326:
        log(f"  reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs(epsg=4326)

    # --- Row-level filter: disputed-area placeholders ------------------------
    if DROP_DISPUTED:
        disp_mask = gdf["shapeType"] == DISPUTED_SHAPE_TYPE
        n_disp = int(disp_mask.sum())
        log(
            f"  DROP_DISPUTED: removing {n_disp} '{DISPUTED_SHAPE_TYPE}' rows "
            "(disputed-area placeholders; non-administrative, non-ISO3 codes)"
        )
        gdf = gdf.loc[~disp_mask].copy()

    # Guard: every retained row must be one of the known administrative levels.
    unexpected = set(gdf["shapeType"].unique()) - set(KEPT_ADMIN_LEVELS)
    if unexpected:
        raise ValueError(
            f"Unexpected shapeType values after filtering: {sorted(unexpected)}; "
            f"expected only {KEPT_ADMIN_LEVELS}."
        )

    # Guard: all retained country codes are ISO3-shaped (3 uppercase letters).
    bad_iso = gdf.loc[~gdf["shapeGroup"].astype(str).str.match(r"^[A-Z]{3}$")]
    if len(bad_iso):
        raise ValueError(
            f"{len(bad_iso)} retained rows have non-ISO3 shapeGroup values: "
            f"{sorted(bad_iso['shapeGroup'].unique())[:10]}"
        )

    # --- Geometry: empty / null / invalid ------------------------------------
    n_null_geom = int(gdf.geometry.isna().sum())
    n_empty_geom = int(gdf.geometry.is_empty.sum())
    if n_null_geom or n_empty_geom:
        log(f"  dropping {n_null_geom} null + {n_empty_geom} empty geometries")
        gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    invalid_mask = ~gdf.geometry.is_valid
    n_invalid = int(invalid_mask.sum())
    log(f"  invalid geometries to repair (make_valid): {n_invalid}")
    if n_invalid:
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            make_valid
        )
        still_invalid = int((~gdf.geometry.is_valid).sum())
        if still_invalid:
            raise ValueError(
                f"{still_invalid} geometries remain invalid after make_valid; aborting."
            )

    # --- Attributes: rename, name gaps, dedup --------------------------------
    gdf = gdf.rename(columns=RENAME)

    gdf["district_id"] = gdf["district_id"].astype(str)
    gdf["iso3"] = gdf["iso3"].astype(str)
    gdf["admin_level"] = gdf["admin_level"].astype(str)
    gdf["district_name"] = gdf["district_name"].fillna("").astype(str).str.strip()

    n_empty_name = int((gdf["district_name"] == "").sum())
    log(
        f"  rows with empty district_name in source (kept): {n_empty_name} "
        "(valid units missing only a name)"
    )

    n_dup = int(gdf["district_id"].duplicated().sum())
    if n_dup:
        log(f"  dropping {n_dup} duplicate district_id rows (keeping first)")
        gdf = gdf.drop_duplicates(subset="district_id", keep="first").copy()

    # Hard invariant: the spine's primary key is unique.
    if gdf["district_id"].duplicated().any():
        raise AssertionError("district_id is not unique after dedup; aborting.")
    assert gdf["district_id"].notna().all(), "null district_id present"
    assert gdf["iso3"].notna().all(), "null iso3 present"

    # --- Deterministic sort & column order -----------------------------------
    gdf = gdf[FINAL_COLS + ["geometry"]]
    gdf = gdf.sort_values(SORT_COLS, kind="mergesort").reset_index(drop=True)

    # --- Write outputs -------------------------------------------------------
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(gdf[FINAL_COLS])
    df.to_parquet(OUT_PARQUET, index=False)
    log(f"Wrote {OUT_PARQUET} ({len(df):,} rows)")

    if OUT_GPKG.exists():
        OUT_GPKG.unlink()
    gdf.to_file(OUT_GPKG, layer=GPKG_LAYER, driver="GPKG")
    log(f"Wrote {OUT_GPKG} (layer '{GPKG_LAYER}', {len(gdf):,} rows)")

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== SPINE SUMMARY ===")
    log(f"  total districts:     {len(df):,}")
    log(f"  distinct iso3:       {df['iso3'].nunique()}")
    log(f"  by admin_level:")
    for lvl, cnt in df["admin_level"].value_counts().sort_index().items():
        log(f"      {lvl}: {cnt:,}")
    log(f"  invalid geoms fixed: {n_invalid}")
    log(f"  empty names kept:    {n_empty_name}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
