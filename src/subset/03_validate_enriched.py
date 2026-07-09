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

    # --- base panel intact ---
    chk("base conflict column intact", "n_events_total" in df.columns and df["n_events_total"].notna().any())
    chk("column count == 93", df.shape[1] == 93, str(df.shape[1]))

    n_pass = sum(v for _, v in CHECKS)
    print(f"\n{n_pass}/{len(CHECKS)} checks passed")
    if n_pass != len(CHECKS):
        print("FAILED:", [n for n, v in CHECKS if not v])
        return 1
    print("ALL ENRICHMENT CHECKS PASS ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
