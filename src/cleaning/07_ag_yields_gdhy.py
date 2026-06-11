#!/usr/bin/env python3
"""Aggregate GDHY gridded crop yields to the admin-2 spine (district x year x crop).

Purpose
-------
Turn the raw GDHY 0.5-degree annual yield rasters into a tidy district-year-crop
table of area-weighted mean yield (t/ha). For each crop-year raster we compute,
per spine district, the coverage-area-weighted mean of the grid cells the
district polygon overlaps (each cell contributes in proportion to the fraction
of the cell covered by the district). This is the standard "area-weighted mean"
zonal statistic and the t/ha unit is preserved.

GDHY longitudes run 0-360; they are normalized to -180..180 (and the grid is
oriented north-up) before zonal extraction so it aligns with the EPSG:4326
spine. Alignment is verified against a known breadbasket: US Midwest (Iowa-area)
maize in 2010 should land in roughly the 8-11 t/ha range.

Crops & seasons
---------------
The four staple crops are taken from the archive's bare-crop convenience
folders (maize, rice, wheat, soybean), which mirror each crop's PRIMARY season
(maize_major, rice_major, wheat_winter, soybean). Per-season variants
(maize_second, rice_second, wheat_spring) are not used here; the primary season
is the conventional single-yield-per-crop choice and is documented in the
registry. Each folder supplies annual files yield_YYYY.nc4 for 1981-2016.

Inputs
------
    data/raw/gdhy/extracted/<crop>/yield_YYYY.nc4
        (produced by src/acquisition/07_download_gdhy.py; variable "var" =
         yield in t/ha on a 0.5-deg lat/lon grid, lon 0-360, NaN where the crop
         is absent / not estimated)
    data/interim/spine.gpkg  (layer "spine", admin-2 panel spine, EPSG:4326)

Outputs
-------
    data/interim/ag_yields_gdhy.parquet
        One row per (district_id, year, crop) that has any yield data:
            district_id  (str)    spine shapeID  [key]
            iso3         (str)    spine country code [key context]
            year         (int)    1981..2016     [key]
            crop         (str)    maize|rice|wheat|soybean [key]
            yield_t_ha   (float)  area-weighted district mean yield (t/ha)
        Rows where a district has NO overlapping crop cells in a given year are
        omitted (rather than stored as NaN) to keep the table compact; the
        merge step left-joins onto the spine x year x crop frame, so absent
        crop-district-years naturally become NaN downstream. (A NaN-fill variant
        is available behind KEEP_EMPTY_AS_NAN below if a dense table is wanted.)

    Sorted deterministically by (district_id, year, crop) so re-runs are
    byte-stable.

Method notes
------------
  * Engine: exactextract (coverage-fraction-weighted mean). If exactextract
    fails to import/run, the script falls back to rasterstats zonal_stats with
    all_touched + a manual coverage approximation (documented inline). The
    primary path is exactextract.
  * Each crop-year grid is materialized to a temporary north-up GeoTIFF with a
    sentinel nodata (-9999) so the engine excludes no-data cells from the mean.
  * Districts with no overlapping valid cell yield no row for that crop-year.

Runtime
-------
~ a few minutes: 4 crops x 36 years = 144 rasters, each a global zonal pass
over ~49k districts.

How to run
----------
    .venv/bin/python src/cleaning/07_ag_yields_gdhy.py

Idempotent: the output parquet is rewritten in full each run from the immutable
raw rasters.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "gdhy" / "extracted"
SPINE_GPKG = REPO_ROOT / "data" / "interim" / "spine.gpkg"
SPINE_LAYER = "spine"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "ag_yields_gdhy.parquet"

# Crops -> source folder (bare-crop convenience folders = primary season).
CROPS = {
    "maize": "maize",
    "rice": "rice",
    "wheat": "wheat",
    "soybean": "soybean",
}

YEAR_MIN = 1981
YEAR_MAX = 2016

# NetCDF variable name and the sentinel used when materializing to GeoTIFF.
NC_VAR = "var"
NODATA = -9999.0

# A plausible yield ceiling (t/ha) used only as a loud sanity guard, not a clip.
# Even the most productive maize districts sit well under this.
SANITY_MAX_T_HA = 50.0

# If True, emit a dense table with NaN for districts lacking data in a crop-year.
# Default False: omit empty rows (the merge step fills NaN via a left join).
KEEP_EMPTY_AS_NAN = False

FINAL_COLS = ["district_id", "iso3", "year", "crop", "yield_t_ha"]
SORT_COLS = ["district_id", "year", "crop"]

# Alignment check: US Midwest (Iowa-area) maize ~ 8-11 t/ha in the 2010s.
ALIGN_CHECK = {
    "crop": "maize",
    "year": 2010,
    # lat/lon box roughly over Iowa.
    "lat": (40.0, 44.0),
    "lon": (-96.0, -90.0),
    "lo": 7.0,
    "hi": 13.0,
}


def log(msg: str) -> None:
    print(msg, flush=True)


def load_grid_normalized(nc_path: Path) -> xr.DataArray:
    """Load a GDHY raster, normalize lon 0-360 -> -180..180, orient north-up.

    Returns a DataArray with NaN preserved for missing cells. CRS / nodata are
    applied when written to GeoTIFF, not here.
    """
    da = xr.open_dataset(nc_path)[NC_VAR]
    lon = da["lon"].values
    if lon.max() > 180.0:  # 0-360 convention -> -180..180
        da = da.assign_coords(lon=(((lon + 180.0) % 360.0) - 180.0))
    da = da.sortby("lon").sortby("lat", ascending=False)  # north-up, west->east
    da.attrs = {}
    da.encoding = {}
    return da


def grid_to_geotiff(da: xr.DataArray, dst: Path) -> None:
    """Write a normalized grid to a north-up EPSG:4326 GeoTIFF with sentinel nodata."""
    out = da.fillna(NODATA)
    out = out.rio.set_spatial_dims(x_dim="lon", y_dim="lat")
    out = out.rio.write_crs("EPSG:4326")
    out = out.rio.write_nodata(NODATA)
    out.rio.to_raster(dst)


def verify_alignment(tmpdir: Path, spine: gpd.GeoDataFrame) -> None:
    """Sanity-check lon normalization against a known maize breadbasket.

    Reads the raw box mean directly from the normalized grid (no zonal step) so
    the test isolates georeferencing from polygon overlay; a US-Midwest maize
    value outside the plausible band is a hard error.
    """
    crop = ALIGN_CHECK["crop"]
    year = ALIGN_CHECK["year"]
    nc = RAW_DIR / CROPS[crop] / f"yield_{year}.nc4"
    da = load_grid_normalized(nc)
    box = da.sel(
        lat=slice(ALIGN_CHECK["lat"][1], ALIGN_CHECK["lat"][0]),  # north-up: hi..lo
        lon=slice(ALIGN_CHECK["lon"][0], ALIGN_CHECK["lon"][1]),
    )
    val = float(np.nanmean(box.values))
    log(
        f"  alignment check: {crop} {year} US-Midwest box mean = {val:.2f} t/ha "
        f"(expected ~{ALIGN_CHECK['lo']:.0f}-{ALIGN_CHECK['hi']:.0f})"
    )
    if not (ALIGN_CHECK["lo"] <= val <= ALIGN_CHECK["hi"]):
        raise RuntimeError(
            f"Longitude alignment check FAILED: US-Midwest {crop} {year} mean "
            f"{val:.2f} t/ha is outside [{ALIGN_CHECK['lo']}, {ALIGN_CHECK['hi']}]. "
            "Grid georeferencing is wrong; aborting before zonal aggregation."
        )


def zonal_mean(geotiff: Path, spine: gpd.GeoDataFrame) -> pd.DataFrame:
    """Coverage-area-weighted district mean of a single raster via exactextract.

    Falls back to rasterstats if exactextract is unavailable. Returns a frame
    with columns [district_id, yield_t_ha, n_cells]; rows with no overlapping
    valid cell have NaN yield and n_cells == 0.
    """
    try:
        from exactextract import exact_extract

        res = exact_extract(
            str(geotiff),
            spine,
            ["mean", "count"],
            include_cols=["district_id"],
            output="pandas",
        )
        res = res.rename(columns={"mean": "yield_t_ha", "count": "n_cells"})
        return res[["district_id", "yield_t_ha", "n_cells"]]
    except ImportError:
        # Fallback: rasterstats. nodata is honored; "mean" excludes nodata cells.
        from rasterstats import zonal_stats

        log("  (exactextract unavailable -> falling back to rasterstats)")
        stats = zonal_stats(
            spine,
            str(geotiff),
            stats=["mean", "count"],
            nodata=NODATA,
            all_touched=False,
            geojson_out=False,
        )
        df = pd.DataFrame(stats)
        df["district_id"] = spine["district_id"].values
        df = df.rename(columns={"mean": "yield_t_ha", "count": "n_cells"})
        df["n_cells"] = df["n_cells"].fillna(0)
        return df[["district_id", "yield_t_ha", "n_cells"]]


def main() -> int:
    if not SPINE_GPKG.exists():
        raise FileNotFoundError(
            f"Spine missing: {SPINE_GPKG}\n"
            "Run: .venv/bin/python src/cleaning/01_spine.py"
        )
    for crop, folder in CROPS.items():
        if not (RAW_DIR / folder).is_dir():
            raise FileNotFoundError(
                f"Raw GDHY crop folder missing: {RAW_DIR / folder}\n"
                "Run: .venv/bin/python src/acquisition/07_download_gdhy.py"
            )

    log(f"Reading spine: {SPINE_GPKG}")
    spine = gpd.read_file(SPINE_GPKG, layer=SPINE_LAYER)
    if spine.crs is None or spine.crs.to_epsg() != 4326:
        raise ValueError(f"Spine CRS must be EPSG:4326; got {spine.crs}.")
    spine = spine[["district_id", "iso3", "geometry"]].copy()
    n_districts = len(spine)
    log(f"  spine districts: {n_districts:,}")

    id_to_iso = dict(zip(spine["district_id"], spine["iso3"]))

    with tempfile.TemporaryDirectory(prefix="gdhy_") as td:
        tmpdir = Path(td)

        log("Verifying longitude alignment ...")
        verify_alignment(tmpdir, spine)

        frames: list[pd.DataFrame] = []
        for crop, folder in CROPS.items():
            crop_rows = 0
            for year in range(YEAR_MIN, YEAR_MAX + 1):
                nc = RAW_DIR / folder / f"yield_{year}.nc4"
                if not nc.exists():
                    raise FileNotFoundError(f"Expected raster missing: {nc}")
                da = load_grid_normalized(nc)
                tif = tmpdir / f"{crop}_{year}.tif"
                grid_to_geotiff(da, tif)

                res = zonal_mean(tif, spine)
                tif.unlink(missing_ok=True)

                # Keep only districts that actually overlapped valid cells.
                have = res["n_cells"].fillna(0) > 0
                res = res.loc[have & res["yield_t_ha"].notna()].copy()

                # Loud sanity guard (never clip; just fail if implausible).
                bad = res["yield_t_ha"] > SANITY_MAX_T_HA
                if bad.any():
                    raise RuntimeError(
                        f"{crop} {year}: {int(bad.sum())} districts exceed "
                        f"{SANITY_MAX_T_HA} t/ha (max {res['yield_t_ha'].max():.1f}); "
                        "likely a units / nodata error; aborting."
                    )

                res["year"] = year
                res["crop"] = crop
                res["iso3"] = res["district_id"].map(id_to_iso)
                frames.append(res[["district_id", "iso3", "year", "crop", "yield_t_ha"]])
                crop_rows += len(res)
            log(f"  {crop:8s}: {crop_rows:,} district-year rows")

        out = pd.concat(frames, ignore_index=True)

    out["year"] = out["year"].astype("int32")
    out["district_id"] = out["district_id"].astype(str)
    out["iso3"] = out["iso3"].astype(str)
    out["crop"] = out["crop"].astype(str)
    out["yield_t_ha"] = out["yield_t_ha"].astype("float64")

    if KEEP_EMPTY_AS_NAN:
        # Dense frame: every district x year x crop, NaN where no data.
        idx = pd.MultiIndex.from_product(
            [
                sorted(spine["district_id"]),
                range(YEAR_MIN, YEAR_MAX + 1),
                list(CROPS),
            ],
            names=["district_id", "year", "crop"],
        )
        dense = out.set_index(["district_id", "year", "crop"]).reindex(idx)
        dense["iso3"] = dense.index.get_level_values("district_id").map(id_to_iso)
        out = dense.reset_index()[FINAL_COLS]

    out = out[FINAL_COLS].sort_values(SORT_COLS, kind="mergesort").reset_index(drop=True)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    log(f"Wrote {OUT_PARQUET} ({len(out):,} rows)")

    # --- Summary -------------------------------------------------------------
    districts_with_data = out["district_id"].nunique()
    log("")
    log("=== GDHY YIELDS SUMMARY ===")
    log(f"  rows:                 {len(out):,}")
    log(f"  year range:           {int(out['year'].min())}-{int(out['year'].max())}")
    log(f"  crops:                {sorted(out['crop'].unique())}")
    log(
        f"  districts w/ any data:{districts_with_data:,} / {n_districts:,} "
        f"({100.0 * districts_with_data / n_districts:.1f}%)"
    )
    for crop in CROPS:
        sub = out[out["crop"] == crop]
        log(
            f"      {crop:8s}: rows={len(sub):>7,}  "
            f"districts={sub['district_id'].nunique():>6,}  "
            f"mean={sub['yield_t_ha'].mean():.2f} t/ha"
        )
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
