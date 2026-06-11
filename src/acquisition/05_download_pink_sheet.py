#!/usr/bin/env python3
"""Download the World Bank "Pink Sheet" (CMO) historical commodity-price workbooks.

Purpose
-------
Acquire the two World Bank Commodity Markets (Pink Sheet) historical-data
workbooks - the ANNUAL file (1960-2025, nominal and real prices) and the
MONTHLY file (1960M01-2026M05, nominal prices) - which supply the global
commodity-price "shift" used to build a district-year shift-share producer
price-shock index (see docs/DATA_SOURCES.md, "World Bank Pink Sheet").

Source / registry
-----------------
World Bank Prospects Group, "World Bank Commodity Price Data (The Pink Sheet)",
CC BY 4.0. The registry-pinned URLs embed a vintage segment ("0050012026"):

    Annual:  https://thedocs.worldbank.org/en/doc/
             74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/
             CMO-Historical-Data-Annual.xlsx
    Monthly: .../CMO-Historical-Data-Monthly.xlsx

The registry warns these vintage-stamped URLs break roughly annually (the
landing page must then be re-scraped and the registry corrected). Both URLs
resolved HTTP 200 with an XLSX content-type on the verification date; if a
download falls below the size floor below, the script fails loudly rather than
writing a stub.

Inputs
------
None (anonymous HTTPS GET; no credentials, no registration).

Outputs
-------
    data/raw/pink_sheet/CMO-Historical-Data-Annual.xlsx
    data/raw/pink_sheet/CMO-Historical-Data-Monthly.xlsx
    data/raw/pink_sheet/MANIFEST.txt   (per file: URL, UTC timestamp, bytes, SHA-256)

Runtime
-------
Network-bound; a few seconds (annual ~3 MiB, monthly ~0.6 MiB).

How to run
----------
    .venv/bin/python src/acquisition/05_download_pink_sheet.py
    .venv/bin/python src/acquisition/05_download_pink_sheet.py --force   # re-download

Idempotent: if a target file already exists and clears its size floor, the
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
SOURCE = "pink_sheet"
BASE = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
)

# (filename, url, size floor in bytes). The floors are deliberately well below
# the verified sizes (annual ~3.18 MB, monthly ~0.59 MB) so a truncated body or
# an HTML error page fails loudly, while a modestly-revised next vintage passes.
FILES = (
    ("CMO-Historical-Data-Annual.xlsx", BASE + "CMO-Historical-Data-Annual.xlsx", 1_000_000),
    ("CMO-Historical-Data-Monthly.xlsx", BASE + "CMO-Historical-Data-Monthly.xlsx", 200_000),
)

# XLSX files begin with the ZIP local-file-header magic "PK\x03\x04".
XLSX_MAGIC = b"PK\x03\x04"

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


def download(url: str, dest: Path, min_bytes: int) -> None:
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
    log(f"  wrote {written:,} bytes to temp file")

    if written < min_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download too small ({written:,} bytes < {min_bytes:,} floor) for {url}. "
            "Endpoint may have returned an error page or a truncated body; aborting."
        )
    with tmp.open("rb") as fh:
        head = fh.read(len(XLSX_MAGIC))
    if head != XLSX_MAGIC:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded body for {url} is not an XLSX (bad magic {head!r}); "
            "the endpoint may have moved or returned HTML. Aborting."
        )
    tmp.replace(dest)


def write_manifest(records: list[tuple[Path, str]], manifest_path: Path) -> None:
    header = "filename\turl\tretrieved_utc\tbytes\tsha256\n"
    lines = [header]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for path, url in records:
        size = path.stat().st_size
        digest = sha256_of(path)
        lines.append(f"{path.name}\t{url}\t{ts}\t{size}\t{digest}\n")
        log(f"  {path.name}: {size:,} bytes  sha256={digest}")
    manifest_path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the target files already exist.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    records: list[tuple[Path, str]] = []

    for filename, url, min_bytes in FILES:
        dest = RAW_DIR / filename
        if dest.exists() and dest.stat().st_size >= min_bytes and not args.force:
            log(f"Already present: {dest} ({dest.stat().st_size:,} bytes); skipping.")
            log("  Pass --force to re-download.")
        else:
            download(url, dest, min_bytes)
        # Post-download invariant.
        if dest.stat().st_size < min_bytes:
            raise RuntimeError(
                f"Final file smaller than floor ({dest.stat().st_size:,} < "
                f"{min_bytes:,}) for {dest}; aborting."
            )
        records.append((dest, url))

    manifest = RAW_DIR / "MANIFEST.txt"
    log("Writing manifest")
    write_manifest(records, manifest)
    log(f"Manifest: {manifest}")
    log("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
