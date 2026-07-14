#!/usr/bin/env python3
"""Independent validator for the enriched study panel (colonial + pest layers).

Re-checks the enrichment against source facts, known history, and the design
rules (Africa-only pest, no zero-fill, complete colonial). Mirrors
src/merge/02_validate_panel.py. Exit 0 iff every check passes.

Run
---
    .venv/bin/python src/subset/03_validate_enriched.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "panel_africa_samerica_caribbean_enriched.parquet"

CHECKS: list[tuple[str, bool]] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond)))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    df = pd.read_parquet(PANEL)
    amer = df["region"].isin(["South America", "Caribbean"])
    afr = df["region"] == "Africa"
    one = df.drop_duplicates("iso3").set_index("iso3")

    # --- structure ---
    chk("row count 583,490", len(df) == 583_490, str(len(df)))
    chk("unique (district_id, year)", df.duplicated(["district_id", "year"]).sum() == 0)
    chk("79 study countries", df["iso3"].nunique() == 79)
    chk("regions == {Africa, South America, Caribbean}",
        set(df["region"].unique()) == {"Africa", "South America", "Caribbean"})

    # --- colonial completeness + correctness ---
    chk("colonizer complete (79/79)", df[df["colonizer"].isna()]["iso3"].nunique() == 0)
    chk("legal tradition complete", df["civil_vs_common"].notna().all())
    chk("independence_year complete", df["independence_year"].notna().all())
    chk("independence range 1822–2011",
        int(df["independence_year"].min()) == 1822 and int(df["independence_year"].max()) == 2011)
    chk("years_since_independence identity",
        (df["years_since_independence"] == df["year"] - df["independence_year"]).all())
    # known-history spot checks
    spot = {"BRA": ("Portuguese", "civil"), "CUB": ("Spanish", "civil"), "COD": ("Belgian", "civil"),
            "NGA": ("British", "common"), "SUR": ("Dutch", "civil"), "ETH": ("None", "civil"),
            "DZA": ("French", "civil"), "JAM": ("British", "common"), "GNQ": ("Spanish", "civil")}
    for iso, (colz, law) in spot.items():
        chk(f"{iso} = {colz}/{law}",
            one.loc[iso, "colonizer"] == colz and one.loc[iso, "civil_vs_common"] == law,
            f"{one.loc[iso,'colonizer']}/{one.loc[iso,'civil_vs_common']}")
    chk("CUB legal_origin = Socialist (La Porta)", one.loc["CUB", "legal_origin"] == "Socialist")
    chk("colonizer×region: South America Spanish==9",
        (df[df.region == "South America"].drop_duplicates("iso3")["colonizer"] == "Spanish").sum() == 9)

    # --- pest: Africa-only, no zero-fill ---
    pest = ["faw_present", "dl_present_flag", "faw_confirmed_sum", "dl_swarm_obs",
            "years_since_faw_arrival", "dl_first_gregarious_year", "faw_first_detection_year"]
    chk("pest ALL NaN for South America + Caribbean", df.loc[amer, pest].isna().all().all())
    chk("dl_present_flag ∈ {1, NaN} (presence-only, no spurious 0)",
        set(df["dl_present_flag"].dropna().unique()) == {1.0})
    chk("Africa pest is sparse NaN (monitoring, not zero-filled)",
        df.loc[afr, "faw_present"].isna().mean() > 0.9 and df.loc[afr, "dl_present_flag"].isna().mean() > 0.9)
    chk("locust belt = 20 African countries",
        df[df["dl_present_flag"].notna()]["iso3"].nunique() == 20)
    chk("locust belt excludes non-arid (no COG/GHA/AGO)",
        not {"COG", "GHA", "AGO"} & set(df[df["dl_present_flag"].notna()]["iso3"]))
    # 2020 East-Africa upsurge must show locust in KEN/ETH/SOM
    up = df[(df["year"] == 2020) & (df["iso3"].isin(["KEN", "ETH", "SOM"])) & (df["dl_present_flag"] == 1)]
    chk("2020 upsurge present in KEN/ETH/SOM (>5 districts)", up["district_id"].nunique() > 5,
        f"{up['district_id'].nunique()} districts")
    chk("FAW invasion post-2015 only (first_detection_year >= 2018)",
        df["faw_first_detection_year"].dropna().min() >= 2018)

    # --- colonial correctness regressions (adversarial-review fixes) ---
    chk("ZWE independence_year == 1980 (not UDI 1965)", int(one.loc["ZWE", "independence_year"]) == 1980)
    chk("ERI legal tradition == civil (not imputed common)", one.loc["ERI", "civil_vs_common"] == "civil")

    # --- pest completeness: no out-of-window arrival, every in-window African obs lands ---
    ymax = int(df["year"].max())
    chk("no pest first-year beyond panel window",
        (df["faw_first_detection_year"].dropna() <= ymax).all()
        and (df["dl_first_gregarious_year"].dropna() <= ymax).all())
    afr_ids = set(df.loc[df["region"] == "Africa", "district_id"])

    def lands(interim_path: Path, flag: str) -> bool:
        it = pd.read_parquet(interim_path)
        obs = it[(it["year"] <= ymax) & (it["district_id"].isin(afr_ids))][["district_id", "year"]].drop_duplicates()
        m = obs.merge(df[["district_id", "year", flag]], on=["district_id", "year"], how="left")
        return bool(m[flag].notna().all())

    interim = ROOT / "data" / "interim"
    chk("every in-window African locust obs lands in panel", lands(interim / "locust_district_year.parquet", "dl_present_flag"))
    chk("every in-window African FAW obs lands in panel", lands(interim / "faw_district_year.parquet", "faw_present"))

    # --- country-year mediators (state capacity / regime / repression) ---
    chk("PTS repression covers all 79 (ZAR->COD fix)", df[df["pts_score"].notna()]["iso3"].nunique() == 79)
    chk("V-Dem covers 72/79 (7 Caribbean microstates absent)", df[df["vdem_polyarchy"].notna()]["iso3"].nunique() == 72)
    chk("GRD tax covers 76/79", df[df["grd_tax_pct_gdp"].notna()]["iso3"].nunique() == 76)
    chk("no zero-fill leak: tax/regime/pts NaN not 0 where missing",
        df["grd_tax_pct_gdp"].min() > 0 and df["vdem_polyarchy"].min() > 0 and df["pts_score"].min() >= 1)
    chk("mediators time-varying (not absorbed by country FE)",
        df.groupby("iso3")["pts_score"].nunique().max() > 1 and df.groupby("iso3")["grd_tax_pct_gdp"].nunique().max() > 1)
    # known-history spot checks
    rw = df[(df["iso3"] == "RWA") & (df["year"] == 1994)]["pts_score"]
    chk("Rwanda 1994 repression = 5 (genocide)", (rw == 5).all() and len(rw) > 0)
    za = df[df["iso3"] == "ZAF"].groupby("year")["vdem_polyarchy"].first()
    chk("South Africa democratized (polyarchy 1993 < 1995)", za.get(1993, 1) < za.get(1995, 0))
    # Polity ccode-crosswalk regressions (adversarial-review fixes)
    def pol_span(iso: str) -> tuple[int, int]:
        s = df[(df["iso3"] == iso) & (df["polity2"].notna())]["year"]
        return (int(s.min()), int(s.max())) if len(s) else (0, 0)
    chk("Ethiopia polity2 spans to >=2018 (post-1993 ccode 529 fix)", pol_span("ETH")[1] >= 2018)
    chk("Sudan polity2 spans to >=2018 (ccode 626 fix)", pol_span("SDN")[1] >= 2018)
    ssd15 = df[(df["iso3"] == "SSD") & (df["year"] == 2015)]["polity2"]
    chk("South Sudan 2015 polity2 == 0 (own value, not Sudan's -4)", (ssd15 == 0).all() and len(ssd15) > 0)
    chk("polity2 covers >=69/79 study countries", df[df["polity2"].notna()]["iso3"].nunique() >= 69)

    # --- displacement (UNHCR origins + IDMC) ---
    chk("UNHCR refugees_origin covers all 79", df[df["refugees_origin"].notna()]["iso3"].nunique() == 79)
    chk("IDMC conflict-stock covers the conflict-affected subset (>=35)",
        df[df["idp_stock_conflict"].notna()]["iso3"].nunique() >= 35)
    chk("displacement not zero-filled (NaN where unobserved)",
        df["idp_stock_conflict"].isna().any() and df["new_disp_disaster"].isna().any())
    col15 = df[(df["iso3"] == "COL") & (df["year"] == 2015)]["idp_stock_conflict"]
    chk("Colombia 2015 conflict IDP stock > 5M (real crisis)", (col15 > 5_000_000).all() and len(col15) > 0)
    rw94 = df[(df["iso3"] == "RWA") & (df["year"] == 1994)]["refugees_origin"]
    chk("Rwanda 1994 refugees > 2M (genocide exodus)", (rw94 > 2_000_000).all() and len(rw94) > 0)

    # --- spatial layers: temperature / market access / resources / ethnic exclusion ---
    chk("temperature covers all 79", df[df["temp_mean"].notna()]["iso3"].nunique() == 79)
    chk("temp_mean physically plausible (-30..45 C)", df["temp_mean"].min() > -30 and df["temp_mean"].max() < 45)
    chk("temperature 2025 is NaN (CRU ends 2024, no zero-fill)", df[df["year"] == 2025]["temp_mean"].isna().all())
    tmean = df.groupby("iso3")["temp_mean"].mean()
    chk("Niger hotter than Chile (sanity)", tmean.get("NER", 0) > tmean.get("CHL", 99))
    chk("temp_anomaly physically bounded (|z| < 8, no degenerate-baseline blowup)",
        df["temp_anomaly"].abs().max() < 8)
    chk("market access covers all 79", df[df["travel_time_to_city_min_median"].notna()]["iso3"].nunique() == 79)
    chk("travel-time keeps in-city 0s (min == 0, not masked)", df["travel_time_to_city_min_median"].min() == 0)
    chk("Fernando de Noronha covered (tile-seam gap closed)",
        df[df["district_id"] == "56859067B68153873864864"]["travel_time_to_city_min_median"].notna().any())
    # resources: lootable-diamond distinction (Sierra Leone alluvial vs Botswana kimberlite)
    sle = df[df["iso3"] == "SLE"]["has_lootable_diamond"]
    bwa = df[df["iso3"] == "BWA"]
    chk("Sierra Leone has lootable diamonds", (sle == 1).any())
    chk("Botswana diamonds are NON-lootable (kimberlite)",
        (bwa["has_diamond"] == 1).any() and (bwa["has_lootable_diamond"] == 1).sum() == 0)
    chk("resources zero-filled census (has_oil_gas all 79)", df[df["has_oil_gas"].notna()]["iso3"].nunique() == 79)
    # gold: African artisanal-gold gap filled via USGS (MRDS alone had Mali=4)
    chk("Mali has gold (USGS Africa fills the MRDS gap)", (df[df["iso3"] == "MLI"]["has_gold"] == 1).any())
    chk("Burkina/Ghana/DRC/Tanzania gold present",
        all((df[df["iso3"] == c]["has_gold"] == 1).any() for c in ["BFA", "GHA", "COD", "TZA"]))
    chk("Americas gold present (MRDS): Peru & Colombia", (df[df["iso3"] == "PER"]["has_gold"] == 1).any() and (df[df["iso3"] == "COL"]["has_gold"] == 1).any())
    chk("has_gold covers all 79 (census, 0/1)", df[df["has_gold"].notna()]["iso3"].nunique() == 79 and set(df["has_gold"].dropna().unique()) <= {0, 1})
    # ethnic exclusion: South Africa apartheid -> democracy
    za_ex = df[df["iso3"] == "ZAF"].groupby("year")["share_area_excluded"].mean()
    chk("South Africa excluded-share fell after apartheid (1990 >> 2000)", za_ex.get(1990, 0) > 0.5 and za_ex.get(2000, 1) < 0.2)
    chk("EPR not zero-filled (homogeneous/post-2021 NaN)", df["share_area_excluded"].isna().any())

    # --- food insecurity (FEWS/IPC) ---
    chk("food insecurity covers >=20 study countries", df[df["ipc_phase_max"].notna()]["iso3"].nunique() >= 20)
    chk("food insecurity reaches Haiti (Americas)", df[(df["iso3"] == "HTI") & (df["ipc_phase_max"].notna())].shape[0] > 0)
    chk("IPC phases in 1..5", df["ipc_phase_max"].dropna().between(1, 5).all())
    chk("South Sudan 2017 famine captured (phase 5)",
        (df[(df["iso3"] == "SSD") & (df["year"] == 2017)]["ipc_phase_max"] == 5).any())
    chk("food insecurity NOT zero-filled (uncovered = NaN)", df["ipc_phase_max"].isna().any())
    chk("ipc_phase3plus_area_share is a valid 0-1 share", df["ipc_phase3plus_area_share"].dropna().between(0, 1).all())
    chk("ipc_crisis_flag == (phase>=3) where observed",
        (df.loc[df["ipc_phase_max"].notna(), "ipc_crisis_flag"] ==
         (df.loc[df["ipc_phase_max"].notna(), "ipc_phase_max"] >= 3).astype(int)).all())

    # --- FAOSTAT agricultural output ---
    chk("FAOSTAT cereal covers 75/79 (4 non-cereal island states NaN)",
        df[df["fao_cereal_prod_t"].notna()]["iso3"].nunique() == 75)
    chk("FAOSTAT 2025 NaN (bulk ends 2024, not carried)", df[df["year"] == 2025]["fao_cereal_prod_t"].isna().all())
    chk("FAOSTAT not blanket zero-filled (mostly NaN or real values)", df["fao_maize_prod_t"].isna().any())
    ng = df[(df["iso3"] == "NGA") & (df["year"] == 2020)]["fao_cassava_prod_t"]
    chk("Nigeria 2020 cassava > 40M t (world's #1 producer)", (ng > 40_000_000).all() and len(ng) > 0)
    br = df[(df["iso3"] == "BRA") & (df["year"] == 2020)]["fao_maize_prod_t"]
    chk("Brazil 2020 maize > 50M t", (br > 50_000_000).all() and len(br) > 0)
    chk("FAOSTAT cereal yield plausible (200-15000 kg/ha)",
        df["fao_cereal_yield_kgha"].dropna().between(200, 15000).mean() > 0.99)
    chk("Ethiopia FAOSTAT back-series recovered (1989 present via Ethiopia-PDR fix)",
        df[(df["iso3"] == "ETH") & (df["year"] == 1989)]["fao_cereal_prod_t"].notna().any())

    # --- base panel intact ---
    chk("base conflict column intact", "n_events_total" in df.columns and df["n_events_total"].notna().any())
    chk("column count == 175", df.shape[1] == 175, str(df.shape[1]))

    n_pass = sum(v for _, v in CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} checks passed")
    if n_pass != len(CHECKS):
        print("FAILED:", [n for n, v in CHECKS if not v])
        return 1
    print("ALL ENRICHMENT CHECKS PASS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
