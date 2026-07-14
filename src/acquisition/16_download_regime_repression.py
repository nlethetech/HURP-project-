#!/usr/bin/env python3
"""Download the political-institutions layer: V-Dem, Polity5, Political Terror Scale.

Purpose
-------
Acquire the three country-year political sources for the study panel (see
docs/DATA_SOURCES.md, "Regime & democracy" and "State repression"): regime type
and democracy (V-Dem + Polity5) and state repression (PTS). All country-year ->
iso3_broadcast, TIME-VARYING.

Sources / registry
-----------------
1. V-Dem v16 (2026). Keyless via the vdemdata GitHub mirror (vdem.net CSV is
   email-gated): https://raw.githubusercontent.com/vdeminstitute/vdemdata/master/data/vdem.RData
   License CC BY-SA 4.0 (derived columns fine in a private repo; share-alike binds
   only on public release). Cite Coppedge et al. (2026), V-Dem v16.
   NB: the file tracks a rolling `master`; the MANIFEST sha256 pins the content.
2. Polity5 v2018. https://www.systemicpeace.org/inscr/p5v2018.sav
   Free academic use; cite Marshall & Gurr, Polity5 (2020). Ends 2018.
3. Political Terror Scale, PTS-2025 (v8.00). https://www.politicalterrorscale.org/Data/Files/PTS-2025.csv
   License CC BY-NC 4.0; cite Gibney et al., PTS 1976-2024. Latin-1 encoded.

Outputs
-------
    data/raw/vdem/vdem.RData
    data/raw/polity5/p5v2018.sav
    data/raw/pts/PTS-2025.csv
    data/raw/<each>/MANIFEST.txt

Run
---
    .venv/bin/python src/acquisition/16_download_regime_repression.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

# V-Dem tracks a rolling GitHub `master`; pin the exact content so a silent
# upstream bump is caught (reproducibility). Update ONLY after verifying the new
# V-Dem version. None = no pin (versioned/frozen URLs).
VDEM_SHA256 = "39b412d39a061c18f20c98e4ad4d6355b05a0441df31be4ee9aec420dc3d95ea"  # V-Dem v16 (2026-03)

# name -> (subdir, filename, url, min_bytes, header_substrings or None, expected_sha256 or None)
SOURCES = {
    "V-Dem": ("vdem", "vdem.RData",
              "https://raw.githubusercontent.com/vdeminstitute/vdemdata/master/data/vdem.RData",
              10_000_000, None, VDEM_SHA256),
    "Polity5": ("polity5", "p5v2018.sav",
                "https://www.systemicpeace.org/inscr/p5v2018.sav",
                500_000, None, None),
    "PTS": ("pts", "PTS-2025.csv",
            "https://www.politicalterrorscale.org/Data/Files/PTS-2025.csv",
            200_000, ["Year", "PTS_S", "WordBank_Code_A"], None),
}


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def validate(p: Path, min_bytes: int, header: list[str] | None, expected_sha: str | None = None) -> None:
    if p.stat().st_size < min_bytes:
        raise RuntimeError(f"{p.name}: {p.stat().st_size:,} bytes < {min_bytes:,} floor")
    if header:
        head = p.open("r", encoding="latin-1").readline()
        missing = [c for c in header if c not in head]
        if missing:
            raise RuntimeError(f"{p.name}: header missing {missing}; layout changed?")
    if expected_sha:
        actual = sha256_of(p)
        if actual != expected_sha:
            raise RuntimeError(
                f"{p.name}: sha256 {actual} != pinned {expected_sha} -- upstream (rolling "
                "GitHub master) changed; verify the new V-Dem version, then update VDEM_SHA256."
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for name, (subdir, fname, url, min_bytes, header, expected_sha) in SOURCES.items():
        d = RAW / subdir
        d.mkdir(parents=True, exist_ok=True)
        dest = d / fname
        print(f"[{name}]")
        if dest.exists() and dest.stat().st_size >= min_bytes and not args.force:
            print(f"  present: {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes); skipping")
        else:
            tmp = dest.with_suffix(dest.suffix + ".part")
            print(f"  downloading {url}")
            with requests.get(url, stream=True, timeout=180, allow_redirects=True) as r:
                r.raise_for_status()
                with tmp.open("wb") as fh:
                    for c in r.iter_content(1 << 20):
                        if c:
                            fh.write(c)
            validate(tmp, min_bytes, header, expected_sha)
            tmp.replace(dest)
        validate(dest, min_bytes, header, expected_sha)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (d / "MANIFEST.txt").write_text(
            "filename\turl\tretrieved_utc\tbytes\tsha256\n"
            f"{dest.name}\t{url}\t{ts}\t{dest.stat().st_size}\t{sha256_of(dest)}\n",
            encoding="utf-8",
        )
        print(f"  OK  {dest.stat().st_size:,} bytes")
    print("regime + repression sources acquired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
