#!/usr/bin/env python3
"""Aggregate CRU TS v4.09 monthly temperature to district-year means + anomaly.

Purpose
-------
The keyless twin of the CHIRPS precip lane (src/cleaning/08_weather_chirps.py),
for temperature. For each year, average the 12 monthly CRU `tmp` grids to an
annual-mean 0.5deg raster, then area-weight it over the admin-2 spine with
exactextract → `temp_mean` (degC). Also derive `temp_anomaly` = the district's
standardized heat deviation from its own 1989–2010 baseline. A second exogenous
weather shock alongside rainfall (see docs/CODEBOOK.md, "Temperature").

Inputs
------
    data/raw/cru_temperature/cru_ts4.09.<decade>.tmp.dat.nc.gz  (monthly NetCDF)
    data/interim/spine.gpkg  (layer "spine"; EPSG:4326)

Output
------
    data/interim/temperature_cru.parquet   one row per (district_id, year), 1989-2024

Run
---
    .venv/bin/python src/cleaning/19_temperature_cru.py
"""
from __future__ import annotations

import gzip
import logging
import shutil
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rioxarray  # noqa: F401  registers the .rio accessor
import xarray as xr
from exactextract import exact_extract
from exactextract.raster import RasterioRasterSource

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cru_temperature"
SPINE = ROOT / "data" / "interim" / "spine.gpkg"
OUT = ROOT / "data" / "interim" / "temperature_cru.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("temperature")

YMIN, YMAX = 1989, 2024        # v4.09 ends Dec 2024; 2025 -> NaN (like CHIRPS)
BASELINE = (1989, 2010)        # district anomaly baseline window
NODATA = -9999.0


class CruRasterSource(RasterioRasterSource):
    def nodata_value(self):
        return NODATA


def write_annual_tif(tmp_var: xr.DataArray, year: int, dst: Path) -> bool:
    """Write the 12-month mean for `year` as a north-up EPSG:4326 GeoTIFF."""
    yrs = pd.to_datetime(tmp_var["time"].values).year
    sel = tmp_var.isel(time=np.where(yrs == year)[0])
    if sel.sizes["time"] == 0:
        return False
    ann = sel.mean("time", skipna=True).rename({"lon": "x", "lat": "y"})
    ann = ann.rio.write_crs("EPSG:4326").sortby("y", ascending=False)
    ann = ann.fillna(NODATA)               # CRU ocean cells (xarray-decoded NaN) -> sentinel
    ann.rio.write_nodata(NODATA, inplace=True)
    ann.rio.to_raster(dst)
    return True


def main() -> None:
    spine = gpd.read_file(SPINE, layer="spine")[["district_id", "geometry"]]
    if spine.crs.to_epsg() != 4326:
        raise ValueError(f"spine CRS {spine.crs} != EPSG:4326")
    n = len(spine)

    chunks = sorted(RAW.glob("cru_ts4.09.*.tmp.dat.nc.gz"))
    if not chunks:
        raise SystemExit(f"no CRU chunks in {RAW} — run src/acquisition/18_download_cru_temp.py")

    frames = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for gz in chunks:
            nc = td / gz.stem  # drop .gz
            with gzip.open(gz, "rb") as fi, nc.open("wb") as fo:
                shutil.copyfileobj(fi, fo)
            ds = xr.open_dataset(nc)
            if "tmp" not in ds:
                raise ValueError(f"{gz.name}: expected variable 'tmp', got {list(ds.data_vars)}")
            yrs = sorted(set(pd.to_datetime(ds["tmp"]["time"].values).year))
            for year in [y for y in yrs if YMIN <= y <= YMAX]:
                tif = td / f"cru_{year}.tif"
                if not write_annual_tif(ds["tmp"], year, tif):
                    continue
                with rasterio.open(tif) as rds:
                    res = exact_extract(CruRasterSource(rds, name="temp"), spine, ["mean", "count"],
                                        include_cols=["district_id"], output="pandas")
                assert len(res) == n, f"{year}: {len(res)} rows != {n} districts"
                zero = res["count"] == 0
                assert bool((res["mean"].isna() == zero).all()), f"{year}: NaN/zero-cov mismatch"
                frames.append(pd.DataFrame({"district_id": res["district_id"].astype(str),
                                            "year": year, "temp_mean": res["mean"].astype("float64")}))
                tif.unlink(missing_ok=True)
            ds.close()
            nc.unlink(missing_ok=True)
            log.info("processed %s", gz.name)

    df = pd.concat(frames, ignore_index=True)

    # District heat anomaly: standardize each district vs its own 1989-2010 baseline.
    base = df[df["year"].between(*BASELINE)].groupby("district_id")["temp_mean"].agg(["mean", "std", "count"])
    base = base.rename(columns={"mean": "_mu", "std": "_sd", "count": "_n"})
    df = df.merge(base, on="district_id", how="left")
    # Guard against DEGENERATE baselines: over data-sparse cells CRU relaxes to a
    # fixed climatology, making the baseline decade LITERALLY constant (sd ~1e-3).
    # `sd > 0` would pass such cells and divide real ~0.1 C variation by a fake sd,
    # exploding the z-score (up to +41). Require >=5 baseline years and sd >= 0.05 C
    # (well below the 0.31 C 25th-percentile of real baseline sd).
    ok = (df["_n"] >= 5) & (df["_sd"] >= 0.05)
    df["temp_anomaly"] = np.where(ok, (df["temp_mean"] - df["_mu"]) / df["_sd"], np.nan)
    n_degenerate = int((df.drop_duplicates("district_id")["_sd"] < 0.05).sum())
    df = df.drop(columns=["_mu", "_sd", "_n"]).sort_values(["district_id", "year"]).reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    cw = pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv")
    log.info("wrote %s: %d district-years, %d districts, %d-%d",
             OUT.name, len(df), df["district_id"].nunique(), int(df["year"].min()), int(df["year"].max()))
    log.info("temp_mean non-null: %.1f%% | anomaly non-null: %.1f%%",
             100 * df["temp_mean"].notna().mean(), 100 * df["temp_anomaly"].notna().mean())
    log.info("temp_mean range: %.1f to %.1f degC | temp_anomaly range: %.2f to %.2f | degenerate baselines (sd<0.05): %d",
             df["temp_mean"].min(), df["temp_mean"].max(),
             df["temp_anomaly"].min(), df["temp_anomaly"].max(), n_degenerate)


if __name__ == "__main__":
    main()
