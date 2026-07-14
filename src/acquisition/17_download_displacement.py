#!/usr/bin/env python3
"""Download the displacement layer: UNHCR refugee origins + IDMC internal displacement.

Purpose
-------
Acquire the forced-displacement country-year sources for the study panel (see
docs/DATA_SOURCES.md, "Displacement"): UNHCR Refugee Data Finder (refugees /
asylum-seekers / IDPs / returnees by country of ORIGIN) and IDMC's Global
Internal Displacement Database (conflict vs disaster IDP stocks + flows). Both
country-year -> iso3_broadcast, TIME-VARYING. Displacement is both a cause and a
consequence of conflict and disrupts agriculture.

Sources / registry
-----------------
1. UNHCR Refugee Data Finder API (keyless, CC BY 4.0). Origin totals 1989-2025.
   Key on the RETURNED `coo_iso` (ISO3), never the `coo` request param.
2. IDMC Global Internal Displacement Database (GIDD) via HDX (keyless, CC BY).
   Package `idmc_internal_displacement_conflict-violence_disasters`; the resource
   download URL carries a version suffix (…-NN.xlsx) that changes on refresh, so
   we RESOLVE it at runtime via the HDX package_show API.

Outputs
-------
    data/raw/unhcr/unhcr_population.json
    data/raw/idmc/idmc_gidd.xlsx
    data/raw/<each>/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/17_download_displacement.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
UNHCR_DIR = ROOT / "data" / "raw" / "unhcr"
IDMC_DIR = ROOT / "data" / "raw" / "idmc"

UNHCR_URL = ("https://api.unhcr.org/population/v1/population/?limit=100000"
             "&yearFrom=1989&yearTo=2025&coo_all=true"
             "&columns=refugees,asylum_seekers,idps,returned_refugees,returned_idps,stateless")
HDX_PKG = ("https://data.humdata.org/api/3/action/package_show?"
           "id=idmc_internal_displacement_conflict-violence_disasters")


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def manifest(dest: Path, url: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (dest.parent / "MANIFEST.txt").write_text(
        "filename\turl\tretrieved_utc\tbytes\tsha256\n"
        f"{dest.name}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}\n",
        encoding="utf-8",
    )


def resolve_idmc_url() -> str:
    """Find the conflict-violence-disasters xlsx download URL (version-suffixed)."""
    pkg = requests.get(HDX_PKG, timeout=60).json()["result"]["resources"]
    for r in pkg:
        name = (r.get("name") or "").lower()
        if r.get("format", "").lower() == "xlsx" and "conflict" in name and "disaster" in name:
            return r["url"]
    raise RuntimeError("could not resolve the IDMC conflict-violence-disasters xlsx on HDX")


def download(url: str, dest: Path, min_bytes: int) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  downloading {url[:90]}...")
    with requests.get(url, stream=True, timeout=180, allow_redirects=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for c in r.iter_content(1 << 20):
                if c:
                    fh.write(c)
    if tmp.stat().st_size < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: {tmp.stat().st_size} bytes < {min_bytes} floor")
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    UNHCR_DIR.mkdir(parents=True, exist_ok=True)
    IDMC_DIR.mkdir(parents=True, exist_ok=True)

    print("[UNHCR]")
    dest = UNHCR_DIR / "unhcr_population.json"
    if dest.exists() and dest.stat().st_size > 100_000 and not args.force:
        print(f"  present: {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes); skipping")
    else:
        download(UNHCR_URL, dest, 100_000)
    manifest(dest, UNHCR_URL)
    print(f"  OK  {dest.stat().st_size:,} bytes")

    print("[IDMC]")
    dest = IDMC_DIR / "idmc_gidd.xlsx"
    idmc_url = resolve_idmc_url()
    if dest.exists() and dest.stat().st_size > 100_000 and not args.force:
        print(f"  present: {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes); skipping")
    else:
        download(idmc_url, dest, 100_000)
    manifest(dest, idmc_url)
    print(f"  OK  {dest.stat().st_size:,} bytes")
    print("displacement sources acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
