# Dataset Plan

Design document for the project's analysis dataset. Read this first; `DATA_SOURCES.md` holds the per-source details and `CODEBOOK.md` the final variable definitions.

## Research target

A **global subnational panel** linking conflict / political violence to agricultural output, supporting comparisons across development levels (low- and middle-income vs high-income countries).

## Panel design

- **Unit of analysis**: admin-2 district × calendar year.
- **Spine**: geoBoundaries **CGAZ v6.0.0** admin-2 polygons, frozen for the life of the project. Chosen over GADM 4.1 because geoBoundaries is openly licensed (redistributable, so the spine itself can live in this repo), while GADM blocks redistribution. All other layers are aggregated onto this spine — point events by spatial join, rasters by zonal statistics.
- **Time window**: **1989–2025**, set by UCDP GED (the only global geocoded conflict series). Layers that start later or end earlier are carried with documented gaps rather than trimming the panel.
- **Country layer**: World Bank historical income classification (OGHIST, FY89–FY26) joined onto each district-year, so the analysis can split LEDC/MEDC (income groups) without rebuilding the panel.

## Data layers

| Layer | Source (verified window) | Form |
|-------|--------------------------|------|
| Conflict events | UCDP GED 26.1 (1989–2025, CC BY); ACLED (region-staggered: Africa 1997, most of Asia 2010s, global by 2018+; no redistribution) | Geocoded points → district-year counts, fatalities, by event type |
| Agricultural output (annual) | GDHY v1.2/1.3 gridded yields (1981–2016); PKU GIMMS NDVI (1982–2022) + MODIS MOD13Q1 (2000–), cropland-masked growing-season | District-year zonal means |
| Crop mix (baseline weights) | SPAM snapshots 2000 / 2005 / 2010 / 2020 (CC BY) | Per-crop harvested area → district crop shares |
| Country ag backbone | FAOSTAT QCL (1961–2024) + Producer Prices (1991–) | Country-year production, prices |
| Price shocks | World Bank Pink Sheet (monthly, 1960–) and IMF PCPS (1992–) × SPAM crop mix | Shift-share district-year producer-price shock |
| Weather | CHIRPS v2.0 rainfall (1981–, 50°S–50°N); ERA5/ERA5-Land temperature (1940/1950–, global, fills high latitudes); SPEIbase drought | District-year zonal stats |
| Controls | HYDE 3.3/3.4 + WorldPop/GPWv4 population; harmonized DMSP–VIIRS nightlights (1992–2024) | District-year zonal stats |
| Classification | World Bank OGHIST income groups (FY89–FY26) | Country-year join |

Rationale: no harmonized *official* district-level crop statistics exist globally, so agricultural output enters through (a) gridded yield/greenness products and (b) price × crop-mix shocks — both standard in this literature (e.g. McGuirk & Burke 2020; Ubilava, Hastings & Atalay 2023). Full per-source detail — exact download URLs, licenses, citations, aggregation pitfalls — is in `DATA_SOURCES.md`.

## Pipeline

```
src/acquisition/  one script per source; downloads to data/raw/<source>/ ; never transforms
src/cleaning/     one script per source; raw → tidy district-year (or district) table in data/interim/
src/merge/        joins interim tables onto the spine → data/processed/panel_district_year.parquet
```

Rules:

1. Scripts are numbered in execution order and runnable end-to-end with no manual steps (credentials via `.env` only).
2. Each raw download records its retrieval date and version/checksum in `data/raw/<source>/MANIFEST.txt` (written by the acquisition script).
3. Zonal statistics always use the same frozen boundary file and record the aggregation method (mean/sum, cropland-masked or not) in the codebook entry.
4. Sources whose licenses forbid redistribution are **never committed**; the acquisition script plus `DATA_SOURCES.md` entry must be sufficient for a third party to re-obtain the identical file.

## Validation (notebooks/)

- Cross-check district aggregates against published country totals (e.g. national production, national conflict death tolls).
- Coverage heatmaps: which districts/years are missing per layer.
- Sanity replication: reproduce one known stylized fact from the literature before trusting the merge.

## License constraints shaping the repo

- **Redistributable** (may be committed or mirrored if ever needed): UCDP GED (CC BY 4.0), SPAM (CC BY 4.0 per Dataverse), geoBoundaries, World Bank/IMF series, CHIRPS, SPEIbase, harmonized nightlights, HYDE/WorldPop.
- **Not redistributable** (acquisition script + registry entry only; data never committed): ACLED (registered access, ToU forbid redistribution), GADM (not used for this reason), ERA5 (Copernicus license requires registration; derived district aggregates are fine).

## Status

All 13 sources researched, fact-checked against live provider pages (2026-06-11), and registered in `DATA_SOURCES.md`. Next: acquisition scripts in dependency order — spine first (geoBoundaries CGAZ), then UCDP GED, then rasters.
