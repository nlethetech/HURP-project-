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
│   ├── merge/            # Scripts that join interim files into the global panel
│   └── subset/           # Study subset: region filter + colonial/pest enrichment + validator
├── reference/            # Committed small crosswalks (SPAM↔Pink Sheet, iso3↔region)
├── notebooks/            # Exploratory analysis and validation checks (not part of the pipeline)
└── requirements.txt      # Pinned Python dependencies
```

Pipeline convention: `data/raw` → (`src/cleaning`) → `data/interim` → (`src/merge`) → `data/processed` → (`src/subset`) → study panel. Scripts are numbered in execution order within each folder (e.g. `01_download_acled.py`).

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
   .venv/bin/python src/acquisition/09_download_coups_pt.py      # Powell & Thyne coups (v0.2)
   .venv/bin/python src/acquisition/10_download_acled.py         # ACLED events (v0.2; needs ACLED_EMAIL/ACLED_PASSWORD in .env)
   .venv/bin/python src/acquisition/11_download_wb_wdi.py        # World Bank WDI covariates (v0.2)
   .venv/bin/python src/acquisition/12_download_colonial.py      # COLDAT + QoG jan22 + COW states (study colonial layer)
   .venv/bin/python src/acquisition/13_download_faw.py           # FAO FAMEWS fall-armyworm traps (study pest layer, Africa)
   .venv/bin/python src/acquisition/14_download_locust.py        # FAO Locust Hub swarms + bands (study pest layer, Africa)
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
   .venv/bin/python src/cleaning/09_coups_pt.py         # -> coups_pt.parquet (v0.2)
   .venv/bin/python src/cleaning/10_acled.py            # -> acled_district_year.parquet (+ acled_coverage) (v0.2)
   .venv/bin/python src/cleaning/11_wb_wdi.py           # -> wb_wdi.parquet (v0.2)
   .venv/bin/python src/cleaning/12_colonial.py         # -> colonial.parquet (study colonial layer)
   .venv/bin/python src/cleaning/13_faw.py              # -> faw_district_year.parquet (study pest, Africa)
   .venv/bin/python src/cleaning/14_locust.py           # -> locust_district_year.parquet (study pest, Africa)
   ```

   **Merge** (`src/merge/`, joins the interim tables onto the spine × year frame):
   ```
   .venv/bin/python src/merge/01_build_panel.py         # -> data/processed/panel_district_year.parquet (+ reports/panel_build_report.txt)
   ```

   The merge step also reads the committed crosswalk `reference/spam_pinksheet_crosswalk.csv` (SPAM crop → Pink Sheet commodity).

   **Study subset / enrich** (`src/subset/`, the Africa + South America + Caribbean
   conflict×agriculture study — filter the global panel, add the colonial moderator
   layer and the Africa-only pest shocks):
   ```
   .venv/bin/python src/subset/01_region_filter.py      # -> panel_africa_samerica_caribbean.parquet (+ reference/iso3_region_crosswalk.csv)
   .venv/bin/python src/subset/02_enrich_study.py       # -> panel_africa_samerica_caribbean_enriched.parquet (93 cols)
   .venv/bin/python src/subset/03_validate_enriched.py  # 34 automated checks; exits nonzero on any failure
   ```
   Study panel: **79 countries (Africa + South America + Caribbean), 583,490 rows,
   93 columns** — the global panel plus the colonial legacy layer (all 79) and the
   Africa-only fall-armyworm + desert-locust shocks. See `docs/CODEBOOK.md`
   ("Study subset", "Colonial legacy layer", "Pest layer — Africa").

The final panel is one row per admin-2 district × year: **49,329 districts × 37 years (1989–2025) = 1,825,173 rows, 61 columns** (35 core + 26 v0.2 enrichment: coups, ACLED political violence/unrest, and World Bank socioeconomic & agricultural covariates). Variable definitions are in `docs/CODEBOOK.md`.

Raw and processed data are **not** committed to the repository (size and license restrictions); `docs/DATA_SOURCES.md` records exactly where and how each raw file was obtained so the inputs can be re-downloaded.

## The panel at a glance

`data/processed/panel_district_year.parquet` — one row per admin-2 district x calendar year:

