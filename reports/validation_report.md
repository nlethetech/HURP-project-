# Panel validation report

Independent validation of `data/processed/panel_district_year.parquet` by `src/merge/02_validate_panel.py`. Every figure below is re-derived from the immutable `data/interim/` tables, the spine geometry, and the externally published reference figures cited inline (each with its URL). Any FAIL makes the script exit non-zero.

- Panel under test: `data/processed/panel_district_year.parquet`
- Rows: 1,825,173; columns: 61
- Network checks: performed (HTTP HEAD/GET)


## 1. Structure
- **PASS** [STRUCTURE] row count == 49,329 x 37: rows=1,825,173 expected=1,825,173
- **PASS** [STRUCTURE] column count: cols=61 expected=61
- **PASS** [STRUCTURE] unique (district_id, year): duplicate keys=0
- **PASS** [STRUCTURE] distinct districts == spine: districts=49,329 expected=49,329
- **PASS** [STRUCTURE] every district in all 37 years: years/district min=37 max=37; year span 1989-2025; distinct years=37
- **PASS** [STRUCTURE] no null keys (district_id, iso3, year): null key cells=0
- **PASS** [STRUCTURE] dtypes sane: conflict+year int=True; measure cols float=True; income_group_carried bool=True
- **PASS** [STRUCTURE] no all-NaN columns: all-NaN columns=[]

