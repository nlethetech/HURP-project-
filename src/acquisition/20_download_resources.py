#!/usr/bin/env python3
"""Download the natural-resource layers: PRIO PETRODATA, PRIO DIADATA, USGS MRDS.

Purpose
-------
Acquire the resource-endowment sources for the study panel (see
docs/DATA_SOURCES.md, "Natural resources"): oil/gas fields (PETRODATA), diamond
deposits with the primary/secondary=lootable split (DIADATA), and mineral
deposits (USGS MRDS). Static geological endowment -> district-constant
moderators (broadcast to all years). The lootable-resource / "greed" channel;
interacts with colonial extraction.

Sources / registry
-----------------
1. PRIO PETRODATA v1.2 (onshore oil/gas). Keyless (curl -L past a soft OAuth
   redirect). Cite Lujala, Rod & Thieme (2007). Academic use; raw gitignored.
2. PRIO DIADATA (diamond deposits). Keyless. Cite Gilmore et al. (2005),
   Lujala et al. (2005). Academic use; raw gitignored.
3. USGS Mineral Resources Data System (MRDS). PUBLIC DOMAIN. mrdata.usgs.gov.

Outputs
-------
    data/raw/petrodata/petrodata_v12.zip (+ extracted shp)
    data/raw/diadata/diadata.zip (+ extracted shp)
    data/raw/mrds/mrds-csv.zip (+ mrds.csv)
    data/raw/<each>/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/20_download_resources.py [--force]
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
RAW = ROOT / "data" / "raw"

SOURCES = {
    "petrodata": ("petrodata_v12.zip",
                  "https://cdn.cloud.prio.org/files/72fca956-7b50-4cf6-bdb3-86ba2830301f/PETRODATA%20v12%20Data.zip",
                  1_000_000),
    "diadata": ("diadata.zip",
                "https://cdn.cloud.prio.org/files/d042fc6a-ce8a-4c74-b555-e84d68365b99/DIADATA%20Data.zip",
                100_000),
    "mrds": ("mrds-csv.zip", "https://mrdata.usgs.gov/mrds/mrds-csv.zip", 5_000_000),
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

    for subdir, (fname, url, min_bytes) in SOURCES.items():
        d = RAW / subdir
        d.mkdir(parents=True, exist_ok=True)
        dest = d / fname
        print(f"[{subdir}]")
        if dest.exists() and dest.stat().st_size >= min_bytes and not args.force:
            print(f"  present: {dest.name} ({dest.stat().st_size:,} bytes); skipping")
        else:
            tmp = dest.with_suffix(dest.suffix + ".part")
            with requests.get(url, stream=True, timeout=400, allow_redirects=True) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    for c in r.iter_content(1 << 20):
                        if c:
                            fh.write(c)
            if tmp.stat().st_size < min_bytes:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{fname}: {tmp.stat().st_size} bytes < floor")
            tmp.replace(dest)
        with zipfile.ZipFile(dest) as z:
            z.extractall(d)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (d / "MANIFEST.txt").write_text(
            "filename\turl\tretrieved_utc\tbytes\tsha256\n"
            f"{dest.name}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}\n",
            encoding="utf-8",
        )
        print(f"  OK  {dest.stat().st_size:,} bytes (extracted)")
    print("resource sources acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
