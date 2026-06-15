#!/usr/bin/env python3
"""Download the Powell & Thyne country-year coup d'état dataset.

Purpose
-------
Acquire the Powell & Thyne "Global Instances of Coups" country-year file, the
political-instability layer that complements UCDP GED with counts of coup
d'état attempts (successful vs failed) per country-year (see
docs/DATA_SOURCES.md, "Powell & Thyne -- Global Instances of Coups").

Source / registry
-----------------
Jonathan M. Powell & Clayton L. Thyne. Country-year text file served from
Thyne's UKy directory:
    https://www.uky.edu/~clthyn2/coup_data/powell_thyne_ccode_year.txt
Tab-separated, header row, quoted string fields. Living dataset (updated as
coups occur); the snapshot carries a `version` string (e.g. V2026.01.13).
License: academic-use, cite-required (no open CC grant) -- mirror via this
script, do not commit the raw file.

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/coups_powell_thyne/powell_thyne_ccode_year.txt
    data/raw/coups_powell_thyne/MANIFEST.txt  (URL, UTC timestamp, bytes,
                                                SHA-256, dataset version)

Runtime
-------
Network-bound; a second or two for the ~700 KiB text file.

How to run
----------
    .venv/bin/python src/acquisition/09_download_coups_pt.py
    .venv/bin/python src/acquisition/09_download_coups_pt.py --force

Idempotent: if the target file already exists and is non-empty, the download is
skipped (use --force to re-fetch). Partial downloads go to a temp name and are
renamed only on success. The download is validated as the expected TSV (header
columns present, a plausible row count, parseable `version` cell) before commit.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "coups_powell_thyne"
DOWNLOAD_URL = "https://www.uky.edu/~clthyn2/coup_data/powell_thyne_ccode_year.txt"
FILENAME = "powell_thyne_ccode_year.txt"

# The country-year file is ~700 KiB / ~12k rows. Use a conservative floor so a
# truncated body or an HTML error page (tiny, or lacking the header) is caught.
MIN_EXPECTED_BYTES = 200_000
MIN_EXPECTED_ROWS = 10_000
# Header columns that must all be present (tab-separated, first line).
EXPECTED_COLUMNS = [
    "ccode", "abbrev", "country", "year", "ccode_gw", "ccode_polity",
    "coup1", "coup2", "coup3", "coup4",
    "date1", "date2", "date3", "date4", "version",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_version(path: Path) -> str:
    """Return the dataset `version` string from the last column of the data.

    The `version` cell is constant down the file (e.g. "V2026.01.13"); read the
    first data row's last field. Raises if the file layout is unexpected.
    """
    with path.open("r", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        if header != EXPECTED_COLUMNS:
            raise RuntimeError(
                f"Unexpected header columns in {path.name}:\n  got {header}\n"
                f"  expected {EXPECTED_COLUMNS}\nSource layout may have changed."
            )
        first = fh.readline().rstrip("\n").split("\t")
    if len(first) != len(EXPECTED_COLUMNS):
        raise RuntimeError(
            f"First data row has {len(first)} fields, expected "
            f"{len(EXPECTED_COLUMNS)}; aborting."
        )
    return first[-1].strip().strip('"')


def validate_tsv(path: Path) -> tuple[int, str]:
    """Fail loudly unless `path` is the expected coup TSV. Returns (rows, version)."""
    with path.open("r", encoding="utf-8") as fh:
        lines = sum(1 for _ in fh)
    data_rows = lines - 1  # minus header
    if data_rows < MIN_EXPECTED_ROWS:
        raise RuntimeError(
            f"Only {data_rows} data rows (< {MIN_EXPECTED_ROWS} floor); the "
            "endpoint may have returned an error page or truncated body; aborting."
        )
    version = parse_version(path)
    if not version:
        raise RuntimeError("Could not read a dataset `version` cell; aborting.")
    return data_rows, version


def download(url: str, dest: Path) -> int:
    """Stream `url` to `dest` via a temp file, renamed only on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    print(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=120, allow_redirects=True) as resp:
        resp.raise_for_status()
        written = 0
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
        print(f"Wrote {written:,} bytes to temp file")
    if written < MIN_EXPECTED_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download too small ({written:,} bytes < {MIN_EXPECTED_BYTES:,} floor); "
            "aborting."
        )
    validate_tsv(tmp)
    tmp.replace(dest)
    return written


def write_manifest(file_path: Path, url: str, version: str,
                   manifest_path: Path) -> tuple[int, str]:
    size = file_path.stat().st_size
    digest = sha256_of(file_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = "filename\turl\tretrieved_utc\tbytes\tsha256\tdataset_version\n"
    line = f"{file_path.name}\t{url}\t{ts}\t{size}\t{digest}\t{version}\n"
    manifest_path.write_text(header + line, encoding="utf-8")
    return size, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if the target file already exists.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / FILENAME
    manifest = RAW_DIR / "MANIFEST.txt"

    if dest.exists() and dest.stat().st_size >= MIN_EXPECTED_BYTES and not args.force:
        print(f"Already present: {dest} ({dest.stat().st_size:,} bytes); skipping.")
        print("Pass --force to re-download.")
    else:
        download(DOWNLOAD_URL, dest)

    rows, version = validate_tsv(dest)
    size, digest = write_manifest(dest, DOWNLOAD_URL, version, manifest)
    print(f"File:    {dest}")
    print(f"Rows:    {rows:,}")
    print(f"Version: {version}")
    print(f"Bytes:   {size:,}")
    print(f"SHA256:  {digest}")
    print(f"Manifest: {manifest}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
