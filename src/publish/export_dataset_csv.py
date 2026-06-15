#!/usr/bin/env python3
"""Export the built panel to shareable CSVs under data/published/.

Purpose
-------
Produce human-/tool-friendly CSV exports of the final panel for sharing in the
(PRIVATE) research repo: a full gzipped CSV for download / Colab, and a small
uncompressed sample that GitHub renders as a browsable table.

LICENSE NOTE
------------
The full export includes the ACLED-derived columns (acled_*). ACLED's EULA
forbids PUBLIC redistribution of raw or derived data, so these CSVs may live
ONLY in a PRIVATE repo for the licensee's own research. This script refuses to
run unless --i-confirm-private is passed, as a guard against accidentally
publishing licensed content. (The acquisition/cleaning scripts remain the
canonical, reproducible source; these CSVs are a convenience artifact.)

Inputs
------
    data/processed/panel_district_year.parquet

Outputs
-------
    data/published/hurp_panel_v0.2_full.csv.gz   (all 61 columns, gzipped)
    data/published/hurp_panel_sample.csv         (illustrative sample, rendered)

How to run
----------
    .venv/bin/python src/publish/export_dataset_csv.py --i-confirm-private

Idempotent: rewritten in full from the immutable panel, deterministic sort and
sample seed, so re-runs are stable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL = REPO_ROOT / "data" / "processed" / "panel_district_year.parquet"
OUT_DIR = REPO_ROOT / "data" / "published"
OUT_FULL = OUT_DIR / "hurp_panel_v0.2_full.csv.gz"
OUT_SAMPLE = OUT_DIR / "hurp_panel_sample.csv"

FLOAT_DECIMALS = 4
SAMPLE_DISTRICTS = 20          # random districts (plus the highlighted one)
SAMPLE_SEED = 42
HIGHLIGHT_ID = "59680162B20780696540875"  # Maiduguri, Nigeria (Boko Haram)


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--i-confirm-private", action="store_true",
        help="Required. Confirms the destination repo is PRIVATE -- the export "
        "contains ACLED-derived columns that must not be published publicly.")
    args = parser.parse_args()
    if not args.i_confirm_private:
        raise SystemExit(
            "Refusing to export: the CSV includes ACLED-derived columns (EULA "
            "forbids PUBLIC redistribution). Re-run with --i-confirm-private "
            "ONLY if the repo is private and the data stays for your own "
            "research. See data/published/README.md.")

    if not PANEL.exists():
        raise FileNotFoundError(f"Missing panel: {PANEL}. Build it first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log(f"Reading {PANEL}")
    df = pd.read_parquet(PANEL)
    log(f"  {len(df):,} rows x {df.shape[1]} cols")

    # Round float columns for size + readability (parquet keeps full precision).
    floats = df.select_dtypes("float").columns
    df[floats] = df[floats].round(FLOAT_DECIMALS)
    df = df.sort_values(["district_id", "year"], kind="mergesort").reset_index(drop=True)

    # --- full gzipped CSV ----------------------------------------------------
    df.to_csv(OUT_FULL, index=False, compression={"method": "gzip", "compresslevel": 9})
    size_mb = OUT_FULL.stat().st_size / 1e6
    log(f"Wrote {OUT_FULL.name} ({size_mb:.1f} MB gzipped, all {df.shape[1]} cols)")

    # --- illustrative sample (renders in GitHub's web UI) --------------------
    dids = df["district_id"].drop_duplicates()
    chosen = set(dids.sample(SAMPLE_DISTRICTS, random_state=SAMPLE_SEED))
    chosen.add(HIGHLIGHT_ID)
    sample = df[df["district_id"].isin(chosen)].copy()
    sample.to_csv(OUT_SAMPLE, index=False)
    log(f"Wrote {OUT_SAMPLE.name} ({len(sample):,} rows from "
        f"{sample['district_id'].nunique()} districts, full {df.shape[1]} cols)")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
