#!/usr/bin/env python3
"""Tag every district with continent/region and cut the study subset.

Purpose
-------
The global panel (`data/processed/panel_district_year.parquet`) has no
geographic grouping above the country (`iso3`). This step derives two
grouping columns and writes the region-restricted study panel for the
conflict x agriculture investigation:

    continent   Africa | America | Asia | Europe | Oceania | Antarctica
    region      Africa | South America | Central America | Caribbean |
                Northern America | <continent> (for non-America continents)

Both are deterministic functions of `iso3` via country_converter (coco,
pinned in requirements.txt). The mapping is written out verbatim to
`reference/iso3_region_crosswalk.csv` so a third party can audit exactly
which country went to which region.

Study definition
----------------
Keep `region in {Africa, South America, Caribbean}` -- the three heavily
colonized, agriculture-dependent regions chosen for the conflict/violence
<-> agricultural-output investigation (see docs/DATASET_PLAN.md, "Study
subset"). Everything else is filtered out. No rows are otherwise altered:
the subset is a strict row filter of the master panel plus the two new
columns, so every downstream fill/mask from the master panel is preserved.

Inputs
------
    data/processed/panel_district_year.parquet
        Global district-year master panel (1,825,173 rows x 61 cols).

Outputs
-------
    data/processed/panel_africa_samerica_caribbean.parquet
        Study panel: master rows whose region is Africa / South America /
        Caribbean, plus `continent` and `region`. One row per
        (district_id, year); 63 columns.
    reference/iso3_region_crosswalk.csv
        Every iso3 in the master panel -> continent, region, kept flag.
        Small, reproducible, auditable (track in git alongside the scripts).

Run
---
    .venv/bin/python src/subset/01_region_filter.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import country_converter as coco
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "panel_district_year.parquet"
OUT_PANEL = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean.parquet"
OUT_CROSSWALK = ROOT / "reference" / "iso3_region_crosswalk.csv"

# The three regions that define the study subset.
KEEP_REGIONS = ("Africa", "South America", "Caribbean")

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("region_filter")


def build_region_map(iso3_codes: list[str]) -> pd.DataFrame:
    """Map each iso3 -> continent and region via coco (deterministic)."""
    cc = coco.CountryConverter()
    # coco returns "not found" (not an exception) for codes it cannot resolve.
    continent = cc.convert(iso3_codes, src="ISO3", to="continent", not_found="not found")
    unregion = cc.convert(iso3_codes, src="ISO3", to="UNregion", not_found="not found")

    m = pd.DataFrame({"iso3": iso3_codes, "continent": continent, "unregion": unregion})

    # `region` = finer split inside the Americas, continent elsewhere.
    def region_of(row: pd.Series) -> str:
        if row["continent"] == "America":
            return row["unregion"]  # South America / Central America / Caribbean / Northern America
        return row["continent"]

    m["region"] = m.apply(region_of, axis=1)
    m["kept"] = m["region"].isin(KEEP_REGIONS)

    unmapped = m[m["continent"] == "not found"]
    if len(unmapped):
        log.warning(
            "WARNING: %d iso3 codes did not resolve to a continent: %s",
            len(unmapped),
            ", ".join(sorted(unmapped["iso3"])),
        )
    return m


def main() -> None:
    if not MASTER.exists():
        raise SystemExit(f"master panel not found: {MASTER}")

    log.info("reading %s", MASTER.name)
    df = pd.read_parquet(MASTER)
    n_before = len(df)

    iso3_codes = sorted(df["iso3"].dropna().unique().tolist())
    log.info("resolving continent/region for %d countries", len(iso3_codes))
    region_map = build_region_map(iso3_codes)

    # Persist the audit crosswalk (sorted, deterministic).
    OUT_CROSSWALK.parent.mkdir(parents=True, exist_ok=True)
    region_map.sort_values("iso3").to_csv(OUT_CROSSWALK, index=False)
    log.info("wrote crosswalk -> %s (%d countries)", OUT_CROSSWALK.name, len(region_map))

    # Attach continent/region, then filter.
    lookup = region_map.set_index("iso3")[["continent", "region"]]
    df = df.merge(lookup, left_on="iso3", right_index=True, how="left")

    study = df[df["region"].isin(KEEP_REGIONS)].copy()
    study = study.sort_values(["district_id", "year"]).reset_index(drop=True)

    # Integrity: still exactly one row per (district_id, year).
    dup = study.duplicated(["district_id", "year"]).sum()
    assert dup == 0, f"{dup} duplicate (district_id, year) rows after filter"

    study.to_parquet(OUT_PANEL, index=False)

    # Summary.
    log.info("")
    log.info("=== study subset written ===")
    log.info("rows: %d -> %d  (%.1f%% of master)", n_before, len(study), 100 * len(study) / n_before)
    log.info("countries: %d", study["iso3"].nunique())
    log.info("years: %d-%d", int(study["year"].min()), int(study["year"].max()))
    log.info("columns: %d", study.shape[1])
    log.info("")
    for reg in KEEP_REGIONS:
        sub = study[study["region"] == reg]
        log.info("  %-16s %8d rows  %3d countries", reg, len(sub), sub["iso3"].nunique())
    log.info("")
    log.info("wrote -> %s", OUT_PANEL.relative_to(ROOT))


if __name__ == "__main__":
    main()
