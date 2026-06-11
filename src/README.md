# Pipeline conventions

Binding rules for every script in `src/`. The goal is that a third party can rebuild `data/processed/` from nothing but this repository and an internet connection.

## Ground truth

- Download URLs, license terms, and coverage facts come **only** from `docs/DATA_SOURCES.md`. If a URL there stops working, fix the registry first (with a note), then the script. Never introduce an undocumented endpoint.
- Credentials (ACLED, Copernicus) come only from `.env` (see `.env.example`); scripts must fail with a clear message when a required credential is absent, and must never print credential values.

## Acquisition scripts (`src/acquisition/`)

- One script per source, numbered in execution order; runnable as `.venv/bin/python src/acquisition/NN_name.py` with no arguments for the default build.
- Download to `data/raw/<source>/` only. Never transform, never overwrite an existing file silently (skip with a message if the target exists and matches the expected checksum; `--force` to re-download).
- After downloading, write/update `data/raw/<source>/MANIFEST.txt`: one line per file with URL, retrieval timestamp (UTC), byte size, and SHA-256.
- Verify what was downloaded: file size and, where the registry records one, the expected checksum/row count. A failed check is a hard error, not a warning.

## Cleaning scripts (`src/cleaning/`)

- One script per source: `data/raw/<source>/` → a single tidy table `data/interim/<name>.parquet` (geometry, if any, in `data/interim/<name>.gpkg`).
- Keys are explicit and consistent: `district_id` (spine shapeID), `iso3`, `year`. No implicit index joins.
- Every row-level filter (e.g. dropping low-precision geocodes) logs how many rows it removed and why; the thresholds are constants at the top of the script.
- Deterministic output: same inputs → byte-identical parquet (fixed sort order, no timestamps in data).

## Merge scripts (`src/merge/`)

- Join interim tables onto the spine × year frame; no source-specific cleaning here.
- Joins state their expected cardinality and assert it (`validate=` in pandas merges).
- Output: `data/processed/panel_district_year.parquet`, plus a validation report under `reports/`.

## Every script

- Header docstring: purpose, inputs, outputs, runtime, how to run.
- Loud failure: no bare `except`, no silent fallbacks; if data looks wrong, stop.
- Idempotent: safe to re-run; partial downloads are written to a temp name and renamed only on success.
- No notebook-only logic — notebooks are for inspection, never part of the build.
