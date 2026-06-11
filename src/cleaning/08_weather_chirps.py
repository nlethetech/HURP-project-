#!/usr/bin/env python3
"""Aggregate CHIRPS v2.0 annual rainfall rasters to area-weighted district means.

Purpose
-------
For every CHIRPS v2.0 global annual GeoTIFF on disk, compute the area-weighted
mean of annual precipitation (mm) within each admin-2 spine polygon, producing
a tidy district x year table (see docs/DATA_SOURCES.md, "CHIRPS ... v2.0").
Aggregation uses exactextract's exact cell/polygon overlap fractions as
weights, so partially-covered cells contribute proportionally.

CHIRPS covers only 50S-50N (v2.0). The annual GeoTIFFs carry an UNTAGGED
-9999 nodata sentinel (the file metadata reports nodata=None), so this script
forces -9999 to be treated as nodata before extraction. Districts lying wholly
outside 50S-50N intersect no valid cells and receive precip_mm = NaN; their
count is reported once.

Inputs
------
    data/interim/spine.gpkg  (layer "spine"; produced by src/cleaning/01_spine.py)
        admin-2 polygons keyed by district_id (+ iso3), EPSG:4326.
    data/raw/chirps/chirps-v2.0.YYYY.tif
        annual rainfall rasters (produced by
        src/acquisition/08_download_chirps.py); 0.05 deg, float32,
        -9999 nodata sentinel, 50S-50N.

Outputs
-------
    data/interim/weather_chirps.parquet
        one row per (district_id, year):
            district_id  (str)    <- spine shapeID
            year         (int32)  <- calendar year of the annual raster
            precip_mm    (float64)<- area-weighted mean annual precip (mm);
                                     NaN where the district lies outside 50S-50N
        Sorted deterministically by (district_id, year).

Method / constants
------------------
  * NODATA = -9999.0  : forced nodata sentinel (registry gotcha #5).
  * Weighted operation: exactextract "mean" with cell-coverage-fraction
    weights (its default for "mean") gives the area-weighted polygon mean.
  * "count" (sum of covered valid-cell coverage fractions) is computed
    alongside "mean" purely to flag zero-coverage (outside-50S-50N) districts;
    it is not written to the output.

Runtime
-------
Compute-heavy: each annual raster is 7200x2000 and the spine has ~49k
polygons. Expect on the order of one to a few minutes per year on a laptop;
the full ~36-year span runs in roughly half an hour to an hour. Years are
processed sequentially with progress prints.

How to run
----------
    .venv/bin/python src/cleaning/08_weather_chirps.py

Idempotent: the output is rewritten in full each run from the raw rasters.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from exactextract import exact_extract
from exactextract.raster import RasterioRasterSource

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SPINE_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
SPINE_LAYER = "spine"
RAW_DIR = REPO_ROOT / "data" / "raw" / "chirps"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "weather_chirps.parquet"

# CHIRPS v2.0 ocean/outside-domain sentinel. The annual GeoTIFFs do NOT tag a
# nodata value in metadata (rasterio reports nodata=None); -9999 must be masked
# explicitly or it would poison the area-weighted mean.
NODATA = -9999.0

# Filename pattern for the annual rasters, e.g. chirps-v2.0.1989.tif
FILE_RE = re.compile(r"^chirps-v2\.0\.(\d{4})\.tif$")

# Operations: area-weighted polygon mean, plus a coverage count used only to
# flag districts that intersect no valid cells (i.e. lie outside 50S-50N).
OPS = ["mean", "count"]

FINAL_COLS = ["district_id", "year", "precip_mm"]
SORT_COLS = ["district_id", "year"]


def log(msg: str) -> None:
    print(msg, flush=True)


class ChirpsRasterSource(RasterioRasterSource):
    """RasterioRasterSource that forces the CHIRPS -9999 sentinel as nodata.

    The annual CHIRPS GeoTIFFs leave nodata untagged in their metadata, so the
    base class would treat -9999 as a real precipitation value. Overriding
    nodata_value() ensures those cells are excluded from the weighted mean.
    """

    def nodata_value(self):  # noqa: D401 - simple override
        return NODATA


def discover_rasters() -> list[tuple[int, Path]]:
    """Return [(year, path), ...] for every CHIRPS annual raster on disk, sorted."""
    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"Raw CHIRPS directory missing: {RAW_DIR}\n"
            "Run: .venv/bin/python src/acquisition/08_download_chirps.py"
        )
    found: list[tuple[int, Path]] = []
    for p in sorted(RAW_DIR.iterdir()):
        m = FILE_RE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    found.sort(key=lambda t: t[0])
    return found


def main() -> int:
    if not SPINE_GPKG.exists():
        raise FileNotFoundError(
            f"Spine missing: {SPINE_GPKG}\n"
            "Run: .venv/bin/python src/cleaning/01_spine.py"
        )

    rasters = discover_rasters()
    if not rasters:
        raise FileNotFoundError(
            f"No chirps-v2.0.YYYY.tif files found in {RAW_DIR}.\n"
            "Run: .venv/bin/python src/acquisition/08_download_chirps.py"
        )
    years = [y for y, _ in rasters]
    log(f"CHIRPS rasters found: {len(rasters)} ({min(years)}-{max(years)})")

    log(f"Reading spine: {SPINE_GPKG} (layer '{SPINE_LAYER}')")
    spine = gpd.read_file(SPINE_GPKG, layer=SPINE_LAYER)
    if spine.crs is None or spine.crs.to_epsg() != 4326:
        raise ValueError(
            f"Spine CRS is {spine.crs}; expected EPSG:4326 to match CHIRPS."
        )
    n_districts = len(spine)
    log(f"  districts: {n_districts:,}")

    # Carry only the join key + geometry into extraction.
    spine_geo = spine[["district_id", "geometry"]].copy()

    frames: list[pd.DataFrame] = []
    nan_counts: dict[int, int] = {}

    for i, (year, path) in enumerate(rasters, start=1):
        log(f"[{i}/{len(rasters)}] {year}: extracting from {path.name}")
        with rasterio.open(path) as ds:
            src = ChirpsRasterSource(ds, name="precip")
            res = exact_extract(
                src,
                spine_geo,
                OPS,
                include_cols=["district_id"],
                output="pandas",
            )

        # exactextract returns one row per input feature, in input order.
        if len(res) != n_districts:
            raise AssertionError(
                f"{year}: extract returned {len(res)} rows, expected {n_districts}."
            )

        # Districts intersecting no valid cells (outside 50S-50N) have count==0
        # and a NaN mean; keep the NaN explicitly.
        zero_cov = res["count"] == 0
        n_nan = int(zero_cov.sum())
        nan_counts[year] = n_nan

        out = pd.DataFrame(
            {
                "district_id": res["district_id"].astype(str),
                "year": year,
                "precip_mm": res["mean"].astype("float64"),
            }
        )
        # Make outside-domain explicit NaN (mean is already NaN where count==0,
        # but assert the equivalence so a future change can't silently leak 0s).
        if not bool((res["mean"].isna() == zero_cov).all()):
            raise AssertionError(
                f"{year}: NaN-mean and zero-coverage masks disagree; "
                "nodata handling may be wrong."
            )

        valid = out["precip_mm"].dropna()
        log(
            f"    districts with data: {len(valid):,}  NaN (outside 50S-50N): "
            f"{n_nan:,}  precip range: {valid.min():.1f}-{valid.max():.1f} mm"
        )
        frames.append(out)

    panel = pd.concat(frames, ignore_index=True)
    panel["year"] = panel["year"].astype("int32")

    # Deterministic sort and column order.
    panel = panel[FINAL_COLS]
    panel = panel.sort_values(SORT_COLS, kind="mergesort").reset_index(drop=True)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT_PARQUET, index=False)

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== CHIRPS DISTRICT-YEAR SUMMARY ===")
    log(f"  rows written:        {len(panel):,}")
    log(f"  districts (spine):   {n_districts:,}")
    log(f"  years:               {min(years)}-{max(years)} ({len(years)} years)")
    log(f"  output: {OUT_PARQUET}")

    # The NaN (outside-50S-50N) district set is geometry-driven and so is nearly
    # constant year-to-year. A handful of districts sit exactly on the 50S/50N
    # edge of the gauge-satellite domain: they touch only a thin strip of cells
    # near the boundary, and in a year where those specific edge cells carry the
    # -9999 sentinel the district's mean is NaN, otherwise it has data. This
    # produces a small year-to-year wobble in the NaN count; it is expected
    # boundary behaviour, not an error. Report the baseline and the wobble.
    nan_set = set(nan_counts.values())
    if len(nan_set) == 1:
        log(
            f"  districts NaN every year (wholly outside 50S-50N): "
            f"{next(iter(nan_set)):,}"
        )
    else:
        log(
            f"  districts NaN per year: {min(nan_counts.values()):,}-"
            f"{max(nan_counts.values()):,} (small edge-of-domain wobble near "
            "50S/50N; expected, not an error)"
        )

    # District-level coverage: a district has data if precip_mm is non-NaN in
    # any year (equivalently, every year for a fixed domain).
    per_district_nan = (
        panel.groupby("district_id")["precip_mm"].apply(lambda s: s.isna().all())
    )
    n_district_all_nan = int(per_district_nan.sum())
    n_district_with_data = int((~per_district_nan).sum())
    log(f"  districts with data (>=1 year): {n_district_with_data:,}")
    log(f"  districts NaN in all years:     {n_district_all_nan:,}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
