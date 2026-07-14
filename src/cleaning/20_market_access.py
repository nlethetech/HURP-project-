#!/usr/bin/env python3
"""Aggregate the MAP 2015 travel-time raster to district median/mean (market access).

Purpose
-------
Mosaic the two travel-time-to-cities tiles and area-weight them over the admin-2
spine with exactextract → district median & mean travel time in minutes (2015
snapshot; see docs/CODEBOOK.md, "Market access"). TIME-INVARIANT: one row per
district, broadcast to all panel years at merge.

Inputs
------
    data/raw/travel_time/travel_time_{africa,americas}.tif  (int32 minutes, nodata -9999)
    data/interim/spine.gpkg  (layer "spine"; EPSG:4326)

Output
------
    data/interim/market_access.parquet   one row per district_id (no year)

Run
---
    .venv/bin/python src/cleaning/20_market_access.py
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from exactextract import exact_extract
from exactextract.raster import RasterioRasterSource
from rasterio.merge import merge

# value 0 is a VALID measurement (inside a city); ONLY -9999 is nodata. The MAP
# tiles tag nodata=-9999, so RasterioRasterSource reads it directly (no override,
# unlike CHIRPS). We cast the mosaic to float32 so exactextract's mean/median
# return cleanly (int raster + float nodata triggers a pybind cast error).

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "travel_time"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "market_access.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("market_access")

NODATA = -9999.0


def main() -> None:
    tiles = sorted(RAW.glob("travel_time_*.tif"))
    if not tiles:
        raise SystemExit(f"no travel-time tiles in {RAW} — run src/acquisition/19_download_travel_time.py")
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "geometry"]]
    if spine.crs.to_epsg() != 4326:
        raise ValueError(f"spine CRS {spine.crs} != EPSG:4326")
    n = len(spine)

    srcs = [rasterio.open(t) for t in tiles]
    mosaic, transform = merge(srcs, nodata=NODATA)
    meta = srcs[0].meta.copy()
    for s in srcs:
        s.close()
    mosaic = mosaic.astype("float32")
    meta.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform,
                dtype="float32", nodata=NODATA)

    with tempfile.TemporaryDirectory() as td:
        mpath = Path(td) / "travel_time_mosaic.tif"
        with rasterio.open(mpath, "w", **meta) as d:
            d.write(mosaic)
        with rasterio.open(mpath) as ds:
            res = exact_extract(RasterioRasterSource(ds, name="tt"), spine,
                                ["median", "mean", "count"], include_cols=["district_id"], output="pandas")

    assert len(res) == n, f"extract returned {len(res)} rows != {n} districts"
    zero = res["count"] == 0
    out = pd.DataFrame({
        "district_id": res["district_id"].astype(str),
        "travel_time_to_city_min_median": res["median"].astype("float64"),
        "travel_time_to_city_min_mean": res["mean"].astype("float64"),
    })
    out["travel_time_to_city_log1p"] = np.log1p(out["travel_time_to_city_min_median"])
    out["market_access_snapshot_year"] = 2015
    out.loc[zero.values, ["travel_time_to_city_min_median", "travel_time_to_city_min_mean",
                          "travel_time_to_city_log1p"]] = np.nan
    out = out.sort_values("district_id").reset_index(drop=True)
    out.to_parquet(OUT, index=False)

    log.info("wrote %s: %d districts", OUT.name, len(out))
    log.info("travel_time median non-null: %.1f%% (%.0f districts NaN = no land cell)",
             100 * out["travel_time_to_city_min_median"].notna().mean(), int(zero.sum()))
    log.info("median travel-time range: %.0f to %.0f min",
             out["travel_time_to_city_min_median"].min(), out["travel_time_to_city_min_median"].max())


if __name__ == "__main__":
    main()
