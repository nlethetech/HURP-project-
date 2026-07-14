#!/usr/bin/env python3
"""Download the ICTD/UNU-WIDER Government Revenue Dataset (fiscal state capacity).

Purpose
-------
Acquire the Government Revenue Dataset (GRD 2025), the fiscal-capacity layer for
the study panel (see docs/DATA_SOURCES.md, "State capacity"). GRD gives a
country-year tax/revenue-as-%-of-GDP series with strong developing-country
coverage -- a time-varying measure of the state's ability to extract revenue,
the mediator between shocks and conflict the study interacts with.

Source / registry
-----------------
UNU-WIDER Government Revenue Dataset 2025. https://www.wider.unu.edu/database/grd
File: UNUWIDERGRD_2025.xlsx (sheet "Merged" = the recommended one-row-per-
country-year series). doi:10.35188/UNU-WIDER/GRD-2025. Open data, cite the DOI.

NB: the Azure gateway 403s a bare request; a browser User-Agent + Referer header
is required (handled below). Keyless otherwise.

Output
------
    data/raw/grd/UNUWIDERGRD_2025.xlsx
    data/raw/grd/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/15_download_state_capacity.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "grd"
DEST = RAW / "UNUWIDERGRD_2025.xlsx"
URL = "https://www.wider.unu.edu/sites/default/files/Data/UNUWIDERGRD_2025.xlsx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": "https://www.wider.unu.edu/",
}
MIN_BYTES = 2_000_000  # ~9.7 MB expected


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    if DEST.exists() and DEST.stat().st_size >= MIN_BYTES and not args.force:
        print(f"present: {DEST.relative_to(ROOT)} ({DEST.stat().st_size:,} bytes); skipping")
    else:
        tmp = DEST.with_suffix(".part")
        print("downloading GRD 2025")
        with requests.get(URL, headers=HEADERS, stream=True, timeout=120) as r:
            r.raise_for_status()
            with tmp.open("wb") as fh:
                for c in r.iter_content(1 << 20):
                    if c:
                        fh.write(c)
        if tmp.stat().st_size < MIN_BYTES:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"download too small ({tmp.stat().st_size} bytes)")
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