- **49,329 districts** (geoBoundaries CGAZ v6.0.0; 198 countries) x **37 years** (1989-2025) = **1,825,173 rows**, 61 columns, exactly one row per `(district_id, year)`.
- Deterministic build: re-running the pipeline reproduces the file byte-for-byte.
- Conflict columns are zero-filled (UCDP GED is globally complete for fatal organized violence, so absence = a true zero). All other gaps are honest `NaN` with the reason documented per column in `docs/CODEBOOK.md`.

### Core columns (v0.1, 35)

| # | Column | Type | Unit | Non-null | Description |
|---|--------|------|------|----------|-------------|
| 1 | `district_id` | text | - | 1,825,173 (100%) | Admin-2 district identifier (geoBoundaries CGAZ shapeID); cross-sectional key |
| 2 | `iso3` | text | - | 1,825,173 (100%) | ISO 3166-1 alpha-3 country code of the district |
| 3 | `district_name` | text | - | 1,825,173 (100%) | District name as published by geoBoundaries (descriptive only) |
| 4 | `admin_level` | text | - | 1,825,173 (100%) | Administrative level of the spine unit (ADM2; ADM1/ADM0 where no ADM2 exists) |
| 5 | `year` | int | - | 1,825,173 (100%) | Calendar year, 1989-2025; the panel time index |
| 6 | `n_events_sb` | int | count | 1,825,173 (100%) | Fatal state-based conflict events (UCDP type 1) |
| 7 | `n_events_ns` | int | count | 1,825,173 (100%) | Fatal non-state conflict events (UCDP type 2) |
| 8 | `n_events_os` | int | count | 1,825,173 (100%) | Fatal one-sided violence events (UCDP type 3) |
| 9 | `n_events_total` | int | count | 1,825,173 (100%) | All fatal organized-violence events (sb+ns+os) |
| 10 | `deaths_best_sb` | int | count | 1,825,173 (100%) | Best-estimate deaths, state-based |
| 11 | `deaths_best_ns` | int | count | 1,825,173 (100%) | Best-estimate deaths, non-state |
| 12 | `deaths_best_os` | int | count | 1,825,173 (100%) | Best-estimate deaths, one-sided |
| 13 | `deaths_best_total` | int | count | 1,825,173 (100%) | Best-estimate deaths, all types |
| 14 | `deaths_low_sb` | int | count | 1,825,173 (100%) | Lower-bound deaths, state-based |
| 15 | `deaths_low_ns` | int | count | 1,825,173 (100%) | Lower-bound deaths, non-state |
| 16 | `deaths_low_os` | int | count | 1,825,173 (100%) | Lower-bound deaths, one-sided |
| 17 | `deaths_low_total` | int | count | 1,825,173 (100%) | Lower-bound deaths, all types |
| 18 | `deaths_high_sb` | int | count | 1,825,173 (100%) | Upper-bound deaths, state-based |
| 19 | `deaths_high_ns` | int | count | 1,825,173 (100%) | Upper-bound deaths, non-state |
| 20 | `deaths_high_os` | int | count | 1,825,173 (100%) | Upper-bound deaths, one-sided |
| 21 | `deaths_high_total` | int | count | 1,825,173 (100%) | Upper-bound deaths, all types |
| 22 | `deaths_civilians_sb` | int | count | 1,825,173 (100%) | Civilian deaths, state-based |
| 23 | `deaths_civilians_ns` | int | count | 1,825,173 (100%) | Civilian deaths, non-state |
| 24 | `deaths_civilians_os` | int | count | 1,825,173 (100%) | Civilian deaths, one-sided |
| 25 | `deaths_civilians_total` | int | count | 1,825,173 (100%) | Civilian deaths, all types |
| 26 | `precip_mm` | float | mm/yr | 1,587,484 (87.0%) | Annual precipitation, area-weighted district mean (CHIRPS v2.0) |
| 27 | `yield_maize` | float | t/ha | 751,744 (41.2%) | Maize yield, district zonal mean (GDHY) |
| 28 | `yield_rice` | float | t/ha | 532,261 (29.2%) | Rice yield, district zonal mean (GDHY) |
| 29 | `yield_wheat` | float | t/ha | 623,343 (34.2%) | Wheat yield, district zonal mean (GDHY) |
| 30 | `yield_soybean` | float | t/ha | 280,354 (15.4%) | Soybean yield, district zonal mean (GDHY) |
| 31 | `income_group` | text | - | 1,825,099 (100.0%) | World Bank income classification of the country (L/LM/UM/H; NA = unclassified) |
| 32 | `income_group_carried` | bool | - | 1,825,173 (100%) | True where income_group is carried forward past the last OGHIST data year |
| 33 | `cropland_ha` | float | ha | 1,511,820 (82.8%) | District total harvested area, all 46 SPAM crops (time-invariant) |
| 34 | `price_shock_coverage` | float | 0-1 | 1,511,820 (82.8%) | Share of district cropland in crops mapped to a world price series (time-invariant) |
| 35 | `price_shock` | float | dlog | 1,511,820 (82.8%) | Shift-share producer-price shock: sum of crop shares x dlog real world price |

