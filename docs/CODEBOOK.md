# Codebook

Definition of every variable in `data/processed/panel_district_year.parquet`,
the district-year analysis panel built by `src/merge/01_build_panel.py`.

- **Unit of analysis**: admin-2 district × calendar year.
- **Shape**: 49,329 districts × 37 years (1989–2025) = **1,825,173 rows**, 35
  columns. Exactly one row per `(district_id, year)` (asserted at build time).
- **Spine**: geoBoundaries CGAZ v6.0.0 admin-2 polygons (time-invariant
  geometry; `district_id` = the spine shapeID).
- **Time window**: 1989–2025, set by UCDP GED coverage. Layers that start later
  or end earlier are carried with documented gaps (NaN), never trimmed.
- **Source registry**: every "Source" name below is the dataset entry in
  `docs/DATA_SOURCES.md`, where its provider, exact download URL, license,
  citation and access date live.

A column is "not filled" when its NaN is meaningful (genuine absence of an
observation) and "zero-filled" only where an absent record provably means zero
(see UCDP GED below).

---

## Keys and identity

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `district_id` | Admin-2 district identifier (geoBoundaries CGAZ shapeID). | id (string) | geoBoundaries CGAZ v6.0.0 | Cross-sectional key; time-invariant. Cross-product with `year` forms the frame. No nulls. |
| `iso3` | ISO 3166-1 alpha-3 country code of the district. | code (string) | geoBoundaries CGAZ v6.0.0 | Carried from the spine (the country the polygon belongs to), not from any event source, so it is consistent with `district_id`. No nulls. |
| `district_name` | District name as published by geoBoundaries. | text | geoBoundaries CGAZ v6.0.0 | Descriptive only; not a join key (names are not standardized across sources). |
| `admin_level` | Administrative level of the unit. | text | geoBoundaries CGAZ v6.0.0 | Constant `ADM2` for the current spine. |
| `year` | Calendar year. | year (int) | (frame) | 1989–2025 inclusive; the panel time index. No nulls. |

## Conflict — UCDP GED 26.1 (zero-filled)

All conflict columns are integer counts. They come from the wide GED layer
(`data/interim/conflict_ged.parquet`), left-joined on `(district_id, year)` and
then **zero-filled**. Zero-fill rationale: UCDP GED is globally complete for
fatal organized violence over its entire 1989–2025 window, so a district-year
absent from GED records *zero* fatal organized-violence events, not a missing
observation. The cleaning step (`src/cleaning/02_conflict_ged.py`) keeps only
events with **`where_prec ≤ 3`** (geo-precision 1 = exact, 2 = within 25 km, 3 =
ADM2 representative point; 85% of events); events located only to ADM1, country
or fuzzy/sea-air representative points (`where_prec` 4–7) are dropped before the
spatial join so a naive polygon join cannot fabricate concentration in centroid
districts. Suffixes: `sb` = state-based, `ns` = non-state, `os` = one-sided
(UCDP `type_of_violence` 1/2/3); `total` = `sb + ns + os` (holds row-wise).

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `n_events_sb` / `_ns` / `_os` / `_total` | Count of fatal organized-violence events in the district-year, by violence type and total. | count | UCDP GED 26.1 | Spatial join of event points (`where_prec ≤ 3`) to the spine, summed per district-year-type. Absent ⇒ 0. |
| `deaths_best_sb` / `_ns` / `_os` / `_total` | UCDP "best" fatality estimate, summed. | deaths | UCDP GED 26.1 | Best point estimate; multi-location reports are split with deaths divided evenly upstream by UCDP. Absent ⇒ 0. |
| `deaths_low_sb` / `_ns` / `_os` / `_total` | UCDP "low" (lower-bound) fatality estimate, summed. | deaths | UCDP GED 26.1 | Lower bound of the fatality range. Absent ⇒ 0. |
| `deaths_high_sb` / `_ns` / `_os` / `_total` | UCDP "high" (upper-bound) fatality estimate, summed. | deaths | UCDP GED 26.1 | Upper bound of the fatality range. Absent ⇒ 0. |
| `deaths_civilians_sb` / `_ns` / `_os` / `_total` | Civilian deaths, summed. | deaths | UCDP GED 26.1 | Civilian share of `deaths_best`. Absent ⇒ 0. |

