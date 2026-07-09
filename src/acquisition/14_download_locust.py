#!/usr/bin/env python3
"""Download FAO Desert Locust gregarious-phase (swarm + hopper band) observations.

Purpose
-------
Acquire georeferenced, dated desert-locust (Schistocerca gregaria) observations
from the FAO Locust Hub / RAMSES open catalog (see docs/DATA_SOURCES.md,
"Pest / crop disease (Africa)"). We take the two GREGARIOUS, crop-destroying
phases — flying adult SWARMs and marching hopper BANDs — which are the
agriculturally-relevant plague signal and, critically, the only two categories
the FAO "smart-csv" preview endpoint returns COMPLETE (below its hard 50,000-row
cap). Scattered solitary ADULT / HOPPER / NO-LOCUST categories are each capped
at 50k by the endpoint and are lower-intensity, so they are deliberately
excluded. Result spans 2004-2026 across the desert-locust belt (Sahel, Horn,
N. Africa, Arabia/SW-Asia) — Africa-only for this study.

Source / registry
-----------------
FAO Open Data catalog, "Desert locusts observations (Global)"
(UUID 088f29ea-6e33-4e9c-8779-9b64dd2450b0), BigQuery-backed CSV, no key.
Query param `cat=SWARM` / `cat=BAND` selects the phase. License: see registry
(FAO; treat as CC-BY-NC-SA by default until the CC-BY vs NC-SA ambiguity across
FAO pages is resolved — fine for internal/private use).

Output
------
    data/raw/locust_hub/locust_swarms.csv
    data/raw/locust_hub/locust_bands.csv
    data/raw/locust_hub/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/14_download_locust.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "locust_hub"
BASE = (
    "https://api.data.apps.fao.org/api/v2/bigquery?sql_url="
    "https://data.apps.fao.org/catalog/dataset/088f29ea-6e33-4e9c-8779-9b64dd2450b0/"
    "resource/8513be12-5a1d-4fe1-81a7-9e3b8160fee0/download/locusts-parameterized-query-4.sql"
    "&period=all&dim_country=All%20Countries"
)
CATS = {"locust_swarms.csv": "SWARM", "locust_bands.csv": "BAND"}
REQUIRED = ["category", "lat", "lon", "start_date", "area_treated_in_ha"]
CAP = 50_000  # endpoint hard cap; a full 50k pull means the category was truncated.


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def fetch(cat: str, dest: Path) -> int:
    url = f"{BASE}&cat={cat}"
    tmp = dest.with_suffix(".part")
    print(f"  downloading cat={cat}")
    with requests.get(url, stream=True, timeout=240) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for c in r.iter_content(1 << 20):
                if c:
                    fh.write(c)
    head = tmp.open("r", encoding="utf-8", errors="replace").readline()
    missing = [c for c in REQUIRED if c not in head]
    if missing:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"cat={cat}: header missing {missing}; layout changed?")
    n_rows = sum(1 for _ in tmp.open("r", encoding="utf-8", errors="replace")) - 1
    if n_rows >= CAP:
        # Should not happen for SWARM/BAND (both < 50k); guard against silent truncation.
        raise RuntimeError(f"cat={cat}: {n_rows} rows hit the {CAP} cap — data is TRUNCATED; do not use.")
    tmp.replace(dest)
    return n_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    lines = ["filename\turl\tretrieved_utc\tbytes\tsha256\trows"]
    for fname, cat in CATS.items():
        dest = RAW / fname
        if dest.exists() and not args.force:
            print(f"[{cat}] present: {dest.relative_to(ROOT)}; re-verifying")
            n = sum(1 for _ in dest.open("r", encoding="utf-8", errors="replace")) - 1
            if n >= CAP:
                print("  hit cap on disk; re-downloading")
                n = fetch(cat, dest)
        else:
            n = fetch(cat, dest)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{fname}\t{BASE}&cat={cat}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}\t{n}")
        print(f"  OK  {n:,} rows  {dest.stat().st_size:,} bytes")
    (RAW / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("locust swarm+band observations acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