### Enrichment columns (v0.2, +26): political violence & socioeconomic drivers

Added to explain conflict and agricultural output with a richer set of drivers. Coups and World Bank covariates are national series broadcast onto every district by `iso3 + year`; ACLED is geocoded and spatially joined like UCDP.

**Coups — Powell & Thyne (national, zero-filled):**

| Column | Type | Non-null | Description |
|--------|------|----------|-------------|
| `coups_total` / `_successful` / `_failed` | int | 1,825,173 (100%) | Coup d'état attempts per country-year (successful = 2, failed = 1) |

**ACLED political violence & unrest (geocoded → district-year; coverage-masked):** captures **non-lethal** events UCDP omits — protests, riots, violence against civilians without deaths. `NaN` = outside ACLED's staggered country coverage (Africa 1997 → USA 2020); `0` = covered but no event. Non-null 510,836 (28.0%) each.

| Column | Description |
|--------|-------------|
| `acled_events_total` | All ACLED events in the district-year |
| `acled_events_battles` / `_protests` / `_riots` / `_vac` / `_explosions` / `_strategic` | Counts by ACLED event type (vac = violence against civilians) |
| `acled_fatalities` | ACLED fatality estimate (sum) |

**World Bank WDI socioeconomic & agricultural covariates (national; CC BY 4.0):** continuous measures, `NaN` = no WB observation (not zero).

| Column | Unit | Non-null | Column | Unit | Non-null |
|--------|------|----------|--------|------|----------|
| `wb_unemployment` | % | 93.2% | `wb_pop_0_14` | % | 96.6% |
| `wb_unemployment_youth` | % | 93.2% | `wb_urban_pct` | % | 96.6% |
| `wb_gdp_pc` | US$ | 95.2% | `wb_ag_valueadd_pct` | % GDP | 89.4% |
| `wb_gdp_growth` | % | 94.7% | `wb_ag_employment_pct` | % | 93.2% |
| `wb_inflation` | % | 90.0% | `wb_ag_land_pct` | % | 92.3% |
| `wb_population` | persons | 96.6% | `wb_cereal_yield` | kg/ha | 91.9% |
| `wb_pop_growth` | % | 96.6% | `wb_food_prod_index` | index | 89.4% |
| | | | `wb_arable_land_pct` | % | 92.2% |

Full definitions, units, sources, and construction notes (filters, fills, crosswalk, coverage mask) for every column are in [`docs/CODEBOOK.md`](docs/CODEBOOK.md).

### What the rows look like

Maiduguri, Nigeria (Borno State, the Boko Haram epicenter) across selected years - the insurgency's 2009 outbreak and 2014-15 peak emerge directly from the spatial join of UCDP events, with Sahel rainfall, maize yields, income reclassification, and world-price shocks alongside (selected columns; the file has all 35):

