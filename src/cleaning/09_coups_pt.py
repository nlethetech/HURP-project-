#!/usr/bin/env python3
"""Parse Powell & Thyne coups into a tidy ISO3 country-year coup-count table.

Purpose
-------
Turn the Powell & Thyne country-year coup file (raw, downloaded by
src/acquisition/09_download_coups_pt.py) into a long, deterministic
country-year table of coup counts for the panel (see docs/DATA_SOURCES.md,
"Powell & Thyne -- Global Instances of Coups").

The raw file has up to four coup events per country-year in columns
`coup1`..`coup4`, each cell coding ONE event: 2 = successful coup, 1 = failed
(attempted) coup, 0 = none. This step collapses those into per-country-year
counts and maps each country to ISO3 so it can be broadcast onto the spine.

Inputs
------
    data/raw/coups_powell_thyne/powell_thyne_ccode_year.txt
        (tab-separated; columns ccode, abbrev, country, year, ccode_gw,
         ccode_polity, coup1..coup4, date1..date4, version; quoted strings)

Output
------
    data/interim/coups_pt.parquet
        One row per (iso3, year) that carries at least one coup event in the
        panel window (rows with zero events are NOT stored; the merge step
        zero-fills the full district-year frame -- the file is globally
        complete, so an absent country-year is a true zero, like UCDP GED):
            iso3              (str)  ISO3 country code  [from country name]
            year              (int)
            coups_total       (int)  count of coup events that year (coupN != 0)
            coups_successful  (int)  count of coupN == 2
            coups_failed      (int)  count of coupN == 1
        Sorted deterministically by (iso3, year).

Country -> ISO3 mapping (registry "Gotchas" 1-2)
------------------------------------------------
The file has no ISO3 column; the COW `abbrev` differs from ISO3 and the COW
`ccode` is not supported by country_converter. We therefore map the `country`
NAME string with country_converter's regex matcher. A small, explicit set of
historical / non-sovereign entities does not resolve to a modern ISO3 and is
dropped (logged): South Vietnam (ended 1975), the pre-1990 German states,
Yugoslavia, Zanzibar, Tibet, Abkhazia, South Ossetia. A HARD GUARD asserts that
every coup EVENT in the panel window 1989-2025 lands on a mapped ISO3, so a
future coup recorded for an entity we silently drop will fail the build loudly.

Runtime
-------
A few seconds (one small text file; one country_converter pass).

How to run
----------
    .venv/bin/python src/cleaning/09_coups_pt.py

Idempotent: the output parquet is rewritten in full each run from the immutable
raw file, with a fixed sort order, so re-runs are byte-stable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import country_converter as coco
import pandas as pd

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_TXT = REPO_ROOT / "data" / "raw" / "coups_powell_thyne" / "powell_thyne_ccode_year.txt"
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "coups_pt.parquet"

COUP_COLS = ["coup1", "coup2", "coup3", "coup4"]

# Panel window over which the coup layer is asserted complete (matches the
# panel's UCDP-set window). Used only for the hard mapping guard below.
WINDOW_MIN, WINDOW_MAX = 1989, 2025

# Historical / non-sovereign entities in the file that do NOT map to a modern
# ISO3. All of these are out of the panel window or never sovereign in it; they
# are dropped with logging. The guard below ensures no IN-WINDOW coup event is
# silently lost this way (the only coup-country here, South Vietnam, ended 1975).
KNOWN_UNMAPPED = {
    "Vietnam, Republic of",          # South Vietnam, dissolved 1975
    "Vietnam, Democratic Republic of",  # North Vietnam -> modern VNM via the
                                         # unified "Vietnam" rows; this label
                                         # is the pre-1976 entity
    "German Democratic Republic",    # East Germany, pre-1990
    "German Federal Republic",       # West Germany label, pre-1990
    "Yugoslavia",                    # SFRY / FRY, dissolved
    "Zanzibar",                      # merged into Tanzania 1964
    "Tibet",                         # not a sovereign state
    "Abkhazia",                      # not a UN-recognized state
    "South Ossetia",                 # not a UN-recognized state
}


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    if not RAW_TXT.exists():
        raise FileNotFoundError(
            f"Raw input missing: {RAW_TXT}\n"
            "Run: .venv/bin/python src/acquisition/09_download_coups_pt.py"
        )

    log(f"Reading {RAW_TXT}")
    df = pd.read_csv(RAW_TXT, sep="\t", dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Strip surrounding quotes from string fields (registry "Gotchas" 5).
    for c in ["abbrev", "country", "version"]:
        df[c] = df[c].str.strip().str.strip('"')

    df["year"] = df["year"].astype(int)
    for c in COUP_COLS:
        # Coup cells are 0/1/2 integers; empty cells (none recorded) -> 0.
        df[c] = pd.to_numeric(df[c], errors="raise").fillna(0).astype(int)

    bad_codes = sorted(set(pd.unique(df[COUP_COLS].values.ravel())) - {0, 1, 2})
    if bad_codes:
        raise ValueError(
            f"Unexpected coup codes {bad_codes}; expected only 0/1/2. Aborting."
        )

    version = df["version"].iloc[0]
    log(f"  dataset version: {version!r}; year range {df['year'].min()}-{df['year'].max()}")

    # --- collapse coup1..4 to per-country-year counts ------------------------
    cells = df[COUP_COLS]
    df["coups_total"] = (cells != 0).sum(axis=1).astype(int)
    df["coups_successful"] = (cells == 2).sum(axis=1).astype(int)
    df["coups_failed"] = (cells == 1).sum(axis=1).astype(int)

    # Keep only country-years with at least one event (zeros are reconstructed
    # by the merge zero-fill over the full district-year frame).
    events = df[df["coups_total"] > 0].copy()
    log(f"  country-years with >=1 coup event: {len(events)} "
        f"(all years {df['year'].min()}-{df['year'].max()})")

    # --- map country name -> ISO3 --------------------------------------------
    names = sorted(events["country"].unique())
    cc = coco.CountryConverter()
    iso = cc.convert(names, src="regex", to="ISO3", not_found=None)
    name_to_iso = {n: (i if i is not None else None) for n, i in zip(names, iso)}

    unmapped = sorted(n for n, i in name_to_iso.items() if i is None)
    unexpected_unmapped = [n for n in unmapped if n not in KNOWN_UNMAPPED]
    if unexpected_unmapped:
        raise RuntimeError(
            "country_converter could not map these coup-country names, and they "
            f"are not in the documented KNOWN_UNMAPPED set: {unexpected_unmapped}. "
            "Add an explicit mapping/override and re-run; aborting."
        )
    if unmapped:
        log(f"  dropped {len(unmapped)} unmappable historical entities: {unmapped}")

    events["iso3"] = events["country"].map(name_to_iso)

    # HARD GUARD: no IN-WINDOW coup event may be dropped by the name mapping.
    in_window_dropped = events[
        events["iso3"].isna()
        & events["year"].between(WINDOW_MIN, WINDOW_MAX)
    ]
    if len(in_window_dropped):
        rows = in_window_dropped[["country", "year", "coups_total"]].to_dict("records")
        raise AssertionError(
            f"{len(in_window_dropped)} coup event(s) in the panel window "
            f"{WINDOW_MIN}-{WINDOW_MAX} fell on an unmapped country: {rows}. "
            "These would be silently lost; add their ISO3 mapping. Aborting."
        )

    events = events[events["iso3"].notna()].copy()

    # --- final shape, types, deterministic order -----------------------------
    out = events[["iso3", "year", "coups_total", "coups_successful",
                  "coups_failed"]].copy()
    out["iso3"] = out["iso3"].astype(str)
    out["year"] = out["year"].astype("int64")
    for c in ["coups_total", "coups_successful", "coups_failed"]:
        out[c] = out[c].astype("int64")

    # Invariant: the file is one row per (country, year), so (iso3, year) is
    # unique unless a name collides on ISO3 (e.g. two labels -> one state in the
    # same year). Collapse defensively by summing, then assert uniqueness.
    out = (
        out.groupby(["iso3", "year"], as_index=False)[
            ["coups_total", "coups_successful", "coups_failed"]
        ].sum()
    )
    if out.duplicated(subset=["iso3", "year"]).any():
        raise AssertionError("Duplicate (iso3, year) after grouping; aborting.")

    out = out.sort_values(["iso3", "year"], kind="mergesort").reset_index(drop=True)

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    log(f"Wrote {OUT_PARQUET} ({len(out):,} rows)")

    # --- summary -------------------------------------------------------------
    win = out[out["year"].between(WINDOW_MIN, WINDOW_MAX)]
    log("")
    log("=== COUPS (Powell & Thyne) SUMMARY ===")
    log(f"  dataset version:            {version}")
    log(f"  country-year rows (all):    {len(out):,}")
    log(f"  distinct countries (all):   {out['iso3'].nunique()}")
    log(f"  year range:                 {out['year'].min()}-{out['year'].max()}")
    log(f"  -- panel window {WINDOW_MIN}-{WINDOW_MAX} --")
    log(f"  coup country-years:         {len(win):,}")
    log(f"  total coup events:          {int(win['coups_total'].sum())}")
    log(f"  successful:                 {int(win['coups_successful'].sum())}")
    log(f"  failed/attempted:           {int(win['coups_failed'].sum())}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