## Weather — CHIRPS v2.0 (not filled)

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `precip_mm` | Annual total precipitation, area-weighted zonal mean over the district. | mm/year | CHIRPS v2.0 | Left-joined on `(district_id, year)`; **not filled**. NaN where CHIRPS does not cover the district (its 50°S–50°N band excludes high-latitude units) and for **2025** (the interim CHIRPS series ends at 2024). Non-null for 1,587,484 of 1,825,173 rows. |

## Agricultural yields — GDHY v1.2/1.3 (not filled)

GDHY long (`district_id, year, crop, yield_t_ha`) is pivoted to one column per
crop. **Not filled.** NaN where the crop is absent from the district's grid
cells or where `year > 2016` (GDHY ends in 2016).

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `yield_maize` | District-year maize yield. | t/ha | GDHY v1.2/1.3 | Zonal mean of the 0.5° GDHY grid over the district. Coverage 1981–2016 (panel keeps 1989–2016). Non-null 751,744. |
| `yield_rice` | District-year rice yield. | t/ha | GDHY v1.2/1.3 | As above. Non-null 532,261. |
| `yield_wheat` | District-year wheat yield. | t/ha | GDHY v1.2/1.3 | As above. Non-null 623,343. |
| `yield_soybean` | District-year soybean yield. | t/ha | GDHY v1.2/1.3 | As above. Non-null 280,354. |

## Country classification — World Bank OGHIST (carried forward)

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `income_group` | World Bank income classification of the country: `L` low, `LM` lower-middle, `UM` upper-middle, `H` high; `NA` = unclassified in OGHIST (".." / blank, e.g. small or recently formed economies). | category | World Bank OGHIST | Joined by `iso3` and `data_year == year` (the GNI reference year, **not** the fiscal-year label, avoiding the OGHIST two-year offset). For panel years beyond an `iso3`'s last `data_year`, the latest classification is carried forward (`income_group_carried = True`). NaN only for `iso3` codes never present in OGHIST. |
| `income_group_carried` | Whether `income_group` was carried forward from an earlier `data_year` rather than taken from a same-year OGHIST observation. | bool | (derived) | OGHIST `data_year` runs 1987–2024, so **every 2025 row is carried**; a few economies whose series ends earlier are also carried. 51,076 district-years carried in total. False (and `income_group` NaN) for the unmatched `iso3` below. |

**Unmatched `iso3` (never in OGHIST):** `ATA` (Antarctica) and `VAT`
(Vatican City) — 1 district each, 2 districts × 37 years = 74 rows with NaN
`income_group`. Both lack a World Bank income classification by definition.

## Crop-mix statics — SPAM 2020 v2.0 R2 (time-invariant per district)

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `cropland_ha` | District total SPAM harvested area, summed over all 46 SPAM crops. | hectares | SPAM 2020 v2.0 R2 | Time-invariant (one SPAM snapshot, broadcast to every year). NaN for districts with no SPAM cropland (313,353 district-years = 8,469 districts × 37 years); those are the only NaN rows for the crop-mix columns. Non-null 1,511,820. |
| `price_shock_coverage` | Share of the district's `cropland_ha` in crops the crosswalk maps to a Pink Sheet commodity. | fraction 0–1 | SPAM 2020 v2.0 R2 × crosswalk | Time-invariant. Records how much of the district's cropland the price shock can "see"; mean ≈ 0.65, median ≈ 0.69. 0 where the district grows only unmapped crops; the shock is then mechanically 0 (not NaN). NaN only where `cropland_ha` is NaN. |

