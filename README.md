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
4. Run the acquisition scripts in `src/acquisition/` in numbered order, then cleaning, then merge. Each script documents its inputs and outputs in its header docstring.

Raw and processed data are **not** committed to the repository (size and license restrictions); `docs/DATA_SOURCES.md` records exactly where and how each raw file was obtained so the inputs can be re-downloaded.

## Documentation rules

- Every new data source gets an entry in `docs/DATA_SOURCES.md` **before** its acquisition script is merged.
- Every variable that reaches `data/processed/` gets an entry in `docs/CODEBOOK.md`.
- Every script starts with a docstring stating purpose, inputs, outputs, and how to run it.

## Status

Project scaffold — data sources under selection.
