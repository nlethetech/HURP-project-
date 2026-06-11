#!/usr/bin/env python3
"""Download the World Bank OGHIST historical income-classification workbook.

Purpose
-------
Acquire the World Bank "Country Analytical History" (OGHIST) workbook, the only
official historical source for the country x fiscal-year income classification
matrix (FY89..FY26). The cleaning step parses it into a tidy country-year table
(see docs/DATA_SOURCES.md, "World Bank Historical Country Income
Classifications (OGHIST)").

Source / registry
-----------------
World Bank, Development Data Group (Data Help Desk article 906519; WDI catalog
dataset 0037712). Canonical historical XLSX served by the WB DDH open API:
    https://ddh-openapi.worldbank.org/resources/DR0095334/download
The endpoint serves an .xlsx (file OGHIST_2026_03_10.xlsx; resource last updated
2026-03-10) under content-type application/octet-stream. License: CC BY 4.0.

Registry-discrepancy note
-------------------------
A HEAD request to this endpoint returns HTTP 404 (the WB DDH gateway does not
support HEAD on the download route), but a GET returns HTTP 200 with the valid
XLSX body. This script therefore probes with GET only; do not "fix" the URL on
the basis of a failing HEAD. The legacy databankfiles OGHIST.xls mirror is STALE
(frozen at FY23) per the registry and is deliberately not used.

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/wb_income_oghist/OGHIST.xlsx
    data/raw/wb_income_oghist/MANIFEST.txt   (URL, UTC timestamp, bytes, SHA-256)

Runtime
-------
Network-bound; a few seconds for the ~115 KiB workbook.

How to run
----------
    .venv/bin/python src/acquisition/03_download_wb_income.py
    .venv/bin/python src/acquisition/03_download_wb_income.py --force   # re-download

Idempotent: if the target file already exists and is non-empty, the download is
skipped (use --force to re-fetch). Partial downloads are written to a temp name
and renamed only on success. The download is validated as a real XLSX (ZIP magic
"PK") and the expected sheet "Country Analytical History" must be present.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "wb_income_oghist"
DOWNLOAD_URL = "https://ddh-openapi.worldbank.org/resources/DR0095334/download"
FILENAME = "OGHIST.xlsx"

# The historical workbook is small (~115 KiB). Use a conservative floor so a
# truncated body or an HTML error page (which would be tiny, or would lack the
# ZIP magic / the expected sheet) is caught loudly.
MIN_EXPECTED_BYTES = 50_000
EXPECTED_SHEET = "Country Analytical History"

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_xlsx(path: Path) -> None:
    """Fail loudly unless `path` is a real XLSX containing the expected sheet."""
    if not zipfile.is_zipfile(path):
        raise RuntimeError(
            f"Downloaded file is not a ZIP/XLSX container: {path}. "
            "The endpoint may have returned an error page; aborting."
        )
    # An XLSX is an OPC ZIP; the worksheet names live in xl/workbook.xml. Rather
    # than parse OPC, confirm the sheet name string is present in workbook.xml.
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        if "xl/workbook.xml" not in names:
            raise RuntimeError(
                f"Downloaded XLSX missing xl/workbook.xml: {path}; aborting."
            )
        workbook_xml = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
    if EXPECTED_SHEET not in workbook_xml:
        raise RuntimeError(
            f"Expected sheet {EXPECTED_SHEET!r} not found in workbook; "
            "the source layout may have changed. Aborting."
        )


def download(url: str, dest: Path) -> int:
    """Stream `url` to `dest` via a temp file, renamed only on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    print(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=300, allow_redirects=True) as resp:
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
            f"Download too small ({written:,} bytes < {MIN_EXPECTED_BYTES:,} floor). "
            "Endpoint may have returned an error page or a truncated body; aborting."
        )
    validate_xlsx(tmp)
    tmp.replace(dest)
    return written


def write_manifest(file_path: Path, url: str, manifest_path: Path) -> tuple[int, str]:
    size = file_path.stat().st_size
    digest = sha256_of(file_path)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{file_path.name}\t{url}\t{ts}\t{size}\t{digest}\n"
    header = "filename\turl\tretrieved_utc\tbytes\tsha256\n"
    manifest_path.write_text(header + line, encoding="utf-8")
    return size, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the target file already exists.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / FILENAME
    manifest = RAW_DIR / "MANIFEST.txt"

    if dest.exists() and dest.stat().st_size >= MIN_EXPECTED_BYTES and not args.force:
        print(f"Already present: {dest} ({dest.stat().st_size:,} bytes); skipping.")
        print("Pass --force to re-download.")
        # Still re-validate the existing file so a corrupted cache is caught.
        validate_xlsx(dest)
    else:
        download(DOWNLOAD_URL, dest)

    size, digest = write_manifest(dest, DOWNLOAD_URL, manifest)
    print(f"File:   {dest}")
    print(f"Bytes:  {size:,}")
    print(f"SHA256: {digest}")
    print(f"Manifest: {manifest}")

    if size < MIN_EXPECTED_BYTES:
        raise RuntimeError(
            f"Final file smaller than floor ({size:,} < {MIN_EXPECTED_BYTES:,}); aborting."
        )
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
