#!/usr/bin/env python3
"""Download CHIRPS v2.0 global ANNUAL precipitation GeoTIFFs (0.05 deg).

Purpose
-------
Acquire the pre-made CHIRPS v2.0 global ANNUAL rainfall rasters (one GeoTIFF
per calendar year, 0.05 degree, quasi-global 50S-50N) that feed the
precipitation covariate layer of the district-year panel (see
docs/DATA_SOURCES.md, "CHIRPS ... v2.0"). The cleaning step
(src/cleaning/08_weather_chirps.py) computes area-weighted district means from
these files.

Source / registry
-----------------
Climate Hazards Center, UC Santa Barbara. Annual products directory:
    https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs/
Filenames follow chirps-v2.0.YYYY.tif. The registry documents that files in
this product may be served as .tif or .tif.gz; this script probes both and
handles either (gzip members are decompressed on download). As verified on
2026-06-11 the annual directory serves only uncompressed .tif (no .tif.gz),
and the latest available year is 2024 (chirps-v2.0.2025.tif returns HTTP 404),
consistent with the registry gotcha that the pre-made annual tifs lag.

License: public domain (CC0-style). No auth, no registration.

Inputs
------
None (anonymous HTTPS GET).

Arguments
---------
    --start YEAR   First year to download (default 1989). The full CHIRPS v2.0
                   annual archive begins in 1981; pass --start 1981 for the
                   complete series.
    --end   YEAR   Last year to attempt (default 2025). Years for which no file
                   exists on the server (e.g. 2025 as of 2026-06-11) are
                   reported and skipped, not treated as an error.
    --force        Re-download even if a target file already exists and is the
                   expected size.

Outputs
-------
    data/raw/chirps/chirps-v2.0.YYYY.tif          (one per available year)
    data/raw/chirps/MANIFEST.txt                  (URL, UTC ts, bytes, SHA-256)

Each annual GeoTIFF is ~55 MiB; the default 1989-2024 span is ~36 files
(~2 GB). Files are written to a temp name and renamed only on success, so
re-runs are safe and partial downloads never masquerade as complete.

Runtime
-------
Network-bound; minutes to tens of minutes for the full span on a typical
connection. Already-present files of the expected size are skipped.

How to run
----------
    .venv/bin/python src/acquisition/08_download_chirps.py
    .venv/bin/python src/acquisition/08_download_chirps.py --start 1981
    .venv/bin/python src/acquisition/08_download_chirps.py --force
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "chirps"
BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_annual/tifs"
FILENAME_TMPL = "chirps-v2.0.{year}.tif"  # uncompressed target name on disk

# Default download window. The CHIRPS v2.0 annual archive runs 1981-present;
# the panel default starts at 1989 (matching the conflict layer's start).
DEFAULT_START = 1989
DEFAULT_END = 2025  # attempt through 2025; missing years are skipped, not fatal.
ARCHIVE_MIN_YEAR = 1981  # earliest year present in the annual product.

# Sanity floor for each annual GeoTIFF. The registry records ~55 MiB; the 7200x
# 2000 float32 raster is ~57.6 MB. A truncated or HTML-error body is far
# smaller; fail loudly if a downloaded file falls under this floor.
MIN_EXPECTED_BYTES = 40_000_000

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_exists(url: str) -> bool:
    """Return True if the URL resolves to a 200 (HEAD), else False."""
    resp = requests.head(url, timeout=120, allow_redirects=True)
    return resp.status_code == 200


def resolve_year_url(year: int) -> str | None:
    """Find the download URL for a given year, trying .tif then .tif.gz.

    Returns the resolved URL, or None if neither variant exists on the server.
    """
    tif_url = f"{BASE_URL}/chirps-v2.0.{year}.tif"
    gz_url = f"{BASE_URL}/chirps-v2.0.{year}.tif.gz"
    if remote_exists(tif_url):
        return tif_url
    if remote_exists(gz_url):
        return gz_url
    return None


def download_year(url: str, dest: Path) -> int:
    """Stream `url` to `dest`, decompressing on the fly if it is gzip.

    Writes to a temp file and renames only on success. Returns bytes written
    (the decompressed GeoTIFF size on disk). Raises on a too-small result.
    """
    is_gzip = url.endswith(".gz")
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    log(f"  downloading {url}")
    with requests.get(url, stream=True, timeout=600, allow_redirects=True) as resp:
        resp.raise_for_status()
        if is_gzip:
            # Decompress the gzip stream into the (uncompressed) .tif on disk.
            resp.raw.decode_content = True
            with gzip.GzipFile(fileobj=resp.raw) as gz, tmp.open("wb") as out:
                shutil.copyfileobj(gz, out, length=1024 * 1024)
        else:
            with tmp.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)

    written = tmp.stat().st_size
    if written < MIN_EXPECTED_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded file too small ({written:,} bytes < "
            f"{MIN_EXPECTED_BYTES:,} floor) for {url}; endpoint may have "
            "returned an error page or a truncated body. Aborting."
        )
    tmp.replace(dest)
    log(f"  wrote {written:,} bytes -> {dest.name}")
    return written


def write_manifest(records: list[tuple[str, str, str, int, str]], manifest_path: Path) -> None:
    """records: (filename, url, retrieved_utc, bytes, sha256), sorted by filename."""
    header = "filename\turl\tretrieved_utc\tbytes\tsha256\n"
    lines = [
        f"{name}\t{url}\t{ts}\t{size}\t{digest}\n"
        for (name, url, ts, size, digest) in sorted(records)
    ]
    manifest_path.write_text(header + "".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--start",
        type=int,
        default=DEFAULT_START,
        help=f"First year to download (default {DEFAULT_START}; archive begins {ARCHIVE_MIN_YEAR}).",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=DEFAULT_END,
        help=f"Last year to attempt (default {DEFAULT_END}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a target file of the expected size exists.",
    )
    args = parser.parse_args()

    if args.start < ARCHIVE_MIN_YEAR:
        raise ValueError(
            f"--start {args.start} precedes the CHIRPS v2.0 annual archive "
            f"start ({ARCHIVE_MIN_YEAR}); nothing to download before then."
        )
    if args.end < args.start:
        raise ValueError(f"--end {args.end} precedes --start {args.start}.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = RAW_DIR / "MANIFEST.txt"

    years = range(args.start, args.end + 1)
    log(f"CHIRPS v2.0 global annual download: years {args.start}-{args.end}")
    log(f"Target dir: {RAW_DIR}")

    records: list[tuple[str, str, str, int, str]] = []
    skipped_missing: list[int] = []
    downloaded = 0
    present = 0

    for year in years:
        dest = RAW_DIR / FILENAME_TMPL.format(year=year)

        if dest.exists() and dest.stat().st_size >= MIN_EXPECTED_BYTES and not args.force:
            log(f"[{year}] present ({dest.stat().st_size:,} bytes); skipping download.")
            url = f"{BASE_URL}/chirps-v2.0.{year}.tif"
            present += 1
        else:
            url = resolve_year_url(year)
            if url is None:
                log(
                    f"[{year}] NOT AVAILABLE on server (.tif and .tif.gz both 404); "
                    "skipping. This is expected for years the annual product has "
                    "not yet published (e.g. 2025 as of 2026-06-11)."
                )
                skipped_missing.append(year)
                continue
            download_year(url, dest)
            downloaded += 1

        size = dest.stat().st_size
        digest = sha256_of(dest)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append((dest.name, url, ts, size, digest))

    if not records:
        raise RuntimeError(
            "No CHIRPS annual files downloaded or present; cannot continue. "
            "Check connectivity and the registry URL."
        )

    write_manifest(records, manifest)

    log("")
    log("=== CHIRPS DOWNLOAD SUMMARY ===")
    log(f"  years requested:     {args.start}-{args.end}")
    log(f"  files downloaded:    {downloaded}")
    log(f"  files already present:{present}")
    log(f"  files on disk total: {len(records)}")
    if skipped_missing:
        log(f"  years not yet published (skipped): {skipped_missing}")
    log(f"  manifest: {manifest}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
