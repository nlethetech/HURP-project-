# HURP Data Analytics

Data collection and dataset construction for a research project on **conflict / political violence and agricultural output**.

This repository contains all code used to acquire, clean, and merge the raw sources into the final analysis dataset. Every step is scripted so the dataset can be rebuilt from scratch by anyone, end to end.

## Repository layout

```
HURP_Data_analytics/
├── data/
│   ├── raw/         # Immutable source downloads. Never edited by hand. (gitignored)
│   ├── interim/     # Intermediate cleaned files, one per source. (gitignored)
│   └── processed/   # Final merged analysis dataset(s). (gitignored)
├── docs/
│   ├── DATA_SOURCES.md   # Every source: provider, URL, license, access date, citation
│   └── CODEBOOK.md       # Every variable in the final dataset: name, definition, unit, source
├── src/
│   ├── acquisition/      # Scripts that download / scrape each raw source
│   ├── cleaning/         # Scripts that turn each raw source into a tidy interim file
│   └── merge/            # Scripts that join interim files into the final panel
├── notebooks/            # Exploratory analysis and validation checks (not part of the pipeline)
└── requirements.txt      # Pinned Python dependencies
```

Pipeline convention: `data/raw` → (`src/cleaning`) → `data/interim` → (`src/merge`) → `data/processed`. Scripts are numbered in execution order within each folder (e.g. `01_download_acled.py`).

## Reproducing the dataset

1. Clone the repository.
2. Create the environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Add any required API credentials to a local `.env` file (see `.env.example`; never commit credentials).
4. Run the scripts in the order below with the project interpreter (`.venv/bin/python`). Each script documents its inputs, outputs and runtime in its header docstring, takes no arguments for the default build, and is idempotent.

   **Acquisition** (`src/acquisition/`, downloads raw sources to `data/raw/<source>/`):
   ```
   .venv/bin/python src/acquisition/01_download_boundaries.py    # geoBoundaries CGAZ v6.0.0 admin-2 spine
   .venv/bin/python src/acquisition/02_download_ucdp_ged.py      # UCDP GED 26.1 conflict events
   .venv/bin/python src/acquisition/03_download_wb_income.py     # World Bank OGHIST income history
   .venv/bin/python src/acquisition/04_download_faostat_qcl.py   # FAOSTAT QCL production
   .venv/bin/python src/acquisition/05_download_pink_sheet.py    # World Bank Pink Sheet commodity prices
   .venv/bin/python src/acquisition/06_download_spam.py          # SPAM 2020 v2.0 R2 crop mix
   .venv/bin/python src/acquisition/07_download_gdhy.py          # GDHY v1.2/1.3 gridded yields
   .venv/bin/python src/acquisition/08_download_chirps.py        # CHIRPS v2.0 monthly precipitation
   ```

   **Cleaning** (`src/cleaning/`, one tidy table per source in `data/interim/`):
   ```
   .venv/bin/python src/cleaning/01_spine.py            # -> spine.parquet (+ spine.gpkg)
   .venv/bin/python src/cleaning/02_conflict_ged.py     # -> conflict_ged.parquet (+ _long)
   .venv/bin/python src/cleaning/03_income_class.py     # -> income_class.parquet
   .venv/bin/python src/cleaning/04_faostat_qcl.py      # -> faostat_qcl.parquet
   .venv/bin/python src/cleaning/05_prices_pinksheet.py # -> prices_pinksheet.parquet
   .venv/bin/python src/cleaning/06_cropmix_spam.py     # -> cropmix_spam2020.parquet
   .venv/bin/python src/cleaning/07_ag_yields_gdhy.py   # -> ag_yields_gdhy.parquet
   .venv/bin/python src/cleaning/08_weather_chirps.py   # -> weather_chirps.parquet
   ```

   **Merge** (`src/merge/`, joins the interim tables onto the spine × year frame):
   ```
   .venv/bin/python src/merge/01_build_panel.py         # -> data/processed/panel_district_year.parquet (+ reports/panel_build_report.txt)
   ```

   The merge step also reads the committed crosswalk `reference/spam_pinksheet_crosswalk.csv` (SPAM crop → Pink Sheet commodity).

The final panel is one row per admin-2 district × year: **49,329 districts × 37 years (1989–2025) = 1,825,173 rows, 35 columns**. Variable definitions are in `docs/CODEBOOK.md`.

Raw and processed data are **not** committed to the repository (size and license restrictions); `docs/DATA_SOURCES.md` records exactly where and how each raw file was obtained so the inputs can be re-downloaded.

## Documentation rules

- Every new data source gets an entry in `docs/DATA_SOURCES.md` **before** its acquisition script is merged.
- Every variable that reaches `data/processed/` gets an entry in `docs/CODEBOOK.md`.
- Every script starts with a docstring stating purpose, inputs, outputs, and how to run it.

## Status

Panel built: `data/processed/panel_district_year.parquet` (1,825,173 district-years, 1989–2025) is reproducible end-to-end from the acquisition → cleaning → merge scripts above. See `docs/CODEBOOK.md` for variable definitions and `reports/panel_build_report.txt` for the build's validation summary.
