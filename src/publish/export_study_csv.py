#!/usr/bin/env python3
"""Export the enriched study panel to shareable CSVs under data/published/.

Purpose
-------
Produce CSV exports of the Africa + South America + Caribbean *study* panel (the
region-specific, fully-enriched 173-column dataset) for analysis / sharing in the
PRIVATE research repo: a full gzipped CSV, and a small uncompressed sample GitHub
renders as a browsable table.

LICENSE NOTE
------------
The panel includes ACLED-derived columns (acled_*). ACLED's EULA forbids PUBLIC
redistribution of raw or derived data, so these CSVs may live ONLY in a PRIVATE
repo for the licensee's own research. This script refuses to run without
--i-confirm-private, as a guard against accidentally publishing licensed content.
The acquisition/cleaning scripts remain the canonical reproducible source; these
CSVs are a convenience artifact.

Input
-----
    data/processed/panel_africa_samerica_caribbean_enriched.parquet

Outputs
-------
    data/published/hurp_study_panel_full.csv.gz     (all 173 columns, gzipped)
    data/published/hurp_study_panel_sample.csv      (illustrative sample, rendered)

Run
---
    .venv/bin/python src/publish/export_study_csv.py --i-confirm-private
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean_enriched.parquet"
PUB = ROOT / "data" / "published"
FULL = PUB / "hurp_study_panel_full.csv.gz"
SAMPLE = PUB / "hurp_study_panel_sample.csv"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--i-confirm-private", action="store_true",
                    help="required: confirm this export (with ACLED-derived columns) stays in a PRIVATE repo")
    args = ap.parse_args()
    if not args.i_confirm_private:
        print("Refusing to export: the panel contains ACLED-derived columns (no public redistribution).\n"
              "Re-run with --i-confirm-private if this repo is private.", file=sys.stderr)
        return 2
    if not PANEL.exists():
        raise SystemExit(f"missing {PANEL} — run src/subset/02_enrich_study.py first")

    PUB.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(PANEL)
    print(f"study panel: {df.shape[0]:,} rows x {df.shape[1]} cols")

    # Shrink the CSV without losing meaning: integer-valued float columns -> nullable
    # Int (writes "5" not "5.0"), and trim float noise to 3 decimals. Keeps the file
    # under GitHub's 100 MB limit; parquet stays the full-precision canonical source.
    for c in df.select_dtypes("float").columns:
        s = df[c]
        nn = s.dropna()
        if len(nn) and (nn % 1 == 0).all():
            df[c] = s.astype("Int64")
        else:
            df[c] = s.round(3)
    df.to_csv(FULL, index=False, compression={"method": "gzip", "compresslevel": 9})
    print(f"wrote {FULL.relative_to(ROOT)}  ({FULL.stat().st_size / 1e6:.1f} MB gzipped)")

    # Browsable sample: a few district-years from one country per region + recent years.
    picks = {"NGA": [2015, 2020], "ETH": [1989, 2020], "BRA": [2015, 2020], "HTI": [2010, 2020]}
    parts = [df[(df["iso3"] == iso) & (df["year"].isin(yrs))] for iso, yrs in picks.items()]
    sample = pd.concat(parts).groupby("iso3", group_keys=False).head(100)
    sample.to_csv(SAMPLE, index=False)
    print(f"wrote {SAMPLE.relative_to(ROOT)}  ({len(sample)} rows, {SAMPLE.stat().st_size / 1e3:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
