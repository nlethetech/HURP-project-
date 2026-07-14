#!/usr/bin/env python3
"""Download the MAP 2015 travel-time-to-cities raster (market access / state reach).

Purpose
-------
Acquire the Weiss et al. (2018) global travel-time-to-cities surface for the
study panel's market-access layer (see docs/DATA_SOURCES.md, "Market access").
A 2015 snapshot (time-invariant); a proxy for BOTH farm market access and state
reach. Downloaded as two continental tiles (Africa; South America + Caribbean)
via the Malaria Atlas GeoServer WCS to avoid the multi-GB global grab.

Source / registry
-----------------
Malaria Atlas Project GeoServer WCS 2.0.1, coverage
`Accessibility__201501_Global_Travel_Time_to_Cities`. 30 arc-sec, EPSG:4326,
int32 minutes, nodata -9999. License CC BY 4.0; cite Weiss, D.J. et al.,
Nature (2018) "A global map of travel time to cities".

Outputs
-------
    data/raw/travel_time/travel_time_africa.tif
    data/raw/travel_time/travel_time_americas.tif
    data/raw/travel_time/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/19_download_travel_time.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import rasterio
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "travel_time"
WCS = ("https://data.malariaatlas.org/geoserver/ows?service=WCS&version=2.0.1"
       "&request=GetCoverage&coverageId=Accessibility__201501_Global_Travel_Time_to_Cities"
       "&format=image/geotiff")
# (lat_min, lat_max, lon_min, lon_max) bounding the study regions with margin.
# Africa lon widened to catch island states: Cape Verde (~-24W), Mauritius/
# Seychelles (~55-57E).
TILES = {
    "travel_time_africa.tif": (-36, 38, -26, 64),
    # Americas lon_max −25 (was −33) closes the seam gap with the Africa tile so
    # Atlantic territories like Fernando de Noronha (BRA, lon −32.4) are covered.
    "travel_time_americas.tif": (-56, 28, -92, -25),
}
MIN_BYTES = 200_000


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def fetch(name: str, box: tuple, dest: Path) -> None:
    lat0, lat1, lon0, lon1 = box
    url = f"{WCS}&subset=Lat({lat0},{lat1})&subset=Long({lon0},{lon1})"
    tmp = dest.with_suffix(".part")
    print(f"  downloading {name} bbox lat[{lat0},{lat1}] lon[{lon0},{lon1}]")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for c in r.iter_content(1 << 20):
                if c:
                    fh.write(c)
    if tmp.stat().st_size < MIN_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{name}: {tmp.stat().st_size} bytes < floor (WCS error/empty?)")
    with rasterio.open(tmp) as ds:  # validate it is a readable raster
        assert ds.count >= 1 and ds.crs is not None, f"{name}: not a valid raster"
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    lines = ["filename\turl\tretrieved_utc\tbytes\tsha256"]
    for name, box in TILES.items():
        dest = RAW / name
        if dest.exists() and dest.stat().st_size >= MIN_BYTES and not args.force:
            print(f"present: {name} ({dest.stat().st_size:,} bytes); skipping")
        else:
            fetch(name, box, dest)
        lat0, lat1, lon0, lon1 = box
        url = f"{WCS}&subset=Lat({lat0},{lat1})&subset=Long({lon0},{lon1})"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{name}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}")
        print(f"  OK  {dest.stat().st_size:,} bytes")
    (RAW / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("travel-time tiles acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