## 2. Internal reconciliation
- **PASS** [RECON] conflict grand-totals == interim GED: all 20 columns match; deaths_best_total grand=2,885,001
- **PASS** [RECON] precip_mm non-null == interim: panel=1,587,484 interim_nonnull=1,587,484
- **PASS** [RECON] yield non-null counts == interim: all 4 crops match (maize=751,744, rice=532,261, wheat=623,343, soybean=280,354)
- **PASS** [RECON] price_shock NaN iff cropland_ha NaN: price_shock NaN=313,353 cropland NaN=313,353 exact_match=True; cropland==0 rows=0
- **PASS** [RECON] price_shock_coverage NaN iff cropland_ha NaN: coverage NaN=313,353 cropland NaN=313,353
- **PASS** [RECON] coups grand-total == interim x districts: panel=20,904 expected=20,904 (interim coup country-years x #districts/country)
- **PASS** [RECON] acled total == sum of event-type columns: checked 510,836 covered district-years; consistent=True
- **PASS** [RECON] acled events grand-total == interim: panel=2,480,760 interim=2,480,760
- **PASS** [RECON] acled coverage mask correct (matched OR in coverage window): non-NaN: expected=510,836 actual=510,836; match=True

## 3. External cross-checks

UCDP global organized-violence fatalities (best) — published: 2020 ~80,100, 2021 ~119,100 (Davies/Pettersson/Oberg, Journal of Peace Research; https://doi.org/10.1177/00223433211026126 , https://doi.org/10.1177/00223433221108428 ).
- **PASS** [EXTERNAL] UCDP fatality ratio in expected band: aggregate panel/published = 0.719 (expected band [0.55, 0.95], <1 due to where_prec<=3 keep 85.0% + ~3.7% unmatched); 2020: panel=58,068 / pub=80,100 = 0.725; 2021: panel=85,137 / pub=119,100 = 0.715
UCDP ratio (2020+2021 aggregate, panel/published) = **0.719**.

FAOSTAT 2020 world production (backbone consistency) — published rounded figures: maize ~1.2 Gt, wheat ~0.8 Gt (~757-760 Mt), rice ~0.8 Gt (FAO production highlights https://www.fao.org/statistics/highlights-archive/highlights-detail/New-FAOSTAT-data-release-Agricultural-production-statistics-(2000-2020)/en ; FAOSTAT QCL https://www.fao.org/faostat/en/#data/QCL ).
- **PASS** [EXTERNAL] FAOSTAT 2020 Maize (corn) vs FAO published: interim=1,153.9 Mt vs published~1,200 Mt (ratio 0.962, tol +/-6%, n_countries=169)
- **PASS** [EXTERNAL] FAOSTAT 2020 Wheat vs FAO published: interim=775.8 Mt vs published~760 Mt (ratio 1.021, tol +/-6%, n_countries=124)
- **PASS** [EXTERNAL] FAOSTAT 2020 Rice vs FAO published: interim=771.6 Mt vs published~760 Mt (ratio 1.015, tol +/-6%, n_countries=136)
FAO ratios (interim/published): Maize (corn)=0.962, Wheat=1.021, Rice=1.015.
- **PASS** [EXTERNAL] Sahara core precip < 150 mm (2020): n=13 districts; max precip=63.5 mm (threshold <150)
- **PASS** [EXTERNAL] Bangladesh precip > 1500 mm (2020): n=64 districts; min precip=1682.9 mm (threshold >1500)
- **PASS** [EXTERNAL] Iowa maize 2010 median in 8-12 t/ha: n=65 districts; median maize yield=9.62 t/ha (band [8.0, 12.0])
- **PASS** [EXTERNAL] 2024 high-income count == World Bank FY26: interim income_class (data_year=2024) High=87 vs World Bank FY26=87 (https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups )
Panel year=2024 distinct High iso3 = 66 (< 87: the panel covers only the 198 countries with spine admin-2 polygons; small high-income territories without districts drop out — documented, expected).
- **PASS** [EXTERNAL] 2008 real wheat/rice price log-change large positive: dlog_real wheat 2008=0.170, rice 2008=0.614 (both should be large positive; 2007-08 food price spike)
- **PASS** [EXTERNAL] 2008 high-wheat shock > zero-cropland (NaN): high-wheat (share>0.5, n=2,940) mean price_shock=0.1268; zero-cropland (n=8,469) price_shock all-NaN=True
- **PASS** [EXTERNAL] ACLED surfaces non-lethal unrest invisible to UCDP: 95,652 district-years with ACLED protests/riots but zero UCDP fatal events (of 105,330 with any protest/riot); demonstrates the enrichment is real
- **PASS** [EXTERNAL] ACLED coverage starts match published schedule: all 7 match: {'NGA': 1997, 'SSD': 2011, 'IDN': 2015, 'IND': 2016, 'SYR': 2017, 'UKR': 2018, 'USA': 2020}

## 4. Missingness map (per column x 5-year era)

| column | 1989-1993 | 1994-1998 | 1999-2003 | 2004-2008 | 2009-2013 | 2014-2018 | 2019-2023 | 2024-2025 | reason |
|---|---|---|---|---|---|---|---|---|---|
| `precip_mm` | 89.4% | 89.4% | 89.4% | 89.4% | 89.4% | 89.4% | 89.4% | 44.7% | CHIRPS v2.0 covers 50S-50N (high-latitude districts NaN) and the interim series ends 2024 (all 2025 NaN). Matches CODEBOOK 'Weather - CHIRPS v2.0'. |
| `yield_maize` | 54.7% | 54.8% | 54.8% | 54.8% | 54.0% | 31.8% | 0.0% | 0.0% | GDHY ends 2016 (>2016 NaN) and is NaN where the crop is absent from the district's grid cells. Matches CODEBOOK 'Agricultural yields - GDHY'. |
| `income_group` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | Joined by iso3; NaN only for iso3 never in OGHIST (ATA, VAT). Matches CODEBOOK 'Country classification - World Bank OGHIST'. |
| `cropland_ha` | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | Time-invariant SPAM static; NaN for districts with no SPAM cropland. Matches CODEBOOK 'Crop-mix statics - SPAM 2020 v2.0 R2'. |
| `price_shock` | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | 82.8% | NaN only where cropland_ha is NaN (no SPAM cropland). Matches CODEBOOK 'Price shock' NaN policy. |
- **PASS** [MISSINGNESS] documented gaps appear as codebook states: precip_mm 2025 non-null=0.0% (expect 0); yield_maize >2016 non-null=0.0% (expect 0); cropland_ha non-null flat across eras=True

## 5. Zero-hallucination sweep (URLs + codebook coverage)

URLs checked: 8 cited in this report + 46 distinct manifest URLs = 54 unique.
- **PASS** [SWEEP] all cited / manifest URLs resolve: 54/54 resolved
- **PASS** [SWEEP] codebook covers every panel column: 61/61 columns documented

## Summary

| # | group | check | status | detail |
|---|-------|-------|--------|--------|
| 1 | STRUCTURE | row count == 49,329 x 37 | **PASS** | rows=1,825,173 expected=1,825,173 |
| 2 | STRUCTURE | column count | **PASS** | cols=61 expected=61 |
| 3 | STRUCTURE | unique (district_id, year) | **PASS** | duplicate keys=0 |
| 4 | STRUCTURE | distinct districts == spine | **PASS** | districts=49,329 expected=49,329 |
| 5 | STRUCTURE | every district in all 37 years | **PASS** | years/district min=37 max=37; year span 1989-2025; distinct years=37 |
| 6 | STRUCTURE | no null keys (district_id, iso3, year) | **PASS** | null key cells=0 |
| 7 | STRUCTURE | dtypes sane | **PASS** | conflict+year int=True; measure cols float=True; income_group_carried bool=True |
| 8 | STRUCTURE | no all-NaN columns | **PASS** | all-NaN columns=[] |
| 9 | RECON | conflict grand-totals == interim GED | **PASS** | all 20 columns match; deaths_best_total grand=2,885,001 |
| 10 | RECON | precip_mm non-null == interim | **PASS** | panel=1,587,484 interim_nonnull=1,587,484 |
| 11 | RECON | yield non-null counts == interim | **PASS** | all 4 crops match (maize=751,744, rice=532,261, wheat=623,343, soybean=280,354) |
| 12 | RECON | price_shock NaN iff cropland_ha NaN | **PASS** | price_shock NaN=313,353 cropland NaN=313,353 exact_match=True; cropland==0 rows=0 |
| 13 | RECON | price_shock_coverage NaN iff cropland_ha NaN | **PASS** | coverage NaN=313,353 cropland NaN=313,353 |
| 14 | RECON | coups grand-total == interim x districts | **PASS** | panel=20,904 expected=20,904 (interim coup country-years x #districts/country) |
| 15 | RECON | acled total == sum of event-type columns | **PASS** | checked 510,836 covered district-years; consistent=True |
| 16 | RECON | acled events grand-total == interim | **PASS** | panel=2,480,760 interim=2,480,760 |
| 17 | RECON | acled coverage mask correct (matched OR in coverage window) | **PASS** | non-NaN: expected=510,836 actual=510,836; match=True |
| 18 | EXTERNAL | UCDP fatality ratio in expected band | **PASS** | aggregate panel/published = 0.719 (expected band [0.55, 0.95], <1 due to where_prec<=3 keep 85.0% + ~3.7% unmatched); 2020: panel=58,068 / pub=80,100 = 0.725; 2021: panel=85,137 / pub=119,100 = 0.715 |
| 19 | EXTERNAL | FAOSTAT 2020 Maize (corn) vs FAO published | **PASS** | interim=1,153.9 Mt vs published~1,200 Mt (ratio 0.962, tol +/-6%, n_countries=169) |
| 20 | EXTERNAL | FAOSTAT 2020 Wheat vs FAO published | **PASS** | interim=775.8 Mt vs published~760 Mt (ratio 1.021, tol +/-6%, n_countries=124) |
| 21 | EXTERNAL | FAOSTAT 2020 Rice vs FAO published | **PASS** | interim=771.6 Mt vs published~760 Mt (ratio 1.015, tol +/-6%, n_countries=136) |
| 22 | EXTERNAL | Sahara core precip < 150 mm (2020) | **PASS** | n=13 districts; max precip=63.5 mm (threshold <150) |
| 23 | EXTERNAL | Bangladesh precip > 1500 mm (2020) | **PASS** | n=64 districts; min precip=1682.9 mm (threshold >1500) |
| 24 | EXTERNAL | Iowa maize 2010 median in 8-12 t/ha | **PASS** | n=65 districts; median maize yield=9.62 t/ha (band [8.0, 12.0]) |
| 25 | EXTERNAL | 2024 high-income count == World Bank FY26 | **PASS** | interim income_class (data_year=2024) High=87 vs World Bank FY26=87 (https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups ) |
| 26 | EXTERNAL | 2008 real wheat/rice price log-change large positive | **PASS** | dlog_real wheat 2008=0.170, rice 2008=0.614 (both should be large positive; 2007-08 food price spike) |
| 27 | EXTERNAL | 2008 high-wheat shock > zero-cropland (NaN) | **PASS** | high-wheat (share>0.5, n=2,940) mean price_shock=0.1268; zero-cropland (n=8,469) price_shock all-NaN=True |
| 28 | EXTERNAL | ACLED surfaces non-lethal unrest invisible to UCDP | **PASS** | 95,652 district-years with ACLED protests/riots but zero UCDP fatal events (of 105,330 with any protest/riot); demonstrates the enrichment is real |
| 29 | EXTERNAL | ACLED coverage starts match published schedule | **PASS** | all 7 match: {'NGA': 1997, 'SSD': 2011, 'IDN': 2015, 'IND': 2016, 'SYR': 2017, 'UKR': 2018, 'USA': 2020} |
| 30 | MISSINGNESS | documented gaps appear as codebook states | **PASS** | precip_mm 2025 non-null=0.0% (expect 0); yield_maize >2016 non-null=0.0% (expect 0); cropland_ha non-null flat across eras=True |
| 31 | SWEEP | all cited / manifest URLs resolve | **PASS** | 54/54 resolved |
| 32 | SWEEP | codebook covers every panel column | **PASS** | 61/61 columns documented |

**Totals: 32 PASS, 0 FAIL, 0 SKIP (of 32 checks).**

### Headline figures
- UCDP ratio (2020+2021, panel/published): **0.719**.
- FAO ratios (interim/published, 2020): Maize (corn) 0.962, Wheat 1.021, Rice 1.015.

**Verdict: ALL CHECKS PASS.**
