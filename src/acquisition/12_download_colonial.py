#!/usr/bin/env python3
"""Download the three colonial-legacy sources for the study enrichment.

Purpose
-------
Acquire the country-level colonial-legacy layer for the Africa study panel
(see docs/DATA_SOURCES.md, "Colonial legacy layer"). All
three are small, static, country-level files that become MODERATORS (interacted
with the time-varying conflict/output shocks), never standalone predictors.

Sources / registry
------------------
1. COLDAT -- Colonial Dates Dataset (Becker 2019, v3 2023). Harvard Dataverse
   doi:10.7910/DVN/T9SDEW, file COLDAT_colonies.tab (wide, one row per country).
   License CC0 1.0 (public domain) -> redistributable. Gives colonizer identity
   (8 European powers) + colonial start/end years.
2. QoG Standard Cross-Section (jan22). University of Gothenburg. Carries
   `ht_colonial` (Hadenius-Teorell colonizer identity, complete for the study countries) and
   `lp_legor` (La Porta legal origin) keyed by ISO3 (`ccodealp`) and COW code
   (`ccodecow`, used to bridge COW -> ISO3). Free academic use, cite QoG.
   NB: jan22 is pinned because `lp_legor` was dropped from QoG >= jan23.
3. Correlates of War State System Membership (states2016). correlatesofwar.org.
   Gives `styear` (year the state entered the international system) -> the
   independence-year / years-since-independence column. Cite COW, no paywall.

Outputs
-------
    data/raw/coldat/COLDAT_colonies.tab
    data/raw/legal_origins/qog_std_cs_jan22.csv
    data/raw/cow_states/states2016.csv
    data/raw/<each>/MANIFEST.txt  (url, UTC timestamp, bytes, SHA-256)

How to run
----------
    .venv/bin/python src/acquisition/12_download_colonial.py
    .venv/bin/python src/acquisition/12_download_colonial.py --force

Idempotent: a non-empty target that passes its column check is skipped unless
--force. Partial downloads go to a .part temp and are renamed only on success.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW = REPO_ROOT / "data" / "raw"

# name -> (subdir, filename, url, min_bytes, required header substrings)
SOURCES = {
    "COLDAT": (
        "coldat", "COLDAT_colonies.tab",
        "https://dataverse.harvard.edu/api/access/datafile/7416946?format=original",
        8_000, ["country", "col.britain", "colstart.britain_max"],
    ),
    "QoG": (
        "legal_origins", "qog_std_cs_jan22.csv",
        "https://www.qogdata.pol.gu.se/data/qog_std_cs_jan22.csv",
        500_000, ["ccodealp", "ccodecow", "ht_colonial", "lp_legor"],
    ),
    "COW": (
        "cow_states", "states2016.csv",
        "https://correlatesofwar.org/wp-content/uploads/states2016.csv",
        5_000, ["stateabb", "ccode", "styear", "endyear"],
    ),
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def header_of(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return fh.readline()


def validate(path: Path, min_bytes: int, required: list[str]) -> None:
    size = path.stat().st_size
    if size < min_bytes:
        raise RuntimeError(f"{path.name}: {size:,} bytes < {min_bytes:,} floor (error page/truncated?)")
    head = header_of(path)
    missing = [c for c in required if c not in head]
    if missing:
        raise RuntimeError(f"{path.name}: header missing {missing}; source layout changed?")


def download(url: str, dest: Path, min_bytes: int, required: list[str]) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.unlink(missing_ok=True)
    print(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=120, allow_redirects=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                if chunk:
                    fh.write(chunk)
    validate(tmp, min_bytes, required)
    tmp.replace(dest)


def write_manifest(dest: Path, url: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (dest.parent / "MANIFEST.txt").write_text(
        "filename\turl\tretrieved_utc\tbytes\tsha256\n"
        f"{dest.name}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    args = ap.parse_args()

    for name, (subdir, fname, url, min_bytes, required) in SOURCES.items():
        d = RAW / subdir
        d.mkdir(parents=True, exist_ok=True)
        dest = d / fname
        print(f"[{name}]")
        if dest.exists() and not args.force:
            try:
                validate(dest, min_bytes, required)
                print(f"  present: {dest.relative_to(REPO_ROOT)} ({dest.stat().st_size:,} bytes); skipping")
            except RuntimeError:
                print("  present but failed validation; re-downloading")
                download(url, dest, min_bytes, required)
        else:
            download(url, dest, min_bytes, required)
        write_manifest(dest, url)
        print(f"  OK  {dest.stat().st_size:,} bytes")
    print("all colonial sources acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
