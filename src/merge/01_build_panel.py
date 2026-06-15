#!/usr/bin/env python3
"""Join the interim layers onto the spine x year frame -> the analysis panel.

Purpose
-------
Build the final district-year analysis panel by left-joining every cleaned
interim layer onto the cross product of the admin-2 spine and the panel years
1989-2025. No source-specific cleaning happens here: each input is already a
tidy district-year (or district, or country-year) table produced by a
src/cleaning/ script. This script only aligns keys, joins with asserted
cardinalities, applies the documented fills / carry-forwards, derives the two
crop-mix statics (cropland_ha, price_shock_coverage) and the shift-share
price shock, and writes one deterministic parquet.

See docs/DATASET_PLAN.md (panel design) and docs/CODEBOOK.md (per-column
definitions). Every fill, carry-forward and filter applied here is recorded in
the codebook.

Inputs
------
    data/interim/spine.parquet
        49,329 admin-2 districts: district_id, iso3, district_name, admin_level
    data/interim/conflict_ged.parquet
        Wide UCDP GED 26.1, one row per (district_id, iso3, year):
        n_events_* and deaths_{best,low,high,civilians}_* for sb/ns/os/total.
    data/interim/weather_chirps.parquet
        CHIRPS v2.0 district-year precip_mm (1989-2024, 50S-50N).
    data/interim/ag_yields_gdhy.parquet
        GDHY v1.2/1.3 district-year-crop yield_t_ha (maize/rice/wheat/soybean,
        1981-2016).
    data/interim/income_class.parquet
        World Bank OGHIST income groups, one row per (iso3, fiscal_year):
        data_year, income_group (L/LM/UM/H/NA), raw_code.
    data/interim/coups_pt.parquet
        Powell & Thyne coup counts, one row per (iso3, year) with >=1 event:
        coups_total, coups_successful, coups_failed (national covariate).
    data/interim/acled_district_year.parquet
        ACLED events per (district_id, iso3, year): acled_events_total + per
        event-type counts (battles/protests/riots/vac/explosions/strategic) +
        acled_fatalities. Coverage-masked at merge time.
    data/interim/acled_coverage.parquet
        Per-iso3 observed ACLED span (acled_first_year, acled_last_year) used
        to build the coverage mask (zero-fill vs NaN).
    data/interim/wb_wdi.parquet
        World Bank WDI socioeconomic/agricultural covariates per (iso3, year):
        15 wb_* columns (unemployment, gdp_pc, inflation, population, ag, ...).
    data/interim/cropmix_spam2020.parquet
        SPAM 2020 v2.0 R2 district crop mix: crop ("<code> <name>"),
        harv_area_ha, crop_share (time-invariant).
    data/interim/prices_pinksheet.parquet
        World Bank Pink Sheet annual commodity prices: commodity_code,
        commodity_name, year, price, price_real, unit, dlog_price (NOMINAL).
    reference/spam_pinksheet_crosswalk.csv
        Confident 1:1 SPAM crop -> Pink Sheet commodity map (committed):
        spam_crop, spam_crop_name, pink_code, pink_name, note.

Outputs
-------
    data/processed/panel_district_year.parquet
        One row per (district_id, year), 49,329 x 37 = 1,825,173 rows.
        Columns: keys + identity (district_id, iso3, district_name,
        admin_level, year); conflict (n_events_*/deaths_*_*, zero-filled);
        weather (precip_mm, not filled); yields (yield_maize/rice/wheat/
        soybean, not filled); income (income_group, income_group_carried);
        crop-mix statics (cropland_ha, price_shock_coverage); shift-share
        price_shock.
    reports/panel_build_report.txt
        Plain-text validation report: row count, per-column non-null counts,
        join cardinalities, income carry-forward and unmatched-iso3 tallies,
        crosswalk coverage, and the price_shock distribution.

Key construction decisions (full rationale in docs/CODEBOOK.md)
---------------------------------------------------------------
  * Frame: spine x [1989..2025]; exactly 49,329 x 37 = 1,825,173 rows
    (asserted).
  * Conflict: left-joined wide GED, then NaN counts/deaths filled with 0.
    UCDP GED is globally complete for fatal organized violence over
    1989-2025, so an absent district-year is a true zero (codebook).
  * Weather: precip_mm left-joined, NOT filled. NaN outside CHIRPS's
    50S-50N band and for 2025 (CHIRPS interim stops at 2024).
  * Yields: GDHY pivoted to yield_{maize,rice,wheat,soybean}; NOT filled.
    NaN where the crop is absent in the district or year > 2016.
  * Income: joined by iso3 + (data_year == panel year). For panel years
    beyond an iso3's last OGHIST data_year, the latest classification is
    carried forward (income_group_carried = True). data_year runs 1987-2024,
    so panel year 2025 is always carried.
  * Crop-mix statics (time-invariant per district): cropland_ha = sum of SPAM
    harv_area_ha; price_shock_coverage = share of that cropland in crops the
    crosswalk maps to a Pink Sheet commodity.
  * price_shock_t = sum over MAPPED crops c of crop_share_c * dlog_real_c,t,
    where dlog_real_c,t = log(price_real_c,t) - log(price_real_c,t-1) from the
    Pink Sheet REAL annual series. Unmapped crops contribute 0 and the shares
    are NOT renormalized (so the shock is comparable across districts: a
    district with little mapped cropland mechanically gets a smaller shock,
    which price_shock_coverage records). A mapped crop whose real price is
    unavailable in year t (barley/sorghum after 2020) contributes 0 that year.
    price_shock is NaN only for districts with no SPAM cropland at all.

Runtime
-------
~30-90 seconds (the GDHY pivot and the SPAM x price shift-share dominate).

How to run
----------
    .venv/bin/python src/merge/01_build_panel.py

Idempotent: the output is rewritten in full each run from the immutable interim
tables and the committed crosswalk. Deterministic: fixed sort order, no
timestamps in the data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM = REPO_ROOT / "data" / "interim"
REFERENCE = REPO_ROOT / "reference"

SPINE = INTERIM / "spine.parquet"
CONFLICT = INTERIM / "conflict_ged.parquet"
WEATHER = INTERIM / "weather_chirps.parquet"
YIELDS = INTERIM / "ag_yields_gdhy.parquet"
INCOME = INTERIM / "income_class.parquet"
COUPS = INTERIM / "coups_pt.parquet"
ACLED = INTERIM / "acled_district_year.parquet"
ACLED_COVERAGE = INTERIM / "acled_coverage.parquet"
WDI = INTERIM / "wb_wdi.parquet"
CROPMIX = INTERIM / "cropmix_spam2020.parquet"
PRICES = INTERIM / "prices_pinksheet.parquet"

# Powell & Thyne coup-count columns (national covariate, zero-filled).
COUPS_COLS = ["coups_total", "coups_successful", "coups_failed"]

# ACLED district-year columns (coverage-masked: 0 where covered-but-no-event,
# NaN where the country-year is OUTSIDE ACLED's staggered coverage window).
ACLED_COLS = [
    "acled_events_total",
    "acled_events_battles", "acled_events_protests", "acled_events_riots",
    "acled_events_vac", "acled_events_explosions", "acled_events_strategic",
    "acled_fatalities",
]

# World Bank WDI socioeconomic/agricultural covariates (national, NOT filled:
# NaN = no WB observation, since these are continuous measures).
WDI_COLS = [
    "wb_unemployment", "wb_unemployment_youth", "wb_gdp_pc", "wb_gdp_growth",
    "wb_inflation", "wb_population", "wb_pop_growth", "wb_pop_0_14",
    "wb_urban_pct", "wb_ag_valueadd_pct", "wb_ag_employment_pct",
    "wb_ag_land_pct", "wb_cereal_yield", "wb_food_prod_index",
    "wb_arable_land_pct",
]
CROSSWALK = REFERENCE / "spam_pinksheet_crosswalk.csv"

OUT_PANEL = REPO_ROOT / "data" / "processed" / "panel_district_year.parquet"
OUT_REPORT = REPO_ROOT / "reports" / "panel_build_report.txt"

# Panel time window (set by UCDP GED coverage; DATASET_PLAN.md).
YEAR_MIN = 1989
YEAR_MAX = 2025
N_YEARS = YEAR_MAX - YEAR_MIN + 1  # 37

# Registry-pinned spine size; asserted on load (loud failure if violated).
EXPECTED_N_DISTRICTS = 49_329
EXPECTED_N_ROWS = EXPECTED_N_DISTRICTS * N_YEARS  # 1,825,173

# GDHY crops -> panel yield columns.
YIELD_CROPS = ["maize", "rice", "wheat", "soybean"]

# Conflict measure stems and per-type/total suffixes (mirrors the wide GED
# layer). Every such column is zero-filled after the left join.
CONFLICT_STEMS = [
    "n_events",
    "deaths_best",
    "deaths_low",
    "deaths_high",
    "deaths_civilians",
]
CONFLICT_SUFFIXES = ["sb", "ns", "os", "total"]


def log(msg: str) -> None:
    print(msg, flush=True)


def require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Required input missing: {path}\n"
            "Run the acquisition + cleaning scripts (see README 'Reproducing "
            "the dataset') before the merge."
        )


def build_frame(spine: pd.DataFrame) -> pd.DataFrame:
    """Cross product spine x [YEAR_MIN..YEAR_MAX]; assert the exact shape."""
    years = pd.DataFrame({"year": np.arange(YEAR_MIN, YEAR_MAX + 1, dtype="int64")})
    frame = spine.merge(years, how="cross")
    if len(frame) != EXPECTED_N_ROWS:
        raise AssertionError(
            f"Frame has {len(frame):,} rows, expected "
            f"{EXPECTED_N_ROWS:,} = {len(spine):,} districts x {N_YEARS} years."
        )
    if frame.duplicated(["district_id", "year"]).any():
        raise AssertionError("Frame has duplicate (district_id, year) keys.")
    return frame


def join_conflict(frame: pd.DataFrame) -> pd.DataFrame:
    """Left-join wide GED on (district_id, year); zero-fill counts/deaths.

    UCDP GED is globally complete for fatal organized violence 1989-2025, so a
    district-year absent from GED is a true zero, not missing data.
    """
    ged = pd.read_parquet(CONFLICT)
    # iso3 is already on the frame (from the spine); drop GED's copy to avoid a
    # redundant/conflicting column, key only on district_id + year.
    ged = ged.drop(columns=["iso3"])
    conflict_cols = [
        f"{stem}_{suf}" for stem in CONFLICT_STEMS for suf in CONFLICT_SUFFIXES
    ]
    missing = set(conflict_cols) - set(ged.columns)
    if missing:
        raise ValueError(f"GED wide layer missing columns: {sorted(missing)}")

    # GED is one row per (district_id, year); a frame row matches at most one
    # GED row -> validate many-to-one (m:1) on the keyed columns.
    out = frame.merge(
        ged[["district_id", "year", *conflict_cols]],
        on=["district_id", "year"],
        how="left",
        validate="m:1",
    )
    n_matched = int(out["n_events_total"].notna().sum())
    out[conflict_cols] = out[conflict_cols].fillna(0).astype("int64")
    log(
        f"  conflict: matched {n_matched:,} district-years to GED; "
        f"zero-filled {len(out) - n_matched:,} (true zeros)"
    )
    return out, conflict_cols


def join_coups(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Left-join Powell & Thyne coup counts on (iso3, year); zero-fill.

    The dataset is globally complete for sovereign states 1950-present, so a
    country-year absent from it had zero coups -- a true zero, like UCDP GED.
    Coups are a NATIONAL (admin-0) covariate: every district in a country-year
    receives that country's coup counts (broadcast on iso3, like income_group).
    """
    cp = pd.read_parquet(COUPS)
    cp["year"] = cp["year"].astype("int64")
    missing = set(COUPS_COLS) - set(cp.columns)
    if missing:
        raise ValueError(f"Coups layer missing columns: {sorted(missing)}")
    if cp.duplicated(["iso3", "year"]).any():
        raise AssertionError("Coups layer has duplicate (iso3, year) rows.")

    # Each frame row matches at most one coup country-year -> many-to-one.
    out = frame.merge(
        cp[["iso3", "year", *COUPS_COLS]],
        on=["iso3", "year"],
        how="left",
        validate="m:1",
    )
    n_matched = int(out["coups_total"].notna().sum())
    out[COUPS_COLS] = out[COUPS_COLS].fillna(0).astype("int64")
    log(
        f"  coups: matched {n_matched:,} district-years to a coup record; "
        f"zero-filled {len(out) - n_matched:,} (true zeros)"
    )
    return out, COUPS_COLS


