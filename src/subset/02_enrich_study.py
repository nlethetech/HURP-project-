#!/usr/bin/env python3
"""Enrich the Africa+SouthAmerica+Caribbean study panel with the new layers.

Purpose
-------
Left-join the enrichment interim tables onto the region-filtered study panel
(`panel_africa_samerica_caribbean.parquet` from src/subset/01_region_filter.py)
and derive the time-varying columns that need `year`.

Layers joined
-------------
    data/interim/colonial.parquet          country-level colonial moderators
        (join on iso3; time-invariant except the independence-year seed).
    data/interim/{state_capacity,regime,repression}.parquet  country-year
        mediators (join on iso3+year; iso3_broadcast, TIME-VARYING; NaN where
        unobserved, never zero-filled).
    data/interim/faw_district_year.parquet  fall-armyworm monitoring (Africa)
        (join on district_id+year for observations; district_id for the
         first-detection-year constant). NON-monitored district-years stay NaN.
    data/interim/locust_district_year.parquet  desert-locust swarm+band (Africa)
        (same join pattern). NON-surveyed district-years stay NaN.

Pest and mediator layers are MONITORING/SURVEY/reported data: absence of a row
means not-observed, NOT zero, so they are NEVER zero-filled across the frame —
only observed rows carry values; everything else is NaN by construction.

Derived here
------------
    years_since_independence  = year - independence_year   (colonial; TIME-VARYING)
    years_since_faw_arrival   = year - faw_first_detection_year (pest; TIME-VARYING;
        broadcast the district's first-detection year to all its years)
    faw_arrived               = 1 if year >= faw_first_detection_year else 0

Inputs / Output
---------------
    in:  data/processed/panel_africa_samerica_caribbean.parquet   (study base, 63 cols)
         data/interim/{colonial,state_capacity,regime,repression,
                       faw_district_year,locust_district_year}.parquet
    out: data/processed/panel_africa_samerica_caribbean_enriched.parquet
         One row per (district_id, year); base + colonial + mediator + pest layers.

Run
---
    .venv/bin/python src/subset/02_enrich_study.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean.parquet"
COLONIAL = ROOT / "data" / "interim" / "colonial.parquet"
FAW = ROOT / "data" / "interim" / "faw_district_year.parquet"
LOCUST = ROOT / "data" / "interim" / "locust_district_year.parquet"
STATE_CAP = ROOT / "data" / "interim" / "state_capacity.parquet"
REGIME = ROOT / "data" / "interim" / "regime.parquet"
REPRESSION = ROOT / "data" / "interim" / "repression.parquet"
DISPLACEMENT = ROOT / "data" / "interim" / "displacement.parquet"
TEMPERATURE = ROOT / "data" / "interim" / "temperature_cru.parquet"
MARKET_ACCESS = ROOT / "data" / "interim" / "market_access.parquet"
RESOURCES = ROOT / "data" / "interim" / "resources.parquet"
ETHNIC = ROOT / "data" / "interim" / "ethnic_epr.parquet"
FOOD_INSEC = ROOT / "data" / "interim" / "food_insecurity.parquet"
FAOSTAT_AG = ROOT / "data" / "interim" / "faostat_ag.parquet"
OUT = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean_enriched.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("enrich")

COLONIAL_COLS = [
    "colonizer", "coldat_colonizer_last", "col_ever_colonized", "coldat_n_colonizers",
    "col_start_year", "col_end_year", "col_duration_years", "independence_year",
    "legal_origin", "legal_origin_filled", "legal_origin_imputed", "civil_vs_common",
    "col_british", "col_french", "col_iberian",
]
# Pest observation columns joined on (district_id, year); NaN where not observed.
FAW_OBS = ["faw_n_trap_checks", "faw_confirmed_sum", "faw_suspconf_sum", "faw_present", "faw_catch_rate"]
LOCUST_OBS = ["dl_swarm_obs", "dl_band_obs", "dl_gregarious_obs", "dl_area_treated_ha", "dl_present_flag"]
# Country-year mediator layers joined on (iso3, year); NaN where unobserved, never zero-filled.
STATE_CAP_COLS = ["grd_tax_pct_gdp", "grd_nonresource_tax_pct_gdp", "grd_totrev_pct_gdp",
                  "grd_resource_rev_pct_gdp", "grd_gov_level", "grd_quality_flag"]
REGIME_COLS = ["vdem_polyarchy", "vdem_libdem", "vdem_rule_of_law", "vdem_corruption",
               "vdem_regime", "vdem_terr_control", "polity2", "anocracy_flag"]
REPRESSION_COLS = ["pts_amnesty", "pts_state", "pts_hrw", "pts_score", "pts_source"]
DISPLACEMENT_COLS = ["refugees_origin", "asylum_seekers_origin", "idp_stock_unhcr",
                     "returned_refugees", "returned_idps", "idp_stock_conflict",
                     "new_disp_conflict", "idp_stock_disaster", "new_disp_disaster"]
# Spatial layers. Temperature + ethnic join on (district_id, year); market access +
# resources are district-constant (join on district_id, broadcast to all years).
TEMPERATURE_COLS = ["temp_mean", "temp_anomaly"]
ETHNIC_COLS = ["n_groups_overlap", "share_area_excluded", "ethnic_fractionalization", "any_excluded"]
FOOD_COLS = ["ipc_phase_max", "ipc_phase_modal", "ipc_n_reports", "ipc_phase3plus_area_share",
             "ipc_crisis_flag", "fews_covered"]
MARKET_COLS = ["travel_time_to_city_min_median", "travel_time_to_city_min_mean",
               "travel_time_to_city_log1p", "market_access_snapshot_year"]
RESOURCE_COLS = ["has_oil_gas", "n_oil_gas_fields", "has_oil", "has_gas", "oil_gas_first_discovery_year",
                 "has_diamond", "n_diamond_deposits", "n_diamond_secondary", "n_diamond_primary",
                 "has_lootable_diamond", "n_mineral_deposits"]


def main() -> None:
    for p, hint in [(BASE, "src/subset/01_region_filter.py"), (COLONIAL, "src/cleaning/12_colonial.py"),
                    (FAW, "src/cleaning/13_faw.py"), (LOCUST, "src/cleaning/14_locust.py")]:
        if not p.exists():
            raise SystemExit(f"missing input {p} — run {hint} first")
    df = pd.read_parquet(BASE)
    n0, ncol0 = df.shape

    # --- Colonial (country-level; broadcast by iso3) ---
    col = pd.read_parquet(COLONIAL)[["iso3"] + COLONIAL_COLS]
    df = df.merge(col, on="iso3", how="left")
    assert len(df) == n0, "row count changed on colonial join"
    df["years_since_independence"] = df["year"] - df["independence_year"]

    # --- Country-year mediators (iso3_broadcast; NaN where unobserved, never zero-filled) ---
    for path, cols in [(STATE_CAP, STATE_CAP_COLS), (REGIME, REGIME_COLS),
                       (REPRESSION, REPRESSION_COLS), (DISPLACEMENT, DISPLACEMENT_COLS)]:
        if not path.exists():
            raise SystemExit(f"missing input {path} — run its cleaning lane first")
        t = pd.read_parquet(path)[["iso3", "year"] + cols]
        df = df.merge(t, on=["iso3", "year"], how="left")
        assert len(df) == n0, f"row count changed joining {path.name}"

    # --- Spatial layers (district-level; NaN where unobserved, never zero-filled) ---
    for path, cols in [(TEMPERATURE, TEMPERATURE_COLS), (ETHNIC, ETHNIC_COLS), (FOOD_INSEC, FOOD_COLS)]:
        if not path.exists():
            raise SystemExit(f"missing input {path} — run its cleaning lane first")
        t = pd.read_parquet(path)[["district_id", "year"] + cols]
        df = df.merge(t, on=["district_id", "year"], how="left")
        assert len(df) == n0, f"row count changed joining {path.name}"
    for path, cols in [(MARKET_ACCESS, MARKET_COLS), (RESOURCES, RESOURCE_COLS)]:
        if not path.exists():
            raise SystemExit(f"missing input {path} — run its cleaning lane first")
        t = pd.read_parquet(path)[["district_id"] + cols]  # district-constant -> broadcast to all years
        df = df.merge(t, on="district_id", how="left")
        assert len(df) == n0, f"row count changed joining {path.name}"

    # --- FAOSTAT agricultural output (country-year, iso3_broadcast; all fao_* cols) ---
    if not FAOSTAT_AG.exists():
        raise SystemExit(f"missing input {FAOSTAT_AG} — run src/cleaning/24_faostat_ag.py first")
    fao = pd.read_parquet(FAOSTAT_AG)
    df = df.merge(fao, on=["iso3", "year"], how="left")
    assert len(df) == n0, "row count changed joining faostat_ag"

    # Pest sources run to 2026 but the panel ends 2025. Drop out-of-window obs
    # EXPLICITLY (log any African-study losses) and recompute first-detection ONLY
    # within the window — else a district whose sole obs is 2026 gets an
    # out-of-panel arrival year pointing at a year with no presence row.
    panel_max = int(df["year"].max())
    afr_districts = set(df.loc[df["region"] == "Africa", "district_id"])

    def cap_to_window(tbl: pd.DataFrame, label: str) -> pd.DataFrame:
        beyond = tbl[(tbl["year"] > panel_max) & (tbl["district_id"].isin(afr_districts))]
        if len(beyond):
            log.info("dropping %d %s obs beyond panel year %d (African study districts, out of window)",
                     len(beyond), label, panel_max)
        return tbl[tbl["year"] <= panel_max]

    # --- Fall armyworm (obs on district_id+year; first-detection broadcast by district) ---
    faw = cap_to_window(pd.read_parquet(FAW), "FAW")
    df = df.merge(faw[["district_id", "year"] + FAW_OBS], on=["district_id", "year"], how="left")
    faw_first = (faw[faw["faw_confirmed_sum"] > 0].groupby("district_id")["year"].min()
                 .rename("faw_first_detection_year").reset_index())
    df = df.merge(faw_first, on="district_id", how="left")
    df["years_since_faw_arrival"] = df["year"] - df["faw_first_detection_year"]
    df["faw_arrived"] = (df["year"] >= df["faw_first_detection_year"]).astype("float")  # NaN if never
    df.loc[df["faw_first_detection_year"].isna(), "faw_arrived"] = pd.NA

    # --- Desert locust (obs on district_id+year; first-year broadcast by district) ---
    loc = cap_to_window(pd.read_parquet(LOCUST), "locust")
    df = df.merge(loc[["district_id", "year"] + LOCUST_OBS], on=["district_id", "year"], how="left")
    loc_first = (loc.groupby("district_id")["year"].min()
                 .rename("dl_first_gregarious_year").reset_index())
    df = df.merge(loc_first, on="district_id", how="left")

    # Pest layers are Africa-only BY DESIGN (no georeferenced locust/FAW data exists
    # for South America or the Caribbean). Mask any stray non-African matches to NaN
    # so the columns cannot imply Americas coverage — in practice this is only 2
    # isolated Peru FAMEWS trap-checks (2021, no FAW detected).
    pest_cols = (FAW_OBS + ["faw_first_detection_year", "years_since_faw_arrival", "faw_arrived"]
                 + LOCUST_OBS + ["dl_first_gregarious_year"])
    n_masked = int(df.loc[df["region"] != "Africa", pest_cols].notna().any(axis=1).sum())
    df.loc[df["region"] != "Africa", pest_cols] = np.nan
    log.info("masked %d non-African district-years to NaN on the pest layer (Africa-only by design)", n_masked)

    assert len(df) == n0, "row count changed after pest joins"
    df = df.sort_values(["district_id", "year"]).reset_index(drop=True)
    assert df.duplicated(["district_id", "year"]).sum() == 0, "duplicate keys after enrich"
    df.to_parquet(OUT, index=False)

    # --- Diagnostics ---
    log.info("=== study panel enriched ===")
    log.info("rows: %d   cols: %d -> %d", n0, ncol0, df.shape[1])
    log.info("countries: %d", df["iso3"].nunique())
    log.info("")
    log.info("[colonial] missing colonizer=%d  legal=%d  independence=%d (countries)",
             df[df["colonizer"].isna()]["iso3"].nunique(),
             df[df["civil_vs_common"].isna()]["iso3"].nunique(),
             df[df["independence_year"].isna()]["iso3"].nunique())
    log.info("")
    log.info("[fall armyworm] observed district-years: %d in %d districts, %d countries (%d–%d)",
             int(df["faw_present"].notna().sum()), df[df["faw_present"].notna()]["district_id"].nunique(),
             df[df["faw_present"].notna()]["iso3"].nunique(),
             int(df.loc[df["faw_present"].notna(), "year"].min()),
             int(df.loc[df["faw_present"].notna(), "year"].max()))
    log.info("[fall armyworm] districts that ever detected FAW: %d",
             df.dropna(subset=["faw_first_detection_year"])["district_id"].nunique())
    log.info("")
    log.info("[desert locust] observed district-years: %d in %d districts, %d countries (%d–%d)",
             int(df["dl_present_flag"].notna().sum()), df[df["dl_present_flag"].notna()]["district_id"].nunique(),
             df[df["dl_present_flag"].notna()]["iso3"].nunique(),
             int(df.loc[df["dl_present_flag"].notna(), "year"].min()),
             int(df.loc[df["dl_present_flag"].notna(), "year"].max()))
    log.info("[desert locust] locust-affected countries in study: %s",
             sorted(df[df["dl_present_flag"].notna()]["iso3"].unique().tolist()))
    log.info("")
    log.info("final columns: %d", df.shape[1])
    log.info("wrote -> %s", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
