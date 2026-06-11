#!/usr/bin/env python3
"""Download the FAOSTAT QCL "All Data Normalized" bulk zip (crop/livestock production).

Purpose
-------
Acquire the FAOSTAT "Production: Crops and livestock products" (domain QCL)
bulk download in "All Data Normalized" (long) format. QCL is the national
(admin-0) agricultural backbone for the panel: country-year Production and
Area harvested by CPC item, 1961-2024 (see docs/DATA_SOURCES.md, "FAOSTAT —
Production: Crops and livestock products (QCL)").

Source / registry
-----------------
FAO Statistics Division (ESS), bulk server (anonymous, no auth, no JWT). The
registry-pinned URL is the normalized all-data zip:
    https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip
The companion XML manifest (datasets_E.xml) advertises this FileLocation with
FileSize 33127KB and DateUpdate 2025-12-31 for domain QCL; the live zip returns
HTTP 200 with content-length ~33.9 MB and Last-Modified 2025-12-31. The file is
an unversioned in-place snapshot (the whole back-series is revised each ~December
release), so the manifest records the retrieval timestamp and SHA-256 to pin
exactly which snapshot was used.

Encoding guidance (registry gotcha #8): the current QCL bulk CSVs are UTF-8
("Cote d'Ivoire", "Mate leaves" etc. as UTF-8 bytes); the cleaning step reads
them as utf-8-sig. This acquisition step only stores the raw zip verbatim and
does not decode it.

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/faostat_qcl/Production_Crops_Livestock_E_All_Data_(Normalized).zip
    data/raw/faostat_qcl/MANIFEST.txt   (URL, UTC timestamp, bytes, SHA-256)

Runtime
-------
Network-bound; ~10-40 s for the ~34 MB download on a typical connection.

How to run
----------
    .venv/bin/python src/acquisition/04_download_faostat_qcl.py
    .venv/bin/python src/acquisition/04_download_faostat_qcl.py --force   # re-download

Idempotent: if the target file already exists and is non-empty (>= floor), the
download is skipped (use --force to re-fetch). Partial downloads are written to
a temp name and renamed only on success.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Registry-pinned facts (docs/DATA_SOURCES.md) ----------------------------
SOURCE = "faostat_qcl"
DOWNLOAD_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
FILENAME = "Production_Crops_Livestock_E_All_Data_(Normalized).zip"

# Registry records ~33,127 KB (~33.9 MB live). A truncated/HTML-error body will
# be far smaller; fail loudly if the download is below this conservative floor.
MIN_EXPECTED_BYTES = 25_000_000

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
        ctype = resp.headers.get("content-type", "")
        if "zip" not in ctype and "octet-stream" not in ctype:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Unexpected content-type '{ctype}' for {url}; expected a zip. "
                "Endpoint may have returned an error page; aborting."
            )
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
