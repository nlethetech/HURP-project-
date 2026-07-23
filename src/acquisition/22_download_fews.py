#!/usr/bin/env python3
"""Download FEWS NET IPC acute food-insecurity phase polygons (per country-date).

Purpose
-------
Acquire subnational IPC-compatible acute food-insecurity classifications from the
FEWS NET Data Warehouse (see docs/DATA_SOURCES.md, "Food insecurity"). For each
covered study country, discover its Current-Status (CS) reporting dates, then
download the phase polygons for each date. FEWS monitors the food-crisis belt,
not every country. ~2011 onward.

Source / registry
-----------------
FEWS NET FDW REST API (keyless, Public data). Dates: /api/ipcphase/ ; polygons:
/api/ipcphasemap/?country={ISO2}&scenario=CS&collection_date={date}&format=geojson.
Free, attribution "Source: FEWS NET, fews.net".

Outputs
-------
    data/raw/fews/{ISO2}_{YYYY-MM-DD}.geojson  (one per country-date with data)
    data/raw/fews/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/22_download_fews.py [--force]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import country_converter as coco
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fews"
PHASE = "https://fdw.fews.net/api/ipcphase/"
PMAP = "https://fdw.fews.net/api/ipcphasemap/"


def dates_for(iso2: str) -> list[str]:
    """Distinct CS reporting dates for a country (empty if not covered)."""
    try:
        r = requests.get(PHASE, params={"country_code": iso2, "scenario": "CS", "format": "json"}, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    rows = data if isinstance(data, list) else data.get("results", [])
    dates = set()
    for row in rows:
        d = row.get("reporting_date") or row.get("collection_date") or row.get("projection_start")
        if d:
            dates.add(str(d)[:10])
    return sorted(dates)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    ours = sorted(set(pd.read_csv(ROOT / "reference" / "iso3_region_crosswalk.csv").query("kept").iso3))
    iso2_map = dict(zip(ours, coco.CountryConverter().convert(ours, src="ISO3", to="ISO2", not_found=None)))

    n_files, covered = 0, []
    for iso3 in ours:
        iso2 = iso2_map.get(iso3)
        if not iso2 or iso2 == "not found":
            continue
        dates = dates_for(iso2)
        if not dates:
            continue
        got = 0
        for d in dates:
            dest = RAW / f"{iso2}_{d}.geojson"
            if dest.exists() and dest.stat().st_size > 200 and not args.force:
                got += 1
                continue
            try:
                r = requests.get(PMAP, params={"country": iso2, "scenario": "CS",
                                               "collection_date": d, "format": "geojson"}, timeout=90)
                if r.status_code != 200:
                    continue
                gj = r.json()
                if gj.get("features"):
                    dest.write_text(r.text, encoding="utf-8")
                    got += 1
            except Exception:
                pass
            time.sleep(0.25)
        if got:
            covered.append(f"{iso3}({iso2}):{got}")
            n_files += got
        print(f"  {iso3} ({iso2}): {got} date-files")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (RAW / "MANIFEST.txt").write_text(
        f"# FEWS NET IPC phase polygons; retrieved {ts}\n"
        f"# source: {PMAP} (scenario=CS)\n"
        f"# files: {n_files}; covered study countries: {len(covered)}\n"
        + "\n".join(covered) + "\n", encoding="utf-8")
    print(f"OK  {n_files} geojson files across {len(covered)} covered study countries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
