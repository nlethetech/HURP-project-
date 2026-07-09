#!/usr/bin/env python3
"""Download the FAO FAMEWS Fall Armyworm trap-monitoring records.

Purpose
-------
Acquire the global fall-armyworm (Spodoptera frugiperda) pheromone-trap records
from FAO FAMEWS (see docs/DATA_SOURCES.md, "Pest / crop disease (Africa)"). Each
row is a dated, georeferenced trap check; the invasion-front FIRST-DETECTION year
is the most defensibly exogenous agricultural pest shock available for the study.
Africa-only in practice (essentially zero Americas rows); a 2018-2023 window.

Source / registry
-----------------
FAO Open Data catalog, dataset "Fall Armyworm Traps (FAMEWS) global lat/lon"
(UUID 13a9fda3-7f3e-4e6d-86aa-13e8c73cc0e4). BigQuery-backed CSV endpoint, no
key/login. License CC-BY-3.0-IGO (redistributable with attribution).

Output
------
    data/raw/famews_faw/famews_traps.csv
    data/raw/famews_faw/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/13_download_faw.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "famews_faw"
DEST = RAW / "famews_traps.csv"
URL = (
    "https://api.data.apps.fao.org/api/v2/bigquery"
    "?sql_url=https://data.apps.fao.org/catalog/dataset/"
    "13a9fda3-7f3e-4e6d-86aa-13e8c73cc0e4/resource/"
    "45c0e0ce-4581-42df-8c71-d550da9e28dd/download/"
    "famews-date-periods-traps-lat-lon-query.sql"
    "&dim_country=All%20Countries&period=all"
)
MIN_BYTES = 500_000
REQUIRED = ["date", "country", "lat", "long", "faw_confirmed_count"]
CAP = 50_000  # FAO smart-csv endpoint hard cap; a full-cap pull means silent truncation.


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def validate(p: Path) -> None:
    if p.stat().st_size < MIN_BYTES:
        raise RuntimeError(f"{p.name}: {p.stat().st_size} bytes < {MIN_BYTES} floor")
    head = p.open("r", encoding="utf-8", errors="replace").readline()
    missing = [c for c in REQUIRED if c not in head]
    if missing:
        raise RuntimeError(f"{p.name}: header missing {missing}; layout changed?")
    n_rows = sum(1 for _ in p.open("r", encoding="utf-8", errors="replace")) - 1
    if n_rows >= CAP:
        raise RuntimeError(f"{p.name}: {n_rows} rows hit the {CAP} endpoint cap — data TRUNCATED; do not use.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    if DEST.exists() and not args.force:
        try:
            validate(DEST)
            print(f"present: {DEST.relative_to(ROOT)} ({DEST.stat().st_size:,} bytes); skipping")
        except RuntimeError:
            args.force = True
    if not DEST.exists() or args.force:
        tmp = DEST.with_suffix(".part")
        print("downloading FAMEWS traps CSV")
        with requests.get(URL, stream=True, timeout=180) as r:
            r.raise_for_status()
            with tmp.open("wb") as fh:
                for c in r.iter_content(1 << 20):
                    if c:
                        fh.write(c)
        validate(tmp)
        tmp.replace(DEST)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (RAW / "MANIFEST.txt").write_text(
        "filename\turl\tretrieved_utc\tbytes\tsha256\n"
        f"{DEST.name}\t{URL}\t{ts}\t{DEST.stat().st_size}\t{sha256_of(DEST)}\n",
        encoding="utf-8",
    )
    print(f"OK  {DEST.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
