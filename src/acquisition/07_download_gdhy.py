#!/usr/bin/env python3
"""Download the GDHY global gridded historical crop-yield dataset (v1.2+v1.3).

Purpose
-------
Acquire the Global Dataset of Historical Yields (GDHY), v1.2 + v1.3 aligned
version, as a single anonymous ZIP from PANGAEA's store host (see
docs/DATA_SOURCES.md, "GDHY"). The ZIP contains per-crop / per-season folders,
each holding 36 annual 0.5-degree NetCDF4/HDF5 rasters named yield_YYYY.nc4
giving crop yield in t/ha for 1981-2016 (soybean: 1981-2016; the second-season
folders begin a year later in source).

The cleaning step (src/cleaning/07_ag_yields_gdhy.py) aggregates these grids to
the admin-2 spine. This script only fetches and extracts the raw archive.

Source / registry
-----------------
Single direct ZIP, no API / no auth, CC-BY-4.0:
    https://store.pangaea.de/Publications/IizumiT_2019/gdhy_v1.2_v1.3_20190128.zip
Registry-recorded facts: ~15.2 MB (15,989,683 bytes), application/zip,
last-modified 2020-01-28. Landing page DOI: 10.1594/PANGAEA.909132.

The archive holds 10 folders:
    maize_major, maize_second, rice_major, rice_second, wheat_winter,
    wheat_spring, soybean, plus bare-crop convenience folders maize, rice, wheat
    (which mirror each crop's primary season).
Each folder holds annual files yield_YYYY.nc4.

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/gdhy/gdhy_v1.2_v1.3_20190128.zip   (the raw archive)
    data/raw/gdhy/extracted/<crop_folder>/yield_YYYY.nc4   (unzipped contents)
    data/raw/gdhy/MANIFEST.txt
        One line per file (the ZIP and every extracted .nc4) with URL,
        retrieval timestamp (UTC), byte size, and SHA-256.

Runtime
-------
Network-bound; the ZIP is ~15 MB so typically well under a minute, plus a few
seconds to extract ~400 small NetCDF files.

How to run
----------
    .venv/bin/python src/acquisition/07_download_gdhy.py
    .venv/bin/python src/acquisition/07_download_gdhy.py --force   # re-download

Idempotent: if the ZIP already exists and matches the expected byte size the
download is skipped (use --force to re-fetch). The ZIP is streamed to a temp
name and renamed only on success; extraction is rewritten in full each run.
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
SOURCE = "gdhy"
DOWNLOAD_URL = (
    "https://store.pangaea.de/Publications/IizumiT_2019/"
    "gdhy_v1.2_v1.3_20190128.zip"
)
ZIP_FILENAME = "gdhy_v1.2_v1.3_20190128.zip"

# Registry records exactly 15,989,683 bytes. Treat a >1% deviation as suspect
# (a truncated download or an error page); the floor catches HTML error bodies.
EXPECTED_ZIP_BYTES = 15_989_683
MIN_EXPECTED_BYTES = 10_000_000

# Crop folders expected inside the archive (registry "Access method").
EXPECTED_CROP_FOLDERS = {
    "maize",
    "maize_major",
    "maize_second",
    "rice",
    "rice_major",
    "rice_second",
    "wheat",
    "wheat_winter",
    "wheat_spring",
    "soybean",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / SOURCE
EXTRACT_DIR = RAW_DIR / "extracted"


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> int:
    """Stream `url` to `dest` via a temp file, renamed only on success."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    log(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=300, allow_redirects=True) as resp:
        resp.raise_for_status()
        written = 0
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
    log(f"Wrote {written:,} bytes to temp file")
    if written < MIN_EXPECTED_BYTES:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download too small ({written:,} bytes < {MIN_EXPECTED_BYTES:,} floor). "
            "Endpoint may have returned an error page or a truncated body; aborting."
        )
    tmp.replace(dest)
    return written


