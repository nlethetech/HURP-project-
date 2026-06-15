#!/usr/bin/env python3
"""Download ACLED event data (global, 1997-present) via the OAuth API.

Purpose
-------
Acquire the ACLED (Armed Conflict Location & Event Data) geolocated event
record -- the political-violence/unrest layer that EXTENDS UCDP GED with
non-lethal events: protests, riots, violence against civilians (incl. without
deaths), battles, explosions/remote violence and strategic developments. The
cleaning step spatially joins the points to the admin-2 spine and aggregates to
district-year-by-event-type (see docs/DATA_SOURCES.md, "ACLED").

Source / registry / auth (verified live 2026-06-15)
---------------------------------------------------
2025-relaunch OAuth2 password grant:
  POST https://acleddata.com/oauth/token
       username=<email> password=<pw> grant_type=password
       client_id=acled scope=authenticated
  -> JSON { access_token (24h), refresh_token (14d), expires_in, token_type }
Read:
  GET https://acleddata.com/api/acled/read?_format=json
      Authorization: Bearer <access_token>
      params: country|iso, event_date=A|B, event_date_where=BETWEEN,
              fields=a|b|c (pipe-delimited), limit=<page_size>, page=<1-based>
  -> JSON { success, data:[...], ... }; pagination is 1-based, pages disjoint;
     there is NO count endpoint (count/total_count are null) -- paginate until a
     short page. Coverage is region-staggered (1997 is Africa-only).

Credentials (via .env only; never committed)
--------------------------------------------
    ACLED_EMAIL, ACLED_PASSWORD   (see .env.example)

Inputs
------
None on the command line; credentials from .env.

Outputs
-------
    data/raw/acled/acled_<YEAR>.parquet     (one file per pulled year)
    data/raw/acled/.token.json              (cached OAuth token; gitignored)
    data/raw/acled/MANIFEST.txt             (per-year rows, pages, date span,
                                             access date, fields, filters)

License (registry): ACLED EULA -- raw data is NOT redistributable. data/raw is
gitignored, so the raw pull stays local; each user re-pulls with own creds.
Attribution must record the access date (recorded in MANIFEST).

Runtime
-------
Network-bound and large: a full global 1997-present pull is millions of events
(~hundreds of pages). Resumable -- a year whose parquet already exists is
skipped unless --force, so an interrupted run continues.

How to run
----------
    .venv/bin/python src/acquisition/10_download_acled.py            # all years
    .venv/bin/python src/acquisition/10_download_acled.py --year 1997
    .venv/bin/python src/acquisition/10_download_acled.py --from 2018 --to 2025
    .venv/bin/python src/acquisition/10_download_acled.py --force    # re-pull all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# --- Registry-pinned facts ---------------------------------------------------
SOURCE = "acled"
TOKEN_URL = "https://acleddata.com/oauth/token"
READ_URL = "https://acleddata.com/api/acled/read"
CLIENT_ID = "acled"
SCOPE = "authenticated"

# Earliest ACLED coverage (Africa); pull from here to the current year.
FIRST_YEAR = 1997
PAGE_SIZE = 5000          # rows per page (API default; max practical page)
TOKEN_MARGIN_S = 120      # refresh the cached token this long before expiry

# Only the columns the panel needs -- requesting a subset massively shrinks the
# payload vs. all 31 fields. (Actors/notes/source/tags/timestamp are dropped.)
FIELDS = [
    "event_id_cnty", "event_date", "year", "time_precision",
    "disorder_type", "event_type", "sub_event_type", "civilian_targeting",
    "iso", "country", "admin1", "admin2", "admin3",
    "latitude", "longitude", "geo_precision", "fatalities",
]

# Network retry policy.
MAX_RETRIES = 5
BACKOFF_BASE_S = 2.0
PAGE_PAUSE_S = 0.25       # politeness pause between pages

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE
TOKEN_CACHE = RAW_DIR / ".token.json"
ENV_PATH = REPO_ROOT / ".env"


def log(msg: str) -> None:
    print(msg, flush=True)


# --- OAuth -------------------------------------------------------------------
def _now() -> float:
    return time.time()


def fetch_new_token(email: str, password: str) -> dict:
    log("Requesting a fresh ACLED access token ...")
    resp = requests.post(
        TOKEN_URL,
        data={
            "username": email, "password": password,
            "grant_type": "password", "client_id": CLIENT_ID, "scope": SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"OAuth token request failed: HTTP {resp.status_code} "
            f"{resp.text[:300]!r}. Check ACLED_EMAIL/ACLED_PASSWORD in .env."
        )
    j = resp.json()
    if "access_token" not in j:
        raise RuntimeError(f"OAuth response missing access_token: {list(j)}")
    j["_obtained_at"] = _now()
    return j


def get_token(email: str, password: str) -> str:
    """Return a valid access token, using the on-disk cache when possible."""
    if TOKEN_CACHE.exists():
        try:
            cached = json.loads(TOKEN_CACHE.read_text())
            age = _now() - cached.get("_obtained_at", 0)
            if age < cached.get("expires_in", 0) - TOKEN_MARGIN_S:
                return cached["access_token"]
        except Exception:
            pass  # fall through to a fresh token
    tok = fetch_new_token(email, password)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(tok))
    return tok["access_token"]


# --- Read with retry ---------------------------------------------------------
def read_page(session: requests.Session, token: str, year: int, page: int,
              creds: tuple[str, str]) -> tuple[list[dict], str]:
    """Fetch one page; returns (rows, token). Re-auths once on 401."""
    params = {
        "_format": "json",
        "event_date": f"{year}-01-01|{year}-12-31",
        "event_date_where": "BETWEEN",
        "fields": "|".join(FIELDS),
        "limit": PAGE_SIZE,
        "page": page,
    }
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(
                READ_URL, params=params,
                headers={"Authorization": f"Bearer {token}"}, timeout=120,
            )
            if r.status_code == 401:
                # token expired/invalid mid-run: re-auth once and retry.
                log("  401 -> refreshing token")
                TOKEN_CACHE.unlink(missing_ok=True)
                token = get_token(*creds)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            j = r.json()
            # Raise on an explicit failure envelope REGARDLESS of a present
            # 'data' key: a {success:false, data:[]} body must not be mistaken
            # for "last page reached" (which would silently truncate the year).
            if j.get("success", True) is False:
                raise RuntimeError(
                    f"API success=false: {j.get('error') or j.get('messages')}")
            data = j.get("data", [])
            if not isinstance(data, list):
                raise RuntimeError(f"API 'data' is not a list: {type(data)}")
            return data, token
        except Exception as e:  # noqa: BLE001 -- retry any transient failure
            last_err = e
            wait = BACKOFF_BASE_S * (2 ** (attempt - 1))
            log(f"  page {page} attempt {attempt}/{MAX_RETRIES} failed "
                f"({type(e).__name__}: {str(e)[:120]}); retry in {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"Page {page} for {year} failed after {MAX_RETRIES} "
                       f"retries: {last_err}")


def pull_year(session: requests.Session, token: str, year: int,
              creds: tuple[str, str]) -> tuple[pd.DataFrame, str, int]:
    """Paginate a full year. Returns (df, token, n_pages)."""
    rows: list[dict] = []
    page = 1
    while True:
        data, token = read_page(session, token, year, page, creds)
        rows.extend(data)
        got = len(data)
        if page == 1 or page % 10 == 0 or got < PAGE_SIZE:
            log(f"  {year}: page {page} -> {got} rows (cumulative {len(rows):,})")
        if got < PAGE_SIZE:
            break
        page += 1
        time.sleep(PAGE_PAUSE_S)
    df = pd.DataFrame(rows)
    return df, token, page


def write_manifest(stats: list[dict]) -> None:
    """Rewrite MANIFEST.txt with one line per pulled year (sorted)."""
    header = ("year\trows\tpages\tmin_event_date\tmax_event_date\t"
              "retrieved_utc\tfields\tfilter\n")
    lines = [header]
    fields_str = "|".join(FIELDS)
    for s in sorted(stats, key=lambda x: x["year"]):
        lines.append(
            f"{s['year']}\t{s['rows']}\t{s['pages']}\t{s['min_date']}\t"
            f"{s['max_date']}\t{s['retrieved_utc']}\t{fields_str}\t"
            f"event_date BETWEEN {s['year']}-01-01|{s['year']}-12-31\n"
        )
    (RAW_DIR / "MANIFEST.txt").write_text("".join(lines), encoding="utf-8")


def load_existing_manifest() -> dict[int, dict]:
    path = RAW_DIR / "MANIFEST.txt"
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 6 and p[0].isdigit():
            out[int(p[0])] = {
                "year": int(p[0]), "rows": int(p[1]), "pages": int(p[2]),
                "min_date": p[3], "max_date": p[4], "retrieved_utc": p[5],
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="Pull a single year only.")
    parser.add_argument("--from", dest="year_from", type=int, default=FIRST_YEAR)
    parser.add_argument("--to", dest="year_to", type=int,
                        default=datetime.now(timezone.utc).year)
    parser.add_argument("--force", action="store_true",
                        help="Re-pull even years whose parquet already exists.")
    parser.add_argument(
        "--refresh-recent", type=int, default=2,
        help="Always re-pull the trailing N years. ACLED back-revises weekly "
        "and the Research tier lags ~12 months, so the most recent year(s) are "
        "partial/stale on first pull; default 2 re-pulls the current and prior "
        "year every run. Use 0 to disable (skip on existence like other years).")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    import os
    email = os.environ.get("ACLED_EMAIL")
    password = os.environ.get("ACLED_PASSWORD")
    if not email or not password:
        raise SystemExit(
            "ACLED_EMAIL / ACLED_PASSWORD not set. Copy .env.example to .env "
            "and fill in your myACLED login (see .env.example)."
        )
    creds = (email, password)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    years = ([args.year] if args.year
             else list(range(args.year_from, args.year_to + 1)))

    session = requests.Session()
    token = get_token(email, password)
    log(f"Authenticated. Pulling years {years[0]}-{years[-1]} "
        f"(page size {PAGE_SIZE}).")

    current_year = datetime.now(timezone.utc).year
    stale_cutoff = current_year - args.refresh_recent  # re-pull years >= cutoff
    stats = load_existing_manifest()
    for year in years:
        dest = RAW_DIR / f"acled_{year}.parquet"
        if dest.exists() and not args.force and year < stale_cutoff:
            log(f"{year}: already present ({dest.name}); skipping (settled year).")
            continue
        if dest.exists() and not args.force and year >= stale_cutoff:
            log(f"{year}: recent year (>= {stale_cutoff}) -- re-pulling to capture "
                "ACLED's rolling ~12-month lag and weekly back-revisions.")
        log(f"== Pulling {year} ==")
        df, token, pages = pull_year(session, token, year, creds)
        if df.empty:
            log(f"  {year}: 0 rows (no coverage this year); writing empty marker.")
            # still record an empty year so resume skips it
            df = pd.DataFrame(columns=FIELDS)
            min_d = max_d = ""
        else:
            min_d = str(df["event_date"].min())
            max_d = str(df["event_date"].max())
        df.to_parquet(dest, index=False)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stats[year] = {"year": year, "rows": len(df), "pages": pages,
                       "min_date": min_d, "max_date": max_d, "retrieved_utc": ts}
        write_manifest(list(stats.values()))
        log(f"  wrote {dest} ({len(df):,} rows, {pages} pages, {min_d}..{max_d})")

    total = sum(s["rows"] for s in stats.values())
    log("")
    log("=== ACLED DOWNLOAD SUMMARY ===")
    log(f"  years on disk: {sorted(stats)}")
    log(f"  total rows:    {total:,}")
    log(f"  latest event:  {max((s['max_date'] for s in stats.values()), default='')}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