def join_acled(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Left-join ACLED district-year counts, then apply the COVERAGE MASK.

    ACLED coverage is region-staggered (1997 Africa-only; most of the world
    only from 2018+), so -- unlike UCDP GED -- a blanket zero-fill would
    fabricate "no unrest" in country-years ACLED never covered. The mask:

      * a district-year that MATCHED ACLED keeps its observed counts;
      * a district-year with NO match but INSIDE its country's coverage window
        [acled_first_year .. acled_last_year] (per-country) is a TRUE zero -> 0.0;
      * a district-year OUTSIDE that window (before the country entered ACLED,
        after its last observed year, or a country ACLED does not cover at all)
        stays NaN -- "not covered", not zero.

    Columns are float64 so NaN (not-covered) and 0.0 (covered, no event) are
    distinct. The per-country window is each country's first..last OBSERVED
    ACLED data year -- a close, data-driven proxy for ACLED's published coverage
    span (conservative: never fabricates a zero where there is no data).
    """
    acled = pd.read_parquet(ACLED)
    cov = pd.read_parquet(ACLED_COVERAGE)
    missing = set(ACLED_COLS) - set(acled.columns)
    if missing:
        raise ValueError(f"ACLED layer missing columns: {sorted(missing)}")
    acled["year"] = acled["year"].astype("int64")
    if acled.duplicated(["district_id", "year"]).any():
        raise AssertionError("ACLED layer has duplicate (district_id, year).")

    out = frame.merge(
        acled[["district_id", "year", *ACLED_COLS]],
        on=["district_id", "year"], how="left", validate="m:1",
    )
    matched = out["acled_events_total"].notna()

    # Per-country coverage WINDOW [first .. last] from the observed ACLED span.
    # Using each country's OWN last data year (not a single global max) avoids
    # fabricating trailing-edge zeros for countries whose ACLED data ends before
    # the global maximum (e.g. lag/coverage differences). A country-year past a
    # country's last observed year stays NaN ("not observed"), never a 0.
    out = out.merge(
        cov[["iso3", "acled_first_year", "acled_last_year"]],
        on="iso3", how="left", validate="m:1",
    )
    covered = (
        out["acled_first_year"].notna()
        & (out["year"] >= out["acled_first_year"])
        & (out["year"] <= out["acled_last_year"])
    )
    fill_zero = covered & ~matched
    for c in ACLED_COLS:
        out.loc[fill_zero, c] = 0.0
        out[c] = out[c].astype("float64")
    out = out.drop(columns=["acled_first_year", "acled_last_year"])

    n_match = int(matched.sum())
    n_zero = int(fill_zero.sum())
    n_nan = int(out["acled_events_total"].isna().sum())
    n_cov_countries = int(cov["iso3"].nunique())
    log(
        f"  acled: matched {n_match:,} district-years; zero-filled {n_zero:,} "
        f"(covered, no event); left NaN {n_nan:,} (outside coverage). "
        f"Coverage: {n_cov_countries} countries (per-country observed spans)."
    )
    return out, ACLED_COLS


def join_wdi(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Left-join World Bank WDI covariates on (iso3, year); do NOT fill.

    National covariates broadcast onto every district of a country-year (like
    income_group / coups). These are continuous measures, so an absent
    (iso3, year) is MISSING DATA -> NaN, never zero. The WB reporting lag means
    the final 1-2 panel years are largely NaN for many indicators (documented
    in the codebook).
    """
    wdi = pd.read_parquet(WDI)
    missing = set(WDI_COLS) - set(wdi.columns)
    if missing:
        raise ValueError(f"WDI layer missing columns: {sorted(missing)}")
    wdi["year"] = wdi["year"].astype("int64")
    if wdi.duplicated(["iso3", "year"]).any():
        raise AssertionError("WDI layer has duplicate (iso3, year) rows.")

    out = frame.merge(
        wdi[["iso3", "year", *WDI_COLS]],
        on=["iso3", "year"], how="left", validate="m:1",
    )
    for c in WDI_COLS:
        out[c] = out[c].astype("float64")
    n_any = int(out[WDI_COLS].notna().any(axis=1).sum())
    log(f"  wdi: matched WB covariates for {n_any:,} district-years "
        f"(>=1 indicator non-null); {len(WDI_COLS)} indicators, not filled.")
    return out, WDI_COLS


def join_weather(frame: pd.DataFrame) -> pd.DataFrame:
    """Left-join CHIRPS precip_mm on (district_id, year); do NOT fill."""
    wx = pd.read_parquet(WEATHER)
    wx = wx[["district_id", "year"]].assign(precip_mm=wx["precip_mm"].astype("float64"))
    wx["year"] = wx["year"].astype("int64")
    out = frame.merge(wx, on=["district_id", "year"], how="left", validate="m:1")
    n = int(out["precip_mm"].notna().sum())
    log(f"  weather: matched precip_mm for {n:,} district-years (not filled)")
    return out


def join_yields(frame: pd.DataFrame) -> pd.DataFrame:
    """Pivot GDHY long to yield_<crop> wide, left-join; do NOT fill."""
    gd = pd.read_parquet(YIELDS)
    bad = set(gd["crop"].unique()) - set(YIELD_CROPS)
    if bad:
        raise ValueError(f"GDHY has unexpected crops {sorted(bad)}; aborting.")
    gd["year"] = gd["year"].astype("int64")
    wide = gd.pivot_table(
        index=["district_id", "year"],
        columns="crop",
        values="yield_t_ha",
        aggfunc="mean",  # one value per district-year-crop already; mean is a guard
    ).reset_index()
    rename = {c: f"yield_{c}" for c in YIELD_CROPS}
    wide = wide.rename(columns=rename)
    for c in YIELD_CROPS:
        col = f"yield_{c}"
        if col not in wide.columns:
            wide[col] = np.nan
    yield_cols = [f"yield_{c}" for c in YIELD_CROPS]
    out = frame.merge(
        wide[["district_id", "year", *yield_cols]],
        on=["district_id", "year"],
        how="left",
        validate="m:1",
    )
    for col in yield_cols:
        n = int(out[col].notna().sum())
        log(f"  yields: {col} non-null {n:,} (not filled; NaN where absent / year>2016)")
    return out, yield_cols


def join_income(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Join OGHIST income_group by iso3 + data_year, carrying the latest
    classification forward for panel years beyond an iso3's last data_year.

    Returns the frame with income_group + income_group_carried, and a stats
    dict (carried count, unmatched iso3 list, affected districts) for the
    report.
    """
    inc = pd.read_parquet(INCOME)
    inc = inc[["iso3", "data_year", "income_group"]].copy()
    inc["data_year"] = inc["data_year"].astype("int64")
    if inc.duplicated(["iso3", "data_year"]).any():
        raise AssertionError("OGHIST has duplicate (iso3, data_year) rows.")

    # 1) Direct join: panel year == OGHIST data_year (the GNI reference year).
    direct = inc.rename(columns={"data_year": "year"})
    out = frame.merge(
        direct,
        on=["iso3", "year"],
        how="left",
        validate="m:1",
    )
    out["income_group_carried"] = False

    # 2) Carry-forward: for rows still NaN, attach the iso3's latest available
    #    classification (max data_year), flagged income_group_carried = True.
    latest = (
        inc.sort_values(["iso3", "data_year"], kind="mergesort")
        .groupby("iso3", as_index=False)
        .tail(1)[["iso3", "income_group"]]
        .rename(columns={"income_group": "income_group_latest"})
    )
    need = out["income_group"].isna()
    out = out.merge(latest, on="iso3", how="left", validate="m:1")
    carried_mask = need & out["income_group_latest"].notna()
    out.loc[carried_mask, "income_group"] = out.loc[carried_mask, "income_group_latest"]
    out.loc[carried_mask, "income_group_carried"] = True
    out = out.drop(columns=["income_group_latest"])

    # iso3 that never match OGHIST at all (no direct, no carry-forward).
    unmatched_iso = sorted(
        set(frame["iso3"].unique()) - set(inc["iso3"].unique())
    )
    affected = frame[frame["iso3"].isin(unmatched_iso)]
    n_affected_districts = affected["district_id"].nunique()

    stats = {
        "n_carried": int(carried_mask.sum()),
        "unmatched_iso": unmatched_iso,
        "n_unmatched_districts": int(n_affected_districts),
        "unmatched_breakdown": (
            affected.groupby("iso3")["district_id"].nunique().to_dict()
        ),
    }
    log(
        f"  income: carried forward {stats['n_carried']:,} district-years; "
        f"iso3 never in OGHIST: {unmatched_iso} "
        f"({n_affected_districts} districts)"
    )
    return out, stats


def build_crop_statics_and_shock(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Derive cropland_ha, price_shock_coverage and the shift-share price_shock.

    cropland_ha and price_shock_coverage are time-invariant per district; the
    shock varies by year through the Pink Sheet real-price log-changes.
    """
    cm = pd.read_parquet(CROPMIX)
    xw = pd.read_csv(CROSSWALK)
    pk = pd.read_parquet(PRICES)

    # --- crosswalk integrity -------------------------------------------------
    if xw["spam_crop"].duplicated().any():
        raise AssertionError("Crosswalk has duplicate spam_crop entries.")
    if xw["pink_code"].duplicated().any():
        raise AssertionError("Crosswalk has duplicate pink_code entries.")

    # SPAM crop code = leading token of the "<code> <name>" crop string.
    cm = cm.copy()
    cm["spam_crop"] = cm["crop"].str.split(" ", n=1).str[0]

    spam_codes = set(cm["spam_crop"].unique())
    pink_codes = set(pk["commodity_code"].unique())
    bad_spam = sorted(set(xw["spam_crop"]) - spam_codes)
    bad_pink = sorted(set(xw["pink_code"]) - pink_codes)
    if bad_spam:
        raise ValueError(f"Crosswalk spam_crop not in SPAM data: {bad_spam}")
    if bad_pink:
        raise ValueError(f"Crosswalk pink_code not in Pink Sheet data: {bad_pink}")

    mapped_codes = set(xw["spam_crop"])

    # --- cropland_ha and price_shock_coverage (time-invariant) ---------------
    cropland = (
        cm.groupby("district_id", as_index=False)["harv_area_ha"]
        .sum()
        .rename(columns={"harv_area_ha": "cropland_ha"})
    )
    mapped_area = (
        cm[cm["spam_crop"].isin(mapped_codes)]
        .groupby("district_id", as_index=False)["harv_area_ha"]
        .sum()
        .rename(columns={"harv_area_ha": "mapped_area_ha"})
    )
    cov = cropland.merge(mapped_area, on="district_id", how="left")
    cov["mapped_area_ha"] = cov["mapped_area_ha"].fillna(0.0)
    # cropland_ha > 0 for every SPAM district (it is the sum of positive areas).
    if (cov["cropland_ha"] <= 0).any():
        raise AssertionError("Non-positive cropland_ha for a SPAM district.")
    cov["price_shock_coverage"] = cov["mapped_area_ha"] / cov["cropland_ha"]
    cov = cov[["district_id", "cropland_ha", "price_shock_coverage"]]

    # --- real-price log-change per mapped Pink Sheet commodity ---------------
    # The interim dlog_price is NOMINAL; the shock must use REAL prices, so
    # compute dlog_real from price_real here (a derivation, not a re-clean).
    pk = pk.sort_values(["commodity_code", "year"], kind="mergesort").copy()
    if (pk["price_real"].dropna() <= 0).any():
        raise AssertionError("Non-positive price_real in Pink Sheet; log undefined.")
    pk["dlog_real"] = pk.groupby("commodity_code")["price_real"].transform(
        lambda s: np.log(s).diff()
    )
    # restrict to mapped commodities and panel years
    code_map = dict(zip(xw["pink_code"], xw["spam_crop"]))
    pk_mapped = pk[pk["commodity_code"].isin(code_map)].copy()
    pk_mapped = pk_mapped[
        (pk_mapped["year"] >= YEAR_MIN) & (pk_mapped["year"] <= YEAR_MAX)
    ]
    pk_mapped["spam_crop"] = pk_mapped["commodity_code"].map(code_map)
    # year x spam_crop -> dlog_real (NaN where the real series is unavailable,
    # e.g. barley/sorghum after 2020). Such terms drop out of the shock sum
    # below (treated as a 0 contribution that year), which we document.
    price_panel = pk_mapped[["spam_crop", "year", "dlog_real"]].dropna(
        subset=["dlog_real"]
    )

    # --- shift-share shock: per district-year ---------------------------------
    # Long district x crop shares for mapped crops only.
    shares = cm[cm["spam_crop"].isin(mapped_codes)][
        ["district_id", "spam_crop", "crop_share"]
    ].copy()
    # Cartesian over years via the price panel: each (district, mapped crop)
    # share meets that crop's annual dlog_real, contributing share * dlog_real.
    contrib = shares.merge(price_panel, on="spam_crop", how="inner")
    contrib["term"] = contrib["crop_share"] * contrib["dlog_real"]
    shock = (
        contrib.groupby(["district_id", "year"], as_index=False)["term"]
        .sum()
        .rename(columns={"term": "price_shock"})
    )
    shock["year"] = shock["year"].astype("int64")

    # --- attach statics + shock onto the frame -------------------------------
    out = frame.merge(cov, on="district_id", how="left", validate="m:1")
    out = out.merge(shock, on=["district_id", "year"], how="left", validate="m:1")

    # price_shock is NaN only where the district has no SPAM cropland at all.
    # Districts WITH cropland but where no mapped crop had a defined dlog_real
    # in a given year (cannot occur for mapped crops in 1989-2025 except the
    # barley/sorghum-only edge) would land at 0 via the groupby; set price_shock
    # to 0.0 for cropland districts whose shock is still NaN (no mapped crop
    # contributed that year) so NaN means strictly "no cropland".
    has_cropland = out["cropland_ha"].notna()
    out.loc[has_cropland & out["price_shock"].isna(), "price_shock"] = 0.0

    stats = {
        "n_mapped_crops": len(mapped_codes),
        "n_total_crops": len(spam_codes),
        "global_cropland_share_mapped": float(
            cm[cm["spam_crop"].isin(mapped_codes)]["harv_area_ha"].sum()
            / cm["harv_area_ha"].sum()
        ),
        "unmapped_crops": sorted(spam_codes - mapped_codes),
    }
    log(
        f"  crop statics: {stats['n_mapped_crops']}/{stats['n_total_crops']} "
        f"crops mapped; {stats['global_cropland_share_mapped'] * 100:.2f}% of "
        "global cropland mapped"
    )
    return out, stats


def write_report(panel: pd.DataFrame, sections: dict) -> None:
    """Write the plain-text validation report under reports/."""
    lines: list[str] = []
    lines.append("PANEL BUILD REPORT")
    lines.append("==================")
    lines.append(f"output: {OUT_PANEL.relative_to(REPO_ROOT)}")
    lines.append(f"rows:   {len(panel):,}")
    lines.append(f"cols:   {panel.shape[1]}")
    lines.append("")
    lines.append("column list (in order):")
    for c in panel.columns:
        lines.append(f"  {c}  [{panel[c].dtype}]")
    lines.append("")
    lines.append("non-null counts per column:")
    for c in panel.columns:
        nn = int(panel[c].notna().sum())
        lines.append(f"  {c:<24} {nn:>12,}")
    lines.append("")

    inc = sections["income"]
    lines.append("income join:")
    lines.append(f"  carried-forward district-years: {inc['n_carried']:,}")
    lines.append(f"  iso3 never in OGHIST: {inc['unmatched_iso']}")
    lines.append(f"  districts with unmatched iso3: {inc['n_unmatched_districts']}")
    for k, v in inc["unmatched_breakdown"].items():
        lines.append(f"    {k}: {v} district(s)")
    lines.append("")

    cw = sections["crop"]
    lines.append("crosswalk / crop coverage:")
    lines.append(f"  mapped crops: {cw['n_mapped_crops']} / {cw['n_total_crops']}")
    lines.append(
        f"  global cropland share mapped: "
        f"{cw['global_cropland_share_mapped'] * 100:.2f}%"
    )
    lines.append(f"  unmapped crops ({len(cw['unmapped_crops'])}): {cw['unmapped_crops']}")
    lines.append("")

    ps = panel["price_shock"].dropna()
    lines.append("price_shock distribution (non-null):")
    lines.append(f"  n      {len(ps):,}")
    lines.append(f"  mean   {ps.mean():.6f}")
    lines.append(f"  std    {ps.std():.6f}")
    lines.append(f"  min    {ps.min():.6f}")
    lines.append(f"  p5     {ps.quantile(0.05):.6f}")
    lines.append(f"  p50    {ps.quantile(0.50):.6f}")
    lines.append(f"  p95    {ps.quantile(0.95):.6f}")
    lines.append(f"  max    {ps.max():.6f}")
    lines.append("")
    lines.append("price_shock_coverage distribution (non-null):")
    cv = panel["price_shock_coverage"].dropna()
    lines.append(f"  n      {len(cv):,}")
    lines.append(f"  mean   {cv.mean():.6f}")
    lines.append(f"  p5     {cv.quantile(0.05):.6f}")
    lines.append(f"  p50    {cv.quantile(0.50):.6f}")
    lines.append(f"  p95    {cv.quantile(0.95):.6f}")
    lines.append("")
    lines.append("OK")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"Wrote {OUT_REPORT}")


def main() -> int:
    for p in (
        SPINE,
        CONFLICT,
        WEATHER,
        YIELDS,
        INCOME,
        COUPS,
        ACLED,
        ACLED_COVERAGE,
        WDI,
        CROPMIX,
        PRICES,
        CROSSWALK,
    ):
        require(p)

    log("Loading spine ...")
    spine = pd.read_parquet(SPINE)
    if len(spine) != EXPECTED_N_DISTRICTS:
        raise AssertionError(
            f"Spine has {len(spine):,} districts, expected {EXPECTED_N_DISTRICTS:,}."
        )
    if spine["district_id"].duplicated().any():
        raise AssertionError("Spine has duplicate district_id.")
    spine = spine[["district_id", "iso3", "district_name", "admin_level"]].copy()

    log("Building spine x year frame ...")
    panel = build_frame(spine)

    log("Joining conflict (UCDP GED) ...")
    panel, conflict_cols = join_conflict(panel)

    log("Joining coups (Powell & Thyne) ...")
    panel, coups_cols = join_coups(panel)

    log("Joining ACLED (coverage-masked) ...")
    panel, acled_cols = join_acled(panel)

    log("Joining WB WDI covariates ...")
    panel, wdi_cols = join_wdi(panel)

    log("Joining weather (CHIRPS) ...")
    panel = join_weather(panel)

    log("Joining yields (GDHY) ...")
    panel, yield_cols = join_yields(panel)

    log("Joining income (OGHIST) ...")
    panel, income_stats = join_income(panel)

    log("Deriving crop-mix statics + price shock ...")
    panel, crop_stats = build_crop_statics_and_shock(panel)

    # --- final integrity checks ----------------------------------------------
    if len(panel) != EXPECTED_N_ROWS:
        raise AssertionError(
            f"Panel has {len(panel):,} rows, expected {EXPECTED_N_ROWS:,}."
        )
    if panel.duplicated(["district_id", "year"]).any():
        raise AssertionError("Panel has duplicate (district_id, year) keys.")
    if panel[["district_id", "year"]].isna().any().any():
        raise AssertionError("Panel has null key values.")

    # --- deterministic column order ------------------------------------------
    ordered = [
        "district_id",
        "iso3",
        "district_name",
        "admin_level",
        "year",
        *conflict_cols,
        *coups_cols,
        *acled_cols,
        *wdi_cols,
        "precip_mm",
        *yield_cols,
        "income_group",
        "income_group_carried",
        "cropland_ha",
        "price_shock_coverage",
        "price_shock",
    ]
    missing = set(ordered) - set(panel.columns)
    extra = set(panel.columns) - set(ordered)
    if missing or extra:
        raise AssertionError(
            f"Column-set mismatch. missing={sorted(missing)} extra={sorted(extra)}"
        )
    panel = panel[ordered]

    # --- deterministic sort ---------------------------------------------------
    panel = panel.sort_values(
        ["district_id", "year"], kind="mergesort"
    ).reset_index(drop=True)

    OUT_PANEL.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT_PANEL, index=False)
    log(f"Wrote {OUT_PANEL} ({len(panel):,} rows x {panel.shape[1]} cols)")

    write_report(panel, {"income": income_stats, "crop": crop_stats})

    # --- console summary ------------------------------------------------------
    log("")
    log("=== PANEL SUMMARY ===")
    log(f"  rows:                {len(panel):,}")
    log(f"  cols:                {panel.shape[1]}")
    log(f"  districts:           {panel['district_id'].nunique():,}")
    log(f"  years:               {int(panel['year'].min())}-{int(panel['year'].max())}")
    log(f"  coup district-years: {int((panel['coups_total'] > 0).sum()):,} "
        f"(total events {int(panel['coups_total'].sum()):,})")
    log(f"  acled covered d-yrs: {int(panel['acled_events_total'].notna().sum()):,} "
        f"(events>0 in {int((panel['acled_events_total'] > 0).sum()):,}); "
        f"not-covered NaN {int(panel['acled_events_total'].isna().sum()):,}")
    log(f"  wdi unemployment nn: {int(panel['wb_unemployment'].notna().sum()):,}; "
        f"gdp_pc nn: {int(panel['wb_gdp_pc'].notna().sum()):,}")
    log(f"  precip_mm non-null:  {int(panel['precip_mm'].notna().sum()):,}")
    log(f"  yield_maize nonnull: {int(panel['yield_maize'].notna().sum()):,}")
    log(f"  income non-null:     {int(panel['income_group'].notna().sum()):,}")
    log(f"  carried income:      {income_stats['n_carried']:,}")
    log(f"  cropland_ha nonnull: {int(panel['cropland_ha'].notna().sum()):,}")
    log(f"  price_shock nonnull: {int(panel['price_shock'].notna().sum()):,}")
    ps = panel["price_shock"].dropna()
    log(
        f"  price_shock p5/p50/p95: {ps.quantile(0.05):.5f} / "
        f"{ps.quantile(0.50):.5f} / {ps.quantile(0.95):.5f}"
    )
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
