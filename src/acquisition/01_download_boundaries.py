#!/usr/bin/env python3
"""Download the geoBoundaries CGAZ ADM2 global composite (admin-2 spine source).

Purpose
-------
Acquire the geoBoundaries Comprehensive Global Administrative Zones (CGAZ)
ADM2 global composite, which is the source geometry for the admin-2 panel
spine (see docs/DATA_SOURCES.md, "Admin-2 boundary spine"). CGAZ is a single
global file in which countries that lack ADM2 units are represented by their
ADM1 or ADM0 units; the cleaning step records the level actually used per row.

Source / registry
-----------------
geoBoundaries CGAZ v6.0.0 "Modeg" (gbOpen, CC BY 4.0). The documented bulk URL
is the zipped shapefile composite:
    https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM2.zip
This /raw/main/ path is served through Git-LFS and 302-redirects to
media.githubusercontent.com; curl/requests follow the redirect transparently.
The zipped shapefile (~149 MiB) is the smallest official format that preserves
all features (the .gpkg is ~230 MiB and the .geojson ~525 MiB at the same path).

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/geoboundaries_cgaz/geoBoundariesCGAZ_ADM2.zip
    data/raw/geoboundaries_cgaz/MANIFEST.txt   (URL, UTC timestamp, bytes, SHA-256)

Runtime
-------
Network-bound; ~1-3 minutes on a typical connection for the ~149 MiB download.

How to run
----------
    .venv/bin/python src/acquisition/01_download_boundaries.py
    .venv/bin/python src/acquisition/01_download_boundaries.py --force   # re-download

Idempotent: if the target file already exists and is non-empty, the download is
skipped (use --force to re-fetch). Partial downloads are written to a temp name
and renamed only on success.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "geoboundaries_cgaz"
DOWNLOAD_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/main/"
    "releaseData/CGAZ/geoBoundariesCGAZ_ADM2.zip"
)
FILENAME = "geoBoundariesCGAZ_ADM2.zip"

# Sanity floor for the download: the registry records ~149 MiB for this zip.
# A truncated/HTML-error body will be far smaller; fail loudly if so.
MIN_EXPECTED_BYTES = 100_000_000

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
    tmp.replace(dest)


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
