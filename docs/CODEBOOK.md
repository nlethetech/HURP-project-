# Codebook

Definition of every variable in `data/processed/panel_district_year.parquet`,
the district-year analysis panel built by `src/merge/01_build_panel.py`.

- **Unit of analysis**: admin-2 district × calendar year.
- **Shape**: 49,329 districts × 37 years (1989–2025) = **1,825,173 rows**, 61
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

## Coups — Powell & Thyne (national covariate, zero-filled)

Counts of coup d'état **attempts** per country-year, from the Powell & Thyne
"Global Instances of Coups" file (`data/interim/coups_pt.parquet`, version
`V2026.01.13`). This is a **national (admin-0) covariate**: the country's coup
counts are broadcast onto **every** district in that country-year (joined on
`iso3 + year`), exactly like `income_group`. Like UCDP GED, the source is
globally complete for sovereign states over its window (1950–present), so a
country-year absent from it is a true **zero** and the columns are zero-filled
across the whole frame. Country names are mapped to `iso3` via
`country_converter`; the cleaning step (`src/cleaning/09_coups_pt.py`) asserts
every in-window coup event resolves to a valid ISO3. Coups are counted, not
weighted by deaths — pair with the UCDP GED columns for fatality intensity.

**Do not sum `coups_total` across districts**: because the value is replicated
across a country's districts, the district-year sum counts each coup once per
district, not once per event. Collapse to the country-year level first (or read
`data/interim/coups_pt.parquet`) to recover unique events. P&T coding choices
apply (e.g. the 1993 Russian constitutional crisis is not coded as a coup).

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `coups_total` | Number of coup attempts in the country that year (successful + failed). | count | Powell & Thyne (V2026.01.13) | Count of nonzero `coup1`–`coup4` cells. Broadcast to all districts of the country; absent country-year ⇒ 0. |
| `coups_successful` | Number of **successful** coups that year. | count | Powell & Thyne (V2026.01.13) | Count of `coupN` == 2. Absent ⇒ 0. |
| `coups_failed` | Number of **failed/attempted** coups that year. | count | Powell & Thyne (V2026.01.13) | Count of `coupN` == 1. Absent ⇒ 0. `coups_successful + coups_failed == coups_total`. |

## Political violence & unrest — ACLED (coverage-masked)

ACLED geolocated **events** (`data/interim/acled_district_year.parquet`),
spatially joined to the spine and aggregated to district-year by `event_type`.
ACLED **extends UCDP GED**: where UCDP records only fatal organized violence,
ACLED also captures **non-lethal** unrest — protests, riots, and violence
against civilians that caused no deaths — so these columns surface political
disorder that is invisible in the UCDP layer. Events are kept at
`geo_precision ∈ {1,2}` (exact / near-exact coordinates); `geo_precision = 3`
(region-centroid only) is dropped before the join so it cannot fabricate
concentration in centroid districts. All columns are **float64**.

**Coverage mask — the critical difference from UCDP.** ACLED's geographic
coverage starts in different years by region (1997 Africa-only; Middle East
~2016; South/South-East Asia mixed 2010–2018; Europe & Latin America ~2018;
United States 2020; Oceania 2021; with country exceptions such as India 2016,
Indonesia 2015, South Sudan 2011, Afghanistan/Syria 2017). So these columns are
**NOT** blanket zero-filled. For each district-year:

