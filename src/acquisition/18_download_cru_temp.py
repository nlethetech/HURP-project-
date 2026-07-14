#!/usr/bin/env python3
"""Download CRU TS v4.09 monthly mean temperature (keyless UEA mirror).

Purpose
-------
Acquire near-surface monthly mean temperature (CRU TS v4.09 `tmp`, 0.5deg) for
the study panel's temperature layer (see docs/DATA_SOURCES.md, "Temperature").
Downloaded as decade chunks covering 1981-2024 (the panel needs 1989-2024; 2025
is beyond v4.09 and will be NaN, mirroring CHIRPS precip). Keyless UEA mirror
(the CEDA path is login-gated).

Source / registry
-----------------
Climatic Research Unit (CRU), University of East Anglia. CRU TS v4.09.
Base: https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.09/cruts.2503051245.v4.09/tmp/
License OGL-UK-3.0 (redistributable; attribution). Cite Harris et al. 2020,
Scientific Data 7:109.

Outputs
-------
    data/raw/cru_temperature/cru_ts4.09.<decade>.tmp.dat.nc.gz  (x5)
    data/raw/cru_temperature/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/18_download_cru_temp.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cru_temperature"
BASE = "https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.09/cruts.2503051245.v4.09/tmp"
CHUNKS = ["1981.1990", "1991.2000", "2001.2010", "2011.2020", "2021.2024"]
MIN_BYTES = 5_000_000  # each gzip chunk is ~10-36 MB


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
    for chunk in CHUNKS:
        fname = f"cru_ts4.09.{chunk}.tmp.dat.nc.gz"
        url = f"{BASE}/{fname}"
        dest = RAW / fname
        if dest.exists() and dest.stat().st_size >= MIN_BYTES and not args.force:
            print(f"present: {fname} ({dest.stat().st_size:,} bytes); skipping")
        else:
            tmp = dest.with_suffix(dest.suffix + ".part")
            print(f"downloading {fname}")
            with requests.get(url, stream=True, timeout=600) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    for c in r.iter_content(1 << 20):
                        if c:
                            fh.write(c)
            if tmp.stat().st_size < MIN_BYTES:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"{fname}: {tmp.stat().st_size} bytes < floor")
            tmp.replace(dest)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{fname}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}")
    (RAW / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK  {len(CHUNKS)} CRU temperature chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