| district_id | iso3 | district_name | year | n_events_total | deaths_best_total | deaths_civilians_total | precip_mm | yield_maize | income_group | cropland_ha | price_shock_coverage | price_shock |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 59680162B20780696540875 | NGA | Maiduguri | 1995 | 0 | 0 | 0 | 605.3 | 0.47 | L | 8,980 | 0.495 | 0.016 |
| 59680162B20780696540875 | NGA | Maiduguri | 2005 | 0 | 0 | 0 | 571.5 | 0.82 | L | 8,980 | 0.495 | -0.042 |
| 59680162B20780696540875 | NGA | Maiduguri | 2009 | 5 | 293 | 0 | 512.8 | 0.7 | LM | 8,980 | 0.495 | -0.101 |
| 59680162B20780696540875 | NGA | Maiduguri | 2014 | 13 | 918 | 198 | 459.6 | 0.51 | LM | 8,980 | 0.495 | -0.085 |
| 59680162B20780696540875 | NGA | Maiduguri | 2015 | 43 | 1220 | 638 | 615.6 | 0.77 | LM | 8,980 | 0.495 | 0.016 |
| 59680162B20780696540875 | NGA | Maiduguri | 2020 | 5 | 27 | 27 | 699.7 |  | LM | 8,980 | 0.495 | 0.055 |
| 59680162B20780696540875 | NGA | Maiduguri | 2024 | 0 | 0 | 0 | 860.0 |  | LM | 8,980 | 0.495 | -0.03 |

The same district-years through the **v0.2 enrichment** columns — ACLED's wider unrest (blank before Nigeria's 1997 ACLED coverage start; note violence-against-civilians tracking the Boko Haram atrocities), and the World Bank socioeconomic drivers (unemployment climbing into 2020, inflation spiking in 2024):

| district_id | iso3 | district_name | year | acled_events_total | acled_protests | acled_riots | acled_vac | coups_total | wb_unemployment | wb_gdp_pc | wb_inflation |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 59680162B20780696540875 | NGA | Maiduguri | 1995 |  |  |  |  | 0 | 4.2 | 1395 | 72.8 |
| 59680162B20780696540875 | NGA | Maiduguri | 2005 | 1 | 0 | 0 | 0 | 0 | 3.7 | 1889 | 17.9 |
| 59680162B20780696540875 | NGA | Maiduguri | 2009 | 14 | 1 | 1 | 4 | 0 | 3.8 | 2205 | 12.5 |
| 59680162B20780696540875 | NGA | Maiduguri | 2014 | 30 | 4 | 3 | 5 | 0 | 3.9 | 2584 | 8.0 |
| 59680162B20780696540875 | NGA | Maiduguri | 2015 | 51 | 2 | 2 | 6 | 0 | 4.1 | 2586 | 9.0 |
| 59680162B20780696540875 | NGA | Maiduguri | 2020 | 41 | 3 | 0 | 12 | 0 | 5.7 | 2229 | 13.2 |
| 59680162B20780696540875 | NGA | Maiduguri | 2024 | 28 | 9 | 5 | 4 | 0 | 3.0 | 2325 | 33.2 |

(`acled_*` blanks before 1997 = outside ACLED's coverage window, *not* zero — see the codebook. The file has all **61** columns.)

Aggregation: country-level series are obtained by grouping on `iso3 x year` (sums for counts/areas, cropland-weighted means for yields, rainfall and the price shock; national `wb_*`/income/coup series taken once per country-year); `data/interim/faostat_qcl.parquet` additionally provides the official country-year production backbone, 1961-2024. A ready-to-run analysis notebook is in [`notebooks/hurp_analysis_colab.ipynb`](notebooks/hurp_analysis_colab.ipynb), and shareable CSV exports (Colab-friendly) are in [`data/published/`](data/published/).

### Validation

`reports/validation_report.md` records 32 automated checks, all passing - structural integrity, exact reconciliation against every interim layer, and external cross-checks against published figures (UCDP global fatality totals, FAO 2020 production, climate references, World Bank income-group counts), each cited by URL. `src/merge/02_validate_panel.py` re-runs them and exits nonzero on any failure.

## Documentation rules

- Every new data source gets an entry in `docs/DATA_SOURCES.md` **before** its acquisition script is merged.
- Every variable that reaches `data/processed/` gets an entry in `docs/CODEBOOK.md`.
- Every script starts with a docstring stating purpose, inputs, outputs, and how to run it.

## Status

Panel built: `data/processed/panel_district_year.parquet` (1,825,173 district-years, 1989–2025) is reproducible end-to-end from the acquisition → cleaning → merge scripts above. See `docs/CODEBOOK.md` for variable definitions and `reports/panel_build_report.txt` for the build's validation summary.
