#!/usr/bin/env python3
"""Build the tidy country-level colonial-legacy table (one row per iso3).

Purpose
-------
Parse the three raw colonial sources (COLDAT, QoG jan22, COW states2016) into a
single deterministic country-level table keyed by iso3, the moderator layer for
the study panel (see docs/DATA_SOURCES.md, "Colonial legacy layer"; docs/CODEBOOK
"Colonial legacy"). Everything here is TIME-INVARIANT except the seed for
`years_since_independence`, which is derived at merge time (needs `year`).

Inputs
------
    data/raw/coldat/COLDAT_colonies.tab      (Becker 2019, CC0; join by name)
    data/raw/legal_origins/qog_std_cs_jan22.csv  (QoG; ht_colonial + lp_legor, key ccodealp)
    data/raw/cow_states/states2016.csv       (COW; styear, bridged via QoG ccodecow)

Output
------
    data/interim/colonial.parquet   one row per iso3 (global; the study subset
    keeps only its countries). Columns documented in docs/CODEBOOK.md.

Run
---
    .venv/bin/python src/cleaning/12_colonial.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import country_converter as coco
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COLDAT = ROOT / "data" / "raw" / "coldat" / "COLDAT_colonies.tab"
QOG = ROOT / "data" / "raw" / "legal_origins" / "qog_std_cs_jan22.csv"
COW = ROOT / "data" / "raw" / "cow_states" / "states2016.csv"
OUT = ROOT / "data" / "interim" / "colonial.parquet"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("colonial")

# Hadenius-Teorell colonial-origin coding (QoG ht_colonial).
HT_COLONIAL = {
    0: "None", 1: "Dutch", 2: "Spanish", 3: "Italian", 4: "US", 5: "British",
    6: "French", 7: "Portuguese", 8: "Belgian", 9: "British-French", 10: "Australian",
}
# La Porta legal origin (QoG lp_legor).
LP_LEGOR = {1: "English", 2: "French", 3: "Socialist", 4: "German", 5: "Scandinavian"}

# COW state-system entry (styear) != de jure decolonization for a few contested
# cases. Override with the internationally-recognized independence year.
COW_INDEP_OVERRIDE = {
    "ZWE": 1980,  # COW styear 1965 = unrecognized white-minority UDI (Rhodesia); recognized independence = Lancaster House 1980.
}

# Corrections to the colonizer->legal-family IMPUTATION for the 9 lp_legor blanks
# where the British-administration proxy is historically wrong. Still flagged
# legal_origin_imputed=1; this just fixes the family.
LEGAL_ORIGIN_OVERRIDE = {
    "ERI": "French",  # Eritrea: Italian + Ethiopian civil-law heritage, NOT the brief 1941-51 British military administration.
}

# Colonizer -> legal family used ONLY to impute the 9 countries QoG leaves blank
# on lp_legor. British/US colonial administration -> English common law; every
# other European power (and never-colonized civil-law adopters like Ethiopia) ->
# French/continental civil law. Every imputed cell is flagged (legal_origin_imputed).
COLONIZER_TO_LEGAL = {
    "British": "English", "US": "English",
    "French": "French", "Belgian": "French", "Spanish": "French",
    "Portuguese": "French", "Italian": "French", "Dutch": "French",
    "British-French": "English", "Australian": "English", "None": "French",
}
COMMON_LAW = {"English"}


def load_coldat() -> pd.DataFrame:
    """COLDAT wide -> iso3, colonial start/end (mean aggregation), duration, n, last colonizer."""
    df = pd.read_csv(COLDAT)
    cc = coco.CountryConverter()
    df["iso3"] = cc.convert(df["country"].tolist(), src="regex", to="ISO3", not_found=None)
    df = df.dropna(subset=["iso3"]).drop_duplicates("iso3")

    powers = ["belgium", "britain", "france", "germany", "italy", "netherlands", "portugal", "spain"]
    # Canonical COLDAT power name -> our colonizer label (align with ht_colonial vocab).
    label = {"belgium": "Belgian", "britain": "British", "france": "French",
             "germany": "German", "italy": "Italian", "netherlands": "Dutch",
             "portugal": "Portuguese", "spain": "Spanish"}

    rows = []
    for _, r in df.iterrows():
        active = [p for p in powers if r.get(f"col.{p}", 0) == 1]
        starts = [r[f"colstart.{p}_mean"] for p in active if pd.notna(r.get(f"colstart.{p}_mean"))]
        ends = [(r[f"colend.{p}_mean"], p) for p in active if pd.notna(r.get(f"colend.{p}_mean"))]
        col_start = min(starts) if starts else np.nan
        col_end = max(e for e, _ in ends) if ends else np.nan
        last = label[max(ends)[1]] if ends else ("None" if not active else np.nan)
        rows.append({
            "iso3": r["iso3"],
            "coldat_colonizer_last": last,
            "coldat_n_colonizers": len(active),
            "col_start_year": col_start,
            "col_end_year": col_end,
            "col_duration_years": (col_end - col_start) if (starts and ends) else np.nan,
        })
    return pd.DataFrame(rows)


def load_qog() -> pd.DataFrame:
    """QoG -> iso3, colonizer (ht_colonial), legal_origin (lp_legor), + ccodecow bridge."""
    q = pd.read_csv(QOG, low_memory=False)
    out = q[["ccodealp", "ccodecow", "ht_colonial", "lp_legor"]].copy()
    out = out.rename(columns={"ccodealp": "iso3"}).dropna(subset=["iso3"])
    out["colonizer"] = out["ht_colonial"].map(HT_COLONIAL)
    out["legal_origin"] = out["lp_legor"].map(LP_LEGOR)  # NaN where QoG blank
    return out


def load_cow(bridge: pd.DataFrame) -> pd.DataFrame:
    """COW styear -> independence_year per iso3 (current spell), via QoG ccodecow->iso3."""
    cow = pd.read_csv(COW)
    b = bridge.dropna(subset=["ccodecow"]).copy()
    b["ccodecow"] = b["ccodecow"].astype(int)
    m = cow.merge(b[["ccodecow", "iso3"]], left_on="ccode", right_on="ccodecow", how="left")
    # Keep spells that are current as of the file (endyear==2016); take the modern
    # spell's entry year (max styear) for multi-spell states (e.g. post-breakup).
    current = m[m["endyear"] == 2016].dropna(subset=["iso3"])
    ind = current.groupby("iso3")["styear"].max().reset_index()
    ind = ind.rename(columns={"styear": "independence_year"})
    # Apply contested-entry overrides (e.g. Zimbabwe UDI 1965 -> recognized 1980).
    for iso, yr in COW_INDEP_OVERRIDE.items():
        ind.loc[ind["iso3"] == iso, "independence_year"] = yr
    return ind


def main() -> None:
    coldat = load_coldat()
    qog = load_qog()
    cow = load_cow(qog[["ccodecow", "iso3"]])

    df = qog[["iso3", "colonizer", "legal_origin"]].merge(coldat, on="iso3", how="outer")
    df = df.merge(cow, on="iso3", how="left")

    # ever colonized: colonizer is a real power (not None / not missing).
    df["col_ever_colonized"] = (~df["colonizer"].isin(["None"])) & df["colonizer"].notna()
    df["col_ever_colonized"] = df["col_ever_colonized"].astype(int)

    # legal origin: keep raw lp_legor; impute the blanks from colonizer, flag them.
    df["legal_origin_imputed"] = df["legal_origin"].isna().astype(int)
    df["legal_origin_filled"] = df["legal_origin"].where(
        df["legal_origin"].notna(),
        df["colonizer"].map(COLONIZER_TO_LEGAL),
    )
    # Correct historically-wrong imputations (kept flagged as imputed).
    for iso, lo in LEGAL_ORIGIN_OVERRIDE.items():
        mask = (df["iso3"] == iso) & (df["legal_origin"].isna())
        df.loc[mask, "legal_origin_filled"] = lo
    df["civil_vs_common"] = df["legal_origin_filled"].map(
        lambda x: np.nan if pd.isna(x) else ("common" if x in COMMON_LAW else "civil")
    )

    # Moderator-split dummies (based on the complete `colonizer`).
    df["col_british"] = (df["colonizer"] == "British").astype(int)
    df["col_french"] = (df["colonizer"] == "French").astype(int)
    df["col_iberian"] = df["colonizer"].isin(["Spanish", "Portuguese"]).astype(int)

    keep = [
        "iso3", "colonizer", "coldat_colonizer_last", "col_ever_colonized",
        "coldat_n_colonizers", "col_start_year", "col_end_year", "col_duration_years",
        "independence_year", "legal_origin", "legal_origin_filled",
        "legal_origin_imputed", "civil_vs_common", "col_british", "col_french", "col_iberian",
    ]
    df = df[keep].sort_values("iso3").reset_index(drop=True)
    df.to_parquet(OUT, index=False)

    # Diagnostics.
    log.info("wrote %s: %d countries x %d cols", OUT.name, len(df), df.shape[1])
    log.info("colonizer:\n%s", df["colonizer"].value_counts(dropna=False).to_string())
    log.info("legal_origin_filled:\n%s", df["legal_origin_filled"].value_counts(dropna=False).to_string())
    log.info("imputed legal_origin rows: %d", int(df["legal_origin_imputed"].sum()))
    # ht vs coldat colonizer disagreement (non-None both sides) for transparency.
    both = df.dropna(subset=["colonizer", "coldat_colonizer_last"])
    both = both[(both["colonizer"] != "None") & (both["coldat_colonizer_last"] != "None")]
    disagree = both[both["colonizer"] != both["coldat_colonizer_last"]]
    log.info("ht/coldat colonizer disagreements: %d", len(disagree))
    if len(disagree):
        log.info("%s", disagree[["iso3", "colonizer", "coldat_colonizer_last"]].to_string(index=False))


if __name__ == "__main__":
    main()
