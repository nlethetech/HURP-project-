#!/usr/bin/env python3
"""Download the UCDP Georeferenced Event Dataset (GED) global v26.1 CSV zip.

Purpose
-------
Acquire the UCDP GED 26.1 global bulk CSV archive, which is the source of the
conflict / political-violence layer (see docs/DATA_SOURCES.md, "UCDP
Georeferenced Event Dataset"). Each row is one fatal organized-violence event
with point coordinates, a year, a violence type, and best/low/high death
estimates; the cleaning step joins these points to the admin-2 spine.

Source / registry
-----------------
UCDP GED Global version 26.1 (CC BY 4.0, no registration). The registry-pinned
bulk URL is the zipped CSV composite:
    https://ucdp.uu.se/downloads/ged/ged261-csv.zip
The registry records exact sizes that are verified here as hard checks:
    * zip:  39,122,522 bytes
    * inner CSV GEDEvent_v26_1.csv: 273,992,720 bytes, 417,968 events, 49 cols
The REST API now requires an `x-ucdp-access-token` header; the no-auth versioned
zip is used instead (registry gotcha 4).

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/ucdp_ged/ged261-csv.zip
    data/raw/ucdp_ged/MANIFEST.txt   (URL, UTC timestamp, bytes, SHA-256)

Runtime
-------
Network-bound; ~1-2 minutes on a typical connection for the ~37 MiB download.

How to run
----------
    .venv/bin/python src/acquisition/02_download_ucdp_ged.py
    .venv/bin/python src/acquisition/02_download_ucdp_ged.py --force   # re-download

Idempotent: if the target file already exists and matches the registry byte
size exactly, the download is skipped (use --force to re-fetch). Partial
downloads are written to a temp name and renamed only on success.
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
SOURCE = "ucdp_ged"
DOWNLOAD_URL = "https://ucdp.uu.se/downloads/ged/ged261-csv.zip"
FILENAME = "ged261-csv.zip"

# Exact sizes recorded in the registry; these are HARD checks, not floors.
EXPECTED_ZIP_BYTES = 39_122_522
INNER_CSV_NAME = "GEDEvent_v26_1.csv"
EXPECTED_CSV_BYTES = 273_992_720

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    """Stream `url` to `dest` via a temp file, renamed only on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    print(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=600, allow_redirects=True) as resp:
        resp.raise_for_status()
        written = 0
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
        print(f"Wrote {written:,} bytes to temp file")
    if written != EXPECTED_ZIP_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded zip is {written:,} bytes, expected exactly "
            f"{EXPECTED_ZIP_BYTES:,} (registry). Endpoint may have returned an "
            "error page, a truncated body, or a different version; aborting."
        )
    tmp.replace(dest)


def verify_zip_contents(zip_path: Path) -> None:
    """Open the zip and assert the inner CSV name and byte size match registry."""
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if INNER_CSV_NAME not in names:
            raise RuntimeError(
                f"Inner CSV '{INNER_CSV_NAME}' not found in zip; members: {names}"
            )
        info = zf.getinfo(INNER_CSV_NAME)
        if info.file_size != EXPECTED_CSV_BYTES:
            raise RuntimeError(
                f"Inner CSV '{INNER_CSV_NAME}' is {info.file_size:,} bytes, "
                f"expected {EXPECTED_CSV_BYTES:,} (registry); aborting."
            )
    print(
        f"Verified inner CSV '{INNER_CSV_NAME}': "
        f"{EXPECTED_CSV_BYTES:,} bytes (matches registry)"
    )


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

    if dest.exists() and dest.stat().st_size == EXPECTED_ZIP_BYTES and not args.force:
        print(f"Already present: {dest} ({dest.stat().st_size:,} bytes); skipping.")
        print("Pass --force to re-download.")
    else:
        download(DOWNLOAD_URL, dest)

    # Hard size check on the final file (covers the skip path too).
    size = dest.stat().st_size
    if size != EXPECTED_ZIP_BYTES:
        raise RuntimeError(
            f"Final zip is {size:,} bytes, expected exactly {EXPECTED_ZIP_BYTES:,} "
            "(registry); aborting."
        )

    verify_zip_contents(dest)

    size, digest = write_manifest(dest, DOWNLOAD_URL, manifest)
    print(f"File:   {dest}")
    print(f"Bytes:  {size:,}")
    print(f"SHA256: {digest}")
    print(f"Manifest: {manifest}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