- **value** = observed event count, where ACLED matched;
- **0.0** = the country-year is **inside** that country's observed ACLED window
  (`year` between the country's **first** and **last** ACLED data year) but had
  no matching event — a *true zero*;
- **NaN** = the country-year is **outside** that window (before the country
  entered ACLED, or after its last observed year, or a country ACLED does not
  cover) — *not observed*, **not** zero.

The per-country window is the **first..last year ACLED records events under
that country's own ISO code** (ACLED's `iso` field, mapped to ISO3 — *not* the
spine's geographic assignment). Deriving coverage from ACLED's own country
coding is essential: otherwise a handful of border/disputed-territory events
(e.g. a 2010 Kashmir event ACLED codes as Pakistan but whose coordinates sit
inside India's polygon) would make a country look "covered" years before ACLED
began monitoring it. These windows match ACLED's published staggered-coverage
schedule (Nigeria 1997, South Sudan 2011, Indonesia 2015, India 2016, Syria
2017, Ukraine 2018, USA 2020; cross-referenced in `docs/DATA_SOURCES.md`,
"ACLED"). A district-year is **non-NaN iff it has a matched event OR falls in
its country's window** — so a genuine cross-border event keeps its real count
even outside the window, but interior districts before a country's start stay
`NaN`. Using each country's *own* last year (not a global maximum) also avoids
trailing-edge false zeros from the reporting lag. Treat `NaN` as
missing-by-coverage; do not coerce it to 0. ACLED's raw data is **not
redistributable** (EULA), so `data/raw/acled/` is gitignored — re-pull with your
own credentials.

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `acled_events_total` | All ACLED events in the district-year (sum of the six type columns). | count | ACLED | Coverage-masked (see above). NaN ⇒ not covered. |
| `acled_events_battles` | `event_type` = Battles. | count | ACLED | Armed clashes between organized groups. |
| `acled_events_protests` | `event_type` = Protests. | count | ACLED | Non-violent demonstrations. **Absent from UCDP.** |
| `acled_events_riots` | `event_type` = Riots. | count | ACLED | Violent demonstrations / mob violence. **Absent from UCDP.** |
| `acled_events_vac` | `event_type` = Violence against civilians. | count | ACLED | Incl. non-lethal attacks UCDP omits. |
| `acled_events_explosions` | `event_type` = Explosions/Remote violence. | count | ACLED | Shelling, IEDs, air/drone strikes. |
| `acled_events_strategic` | `event_type` = Strategic developments. | count | ACLED | Non-violent but significant (arrests, looting, agreements). |
| `acled_fatalities` | Sum of ACLED `fatalities` over matched events. | deaths | ACLED | ACLED fatality estimates (conservative; differ from UCDP). |

## Socioeconomic & agricultural covariates — World Bank WDI (not filled)

National (admin-0) covariates from the World Bank World Development Indicators
(`data/interim/wb_wdi.parquet`), joined by `iso3 + year` and broadcast onto
every district of a country-year (like `income_group` and the coup columns).
These are the variables the conflict and agricultural-production literature uses
to **explain** violence and output — unemployment, income, growth, inflation,
demography, urbanization, and the agricultural economy. All are **float64** and
**not filled**: `NaN` means the World Bank has no observation for that
country-year — *not* zero (these are continuous measures). Coverage varies by
indicator and the WB reporting lag leaves **2024–2025 largely NaN** for many
series; treat `NaN` as missing, never impute silently. Licence: CC BY 4.0
(World Bank WDI; unemployment/employment via ILO modelled estimates, several
agricultural series via FAO) — redistributable with attribution.

| Variable | Definition | Unit | WDI code |
|----------|------------|------|----------|
| `wb_unemployment` | Unemployment, total (% of total labor force, modelled ILO). | % | SL.UEM.TOTL.ZS |
| `wb_unemployment_youth` | Unemployment, ages 15–24 (% — youth-bulge predictor). | % | SL.UEM.1524.ZS |
| `wb_gdp_pc` | GDP per capita (constant 2015 US$). | US$ | NY.GDP.PCAP.KD |
| `wb_gdp_growth` | GDP growth (annual %). | % | NY.GDP.MKTP.KD.ZG |
| `wb_inflation` | Inflation, consumer prices (annual %). | % | FP.CPI.TOTL.ZG |
| `wb_population` | Population, total. | persons | SP.POP.TOTL |
| `wb_pop_growth` | Population growth (annual %). | % | SP.POP.GROW |
| `wb_pop_0_14` | Population ages 0–14 (% of total; youth bulge). | % | SP.POP.0014.TO.ZS |
| `wb_urban_pct` | Urban population (% of total). | % | SP.URB.TOTL.IN.ZS |
| `wb_ag_valueadd_pct` | Agriculture, forestry & fishing, value added (% of GDP). | % | NV.AGR.TOTL.ZS |
| `wb_ag_employment_pct` | Employment in agriculture (% of total employment, modelled ILO). | % | SL.AGR.EMPL.ZS |
| `wb_ag_land_pct` | Agricultural land (% of land area). | % | AG.LND.AGRI.ZS |
| `wb_cereal_yield` | Cereal yield. | kg/ha | AG.YLD.CREL.KG |
| `wb_food_prod_index` | Food production index (2014–2016 = 100). | index | AG.PRD.FOOD.XD |
| `wb_arable_land_pct` | Arable land (% of land area). | % | AG.LND.ARBL.ZS |

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

---

## Study subset — Africa + South America + Caribbean

`src/subset/01_region_filter.py` derives two grouping columns from `iso3`
(deterministically, via `country_converter`) and cuts the region-restricted
study panel for the conflict × agriculture investigation. It writes:

- `data/processed/panel_africa_samerica_caribbean.parquet` — the study panel,
  **583,490 rows × 63 columns**, one row per `(district_id, year)`, 1989–2025.
- `reference/iso3_region_crosswalk.csv` — every `iso3` in the master panel →
  `continent`, `region`, `kept` flag (committed; the full audit of what went
  where).

| Variable | Definition | Unit | Source | Construction notes |
|----------|------------|------|--------|--------------------|
| `continent` | Continent of the district's country. | text | derived (`country_converter` from `iso3`) | `Africa`, `America`, `Asia`, `Europe`, `Oceania`, `Antarctica`. |
| `region` | Study region. Inside the Americas this is the UN sub-region; elsewhere it equals `continent`. | text | derived (`country_converter` from `iso3`) | `Africa` \| `South America` \| `Central America` \| `Caribbean` \| `Northern America` \| `<continent>`. |

**Subset rule.** Keep `region ∈ {Africa, South America, Caribbean}`. This is a
strict row filter of the master panel plus the two derived columns — no other
value is changed, so every fill/mask/carry-forward documented above is
preserved. Result: **79 countries** — 54 Africa, 12 South America, 13 Caribbean.

| Region | Rows | Countries |
|--------|------|-----------|
| Africa | 197,469 | 54 |
| South America | 317,904 | 12 |
| Caribbean | 68,117 | 13 |

**Deliberately excluded** (documented so the boundary is explicit): all of
**Central America** (incl. Guatemala, El Salvador, Nicaragua, Panama, Costa
Rica, Honduras, Belize), **Northern America** (US, Canada, Mexico, Greenland),
and every district outside Africa and the Americas. The rest of the master
panel is untouched and still rebuildable.

---

## Colonial legacy layer (study subset)

Country-level colonial-legacy moderators added by `src/cleaning/12_colonial.py`
(→ `data/interim/colonial.parquet`) and joined onto the study panel by
`src/subset/02_enrich_study.py` (→ `panel_africa_samerica_caribbean_enriched.parquet`).
Sources: COLDAT (CC0), QoG jan22 (`ht_colonial`, `lp_legor`), COW state-system
membership — see `docs/DATA_SOURCES.md`, "Colonial legacy". Every column is
TIME-INVARIANT and broadcast onto all district-years by `iso3` — **usable only as
interactions/moderators with the time-varying shocks** (a country fixed effect
absorbs them), except `years_since_independence`, which varies over the panel.
Coverage: **79/79 study countries** carry `colonizer`, `civil_vs_common`, and
`independence_year` (zero missing).

| Variable | Definition | Source | Notes |
|----------|------------|--------|-------|
| `colonizer` | Identity of the (main) colonial power: British / French / Spanish / Portuguese / Belgian / Dutch / Italian / US / None. | QoG `ht_colonial` | The primary, complete colonizer variable (Hadenius–Teorell). Captures the *dominant* power, not brief post-war administrations. |
| `coldat_colonizer_last` | Last colonial power to leave (max `colend`), COLDAT vocabulary. | COLDAT | Cross-check only; disagrees with `colonizer` for occupation artifacts (Libya, Morocco, Somalia). |
| `col_ever_colonized` | 1 if `colonizer` is a real power, else 0 (Ethiopia, Liberia = 0). | derived | |
| `coldat_n_colonizers` | Count of distinct European colonizers in COLDAT (flags multi-colonizer cases, e.g. Cameroon). | COLDAT | |
| `col_start_year` | First year of colonial rule (min `colstart`, `_mean` aggregation). | COLDAT | NaN for never-colonized. |
| `col_end_year` | Decolonization year (max `colend`, `_mean` aggregation). | COLDAT | The best "when was it freed from colonial rule" value (e.g. Haiti 1804). NaN for never-colonized. |
| `col_duration_years` | `col_end_year − col_start_year`; length of colonial rule, an extraction-intensity proxy. | derived | NaN for never-colonized. |
| `independence_year` | Year the state entered the international system. | COW `styear` | ≠ `col_end_year` for occupation/protectorate artifacts (Haiti 1934, Ethiopia 1941). Range 1822 (Brazil) – 2011 (South Sudan). |
| `years_since_independence` | `year − independence_year`. **The one time-VARYING colonial column** (survives a country FE); a slow post-colonial state-consolidation control. | derived | |
| `legal_origin` | La Porta legal origin: English / French / Socialist / German / Scandinavian. Raw `lp_legor` (NaN for 9 study countries). | QoG `lp_legor` | The legal/policing institutional-tradition channel. |
| `legal_origin_filled` | `legal_origin` with the 9 blanks imputed from `colonizer` (British/US→English; else→French). | derived | |
| `legal_origin_imputed` | 1 if `legal_origin_filled` was imputed (raw `lp_legor` was blank), else 0. | derived | Transparency flag for the 9 imputed countries. |
| `civil_vs_common` | Binary legal tradition: `common` (English legal origin) vs `civil` (all others). | derived | Study countries: 31 common, 48 civil. |
| `col_british` / `col_french` / `col_iberian` | 0/1 moderator-split dummies (`colonizer` == British / French / in {Spanish, Portuguese}). | derived | Key off `colonizer` (ht_colonial primary power), so Italian-primary states (Libya, Somalia) intentionally carry all three = 0 even where a *secondary* British administration existed. |

**Caveats (read before using the date columns):**

- `col_end_year` / `col_duration_years` are the **COLDAT observed colonial-presence
  window** (max end across *all* colonizers), **not de jure independence**. They
  are unreliable for League/UN-mandate and multi-power / border-changed cases —
  Namibia (`col_end` 1920 = German-mandate handover, independence 1990), Eritrea
  (`col_end` 1951 = end of British military administration, independence 1993),
  Morocco (`col_end` 1975 reflects Western Sahara, 19 yr *after* Morocco's 1956
  independence). For an exposure/decolonization measure use `independence_year`.
- `independence_year` = COW state-system entry, corrected where that reflects a
  contested/unrecognized entry (`ZWE` set to 1980, not the 1965 white-minority
  UDI). It can still differ from `col_end_year` for occupation/protectorate
  artifacts (Haiti 1934, Ethiopia 1941).
- Imputed legal origins (`legal_origin_imputed==1`, 9 study countries) are a crude
  colonizer→legal-family proxy. `ERI` is overridden to French/civil (Italian +
  Ethiopian heritage); `NAM` remains English/common via South-African heritage
  (contested) — treat `civil_vs_common` for these imputed cells with care.
- `SSD` (seceded 2011) is `col_ever_colonized==1` / `colonizer==British` but has
  NaN `col_start_year`/`col_end_year`/`col_duration_years` (no COLDAT spell of its
  own) — a filter on `col_duration_years` silently drops it.

---

## Pest layer — Africa (study subset)

Two georeferenced crop-pest shocks joined by `src/subset/02_enrich_study.py` from
`data/interim/{faw,locust}_district_year.parquet` (built by
`src/cleaning/13_faw.py`, `14_locust.py`). **Africa-only by design** — no
georeferenced locust/FAW data exists for South America or the Caribbean, so every
pest column is NaN for all Americas rows (a species-range fact). Both are
MONITORING/SURVEY feeds: **a missing district-year is *not observed*, not
pest-free** — the columns are NEVER zero-filled across the frame; only observed
district-years carry values (values incl. a true 0 where a monitored district-year
recorded no pest). Observation columns join on `(district_id, year)`; the
first-detection-year constants are broadcast to all of a district's years.

| Variable | Definition | Source | Notes |
|----------|------------|--------|-------|
| `faw_present` | 1 if any confirmed fall-armyworm in the monitored district-year, else 0 (0 = monitored, none confirmed). | FAMEWS | NaN = not monitored. |
| `faw_confirmed_sum` | Sum of confirmed FAW moth counts across trap checks in the district-year. | FAMEWS | |
| `faw_suspconf_sum` | Sum of suspected+confirmed FAW counts. | FAMEWS | |
| `faw_n_trap_checks` | Number of trap checks (monitoring effort / exposure denominator). | FAMEWS | Always divide intensity by this. |
| `faw_catch_rate` | `faw_confirmed_sum / faw_n_trap_checks`; effort-normalized infestation intensity. | derived | |
| `faw_first_detection_year` | First year the district recorded a confirmed FAW detection (invasion-front timing). | derived | District constant; broadcast to all years. |
| `years_since_faw_arrival` | `year − faw_first_detection_year`. TIME-VARYING invasion-wave clock (negative before arrival). | derived | The most defensibly exogenous FAW signal. |
| `faw_arrived` | 1 if `year ≥ faw_first_detection_year`, else 0; NaN if the district never detected FAW. | derived | |
| `dl_present_flag` | 1 for any gregarious desert-locust (swarm/band) observation in the district-year. | Locust Hub | Only ever 1 or NaN (presence obs). |
| `dl_swarm_obs` | Count of flying adult-SWARM observations in the district-year. | Locust Hub | The most crop-destructive phase. |
| `dl_band_obs` | Count of marching hopper-BAND observations. | Locust Hub | |
| `dl_gregarious_obs` | `dl_swarm_obs + dl_band_obs`. | derived | Total damaging-phase activity. |
| `dl_area_treated_ha` | Hectares treated (control operations) in the district-year. | Locust Hub | Response-intensity proxy. |
| `dl_first_gregarious_year` | First year the district recorded a gregarious swarm/band (informational; locust is recurrent, not a one-time invasion). | derived | |

**Coverage (study rows):** FAW = 1,500 monitored district-years across **998
districts** (623 of them confirmed FAW at least once), **42 African countries
monitored** (35 recorded a confirmed detection), 2018–2025. Locust = 1,236
observed district-years, 630 districts, **20 belt countries**, 2004–2025
(captures the 2019–22 upsurge, 2020 peak). Both NaN for all 12 South American +
13 Caribbean countries. Note: source feeds run to 2026, but the panel ends 2025,
so 7 out-of-window 2026 locust observations are dropped at merge (logged).

**Use as an exogenous shock, not a control.** Locust plagues and the FAW invasion
front are weather/wave-driven, not conflict-caused — that is what lets them
identify the *agriculture → conflict* arrow. Interact with the colonial moderators
and read as an **Africa-subsample** result; the Americas are honestly uncovered on
pest.

---

## Country-year mediators: state capacity, regime, repression (study subset)

Three country-year layers added by `src/cleaning/15_state_capacity.py`,
`16_regime.py`, `17_repression.py` and joined by `src/subset/02_enrich_study.py`.
All are **iso3_broadcast** (one country-year value copied to every district of
that country-year), **TIME-VARYING**, and **NaN where unobserved — never
zero-filled**. They are *mediators* between the shocks and conflict (why a shock
does or doesn't become violence); several are partly endogenous to conflict, so
**lag them (t−1); do not treat as clean exogenous causes.** Covers all 79 where
the source does (microstates thin — see per-column notes).

### State capacity — ICTD/UNU-WIDER Government Revenue Dataset (GRD 2025)
Fiscal capacity: the state's ability to raise revenue. Values are % of GDP.
Coverage: tax series 76/79 (Algeria, Egypt, South Sudan lack it → use revenue),
1989–2023 (2024–2025 NaN).

| Variable | Definition | Notes |
|----------|------------|-------|
| `grd_tax_pct_gdp` | Total taxes as % of GDP (PRIMARY fiscal-capacity measure). | |
| `grd_nonresource_tax_pct_gdp` | Non-resource taxes as % of GDP. | Least price-endogenous extractive proxy. |
| `grd_totrev_pct_gdp` | Total revenue as % of GDP. | Broader fallback where tax is missing. |
| `grd_resource_rev_pct_gdp` | Resource revenue as % of GDP. | High for petrostates (Nigeria, Gulf). |
| `grd_gov_level` | `general` or `central` — which government level supplied the row. | GRD "Merged" series (best available per country-year). |
| `grd_quality_flag` | 1 if GRD flagged any data-quality caution for the observation. | |

### Regime & democracy — V-Dem v16 + Polity5
Coverage: V-Dem 72/79 (7 Caribbean microstates — Antigua, Bahamas, Dominica,
Grenada, St Kitts, St Lucia, St Vincent — absent → NaN), 1989–2025. Polity 69/79,
1989–2018 (2019–2025 NaN; project ended).

| Variable | Definition | Notes |
|----------|------------|-------|
| `vdem_polyarchy` | V-Dem electoral democracy index (0–1). | |
| `vdem_libdem` | V-Dem liberal democracy index (0–1). | |
| `vdem_rule_of_law` | V-Dem rule-of-law index (0–1). | |
| `vdem_corruption` | V-Dem political corruption index (0–1). | **HIGH = MORE corrupt** — inverted vs the democracy indices; do not rescale silently. |
| `vdem_regime` | Regimes of the World: 0 closed autocracy, 1 electoral autocracy, 2 electoral democracy, 3 liberal democracy. | Categorical. |
| `vdem_terr_control` | State authority over territory (% of territory). | The coercive/territorial complement to the fiscal state-capacity measures. |
| `polity2` | Polity5 combined score, −10 (full autocracy) to +10 (full democracy). | Interpolated series; −66/−77/−88 already resolved to NaN. |
| `anocracy_flag` | 1 if `|polity2| ≤ 5` (anocracy — most conflict-prone), else 0; NaN where polity2 NaN. | |

### State repression — Political Terror Scale (PTS-2025)
Physical-integrity repression, 1–5 (5 = worst). Coverage 79/79, 1989–2024
(2025 NaN). DR Congo carried under legacy code `ZAR` → remapped to `COD`.

| Variable | Definition | Notes |
|----------|------------|-------|
| `pts_amnesty` / `pts_state` / `pts_hrw` | PTS score from the Amnesty / US State Dept / HRW report (1–5). | State Dept (`pts_state`) is the most complete series. |
| `pts_score` | Coalesced score: State Dept → Amnesty → HRW. | The main repression column. |
| `pts_source` | Which source supplied `pts_score` (`S`/`A`/`H`). | Transparency flag. |

### Displacement — UNHCR origins + IDMC GIDD
Forced displacement, country-year, iso3_broadcast, TIME-VARYING, NaN where
unobserved (never zero-filled; a missing IDMC row is not zero displacement).
**Stocks and flows are separate columns — never sum them.** Both a cause and a
consequence of conflict (mediator; lag it). Best Americas reach of the new
layers (Colombia/Venezuela conflict IDPs, Haiti disaster+conflict). UNHCR origin
totals 79/79; IDMC 2008–2024 (2025 NaN), conflict-stock on the ~41 conflict-
affected study countries.

| Variable | Definition | Source | Notes |
|----------|------------|--------|-------|
| `refugees_origin` | Refugees originating FROM the country (end-year stock). | UNHCR | 79/79. |
| `asylum_seekers_origin` | Asylum-seekers originating from the country (stock). | UNHCR | |
| `idp_stock_unhcr` | UNHCR-reported IDP stock. | UNHCR | Sparse pre-1993. |
| `returned_refugees` | Refugees returned that year (FLOW). | UNHCR | Do not add to stocks. |
| `returned_idps` | IDPs returned that year (FLOW). | UNHCR | |
| `idp_stock_conflict` | IDPs displaced by conflict/violence (end-year STOCK). | IDMC GIDD | 2008+. |
| `new_disp_conflict` | New conflict displacements that year (FLOW). | IDMC GIDD | 2009+; a consequence-of-conflict signal. |
| `idp_stock_disaster` | IDPs displaced by disasters (STOCK). | IDMC GIDD | |
| `new_disp_disaster` | New disaster displacements that year (FLOW). | IDMC GIDD | The plausibly-exogenous hazard shock. |

---

## Spatial layers (study subset): temperature, market access, resources, ethnic exclusion

Four district-level layers joined by `src/subset/02_enrich_study.py`. Temperature
and ethnic exclusion vary by (district_id, year); market access and resources are
district-constant (broadcast to all years). All NaN where unobserved (never
zero-filled), except the resource *census* counts (see below).

### Temperature — CRU TS v4.09 (`src/cleaning/19_temperature_cru.py`)
Area-weighted district annual mean temperature + a standardized heat anomaly. A
second exogenous weather shock alongside rainfall. Global; 1989–2024 (2025 NaN,
CRU ends 2024). ~5% of rows NaN (2025 + micro-islands with no CRU land cell).

| Variable | Definition |
|----------|------------|
| `temp_mean` | Area-weighted district-year annual mean near-surface temperature (°C). NaN outside CRU land / 2025. |
| `temp_anomaly` | `(temp_mean − district 1989–2010 mean) / district 1989–2010 sd`; standardized heat deviation. NaN where the baseline has <2 years or sd=0. |

### Market access — MAP 2015 travel-time-to-cities (`src/cleaning/20_market_access.py`)
District travel time to the nearest city (minutes), 2015 snapshot. TIME-INVARIANT;
proxy for farm market access AND state reach. 0 minutes = inside a city (a valid
value, not nodata).

| Variable | Definition |
|----------|------------|
| `travel_time_to_city_min_median` | District median travel-time to a city (min), 2015. NaN for micro-islands with no land cell. |
| `travel_time_to_city_min_mean` | District mean (outlier-sensitive; prefer median). |
| `travel_time_to_city_log1p` | `log1p(median)` for right-skewed regressors. |
| `market_access_snapshot_year` | 2015 (provenance; back-projecting onto 1989 is an anachronism — a static moderator). |

### Natural resources — PRIO PETRODATA + DIADATA + USGS MRDS (`src/cleaning/21_resources.py`)
Static geological endowment (the "greed"/lootable-resource channel). District-
constant. **Count columns are zero-filled** (global census: no intersecting
deposit = a true 0). Caveat: PETRODATA's 2003 vintage misses the post-2003
East-African oil frontier (Uganda 2006, Kenya 2012) → those are false zeros.

| Variable | Definition |
|----------|------------|
| `has_oil_gas` / `n_oil_gas_fields` | Any / count of onshore oil-gas field polygons intersecting the district. |
| `has_oil` / `has_gas` | Field type present (from RESINFO). |
| `oil_gas_first_discovery_year` | Earliest field discovery year in the district (NaN if none/unknown). |
| `has_diamond` / `n_diamond_deposits` | Any / count of diamond deposits. |
| `n_diamond_primary` / `n_diamond_secondary` | Kimberlite (primary) vs alluvial (secondary). |
| `has_lootable_diamond` | 1 if any SECONDARY (alluvial) OR MIXED deposit (both carry an alluvial, easily-looted component) — the conflict-financing flag (e.g. Sierra Leone = 1, Botswana kimberlite = 0). |
| `has_gold` | 1 if the district has any gold deposit/mine — a major conflict-financing mineral. The **union of both sources** (USGS Mineral Industries GIS of Africa + USGS MRDS), so it can be 1 even where `n_gold_deposits` is 0 (an African district covered only by MRDS). The robust cross-region presence flag. |
| `n_gold_deposits` | Count of gold sites: **Africa** from USGS GIS (facilities + deposits + exploration, de-duplicated), **the Americas** from MRDS. The two sources differ in density → use *within-region*, not cross-region. Small/emerging producers absent from the source (e.g. Rwanda, Benin) read 0; rare offshore island points are dropped by the strict spatial join. |
| `has_oil_gas` vs `has_oil`/`has_gas` | `has_oil_gas` flags any oil/gas field present; `has_oil`/`has_gas` flag the *known* type. A field with RESINFO `---` (unknown type) sets `has_oil_gas=1` while both type flags stay 0 (a real field of undocumented type, not a contradiction). |
| `n_mineral_deposits` | USGS MRDS deposits in the district. **US-biased; undercounts outside North America** — informational. |

### Ethnic exclusion — EPR-Core + GeoEPR (`src/cleaning/22_ethnic_epr.py`)
Share of a district settled by politically EXCLUDED ethnic groups, by year. The
strongest subnational political conflict driver; adds within-country variation
the colonial layer lacks. Coverage 67/79 (12 homogeneous / no-politically-
relevant-group countries → NaN); 1989–2021 (2022–2025 NaN, EPR ends 2021).

| Variable | Definition |
|----------|------------|
| `share_area_excluded` | District area share under groups coded POWERLESS/DISCRIMINATED/SELF-EXCLUSION (0–1). E.g. South Africa 0.96 (1990, apartheid) → 0.0 (2000). |
| `any_excluded` | 1 if any excluded group settles the district. |
| `n_groups_overlap` | Distinct EPR groups overlapping the district that year. |
| `ethnic_fractionalization` | `1 − Σ(group area share)²` within the district (within-district ethnic mixing; low where one group dominates). |

### Food insecurity — FEWS NET IPC phases (`src/cleaning/23_food_insecurity.py`)
Subnational acute food-insecurity phase (1 Minimal … 5 Famine), the literal
bridge between agricultural output and conflict. Coverage-masked (NaN where not
monitored — never zero-filled). 25 study countries, 2011–2025; Africa-heavy with
**Haiti** the Americas reach (Colombia/Venezuela are 2026-only → out of window).
Same-country overlaps only (border slivers of a neighbour's FEWS unit dropped).

| Variable | Definition |
|----------|------------|
| `ipc_phase_max` | Worst IPC phase over units overlapping the district that year (1–5). |
| `ipc_phase_modal` | Area-weighted majority phase. |
| `ipc_phase3plus_area_share` | District area share in Crisis+ (phase ≥ 3), 0–1. |
| `ipc_crisis_flag` | 1 if `ipc_phase_max ≥ 3`. |
| `ipc_n_reports` | Number of FEWS phase polygons intersecting the district that year. |
| `fews_covered` | 1 where FEWS monitored (else the row is absent → NaN after merge). |

---

## Agriculture — FAOSTAT QCL (study subset, country-year)

Agricultural output from FAOSTAT "Production: Crops and livestock products" (QCL),
built by `src/cleaning/24_faostat_ag.py` from the bulk download already fetched by
`src/acquisition/04_download_faostat_qcl.py`. Country-year, iso3_broadcast,
TIME-VARYING; NaN where a country-year does not report the item (never
zero-filled; a genuine FAOSTAT 0 is kept as 0). 1961–2024 (2025 NaN). The
**complete** long table (every crop/livestock item × Production/Area/Yield, all
79 countries, with an `is_aggregate` flag) is `data/interim/faostat_ag_long.parquet`;
the panel carries the headline measures below.

| Variable | Definition |
|----------|------------|
| `fao_cereal_prod_t` / `fao_roots_tubers_prod_t` / `fao_pulses_prod_t` / `fao_fruit_prod_t` / `fao_vegetables_prod_t` | FAO group-total production (tonnes) for the food group. |
| `fao_meat_total_prod_t` / `fao_milk_total_prod_t` | Total meat / milk production (tonnes) — livestock output. |
| `fao_cereal_area_ha` / `fao_cereal_yield_kgha` | Total cereal area harvested (ha) and cereal yield (kg/ha). |
| `fao_{maize,rice,wheat,sorghum,millet,cassava,beans,groundnuts}_prod_t` | Production (tonnes) of the 8 headline staple crops. |
| `fao_{...}_yield_kgha` | Yield (kg/ha) of the same 8 staples. |

Coverage: all 79 countries appear in FAOSTAT; `fao_cereal_prod_t` is NaN for 4
non-cereal island/coastal states (Equatorial Guinea, St Kitts, St Lucia,
Seychelles) that grow roots/tree crops instead. For any crop beyond the headline
staples, join `faostat_ag_long.parquet` on (iso3, year, item).
