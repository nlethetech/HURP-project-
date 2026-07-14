#!/usr/bin/env python3
"""Download Ethnic Power Relations: EPR-Core + GeoEPR (ETH Zurich / ICR).

Purpose
-------
Acquire the ethnic-exclusion layer for the study panel (see docs/DATA_SOURCES.md,
"Ethnic exclusion"). EPR-Core gives each politically-relevant ethnic group's
access to state power per period; GeoEPR gives the group settlement polygons.
Together they yield the strongest subnational political driver of civil conflict:
the share of a district under EXCLUDED groups.

Sources / registry
-----------------
ETH Zurich / International Conflict Research (icr.ethz.ch/data/epr), version 2021
(coverage 1946-2021). Keyless, no registration. No explicit CC tag; academic use,
cite Vogt et al. (2015) JCR 59(7). Ship derived columns only; raw gitignored.

Outputs
-------
    data/raw/epr/EPR-2021.csv
    data/raw/epr/GeoEPR-2021.zip (+ extracted GeoEPR-2021.shp)
    data/raw/epr/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/21_download_epr.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "epr"
SOURCES = {
    "EPR-2021.csv": ("https://icr.ethz.ch/data/epr/core/EPR-2021.csv", 100_000, False),
    "GeoEPR-2021.zip": ("https://icr.ethz.ch/data/epr/geoepr/GeoEPR-2021.zip", 1_000_000, True),
}


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

    lines = ["filename\turl\tretrieved_utc\tbytes\tsha256"]
    for fname, (url, min_bytes, is_zip) in SOURCES.items():
        dest = RAW / fname
        if dest.exists() and dest.stat().st_size >= min_bytes and not args.force:
            print(f"present: {fname} ({dest.stat().st_size:,} bytes); skipping")
        else:
            tmp = dest.with_suffix(dest.suffix + ".part")
            with requests.get(url, stream=True, timeout=200, allow_redirects=True) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    for c in r.iter_content(1 << 20):
                        if c:
                            fh.write(c)
            if tmp.stat().st_size < min_bytes:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{fname}: {tmp.stat().st_size} bytes < floor")
            tmp.replace(dest)
        if is_zip:
            with zipfile.ZipFile(dest) as z:
                z.extractall(RAW)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{fname}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}")
        print(f"OK  {fname}  {dest.stat().st_size:,} bytes")
    (RAW / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("EPR sources acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
