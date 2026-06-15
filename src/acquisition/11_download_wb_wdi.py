#!/usr/bin/env python3
"""Download a curated set of World Bank WDI indicators (country-year covariates).

Purpose
-------
Acquire the socioeconomic & agricultural covariates that the conflict and
agricultural-production literature uses as explanators/controls -- unemployment
(incl. youth), GDP per capita and growth, inflation, population and age
structure, urbanization, and agricultural value-added/employment/land/yield/
food-production -- from the World Bank World Development Indicators REST API.
See docs/DATA_SOURCES.md, "World Bank World Development Indicators (WDI)".

Source / registry
-----------------
World Bank Indicators API v2 (no auth, CC BY 4.0):
    https://api.worldbank.org/v2/country/all/indicator/{CODE}
        ?format=json&per_page=20000&date=1989:2025
Returns [meta, [rows]]; each row carries countryiso3code, date (year), value.

Inputs
------
None (anonymous HTTPS GET).

Outputs
-------
    data/raw/wb_wdi/<CODE>.json     (raw API page(s) per indicator)
    data/raw/wb_wdi/MANIFEST.txt    (code, column, rows, retrieved date, name)

Runtime
-------
Network-bound; ~15 small JSON pulls, a few seconds each.

How to run
----------
    .venv/bin/python src/acquisition/11_download_wb_wdi.py
    .venv/bin/python src/acquisition/11_download_wb_wdi.py --force

Idempotent: an indicator whose JSON already exists is skipped unless --force.
Each download is validated (HTTP 200, non-empty meta.total) so a renamed or
retired indicator code fails loudly rather than silently writing an empty layer.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "wb_wdi"
API = "https://api.worldbank.org/v2/country/all/indicator/{code}"
YEAR_MIN, YEAR_MAX = 1989, 2025
PER_PAGE = 20000

# Curated indicator code -> panel column stem (see registry for descriptions).
INDICATORS = {
    "SL.UEM.TOTL.ZS": "wb_unemployment",
    "SL.UEM.1524.ZS": "wb_unemployment_youth",
    "NY.GDP.PCAP.KD": "wb_gdp_pc",
    "NY.GDP.MKTP.KD.ZG": "wb_gdp_growth",
    "FP.CPI.TOTL.ZG": "wb_inflation",
    "SP.POP.TOTL": "wb_population",
    "SP.POP.GROW": "wb_pop_growth",
    "SP.POP.0014.TO.ZS": "wb_pop_0_14",
    "SP.URB.TOTL.IN.ZS": "wb_urban_pct",
    "NV.AGR.TOTL.ZS": "wb_ag_valueadd_pct",
    "SL.AGR.EMPL.ZS": "wb_ag_employment_pct",
    "AG.LND.AGRI.ZS": "wb_ag_land_pct",
    "AG.YLD.CREL.KG": "wb_cereal_yield",
    "AG.PRD.FOOD.XD": "wb_food_prod_index",
    "AG.LND.ARBL.ZS": "wb_arable_land_pct",
}

MAX_RETRIES = 5
BACKOFF_BASE_S = 2.0
TIMEOUT_S = 90

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_indicator(session: requests.Session, code: str) -> tuple[list, dict]:
    """Fetch all pages of one indicator; returns (rows, meta). Retries."""
    all_rows: list = []
    page = 1
    meta: dict = {}
    while True:
        params = {"format": "json", "per_page": PER_PAGE,
                  "date": f"{YEAR_MIN}:{YEAR_MAX}", "page": page}
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = session.get(API.format(code=code), params=params, timeout=TIMEOUT_S)
                r.raise_for_status()
                j = r.json()
                if not isinstance(j, list) or len(j) < 2 or j[1] is None:
                    raise RuntimeError(f"unexpected API shape: {str(j)[:200]}")
                meta = j[0]
                all_rows.extend(j[1])
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
                log(f"    {code} page {page} attempt {attempt}/{MAX_RETRIES} "
                    f"failed ({type(e).__name__}: {str(e)[:90]}); retry in {wait:.0f}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"{code} page {page} failed after retries: {last_err}")
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    return all_rows, meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="Re-download indicators whose JSON already exists.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    manifest_rows: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for code, col in INDICATORS.items():
        dest = RAW_DIR / f"{code}.json"
        if dest.exists() and not args.force:
            existing = json.loads(dest.read_text())
            rows = existing.get("data", [])
            name = existing.get("indicator_name", "?")
            log(f"{code} ({col}): present ({len(rows)} rows); skipping.")
        else:
            log(f"Fetching {code} -> {col} ...")
            rows, meta = fetch_indicator(session, code)
            total = meta.get("total")
            if not total or len(rows) == 0:
                raise RuntimeError(
                    f"Indicator {code} returned no data (total={total}); the code "
                    "may be retired/renamed. Aborting (no silent empty layer)."
                )
            name = rows[0].get("indicator", {}).get("value", "?")
            dest.write_text(json.dumps(
                {"code": code, "column": col, "indicator_name": name,
                 "retrieved_utc": ts, "data": rows}))
            log(f"  wrote {dest.name} ({len(rows)} rows) -- {name[:60]}")
        manifest_rows.append(f"{code}\t{col}\t{len(rows)}\t{ts}\t{name}")

    header = "code\tcolumn\trows\tretrieved_utc\tindicator_name\n"
    (RAW_DIR / "MANIFEST.txt").write_text(header + "\n".join(manifest_rows) + "\n",
                                          encoding="utf-8")
    log("")
    log("=== WB WDI DOWNLOAD SUMMARY ===")
    log(f"  indicators: {len(INDICATORS)}")
    log(f"  raw dir:    {RAW_DIR}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
