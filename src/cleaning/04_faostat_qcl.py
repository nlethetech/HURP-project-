#!/usr/bin/env python3
"""Clean the FAOSTAT QCL bulk download into a tidy country-year crop table.

Purpose
-------
Turn the raw FAOSTAT "Production: Crops and livestock products" (domain QCL)
"All Data Normalized" bulk zip into the national (admin-0) crop-production
backbone of the panel: country-year Production (tonnes) and Area harvested
(hectares) for crop items, 1961-2024 (see docs/DATA_SOURCES.md, "FAOSTAT —
Production: Crops and livestock products (QCL)").

Inputs
------
    data/raw/faostat_qcl/Production_Crops_Livestock_E_All_Data_(Normalized).zip
        (produced by src/acquisition/04_download_faostat_qcl.py)
    The zip carries, alongside the main long-format CSV, companion code lists:
    AreaCodes (Area Code, M49 Code, Area), ItemCodes (Item Code, CPC Code,
    Item), Elements and Flags. All are read as UTF-8 (registry gotcha #8: the
    current snapshot is UTF-8, not latin-1; reading as latin-1 produces silent
    mojibake on names such as "Cote d'Ivoire").

Outputs
-------
    data/interim/faostat_qcl.parquet
        Tidy long table, one row per (iso3, year, item_code, element):
            iso3        (str)  ISO 3166-1 alpha-3 country code
            year        (int)  1961-2024
            item_code   (int)  FAOSTAT numeric item code
            item        (str)  item label (UTF-8)
            element     (str)  'Production' | 'Area harvested'
            value       (float) reported value
            unit        (str)  't' (Production) | 'ha' (Area harvested)
        Sorted deterministically by (iso3, year, item_code, element) so re-runs
        are byte-stable.

What is kept / dropped (constants below; every filter logs its row count)
------------------------------------------------------------------------
Elements: only Production in tonnes (Element Code 5510, unit 't') and Area
  harvested in hectares (Element Code 5312, unit 'ha'). Yield, livestock head
  counts, stocks, and tonne-reported livestock/processed products are out of
  scope for the crop backbone and are dropped.

Crop items: only primary crop items, identified as CPC division 01 (CPC code
  begins '01'). This excludes live animals (CPC 02), meat/dairy/eggs (CPC
  21/22), processed and derived products (grain-mill 23, beverages 24, fibres
  26, vegetable oils 216xx), and the FAO 'F'-prefixed computed aggregates
  ('Cereals, primary', 'Crops, primary', etc.) which are sums over the very
  items retained here and would double-count. The Production-(t) filter alone
  still admits a handful of crop-derived but non-primary CPC-01x items reported
  in tonnes without harvested area (e.g. cotton lint, cotton seed); these stay
  because they are genuine CPC-01 crop products. The intent is the primary-crop
  production/area backbone, not a Production==Area-harvested inner join.

Area -> ISO3: each FAOSTAT area is mapped to ISO3 via its UN M49 numeric code
  using the M49->ISO3 concordance below. Dropped (logged) are:
    (1) FAO regional/economic aggregates (FAO Area Code >= 5000: World,
        continents, sub-regions, EU(27), LDCs, LLDCs, SIDS, LIFDCs, NFIDCs);
    (2) dissolved-state / successor predecessors and FAO country aggregates
        with no single current ISO3 (Belgium-Luxembourg, Czechoslovakia,
        Ethiopia PDR, Serbia and Montenegro, Sudan (former), USSR, Yugoslav
        SFR, and the FAO 'China' aggregate code 159 which double-counts its
        constituents China;mainland/Taiwan/Hong Kong/Macao that ARE retained).
  Any non-region area whose M49 is absent from the concordance is dropped and
  logged by name; if such a drop list is non-empty and unexpected, inspect it.

Runtime
-------
~30-90 s (the main CSV is ~545 MB uncompressed, ~4.21 M rows; read in chunks).

How to run
----------
    .venv/bin/python src/cleaning/04_faostat_qcl.py

Idempotent: the output is rewritten in full each run from the immutable raw zip.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

# --- Constants ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ZIP = (
    REPO_ROOT
    / "data"
    / "raw"
    / "faostat_qcl"
    / "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
OUT_PARQUET = REPO_ROOT / "data" / "interim" / "faostat_qcl.parquet"

MAIN_CSV = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"
AREA_CSV = "Production_Crops_Livestock_E_AreaCodes.csv"
ENCODING = "utf-8-sig"
CHUNKSIZE = 500_000

# Elements kept: (Element Code, expected Unit). Registry/profile confirmed:
#   5510 'Production'     unit 't'  (1,625,403 rows of which crops are a subset)
#   5312 'Area harvested' unit 'ha' (893,484 rows; intrinsically crop-only)
KEEP_ELEMENTS = {
    "5510": ("Production", "t"),
    "5312": ("Area harvested", "ha"),
}

# Year bounds (registry coverage: QCL 1961-2024).
YEAR_MIN = 1961
YEAR_MAX = 2024

# Crop items = CPC division 01 (CPC code begins with this prefix after the
# leading quote is stripped). Excludes livestock/processed/'F' aggregates.
CROP_CPC_PREFIX = "01"

# FAO regional/economic aggregates carry FAO Area Code >= this floor.
FAO_REGION_AREA_CODE_FLOOR = 5000

# Successor-state predecessors / FAO country aggregates intentionally excluded
# even though they have a "country-like" M49: documented so the concordance
# can stay a pure current-ISO3 table (these M49 keys are simply absent below).
KNOWN_NONMAPPED_AREAS = {
    "Belgium-Luxembourg",
    "China",  # FAO aggregate code 159 = mainland+Taiwan+HK+Macao (kept separately)
    "Czechoslovakia",
    "Ethiopia PDR",
    "Serbia and Montenegro",
    "Sudan (former)",
    "USSR",
    "Yugoslav SFR",
}

# UN M49 numeric -> ISO 3166-1 alpha-3, restricted to the current
# countries/territories present in this QCL snapshot. FAO uses standard M49 for
# all areas here (China;mainland=156->CHN, Taiwan=158->TWN, Hong Kong=344->HKG,
# Macao=446->MAC); the FAO-specific 'China' aggregate (M49 159) is deliberately
# absent so it drops out as a double-count.
M49_TO_ISO3 = {
    4: "AFG", 8: "ALB", 12: "DZA", 16: "ASM", 20: "AND", 24: "AGO", 28: "ATG",
    31: "AZE", 32: "ARG", 36: "AUS", 40: "AUT", 44: "BHS", 48: "BHR", 50: "BGD",
    51: "ARM", 52: "BRB", 56: "BEL", 60: "BMU", 64: "BTN", 68: "BOL", 70: "BIH",
    72: "BWA", 76: "BRA", 84: "BLZ", 90: "SLB", 92: "VGB", 96: "BRN", 100: "BGR",
    104: "MMR", 108: "BDI", 112: "BLR", 116: "KHM", 120: "CMR", 124: "CAN",
    132: "CPV", 140: "CAF", 144: "LKA", 148: "TCD", 152: "CHL", 156: "CHN",
    158: "TWN", 170: "COL", 174: "COM", 178: "COG", 180: "COD", 184: "COK",
    188: "CRI", 191: "HRV", 192: "CUB", 196: "CYP", 203: "CZE", 204: "BEN",
    208: "DNK", 212: "DMA", 214: "DOM", 218: "ECU", 222: "SLV", 226: "GNQ",
    231: "ETH", 232: "ERI", 233: "EST", 234: "FRO", 242: "FJI", 246: "FIN",
    250: "FRA", 254: "GUF", 258: "PYF", 262: "DJI", 266: "GAB", 268: "GEO",
    270: "GMB", 275: "PSE", 276: "DEU", 288: "GHA", 296: "KIR", 300: "GRC",
    308: "GRD", 312: "GLP", 320: "GTM", 324: "GIN", 328: "GUY", 332: "HTI",
    340: "HND", 344: "HKG", 348: "HUN", 352: "ISL", 356: "IND", 360: "IDN",
    364: "IRN", 368: "IRQ", 372: "IRL", 376: "ISR", 380: "ITA", 384: "CIV",
    388: "JAM", 392: "JPN", 398: "KAZ", 400: "JOR", 404: "KEN", 408: "PRK",
    410: "KOR", 414: "KWT", 417: "KGZ", 418: "LAO", 422: "LBN", 426: "LSO",
    428: "LVA", 430: "LBR", 434: "LBY", 440: "LTU", 442: "LUX", 446: "MAC",
    450: "MDG", 454: "MWI", 458: "MYS", 462: "MDV", 466: "MLI", 470: "MLT",
    474: "MTQ", 478: "MRT", 480: "MUS", 484: "MEX", 496: "MNG", 498: "MDA",
    499: "MNE", 504: "MAR", 508: "MOZ", 512: "OMN", 516: "NAM", 520: "NRU",
    524: "NPL", 528: "NLD", 540: "NCL", 548: "VUT", 554: "NZL", 558: "NIC",
    562: "NER", 566: "NGA", 570: "NIU", 578: "NOR", 583: "FSM", 584: "MHL",
    586: "PAK", 591: "PAN", 598: "PNG", 600: "PRY", 604: "PER", 608: "PHL",
    616: "POL", 620: "PRT", 624: "GNB", 626: "TLS", 630: "PRI", 634: "QAT",
    638: "REU", 642: "ROU", 643: "RUS", 646: "RWA", 659: "KNA", 662: "LCA",
    670: "VCT", 678: "STP", 682: "SAU", 686: "SEN", 688: "SRB", 690: "SYC",
    694: "SLE", 702: "SGP", 703: "SVK", 704: "VNM", 705: "SVN", 706: "SOM",
    710: "ZAF", 716: "ZWE", 724: "ESP", 728: "SSD", 729: "SDN", 740: "SUR",
    748: "SWZ", 752: "SWE", 756: "CHE", 760: "SYR", 762: "TJK", 764: "THA",
    768: "TGO", 776: "TON", 780: "TTO", 784: "ARE", 788: "TUN", 792: "TUR",
    795: "TKM", 798: "TUV", 800: "UGA", 804: "UKR", 807: "MKD", 818: "EGY",
    826: "GBR", 834: "TZA", 840: "USA", 854: "BFA", 858: "URY", 860: "UZB",
    862: "VEN", 882: "WSM", 887: "YEM", 894: "ZMB",
}

USECOLS = [
    "Area Code",
    "Area Code (M49)",
    "Item Code",
    "Item Code (CPC)",
    "Item",
    "Element Code",
    "Year",
    "Unit",
    "Value",
]

FINAL_COLS = ["iso3", "year", "item_code", "item", "element", "value", "unit"]
SORT_COLS = ["iso3", "year", "item_code", "element"]


def log(msg: str) -> None:
    print(msg, flush=True)


def build_area_to_iso3(zf: zipfile.ZipFile) -> tuple[dict[int, str], pd.DataFrame]:
    """Return {FAO Area Code -> ISO3} and the AreaCodes frame (for drop logging)."""
    with zf.open(AREA_CSV) as f:
        areas = pd.read_csv(f, dtype=str, encoding=ENCODING)
    areas.columns = [c.strip() for c in areas.columns]
    required = {"Area Code", "M49 Code", "Area"}
    missing = required - set(areas.columns)
    if missing:
        raise ValueError(f"AreaCodes schema changed; missing columns: {sorted(missing)}")
    areas["area_code"] = pd.to_numeric(areas["Area Code"], errors="raise").astype(int)
    areas["m49"] = pd.to_numeric(
        areas["M49 Code"].str.lstrip("'"), errors="coerce"
    ).astype("Int64")
    areas["iso3"] = areas["m49"].map(
        lambda x: M49_TO_ISO3.get(int(x)) if pd.notna(x) else None
    )

    is_region = areas["area_code"] >= FAO_REGION_AREA_CODE_FLOOR
    n_region = int(is_region.sum())
    log(
        f"  AREA: dropping {n_region} FAO regional/economic aggregate areas "
        f"(Area Code >= {FAO_REGION_AREA_CODE_FLOOR})"
    )

    non_region = areas.loc[~is_region]
    unmapped = non_region.loc[non_region["iso3"].isna()]
    log(
        f"  AREA: dropping {len(unmapped)} non-region areas with no current ISO3 "
        "(successor-state predecessors / FAO country aggregates):"
    )
    for name in sorted(unmapped["Area"].tolist()):
        log(f"        - {name}")

    # Guard: the unmapped non-region set must be exactly the documented list.
    unmapped_names = set(unmapped["Area"].tolist())
    unexpected = unmapped_names - KNOWN_NONMAPPED_AREAS
    if unexpected:
        raise ValueError(
            "Unexpected unmapped non-region areas (not in KNOWN_NONMAPPED_AREAS); "
            f"update the M49 concordance or the documented exclusions: {sorted(unexpected)}"
        )

    mapped = areas.loc[(~is_region) & areas["iso3"].notna()]
    if mapped["iso3"].duplicated().any():
        dups = mapped.loc[mapped["iso3"].duplicated(keep=False), ["Area", "iso3"]]
        raise ValueError(f"Two FAO areas map to one ISO3; ambiguous:\n{dups}")
    log(
        f"  AREA: mapped {len(mapped)} country areas -> "
        f"{mapped['iso3'].nunique()} distinct ISO3"
    )
    area_to_iso3 = dict(zip(mapped["area_code"], mapped["iso3"]))
    return area_to_iso3, areas


def main() -> int:
    if not RAW_ZIP.exists():
        raise FileNotFoundError(
            f"Raw input missing: {RAW_ZIP}\n"
            "Run: .venv/bin/python src/acquisition/04_download_faostat_qcl.py"
        )

    log(f"Reading {RAW_ZIP}")
    with zipfile.ZipFile(RAW_ZIP) as zf:
        names = set(zf.namelist())
        for needed in (MAIN_CSV, AREA_CSV):
            if needed not in names:
                raise FileNotFoundError(f"Expected member {needed} not in zip; got {names}")

        area_to_iso3, _ = build_area_to_iso3(zf)

        # Counters for the streaming pass.
        n_total = 0
        n_after_element = 0
        n_after_crop = 0
        n_after_area = 0
        n_after_year = 0
        n_nan_value = 0
        parts: list[pd.DataFrame] = []
        header_checked = False

        with zf.open(MAIN_CSV) as f:
            reader = pd.read_csv(
                f, dtype=str, encoding=ENCODING, usecols=USECOLS, chunksize=CHUNKSIZE
            )
            for chunk in reader:
                if not header_checked:
                    missing = set(USECOLS) - set(chunk.columns)
                    if missing:
                        raise ValueError(
                            f"Main CSV schema changed; missing columns: {sorted(missing)}"
                        )
                    header_checked = True
                n_total += len(chunk)

                # 1) Element filter (code + unit must match the kept pair).
                c = chunk[chunk["Element Code"].isin(KEEP_ELEMENTS)].copy()
                # Validate unit per element; mismatch means a schema/units change.
                for ecode, (ename, eunit) in KEEP_ELEMENTS.items():
                    sub = c.loc[c["Element Code"] == ecode, "Unit"]
                    bad = sub[sub != eunit]
                    if len(bad):
                        raise ValueError(
                            f"Element {ecode} ({ename}) has unexpected unit(s) "
                            f"{sorted(bad.unique())}; expected '{eunit}'."
                        )
                n_after_element += len(c)

                # 2) Crop-item filter: CPC division 01.
                cpc = c["Item Code (CPC)"].str.lstrip("'")
                c = c[cpc.str.startswith(CROP_CPC_PREFIX)].copy()
                n_after_crop += len(c)

                # 3) Area -> ISO3 (rows from dropped areas map to NaN and go).
                area_code = pd.to_numeric(c["Area Code"], errors="raise").astype(int)
                c["iso3"] = area_code.map(area_to_iso3)
                c = c[c["iso3"].notna()].copy()
                n_after_area += len(c)

                # 4) Year bounds.
                c["year"] = pd.to_numeric(c["Year"], errors="raise").astype(int)
                c = c[(c["year"] >= YEAR_MIN) & (c["year"] <= YEAR_MAX)].copy()
                n_after_year += len(c)

                if len(c) == 0:
                    continue

                # Normalise the kept columns.
                c["item_code"] = pd.to_numeric(c["Item Code"], errors="raise").astype(int)
                c["item"] = c["Item"].astype(str)
                c["element"] = c["Element Code"].map(
                    {k: v[0] for k, v in KEEP_ELEMENTS.items()}
                )
                c["unit"] = c["Unit"].astype(str)
                val = pd.to_numeric(c["Value"], errors="coerce")
                n_nan_value += int(val.isna().sum())
                c["value"] = val

                parts.append(c[FINAL_COLS])

    if not parts:
        raise RuntimeError("No rows survived filtering; aborting (input or filters wrong).")

    df = pd.concat(parts, ignore_index=True)

    # Drop rows whose Value failed numeric parsing (NaN); logged.
    n_pre = len(df)
    df = df[df["value"].notna()].copy()
    n_dropped_nan = n_pre - len(df)

    # Deterministic order & dtypes.
    df["year"] = df["year"].astype("int64")
    df["item_code"] = df["item_code"].astype("int64")
    df = df.sort_values(SORT_COLS, kind="mergesort").reset_index(drop=True)
    df = df[FINAL_COLS]

    # Hard invariants.
    if df["iso3"].isna().any():
        raise AssertionError("null iso3 in output")
    if not set(df["element"].unique()) <= {"Production", "Area harvested"}:
        raise AssertionError(f"unexpected elements: {sorted(df['element'].unique())}")
    if not set(df["unit"].unique()) <= {"t", "ha"}:
        raise AssertionError(f"unexpected units: {sorted(df['unit'].unique())}")
    if df["year"].min() < YEAR_MIN or df["year"].max() > YEAR_MAX:
        raise AssertionError(f"year out of bounds: {df['year'].min()}-{df['year'].max()}")

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== FILTER FUNNEL (rows) ===")
    log(f"  raw rows read:                 {n_total:,}")
    log(f"  after element filter:          {n_after_element:,}")
    log(f"  after crop-item filter (CPC01):{n_after_crop:,}")
    log(f"  after area->ISO3 filter:       {n_after_area:,}")
    log(f"  after year bounds:             {n_after_year:,}")
    log(f"  dropped non-numeric Value:     {n_dropped_nan:,} (NaN values seen {n_nan_value:,})")
    log("")
    log("=== FAOSTAT QCL OUTPUT SUMMARY ===")
    log(f"  output rows:        {len(df):,}")
    log(f"  distinct iso3:      {df['iso3'].nunique()}")
    log(f"  year range:         {int(df['year'].min())}-{int(df['year'].max())}")
    log(f"  distinct items:     {df['item_code'].nunique()}")
    by_el = df["element"].value_counts().sort_index()
    for el, cnt in by_el.items():
        log(f"  element '{el}': {cnt:,} rows")
    log(f"Wrote {OUT_PARQUET} ({len(df):,} rows)")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