def extract_zip(zip_path: Path, out_dir: Path) -> list[Path]:
    """Extract the archive into `out_dir`, returning the extracted .nc4 paths.

    Extraction is rewritten in full each run for determinism. Guards against
    path traversal (no member may resolve outside out_dir).
    """
    if out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        out_root = out_dir.resolve()
        for member in zf.infolist():
            if member.is_dir():
                continue
            target = (out_dir / member.filename).resolve()
            if out_root not in target.parents and target != out_root:
                raise RuntimeError(
                    f"Refusing to extract member outside target dir: {member.filename}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                dst.write(src.read())
            if target.suffix == ".nc4":
                extracted.append(target)
    return extracted


def write_manifest(
    manifest_path: Path, url: str, zip_path: Path, nc_files: list[Path]
) -> None:
    """One line per file (ZIP + each .nc4) with url, UTC ts, bytes, sha256."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = "relpath\turl\tretrieved_utc\tbytes\tsha256\n"
    lines = [header]

    # The archive itself.
    lines.append(
        f"{zip_path.name}\t{url}\t{ts}\t{zip_path.stat().st_size}\t{sha256_of(zip_path)}\n"
    )

    # Each extracted NetCDF (relative path under data/raw/gdhy, sorted).
    for nc in sorted(nc_files):
        rel = nc.relative_to(RAW_DIR).as_posix()
        size = nc.stat().st_size
        digest = sha256_of(nc)
        # Extracted-from-archive members share the archive URL provenance.
        lines.append(f"{rel}\t{url}\t{ts}\t{size}\t{digest}\n")

    manifest_path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the target ZIP already exists.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / ZIP_FILENAME
    manifest = RAW_DIR / "MANIFEST.txt"

    if (
        zip_path.exists()
        and zip_path.stat().st_size >= MIN_EXPECTED_BYTES
        and not args.force
    ):
        log(f"Already present: {zip_path} ({zip_path.stat().st_size:,} bytes); skipping.")
        log("Pass --force to re-download.")
    else:
        written = download(DOWNLOAD_URL, zip_path)
        if written != EXPECTED_ZIP_BYTES:
            log(
                f"  NOTE: downloaded {written:,} bytes; registry records "
                f"{EXPECTED_ZIP_BYTES:,}. Proceeding (size within floor) but verify."
            )

    if not zipfile.is_zipfile(zip_path):
        raise RuntimeError(f"{zip_path} is not a valid ZIP archive; aborting.")

    log("Extracting archive ...")
    nc_files = extract_zip(zip_path, EXTRACT_DIR)
    log(f"  extracted {len(nc_files):,} NetCDF (.nc4) files")

    # --- Structural verification (loud failure) ------------------------------
    found_folders = {
        p.name for p in EXTRACT_DIR.iterdir() if p.is_dir()
    } | {
        # archive may nest under a top folder; gather all dirs holding .nc4
        nc.parent.name
        for nc in nc_files
    }
    crop_dirs = {nc.parent.name for nc in nc_files}
    missing = EXPECTED_CROP_FOLDERS - crop_dirs
    if missing:
        raise RuntimeError(
            f"Expected crop folders missing from archive: {sorted(missing)}. "
            f"Found crop folders: {sorted(crop_dirs)}"
        )
    unexpected = crop_dirs - EXPECTED_CROP_FOLDERS
    if unexpected:
        log(f"  NOTE: archive contains extra crop folders: {sorted(unexpected)}")

    if not nc_files:
        raise RuntimeError("No .nc4 files extracted; archive layout unexpected.")

    log("Writing manifest with SHA-256 for ZIP + every .nc4 ...")
    write_manifest(manifest, DOWNLOAD_URL, zip_path, nc_files)

    # --- Summary -------------------------------------------------------------
    log("")
    log("=== GDHY ACQUISITION SUMMARY ===")
    log(f"  ZIP:        {zip_path} ({zip_path.stat().st_size:,} bytes)")
    log(f"  .nc4 files: {len(nc_files):,}")
    log(f"  crop folders ({len(crop_dirs)}): {sorted(crop_dirs)}")
    for folder in sorted(crop_dirs):
        files = sorted(
            nc.name for nc in nc_files if nc.parent.name == folder
        )
        years = sorted(
            int(f.replace("yield_", "").replace(".nc4", ""))
            for f in files
            if f.startswith("yield_")
        )
        if years:
            log(f"      {folder:14s}: {len(years)} files, {years[0]}-{years[-1]}")
        else:
            log(f"      {folder:14s}: {len(files)} files (non-yield_YYYY names)")
    log(f"  Manifest:   {manifest}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
