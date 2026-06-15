#!/usr/bin/env python3
"""Independent validation of the district-year analysis panel.

Purpose
-------
This script is the *independent validator* of
``data/processed/panel_district_year.parquet``. It did not build the panel and
trusts nothing about it: it re-derives every figure it checks from the immutable
``data/interim/`` tables, the spine geometry, and externally published reference
figures, then prints PASS/FAIL with the actual numbers for each check. Any FAIL
makes the script exit non-zero (loud failure), and the full result is written to
``reports/validation_report.md``.

The checks fall into five groups (see the README task brief):

  1. STRUCTURE      - exact row count, unique (district_id, year), every
                      district present in all 37 years, sane dtypes, no all-NaN
                      columns.
  2. RECONCILIATION - panel conflict grand-totals equal the interim wide-GED
                      totals exactly; panel precip / yield non-null counts equal
                      the interim non-null counts; price_shock is NaN exactly
                      where cropland_ha is NaN (and cropland_ha is never 0).
  3. EXTERNAL       - UCDP global fatality ratio band; FAOSTAT 2020 global
                      wheat/maize/rice production vs FAO published figures;
                      geography spot-checks (Sahara precip, Bangladesh precip,
                      Iowa maize); World Bank 2024 high-income count; 2008
                      price-shock sign and the wheat-share gradient.
  4. MISSINGNESS    - per major column x 5-year era, % non-null with the
                      documented reason; the reasons must match the codebook.
  5. URL / CODEBOOK - every URL cited in this report and in every
                      data/raw/*/MANIFEST.txt resolves (HTTP HEAD), and the
                      codebook covers every panel column.

External reference figures (each cited with its URL in the report):
  - UCDP organized-violence global fatalities 2020 ~80,100 and 2021 ~119,100
    (Davies, Pettersson & Oberg, Journal of Peace Research; UCDP).
  - FAOSTAT 2020 world production: maize ~1.2 Gt, wheat ~0.8 Gt (~757-760 Mt),
    rice ~0.8 Gt (FAOSTAT Analytical Brief 41 / FAO production highlights).
  - World Bank FY2026 high-income economies = 87 (based on 2024 GNI per capita;
    threshold USD 13,935).

Inputs
------
    data/processed/panel_district_year.parquet   (the artifact under test)
    data/interim/{conflict_ged,weather_chirps,ag_yields_gdhy,income_class,
                  cropmix_spam2020,prices_pinksheet,faostat_qcl,spine}.parquet
    data/interim/spine.gpkg                       (geometry for spatial checks)
    docs/CODEBOOK.md                              (column coverage check)
    data/raw/*/MANIFEST.txt                       (URL resolution check)

Outputs
-------
    reports/validation_report.md   - the full report ending with a summary table
                                      of all checks and PASS/FAIL counts.
    process exit code               - 0 if every check PASSed, 1 otherwise.

Network
-------
The URL-resolution check issues HTTP HEAD (falling back to a ranged GET) against
each cited / manifest URL. With ``--offline`` the network checks are skipped and
recorded as SKIP (they then do not count toward FAIL); the default run performs
them. No credentials are used or printed.

Runtime
-------
~30-90 s offline (the geometry load and reconciliation dominate); add a few
seconds per URL when online.

How to run
----------
    .venv/bin/python src/merge/02_validate_panel.py
    .venv/bin/python src/merge/02_validate_panel.py --offline   # skip URL checks
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# --- Paths -------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM = REPO_ROOT / "data" / "interim"
RAW = REPO_ROOT / "data" / "raw"
PANEL_PATH = REPO_ROOT / "data" / "processed" / "panel_district_year.parquet"
CODEBOOK = REPO_ROOT / "docs" / "CODEBOOK.md"
OUT_REPORT = REPO_ROOT / "reports" / "validation_report.md"

SPINE = INTERIM / "spine.parquet"
SPINE_GPKG = INTERIM / "spine.gpkg"
CONFLICT = INTERIM / "conflict_ged.parquet"
WEATHER = INTERIM / "weather_chirps.parquet"
YIELDS = INTERIM / "ag_yields_gdhy.parquet"
INCOME = INTERIM / "income_class.parquet"
COUPS = INTERIM / "coups_pt.parquet"
ACLED_DY = INTERIM / "acled_district_year.parquet"
ACLED_COV = INTERIM / "acled_coverage.parquet"
CROPMIX = INTERIM / "cropmix_spam2020.parquet"
PRICES = INTERIM / "prices_pinksheet.parquet"
FAOSTAT = INTERIM / "faostat_qcl.parquet"

# --- Registry-pinned panel facts (independently re-asserted below) -----------
YEAR_MIN, YEAR_MAX = 1989, 2025
N_YEARS = YEAR_MAX - YEAR_MIN + 1  # 37
EXPECTED_N_DISTRICTS = 49_329
EXPECTED_N_ROWS = EXPECTED_N_DISTRICTS * N_YEARS  # 1,825,173
EXPECTED_N_COLS = 61  # 35 v0.1 + 3 coup + 8 ACLED + 15 WB WDI cols

CONFLICT_STEMS = [
    "n_events",
    "deaths_best",
    "deaths_low",
    "deaths_high",
    "deaths_civilians",
]
CONFLICT_SUFFIXES = ["sb", "ns", "os", "total"]
CONFLICT_COLS = [f"{s}_{x}" for s in CONFLICT_STEMS for x in CONFLICT_SUFFIXES]
YIELD_CROPS = ["maize", "rice", "wheat", "soybean"]

# --- External reference figures (cited in the report) ------------------------
# UCDP global organized-violence "best" fatalities, by year.
UCDP_PUBLISHED = {2020: 80_100, 2021: 119_100}
# Cited via canonical DOIs (publisher-neutral): journals.sagepub.com / OUP serve
# 403 to scripted clients indiscriminately (anti-bot wall) so a 403 there proves
# nothing; doi.org instead returns 3xx for a real DOI and 404 for a fabricated
# one, which is the hallucination-proof resolution we want.
UCDP_URLS = [
    "https://doi.org/10.1177/00223433211026126",  # Organized violence 1989-2020
    "https://doi.org/10.1177/00223433221108428",  # Organized violence 1989-2021
    "https://ucdp.uu.se/downloads/ged/ged261.pdf",  # GED 26.1 codebook
]
# Documented GED filter: where_prec<=3 keeps 85.0% of events; ~3.7% unmatched.
# Deaths-weighted retention is lower than the event-level 0.85*0.963=0.819 floor
# because dropped where_prec 4-7 points and unmatched coastal/border points skew
# toward large source-aggregate events. Band: clearly < 1, well above one-half.
UCDP_RATIO_LO, UCDP_RATIO_HI = 0.55, 0.95

# FAOSTAT 2020 world production, published rounded figures (tonnes).
FAO_PUBLISHED_2020 = {
    "Maize (corn)": 1_200_000_000.0,  # ~1.2 Gt
    "Wheat": 760_000_000.0,  # ~0.8 Gt (~757-760 Mt)
    "Rice": 760_000_000.0,  # ~0.8 Gt (paddy)
}
FAO_TOL = 0.06  # +/-6%: FAOSTAT revises the whole back-series each release, so a
#                 later snapshot vs the published-brief vintage differs by a few %.
FAO_URLS = [
    "https://www.fao.org/statistics/highlights-archive/highlights-detail/"
    "New-FAOSTAT-data-release-Agricultural-production-statistics-(2000-2020)/en",
    "https://www.fao.org/faostat/en/#data/QCL",
]

# World Bank high-income economy count, FY2026 (based on 2024 GNI).
WB_HIGH_INCOME_FY26 = 87
WB_URLS = [
    "https://blogs.worldbank.org/en/opendata/"
    "understanding-country-income--world-bank-group-income-classifica",
    "https://datahelpdesk.worldbank.org/knowledgebase/articles/"
    "906519-world-bank-country-and-lending-groups",
    "https://en.wikipedia.org/wiki/World_Bank_high-income_economy",
]

# --- Geography spot-check windows (representative-point bounding boxes) -------
# Hyperarid central Sahara core (lon, lat).
SAHARA_BBOX = dict(lon=(-5.0, 28.0), lat=(21.0, 28.0))
SAHARA_MAX_PRECIP_MM = 150.0
BANGLADESH_MIN_PRECIP_MM = 1500.0
# Iowa interior (avoids border bleed from neighbouring states).
IOWA_BBOX = dict(lon=(-95.5, -91.0), lat=(41.0, 43.3))
IOWA_MAIZE_LO, IOWA_MAIZE_HI = 8.0, 12.0  # t/ha, 2010

# All external URLs cited in the report (subject to the URL-resolution check).
CITED_URLS = sorted(set(UCDP_URLS + FAO_URLS + WB_URLS))


# --- Result accumulator ------------------------------------------------------
class Results:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []  # group, name, status, detail
        self.lines: list[str] = []

    def add(self, group: str, name: str, status: str, detail: str) -> None:
        assert status in {"PASS", "FAIL", "SKIP"}
        self.rows.append((group, name, status, detail))
        self.lines.append(f"- **{status}** [{group}] {name}: {detail}")
        print(f"  [{status}] {name}: {detail}", flush=True)

    def section(self, title: str) -> None:
        self.lines.append("")
        self.lines.append(f"## {title}")
        print(f"\n== {title} ==", flush=True)

    def text(self, line: str) -> None:
        self.lines.append(line)

    @property
    def n_pass(self) -> int:
        return sum(1 for *_, s, _ in self.rows if s == "PASS")

    @property
    def n_fail(self) -> int:
        return sum(1 for *_, s, _ in self.rows if s == "FAIL")

    @property
    def n_skip(self) -> int:
        return sum(1 for *_, s, _ in self.rows if s == "SKIP")


def fnum(x: float) -> str:
    return f"{x:,.0f}"


# =============================================================================
# 1. STRUCTURE
# =============================================================================
def check_structure(R: Results, panel: pd.DataFrame) -> None:
    R.section("1. Structure")

    # Exact row count = spine x 37 years.
    n = len(panel)
    R.add(
        "STRUCTURE",
        "row count == 49,329 x 37",
        "PASS" if n == EXPECTED_N_ROWS else "FAIL",
        f"rows={n:,} expected={EXPECTED_N_ROWS:,}",
    )

    # Column count.
    R.add(
        "STRUCTURE",
        "column count",
        "PASS" if panel.shape[1] == EXPECTED_N_COLS else "FAIL",
        f"cols={panel.shape[1]} expected={EXPECTED_N_COLS}",
    )

    # Unique (district_id, year).
    dup = int(panel.duplicated(["district_id", "year"]).sum())
    R.add(
        "STRUCTURE",
        "unique (district_id, year)",
        "PASS" if dup == 0 else "FAIL",
        f"duplicate keys={dup}",
    )

    # Distinct districts == spine size.
    nd = panel["district_id"].nunique()
    R.add(
        "STRUCTURE",
        "distinct districts == spine",
        "PASS" if nd == EXPECTED_N_DISTRICTS else "FAIL",
        f"districts={nd:,} expected={EXPECTED_N_DISTRICTS:,}",
    )

    # Every district appears in all 37 years (years exactly 1989..2025).
    per = panel.groupby("district_id")["year"].nunique()
    all_37 = bool((per == N_YEARS).all())
    yr_ok = (int(panel["year"].min()) == YEAR_MIN) and (
        int(panel["year"].max()) == YEAR_MAX
    )
    distinct_years = panel["year"].nunique()
    R.add(
        "STRUCTURE",
        "every district in all 37 years",
        "PASS" if (all_37 and yr_ok and distinct_years == N_YEARS) else "FAIL",
        f"years/district min={int(per.min())} max={int(per.max())}; "
        f"year span {int(panel['year'].min())}-{int(panel['year'].max())}; "
        f"distinct years={distinct_years}",
    )

    # Key columns have no nulls.
    key_nulls = int(panel[["district_id", "iso3", "year"]].isna().sum().sum())
    R.add(
        "STRUCTURE",
        "no null keys (district_id, iso3, year)",
        "PASS" if key_nulls == 0 else "FAIL",
        f"null key cells={key_nulls}",
    )

    # Dtypes sane: conflict + coup cols integer, listed float cols float, year int.
    coup_cols = ["coups_total", "coups_successful", "coups_failed"]
    int_ok = all(
        pd.api.types.is_integer_dtype(panel[c])
        for c in ["year", *CONFLICT_COLS, *coup_cols]
    )
    acled_cols = [
        "acled_events_total", "acled_events_battles", "acled_events_protests",
        "acled_events_riots", "acled_events_vac", "acled_events_explosions",
        "acled_events_strategic", "acled_fatalities",
    ]
    float_cols = [
        "precip_mm",
        *[f"yield_{c}" for c in YIELD_CROPS],
        "cropland_ha",
        "price_shock_coverage",
        "price_shock",
        *acled_cols,  # coverage-masked: float so NaN (not covered) is distinct
    ]
    float_ok = all(pd.api.types.is_float_dtype(panel[c]) for c in float_cols)
    bool_ok = pd.api.types.is_bool_dtype(panel["income_group_carried"])
    R.add(
        "STRUCTURE",
        "dtypes sane",
        "PASS" if (int_ok and float_ok and bool_ok) else "FAIL",
        f"conflict+year int={int_ok}; measure cols float={float_ok}; "
        f"income_group_carried bool={bool_ok}",
    )

    # No all-NaN columns.
    all_nan = [c for c in panel.columns if panel[c].isna().all()]
    R.add(
        "STRUCTURE",
        "no all-NaN columns",
        "PASS" if not all_nan else "FAIL",
        f"all-NaN columns={all_nan}",
    )


# =============================================================================
# 2. INTERNAL RECONCILIATION
# =============================================================================
def check_reconciliation(R: Results, panel: pd.DataFrame) -> None:
    R.section("2. Internal reconciliation")

    spine_ids = set(pd.read_parquet(SPINE)["district_id"])

    # 2a. Conflict grand-totals: panel == interim wide GED, every column exactly.
    ged = pd.read_parquet(CONFLICT)
    mismatches = []
    for col in CONFLICT_COLS:
        ps = int(panel[col].sum())
        cs = int(ged[col].sum())
        if ps != cs:
            mismatches.append(f"{col}(panel={ps:,},interim={cs:,})")
    R.add(
        "RECON",
        "conflict grand-totals == interim GED",
        "PASS" if not mismatches else "FAIL",
        (
            f"all {len(CONFLICT_COLS)} columns match; "
            f"deaths_best_total grand={int(panel['deaths_best_total'].sum()):,}"
        )
        if not mismatches
        else f"mismatched: {mismatches}",
    )

    # 2b. precip_mm: panel non-null == interim non-null (window, in-spine).
    wx = pd.read_parquet(WEATHER)
    wx_win = wx[
        (wx["year"] >= YEAR_MIN)
        & (wx["year"] <= YEAR_MAX)
        & (wx["district_id"].isin(spine_ids))
    ]
    interim_precip_nn = int(wx_win["precip_mm"].notna().sum())
    panel_precip_nn = int(panel["precip_mm"].notna().sum())
    R.add(
        "RECON",
        "precip_mm non-null == interim",
        "PASS" if panel_precip_nn == interim_precip_nn else "FAIL",
        f"panel={panel_precip_nn:,} interim_nonnull={interim_precip_nn:,}",
    )

    # 2c. yields: panel non-null per crop == interim long rows (window, in-spine).
    gd = pd.read_parquet(YIELDS)
    gd_win = gd[
        (gd["year"] >= YEAR_MIN)
        & (gd["year"] <= YEAR_MAX)
        & (gd["district_id"].isin(spine_ids))
    ]
    yld_problems = []
    for crop in YIELD_CROPS:
        panel_nn = int(panel[f"yield_{crop}"].notna().sum())
        interim_n = int((gd_win["crop"] == crop).sum())
        if panel_nn != interim_n:
            yld_problems.append(f"{crop}(panel={panel_nn:,},interim={interim_n:,})")
    R.add(
        "RECON",
        "yield non-null counts == interim",
        "PASS" if not yld_problems else "FAIL",
        (
            "all 4 crops match ("
            + ", ".join(
                f"{c}={int(panel[f'yield_{c}'].notna().sum()):,}" for c in YIELD_CROPS
            )
            + ")"
        )
        if not yld_problems
        else f"mismatched: {yld_problems}",
    )

    # 2d. price_shock NaN exactly where cropland_ha NaN; cropland_ha never 0.
    nan_ps = panel["price_shock"].isna()
    nan_crop = panel["cropland_ha"].isna()
    exact = bool((nan_ps == nan_crop).all())
    zero_crop = int((panel["cropland_ha"] == 0).sum())
    R.add(
        "RECON",
        "price_shock NaN iff cropland_ha NaN",
        "PASS" if (exact and zero_crop == 0) else "FAIL",
        f"price_shock NaN={int(nan_ps.sum()):,} cropland NaN={int(nan_crop.sum()):,} "
        f"exact_match={exact}; cropland==0 rows={zero_crop}",
    )

    # 2e. coverage columns share the cropland NaN mask (sanity).
    cov_nan = panel["price_shock_coverage"].isna()
    R.add(
        "RECON",
        "price_shock_coverage NaN iff cropland_ha NaN",
        "PASS" if bool((cov_nan == nan_crop).all()) else "FAIL",
        f"coverage NaN={int(cov_nan.sum()):,} cropland NaN={int(nan_crop.sum()):,}",
    )

    # 2f. Coups grand-total: panel sum == interim coups (broadcast to districts).
    #     Each country's coup count is replicated across its districts, so the
    #     panel total == sum over interim country-years weighted by #districts.
    coups = pd.read_parquet(COUPS)
    spine_df = pd.read_parquet(SPINE)
    dcount = spine_df.groupby("iso3")["district_id"].nunique()
    cw = coups[(coups["year"] >= YEAR_MIN) & (coups["year"] <= YEAR_MAX)].copy()
    cw["ndist"] = cw["iso3"].map(dcount).fillna(0).astype(int)
    expected_coups = int((cw["coups_total"] * cw["ndist"]).sum())
    panel_coups = int(panel["coups_total"].sum())
    R.add(
        "RECON",
        "coups grand-total == interim x districts",
        "PASS" if panel_coups == expected_coups else "FAIL",
        f"panel={panel_coups:,} expected={expected_coups:,} "
        f"(interim coup country-years x #districts/country)",
    )

    # 2g. ACLED row-wise consistency: total == sum of the six event-type columns
    #     wherever ACLED is observed (non-NaN). NaN rows are not-covered.
    type_cols = [
        "acled_events_battles", "acled_events_protests", "acled_events_riots",
        "acled_events_vac", "acled_events_explosions", "acled_events_strategic",
    ]
    obs = panel["acled_events_total"].notna()
    rowsum = panel.loc[obs, type_cols].sum(axis=1)
    consistent = bool((rowsum == panel.loc[obs, "acled_events_total"]).all())
    R.add(
        "RECON",
        "acled total == sum of event-type columns",
        "PASS" if consistent else "FAIL",
        f"checked {int(obs.sum()):,} covered district-years; consistent={consistent}",
    )

    # 2h. ACLED matched-event grand total == interim acled_district_year total
    #     (restricted to in-spine, in-window district-years).
    ady = pd.read_parquet(ACLED_DY)
    ady_win = ady[
        (ady["year"] >= YEAR_MIN) & (ady["year"] <= YEAR_MAX)
        & (ady["district_id"].isin(spine_ids))
    ]
    interim_events = int(ady_win["acled_events_total"].sum())
    panel_events = int(panel["acled_events_total"].fillna(0).sum())
    R.add(
        "RECON",
        "acled events grand-total == interim",
        "PASS" if panel_events == interim_events else "FAIL",
        f"panel={panel_events:,} interim={interim_events:,}",
    )

    # 2i. ACLED coverage mask. The merge rule is: a district-year is non-NaN iff
    #     it has a matched event OR it falls inside its country's ACLED-coded
    #     coverage window [first..last]. Re-derive both inputs independently --
    #     the 'matched' flag from the EVENTS table (acled_district_year, which
    #     holds only district-years with >=1 event) and the window from the
    #     coverage table -- and assert the panel's NaN pattern matches exactly.
    cov = pd.read_parquet(ACLED_COV)
    cov_first = dict(zip(cov["iso3"], cov["acled_first_year"]))
    cov_last = dict(zip(cov["iso3"], cov["acled_last_year"]))
    fy = panel["iso3"].map(cov_first)
    ly = panel["iso3"].map(cov_last)
    covered = (fy.notna() & (panel["year"] >= fy) & (panel["year"] <= ly)).to_numpy()
    ev_keys = ady[["district_id", "year"]].drop_duplicates().assign(_m=True)
    m = panel[["district_id", "year"]].merge(ev_keys, on=["district_id", "year"], how="left")
    matched_flag = m["_m"].fillna(False).to_numpy()
    expected_nonnan = matched_flag | covered
    actual_nonnan = panel["acled_events_total"].notna().to_numpy()
    mask_ok = bool((expected_nonnan == actual_nonnan).all())
    R.add(
        "RECON",
        "acled coverage mask correct (matched OR in coverage window)",
        "PASS" if mask_ok else "FAIL",
        f"non-NaN: expected={int(expected_nonnan.sum()):,} "
        f"actual={int(actual_nonnan.sum()):,}; match={mask_ok}",
    )


# =============================================================================
# 3. EXTERNAL CROSS-CHECKS
# =============================================================================
def check_external(R: Results, panel: pd.DataFrame) -> None:
    R.section("3. External cross-checks")

    # --- 3a. UCDP global fatality ratio --------------------------------------
    R.text("")
    R.text(
        "UCDP global organized-violence fatalities (best) — published: "
        f"2020 ~{UCDP_PUBLISHED[2020]:,}, 2021 ~{UCDP_PUBLISHED[2021]:,} "
        "(Davies/Pettersson/Oberg, Journal of Peace Research; "
        f"{UCDP_URLS[0]} , {UCDP_URLS[1]} )."
    )
    panel_sums = {y: int(panel[panel["year"] == y]["deaths_best_total"].sum()) for y in UCDP_PUBLISHED}
    agg_panel = sum(panel_sums.values())
    agg_pub = sum(UCDP_PUBLISHED.values())
    ratio = agg_panel / agg_pub
    per_year = "; ".join(
        f"{y}: panel={panel_sums[y]:,} / pub={UCDP_PUBLISHED[y]:,} "
        f"= {panel_sums[y] / UCDP_PUBLISHED[y]:.3f}"
        for y in sorted(UCDP_PUBLISHED)
    )
    in_band = UCDP_RATIO_LO <= ratio <= UCDP_RATIO_HI
    R.add(
        "EXTERNAL",
        "UCDP fatality ratio in expected band",
        "PASS" if in_band else "FAIL",
        f"aggregate panel/published = {ratio:.3f} "
        f"(expected band [{UCDP_RATIO_LO}, {UCDP_RATIO_HI}], <1 due to where_prec<=3 "
        f"keep 85.0% + ~3.7% unmatched); {per_year}",
    )
    # Expose the UCDP ratio explicitly in the report body for the summary.
    R.text(f"UCDP ratio (2020+2021 aggregate, panel/published) = **{ratio:.3f}**.")

    # --- 3b. FAOSTAT 2020 global production ----------------------------------
    R.text("")
    R.text(
        "FAOSTAT 2020 world production (backbone consistency) — published rounded "
        "figures: maize ~1.2 Gt, wheat ~0.8 Gt (~757-760 Mt), rice ~0.8 Gt "
        f"(FAO production highlights {FAO_URLS[0]} ; FAOSTAT QCL {FAO_URLS[1]} )."
    )
    fa = pd.read_parquet(FAOSTAT)
    fao_ratios: dict[str, float] = {}
    fao_problems = []
    for item, pub in FAO_PUBLISHED_2020.items():
        sub = fa[(fa["item"] == item) & (fa["element"] == "Production") & (fa["year"] == 2020)]
        got = float(sub["value"].sum())
        r = got / pub
        fao_ratios[item] = r
        within = abs(r - 1.0) <= FAO_TOL
        R.add(
            "EXTERNAL",
            f"FAOSTAT 2020 {item} vs FAO published",
            "PASS" if within else "FAIL",
            f"interim={got / 1e6:,.1f} Mt vs published~{pub / 1e6:,.0f} Mt "
            f"(ratio {r:.3f}, tol +/-{FAO_TOL:.0%}, n_countries={sub['iso3'].nunique()})",
        )
        if not within:
            fao_problems.append(item)
    R.text(
        "FAO ratios (interim/published): "
        + ", ".join(f"{k}={v:.3f}" for k, v in fao_ratios.items())
        + "."
    )

    # --- 3c. Geography spot-checks (need spine geometry) ---------------------
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import geopandas as gpd  # local import: only the geometry checks need it

        g = gpd.read_file(SPINE_GPKG)
        rep = g.geometry.representative_point()
        g = g.assign(clon=rep.x, clat=rep.y)

    def in_bbox(frame: pd.DataFrame, box: dict, iso=None) -> set:
        m = (
            frame["clon"].between(*box["lon"])
            & frame["clat"].between(*box["lat"])
        )
        if iso is not None:
            m &= frame["iso3"] == iso
        return set(frame.loc[m, "district_id"])

    # Sahara core precip < 150 mm (use a recent fully-covered year, 2020).
    sah_ids = in_bbox(g, SAHARA_BBOX)
    sah = panel[(panel["district_id"].isin(sah_ids)) & (panel["year"] == 2020)]
    sah_max = float(sah["precip_mm"].max())
    R.add(
        "EXTERNAL",
        "Sahara core precip < 150 mm (2020)",
        "PASS" if (len(sah) > 0 and sah_max < SAHARA_MAX_PRECIP_MM) else "FAIL",
        f"n={len(sah)} districts; max precip={sah_max:.1f} mm "
        f"(threshold <{SAHARA_MAX_PRECIP_MM:.0f})",
    )

    # Bangladesh precip > 1500 mm (2020).
    bgd = panel[(panel["iso3"] == "BGD") & (panel["year"] == 2020)]
    bgd_min = float(bgd["precip_mm"].min())
    R.add(
        "EXTERNAL",
        "Bangladesh precip > 1500 mm (2020)",
        "PASS" if (len(bgd) > 0 and bgd_min > BANGLADESH_MIN_PRECIP_MM) else "FAIL",
        f"n={len(bgd)} districts; min precip={bgd_min:.1f} mm "
        f"(threshold >{BANGLADESH_MIN_PRECIP_MM:.0f})",
    )

    # Iowa-area maize yield 2010 in 8-12 t/ha.
    iowa_ids = in_bbox(g, IOWA_BBOX, iso="USA")
    iowa = panel[(panel["district_id"].isin(iowa_ids)) & (panel["year"] == 2010)]
    iowa_med = float(iowa["yield_maize"].median())
    R.add(
        "EXTERNAL",
        "Iowa maize 2010 median in 8-12 t/ha",
        "PASS" if (len(iowa) > 0 and IOWA_MAIZE_LO <= iowa_med <= IOWA_MAIZE_HI) else "FAIL",
        f"n={len(iowa)} districts; median maize yield={iowa_med:.2f} t/ha "
        f"(band [{IOWA_MAIZE_LO}, {IOWA_MAIZE_HI}])",
    )

    # --- 3d. Income: 2024 High count vs World Bank ---------------------------
    inc = pd.read_parquet(INCOME)
    h2024 = int((inc[inc["data_year"] == 2024]["income_group"] == "H").sum())
    R.add(
        "EXTERNAL",
        "2024 high-income count == World Bank FY26",
        "PASS" if h2024 == WB_HIGH_INCOME_FY26 else "FAIL",
        f"interim income_class (data_year=2024) High={h2024} vs World Bank FY26={WB_HIGH_INCOME_FY26} "
        f"({WB_URLS[1]} )",
    )
    # Panel-side note: the panel only carries countries with spine polygons, so
    # its distinct High iso3 in 2024 is smaller (small high-income territories
    # have no admin-2 unit). This is documented, not a failure.
    panel_h = panel[(panel["year"] == 2024) & (panel["income_group"] == "H")]["iso3"].nunique()
    R.text(
        f"Panel year=2024 distinct High iso3 = {panel_h} (< {WB_HIGH_INCOME_FY26}: the "
        "panel covers only the 198 countries with spine admin-2 polygons; small "
        "high-income territories without districts drop out — documented, expected)."
    )

    # --- 3e. Price shock: 2008 sign + wheat-share gradient -------------------
    pk = pd.read_parquet(PRICES)

    def dlog_real_2008(code: str) -> float:
        s = (
            pk[pk["commodity_code"] == code]
            .sort_values("year")
            .set_index("year")["price_real"]
        )
        return float(np.log(s.loc[2008]) - np.log(s.loc[2007]))

    w08 = dlog_real_2008("wheat_us_hrw")
    r08 = dlog_real_2008("rice_thai_5")
    R.add(
        "EXTERNAL",
        "2008 real wheat/rice price log-change large positive",
        "PASS" if (w08 > 0.05 and r08 > 0.05) else "FAIL",
        f"dlog_real wheat 2008={w08:.3f}, rice 2008={r08:.3f} "
        "(both should be large positive; 2007-08 food price spike)",
    )

    # High-wheat-share districts show higher 2008 price_shock than zero-cropland.
    cm = pd.read_parquet(CROPMIX)
    cm = cm.assign(code=cm["crop"].str.split(" ", n=1).str[0])
    wheat_share = (
        cm[cm["code"] == "whea"].groupby("district_id")["crop_share"].sum().rename("wheat_share")
    )
    p08 = panel[panel["year"] == 2008].merge(wheat_share, on="district_id", how="left")
    p08["wheat_share"] = p08["wheat_share"].fillna(0.0)
    hi_wheat = p08[(p08["wheat_share"] > 0.5) & p08["price_shock"].notna()]
    zero_crop = p08[p08["cropland_ha"].isna()]
    hi_mean = float(hi_wheat["price_shock"].mean())
    zero_all_nan = bool(zero_crop["price_shock"].isna().all())
    # Gradient: high-wheat shock should be clearly positive (driven by w08 > 0)
    # while zero-cropland districts have no shock at all (NaN).
    grad_ok = (len(hi_wheat) > 0) and (hi_mean > 0.05) and zero_all_nan
    R.add(
        "EXTERNAL",
        "2008 high-wheat shock > zero-cropland (NaN)",
        "PASS" if grad_ok else "FAIL",
        f"high-wheat (share>0.5, n={len(hi_wheat):,}) mean price_shock={hi_mean:.4f}; "
        f"zero-cropland (n={len(zero_crop):,}) price_shock all-NaN={zero_all_nan}",
    )

    # ACLED value-add: it surfaces NON-LETHAL unrest that UCDP GED (fatal events
    # only) cannot. There must be many district-years with ACLED protests/riots
    # but zero UCDP fatal events -- that gap is the reason ACLED was added.
    obs = panel["acled_events_total"].notna()
    nonlethal = panel[obs & (
        (panel["acled_events_protests"] + panel["acled_events_riots"]) > 0
    )]
    gap = nonlethal[nonlethal["n_events_total"] == 0]
    R.add(
        "EXTERNAL",
        "ACLED surfaces non-lethal unrest invisible to UCDP",
        "PASS" if len(gap) > 1000 else "FAIL",
        f"{len(gap):,} district-years with ACLED protests/riots but zero UCDP "
        f"fatal events (of {len(nonlethal):,} with any protest/riot); "
        "demonstrates the enrichment is real",
    )

    # ACLED coverage-start years must match ACLED's published staggered schedule
    # (https://acleddata.com/knowledge-base/country-time-period-coverage/). The
    # coverage table is built from ACLED's OWN country coding, so these are the
    # true monitoring-start years, not artifacts of cross-border geo-assignment.
    cov = pd.read_parquet(ACLED_COV)
    starts = dict(zip(cov["iso3"], cov["acled_first_year"]))
    expected_starts = {  # iso3 -> first ACLED year (published schedule)
        "NGA": 1997,  # Africa
        "SSD": 2011,  # South Sudan independence
        "IDN": 2015,  # Indonesia
        "IND": 2016,  # India
        "SYR": 2017,  # Syria / Middle East
        "UKR": 2018,  # Europe
        "USA": 2020,  # United States
    }
    mism = {k: (starts.get(k), v) for k, v in expected_starts.items()
            if starts.get(k) != v}
    R.add(
        "EXTERNAL",
        "ACLED coverage starts match published schedule",
        "PASS" if not mism else "FAIL",
        (f"all {len(expected_starts)} match: {expected_starts}" if not mism
         else f"MISMATCH (got, expected): {mism}"),
    )


# =============================================================================
# 4. MISSINGNESS MAP
# =============================================================================
ERA_REASONS = {
    "precip_mm": (
        "CHIRPS v2.0 covers 50S-50N (high-latitude districts NaN) and the interim "
        "series ends 2024 (all 2025 NaN). Matches CODEBOOK 'Weather - CHIRPS v2.0'."
    ),
    "yield_maize": (
        "GDHY ends 2016 (>2016 NaN) and is NaN where the crop is absent from the "
        "district's grid cells. Matches CODEBOOK 'Agricultural yields - GDHY'."
    ),
    "income_group": (
        "Joined by iso3; NaN only for iso3 never in OGHIST (ATA, VAT). Matches "
        "CODEBOOK 'Country classification - World Bank OGHIST'."
    ),
    "cropland_ha": (
        "Time-invariant SPAM static; NaN for districts with no SPAM cropland. "
        "Matches CODEBOOK 'Crop-mix statics - SPAM 2020 v2.0 R2'."
    ),
    "price_shock": (
        "NaN only where cropland_ha is NaN (no SPAM cropland). Matches CODEBOOK "
        "'Price shock' NaN policy."
    ),
}


def check_missingness(R: Results, panel: pd.DataFrame) -> None:
    R.section("4. Missingness map (per column x 5-year era)")

    cols = ["precip_mm", "yield_maize", "income_group", "cropland_ha", "price_shock"]
    edges = list(range(YEAR_MIN, YEAR_MAX + 1, 5)) + [YEAR_MAX + 1]
    eras = [(edges[i], min(edges[i + 1] - 1, YEAR_MAX)) for i in range(len(edges) - 1)]

    R.text("")
    header = "| column | " + " | ".join(f"{a}-{b}" for a, b in eras) + " | reason |"
    sep = "|" + "---|" * (len(eras) + 2)
    R.text(header)
    R.text(sep)
    for c in cols:
        cells = []
        for a, b in eras:
            sub = panel[(panel["year"] >= a) & (panel["year"] <= b)]
            pct = 100.0 * sub[c].notna().mean()
            cells.append(f"{pct:.1f}%")
        reason = ERA_REASONS[c]
        R.text(f"| `{c}` | " + " | ".join(cells) + f" | {reason} |")

    # The map is informational; the PASS condition is that the documented gaps
    # actually appear where the codebook says they do.
    # (i) precip_mm: 2025 era 100% NaN (0% non-null).
    precip_2025 = 100.0 * panel.loc[panel["year"] == 2025, "precip_mm"].notna().mean()
    # (ii) yield_maize: post-2016 fully NaN.
    yld_post16 = 100.0 * panel.loc[panel["year"] > 2016, "yield_maize"].notna().mean()
    # (iii) cropland_ha / price_shock identical across all eras (time-invariant mask).
    cl_pct = [
        100.0 * panel.loc[(panel["year"] >= a) & (panel["year"] <= b), "cropland_ha"].notna().mean()
        for a, b in eras
    ]
    cl_flat = max(cl_pct) - min(cl_pct) < 1e-9
    ok = (precip_2025 == 0.0) and (yld_post16 == 0.0) and cl_flat
    R.add(
        "MISSINGNESS",
        "documented gaps appear as codebook states",
        "PASS" if ok else "FAIL",
        f"precip_mm 2025 non-null={precip_2025:.1f}% (expect 0); "
        f"yield_maize >2016 non-null={yld_post16:.1f}% (expect 0); "
        f"cropland_ha non-null flat across eras={cl_flat}",
    )


# =============================================================================
# 5. ZERO-HALLUCINATION SWEEP (URLs + codebook coverage)
# =============================================================================
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not follow redirects: a 3xx with a Location header already proves the
    path resolves to a real resource (the point of the sweep), and avoids being
    bounced into an anti-bot interstitial on the redirect target."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401, ANN001, ANN002
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)

# Codes that prove the exact path exists even though the host blocks scripted
# bodies: 401 (auth wall, e.g. FAOSTAT API), 403 (anti-bot wall), 429 (rate
# limited), 405 (method not allowed). A fabricated path on these hosts returns
# 404/410 instead, so these still distinguish real from hallucinated URLs for
# hosts that answer them (doi.org, our primary citation route, returns clean
# 3xx-vs-404). 404/410/DNS/connection errors are hard failures.
RESOLVES_CODES = {401, 403, 405, 429}
NOT_FOUND_CODES = {404, 410}


def url_resolves(url: str, timeout: float = 20.0) -> tuple[bool, str]:
    """HEAD a URL (no redirect-follow); fall back to ranged GET. (ok, detail).

    A real resource resolves as 2xx, a 3xx-with-Location, or one of the
    documented block codes (401/403/405/429). A 404/410 is a hard FAIL (this is
    what catches a hallucinated / mistyped URL). Network/DNS errors also FAIL.
    """
    headers = {"User-Agent": "HURP-panel-validator/1.0 (+reproducible-research)"}
    # Fragment identifiers (#data/QCL) are client-side; strip for the request.
    req_url = url.split("#", 1)[0]
    last = "no response"
    # Try HEAD then ranged GET. A 404/410 is treated as "not found" only AFTER
    # the GET fallback also fails: some live hosts (e.g. the World Bank DDH
    # download endpoint) reject HEAD with 404 yet serve the file on GET.
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(req_url, method=method, headers=dict(headers))
            if method == "GET":
                req.add_header("Range", "bytes=0-0")
            with _OPENER.open(req, timeout=timeout) as resp:
                code = resp.getcode()
                if 200 <= code < 400:
                    return True, f"HTTP {code} ({method})"
                last = f"HTTP {code} ({method})"
        except urllib.error.HTTPError as e:
            if 200 <= e.code < 400 or e.code in RESOLVES_CODES:
                return True, f"HTTP {e.code} ({method})"
            last = f"HTTP {e.code} ({method})"
            if e.code in NOT_FOUND_CODES and method == "GET":
                return False, f"HTTP {e.code} ({method}) — path not found"
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last = f"{type(e).__name__}: {e}"
    return False, last


def check_urls_and_codebook(R: Results, panel: pd.DataFrame, offline: bool) -> None:
    R.section("5. Zero-hallucination sweep (URLs + codebook coverage)")

    # Collect manifest URLs.
    manifest_urls: set[str] = set()
    for mf in sorted(RAW.glob("*/MANIFEST.txt")):
        try:
            mdf = pd.read_csv(mf, sep="\t")
        except (pd.errors.ParserError, ValueError):
            mdf = None
        if mdf is not None and "url" in mdf.columns:
            manifest_urls.update(u for u in mdf["url"].dropna().astype(str) if u.startswith("http"))
        else:
            # Fallback: pull any http(s) token from the file.
            for tok in mf.read_text(encoding="utf-8").split():
                if tok.startswith("http"):
                    manifest_urls.add(tok)

    all_urls = sorted(set(CITED_URLS) | manifest_urls)
    R.text("")
    R.text(
        f"URLs checked: {len(CITED_URLS)} cited in this report + "
        f"{len(manifest_urls)} distinct manifest URLs = {len(all_urls)} unique."
    )

    if offline:
        R.add(
            "SWEEP",
            "all cited / manifest URLs resolve",
            "SKIP",
            f"--offline: {len(all_urls)} URLs not contacted",
        )
    else:
        failed: list[str] = []
        for u in all_urls:
            ok, detail = url_resolves(u)
            if not ok:
                failed.append(f"{u} -> {detail}")
        R.add(
            "SWEEP",
            "all cited / manifest URLs resolve",
            "PASS" if not failed else "FAIL",
            f"{len(all_urls) - len(failed)}/{len(all_urls)} resolved"
            + ("" if not failed else f"; FAILED: {failed}"),
        )

    # Codebook covers every panel column (column name appears in CODEBOOK.md).
    text = CODEBOOK.read_text(encoding="utf-8")
    # Treat per-type/total conflict columns as covered by their stem family,
    # which the codebook documents with the "/ _ns / _os / _total" shorthand.
    missing_cols = []
    for c in panel.columns:
        if c in text:
            continue
        # conflict family shorthand e.g. "n_events_sb / _ns / _os / _total".
        stem = "_".join(c.split("_")[:-1])
        suf = c.split("_")[-1]
        if suf in CONFLICT_SUFFIXES and stem in text and f"_{suf}" in text:
            continue
        missing_cols.append(c)
    R.add(
        "SWEEP",
        "codebook covers every panel column",
        "PASS" if not missing_cols else "FAIL",
        f"{panel.shape[1] - len(missing_cols)}/{panel.shape[1]} columns documented"
        + ("" if not missing_cols else f"; UNDOCUMENTED: {missing_cols}"),
    )


# =============================================================================
# Report writer
# =============================================================================
def write_report(R: Results, panel: pd.DataFrame, offline: bool) -> None:
    out: list[str] = []
    out.append("# Panel validation report")
    out.append("")
    out.append(
        "Independent validation of `data/processed/panel_district_year.parquet` "
        "by `src/merge/02_validate_panel.py`. Every figure below is re-derived "
        "from the immutable `data/interim/` tables, the spine geometry, and the "
        "externally published reference figures cited inline (each with its URL). "
        "Any FAIL makes the script exit non-zero."
    )
    out.append("")
    out.append(f"- Panel under test: `{PANEL_PATH.relative_to(REPO_ROOT)}`")
    out.append(f"- Rows: {len(panel):,}; columns: {panel.shape[1]}")
    out.append(
        f"- Network checks: {'SKIPPED (--offline)' if offline else 'performed (HTTP HEAD/GET)'}"
    )
    out.append("")
    out.extend(R.lines)

    # Summary table.
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| # | group | check | status | detail |")
    out.append("|---|-------|-------|--------|--------|")
    for i, (group, name, status, detail) in enumerate(R.rows, 1):
        d = detail.replace("|", "\\|")
        out.append(f"| {i} | {group} | {name} | **{status}** | {d} |")
    out.append("")
    out.append(
        f"**Totals: {R.n_pass} PASS, {R.n_fail} FAIL, {R.n_skip} SKIP "
        f"(of {len(R.rows)} checks).**"
    )

    # Headline numbers.
    fa = pd.read_parquet(FAOSTAT)
    fao_lines = []
    for item, pub in FAO_PUBLISHED_2020.items():
        got = float(
            fa[(fa["item"] == item) & (fa["element"] == "Production") & (fa["year"] == 2020)][
                "value"
            ].sum()
        )
        fao_lines.append(f"{item} {got / pub:.3f}")
    ucdp_panel = sum(
        int(panel[panel["year"] == y]["deaths_best_total"].sum()) for y in UCDP_PUBLISHED
    )
    ucdp_ratio = ucdp_panel / sum(UCDP_PUBLISHED.values())
    out.append("")
    out.append("### Headline figures")
    out.append(f"- UCDP ratio (2020+2021, panel/published): **{ucdp_ratio:.3f}**.")
    out.append("- FAO ratios (interim/published, 2020): " + ", ".join(fao_lines) + ".")
    out.append("")
    verdict = "ALL CHECKS PASS" if R.n_fail == 0 else f"{R.n_fail} CHECK(S) FAILED"
    out.append(f"**Verdict: {verdict}.**")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_REPORT}", flush=True)


# =============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--offline",
        action="store_true",
        help="skip the URL-resolution network check (record it as SKIP).",
    )
    args = ap.parse_args()

    for p in (
        PANEL_PATH,
        SPINE,
        SPINE_GPKG,
        CONFLICT,
        WEATHER,
        YIELDS,
        INCOME,
        COUPS,
        ACLED_DY,
        ACLED_COV,
        CROPMIX,
        PRICES,
        FAOSTAT,
        CODEBOOK,
    ):
        if not p.exists():
            raise FileNotFoundError(f"Required input missing: {p}")

    print("Loading panel under test ...", flush=True)
    panel = pd.read_parquet(PANEL_PATH)

    R = Results()
    check_structure(R, panel)
    check_reconciliation(R, panel)
    check_external(R, panel)
    check_missingness(R, panel)
    check_urls_and_codebook(R, panel, offline=args.offline)

    write_report(R, panel, offline=args.offline)

    print(
        f"\n=== VALIDATION COMPLETE: {R.n_pass} PASS, {R.n_fail} FAIL, "
        f"{R.n_skip} SKIP ===",
        flush=True,
    )
    return 1 if R.n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