## Price shock — SPAM crop mix × World Bank Pink Sheet (shift-share)

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `price_shock` | Shift-share district-year producer-price shock: Σ over mapped crops *c* of `crop_share_c × dlog_real_price_{c,t}`. | log-change (≈ fractional change) | SPAM 2020 v2.0 R2 × World Bank Pink Sheet | "Share" = time-invariant district SPAM crop-area shares; "shift" = annual log-change in the Pink Sheet **real** commodity price. NaN only where the district has no cropland at all (`cropland_ha` NaN). See construction notes below. |

**`price_shock` construction (`src/merge/01_build_panel.py`):**

1. **Crosswalk.** `reference/spam_pinksheet_crosswalk.csv` maps SPAM 2020 crop
   codes to Pink Sheet commodity codes for confident 1:1 economic matches
   (e.g. `maiz`→`maize`, `whea`→`wheat_us_hrw`, `rice`→`rice_thai_5`,
   `soyb`→`soybeans`, `coff`/`rcof`→`coffee_arabica`/`coffee_robusta`,
   `coco`→`cocoa`, `teas`→`tea_avg_3_auctions`, `cott`→`cotton_a_index`,
   `sugc`→`sugar_world`, `bana`→`banana_us`, `oilp`→`palm_oil`,
   `rubb`→`rubber_rss3`, `grou`→`groundnuts`, `sorg`→`sorghum`,
   `barl`→`barley`, `toba`→`tobacco_us_import_u_v`, `cnut`→`coconut_oil`).
   **18 of 46** SPAM crops are mapped, covering **67.86%** of global SPAM
   cropland. The 28 unmapped crops have no confident single-commodity Pink
   Sheet benchmark (mixed/aggregate categories such as `vege`, `rest`, `ocer`,
   `opul`, root crops, and crops with no Pink Sheet series such as rapeseed,
   sunflower, cassava, potato).
2. **Real prices, real log-changes.** `dlog_real_price_{c,t} = log(price_real_{c,t})
   − log(price_real_{c,t−1})` is computed from the Pink Sheet **real** annual
   series (`price_real`). The interim file's `dlog_price` is **nominal** and is
   *not* used here; the real series is the economically correct shift.
3. **Unmapped crops contribute 0, no renormalization.** Shares are the
   district's full SPAM shares (summing to 1 over all 46 crops); unmapped crops
   simply add nothing. Shares are deliberately **not** renormalized to the
   mapped subset, so the shock stays comparable across districts: a district
   with little mapped cropland mechanically gets a smaller-magnitude shock, and
   `price_shock_coverage` records exactly how much. Renormalizing would inflate
   thin-coverage districts to look as exposed as fully-covered ones.
4. **Missing-price years.** A mapped crop whose real price is unavailable in
   year *t* contributes 0 that year (its term is undefined, so it drops out of
   the sum). This affects only `barley` and `sorghum` after 2020 (the Pink
   Sheet real annual series ends 2020 for those two).
5. **NaN policy.** `price_shock` is NaN only for district-years whose district
   has no SPAM cropland at all (`cropland_ha` NaN). A district that has cropland
   but only unmapped crops gets `price_shock = 0` and `price_shock_coverage = 0`.

**Observed `price_shock` distribution** (non-null, 1,511,820 rows): mean
0.00341, sd 0.10080, p5 −0.15670, p50 0.00000, p95 0.17595 (min −0.55031, max
0.84836). The median is exactly 0 because many districts' mapped crop mix
nets out to no real-price change in a given year.

---

## Reproducibility

The panel is rebuilt end-to-end by `src/merge/01_build_panel.py` from the
interim tables and the committed crosswalk; the build is deterministic
(byte-identical parquet on re-run). The build also writes
`reports/panel_build_report.txt` with the full per-column non-null counts,
join cardinalities, and the distributions above.
