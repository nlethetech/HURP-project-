# Data Sources

Registry of every raw data source used in this project. **A source must be documented here before its acquisition script is added.** Facts below (URLs, coverage years, license terms) were confirmed against live provider pages on 2026-06-11; re-verify before relying on any access detail that may have changed since.

Template for new entries:

```
### <Dataset name with version>
- **Provider**:
- **Role in panel**:
- **Homepage**:
- **Download / API**: (exact programmatic URL(s))
- **Coverage**: (exact years, update cadence)
- **Spatial detail**: (unit / resolution)
- **Access method**: (scriptable steps; registration yes/no)
- **License**:
- **Redistribution in public repo**: (yes / no / conditions)
- **Required citation**:
- **Fit notes**: (how it aggregates to admin-2 x year)
- **Gotchas**: (known pitfalls)
- **Facts verified**: (date, method)
```

---


## Conflict and political violence


### UCDP Georeferenced Event Dataset (UCDP GED), Global version 26.1
- **Provider**: Uppsala Conflict Data Program (UCDP), Department of Peace and Conflict Research, Uppsala University
- **Role in panel**: Supplies the conflict/political-violence layer — point-located fatal organized-violence events aggregated to district-year counts and death tolls
- **Homepage**: https://ucdp.uu.se/ged (downloads: https://ucdp.uu.se/downloads/ged/)
- **Download / API**: CSV bulk https://ucdp.uu.se/downloads/ged/ged261-csv.zip (39,122,522 bytes; contains GEDEvent_v26_1.csv, 273,992,720 bytes, 417,968 events). Codebook: https://ucdp.uu.se/downloads/ged/ged261.pdf. Also ged261-xlsx.zip plus Rds and Stata .dta. URL pattern stable across versions: ged{VV}{R}-csv.zip (ged251-csv.zip live; ged271-csv.zip 404). REST API base https://ucdpapi.pcr.uu.se/api/gedevents/26.1 now requires header `x-ucdp-access-token` — use the zip, not the API. Old versions: https://ucdp.uu.se/downloads/olddw.html
- **Coverage**: 1989-01-01 to 2025-12-31 (37 years). Updated annually (~June; 26.1 extracted 2026-03-30). Preliminary monthly "candidate events" cover the current year at ~1-month lag but are not final GED
- **Spatial detail**: Point events (WGS84/EPSG:4326 lat/lon, 6 decimals); finest resolution = individual village/town. Carries adm_1/adm_2 name strings (adm_2 populated for 82.4% of events), where_coordinates, geom_wkt, PRIO-GRID cell id. Geo-precision flag where_prec 1–7: 1 exact 46.5%, 2 within 25km 24.2%, 3 ADM2 14.2%, 4 ADM1 9.2%, 5 linear/fuzzy 4.5%, 6 country-only 1.3%, 7 sea/air 0.1%
- **Access method**: Bulk download, fully scriptable, no registration: `curl -LO https://ucdp.uu.se/downloads/ged/ged261-csv.zip && unzip ged261-csv.zip` yields GEDEvent_v26_1.csv (RFC4180, UTF-8, header row, 49 columns incl. id, year, type_of_violence, lat/lon, adm_1/adm_2, where_prec, date_prec, deaths_a/b/civilians/unknown, best/high/low). Codebook section 6: all formats "available for download free of charge (no registration required)"
- **License**: CC BY 4.0. Downloads page: "All datasets are free of charge and licensed under CC BY 4.0 — you are free to use and redistribute them provided you cite the relevant publications listed with each dataset" (https://creativecommons.org/licenses/by/4.0/). Codebook: always include the version number in analyses
- **Redistribution in public repo**: Yes — CC BY 4.0 permits redistributing the raw data, conditional on attribution: cite the required publications, state the version (26.1), and link the license. (The Zenodo mirror 17397479 is an unofficial v25.1 re-upload labeled ODbL; official UCDP terms are CC BY 4.0.)
- **Required citation**: Sundberg, Ralph & Erik Melander (2013) "Introducing the UCDP Georeferenced Event Dataset", Journal of Peace Research 50(4): 523–532. Also cite the version codebook (Högbladh, Stina (2026) "UCDP GED Codebook version 26.1", Uppsala University) and the annual companion article: Davies, Shawn, Therése Pettersson & Magnus Öberg (2026) "Organized violence 1989–2025, and violent political protests", Journal of Peace Research (doi:10.1093/jopres/xjag046). Always state the version (26.1)
- **Fit notes**:
  - Each row is one fatal event with point coordinates and a `year`; no event spans more than one calendar year, so year aggregation is clean.
  - Build: spatial-join lat/lon to a fixed admin-2 shapefile (GADM/geoBoundaries), then sum by district-year: event counts and `best` (with low/high bounds) split by type_of_violence (1 state-based, 2 non-state, 3 one-sided); deaths_a/b/civilians/unknown give composition.
  - Do NOT key on the adm_2 string: only 82.4% populated, no standardized codes, coded to the administrative system in force at event time under the government controlling the capital (e.g., 1989 St. Petersburg coded Leningrad, Soviet Union) — names will not match a modern shapefile.
  - Restrict baseline to where_prec ∈ {1,2,3} (85.0% of events); where_prec 3 points are ADM2 representative points (typically centroids), admin-2 accurate but UCDP's ADM2 delineation may differ from your shapefile's.
- **Gotchas**:
  1. where_prec 4 (ADM1 centroid 9.2%), 5 (fuzzy 4.5%), 6 (country centroid 1.3%), 7 (sea/air 0.1%) sit at representative points; naive polygon joins fabricate concentration in capital/centroid districts — drop, treat as robustness band, or reallocate.
  2. Fatal events only (≥1 direct death): non-lethal violence/protests/riots are absent (unlike ACLED), so zeros mean "no recorded fatal organized violence", not "no unrest".
  3. Multi-location reports are split one event per location with deaths divided evenly (automated); event_clarity=2 events are source-side aggregates — event counts are softer than fatality sums.
  4. The API requires an `x-ucdp-access-token` header (per apidocs, request a token from the maintainer; exact contact unconfirmed) — use the no-auth versioned zip.
  5. Version pinning: each annual release retroactively revises history — pin/archive ged261-csv.zip, not "latest". Actor/dyad/conflict IDs are incompatible with pre-17.1 versions; use `id` (persistent), not `relid`.
  6. CSV omits the binary `geom` (lat/lon and geom_wkt are present); conflict_dset_id/dyad_dset_id/side_*_dset_id are deprecated legacy fields (codebook claims removed, but they remain present and ~99.6% populated in the CSV — treat as deprecated).
  7. The included priogrid_gid assigns cells geometrically, which can disagree with PRIO-GRID's majority-rule country assignment (codebook: never clip PRIO-GRID by country before merging).
  8. Coverage starts exactly 1989 — no earlier event-level data; 2026 requires the preliminary monthly candidate-events feed (under-review quality status).
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### ACLED (Armed Conflict Location & Event Data)
- **Provider**: ACLED — 501(c)(3) non-profit (acleddata.com)
- **Role in panel**: Conflict/political-violence layer — geolocated event and fatality counts aggregated to district-year.
- **Homepage**: https://acleddata.com
- **Download / API**: API read endpoint `https://acleddata.com/api/acled/read?_format=csv` (filters: `country`, `event_date=YYYY-MM-DD|YYYY-MM-DD` with `event_date_where=BETWEEN`, `fields=pipe|delimited`, `limit=N`; default 5000 rows/request, paginate for more; JSON/CSV/XML/TXT). OAuth2 token from `https://acleddata.com/oauth/token` (grant_type=password, client_id=acled, scope=authenticated) → `Authorization: Bearer`; 24h access_token, 14-day refresh_token. Login-gated curated/regional files: https://acleddata.com/conflict-data/download-data-files. Docs: https://acleddata.com/api-documentation/getting-started and /api-documentation/acled-endpoint.
- **Coverage**: Region-staggered start years (per https://acleddata.com/knowledge-base/country-time-period-coverage/): Africa Jan 1997 (South Sudan 2011, small islands 2020); core South/SE Asia 2010 (India/Philippines 2016, Indonesia 2015, Malaysia 2018); Middle East 2015–17; Central Asia/Caucasus/East Asia/Europe/Latin America mostly 2018; US 2020; Canada/Oceania/Antarctica 2021. Updated weekly (confirmed on attribution policy). Research tier delivers event data on a rolling ~12-month lag.
- **Spatial detail**: Point events with lat/lon plus named admin1/admin2/admin3 and location; 31 core fields (event_id_cnty…timestamp, incl. disorder_type, event_type, sub_event_type, actors, civilian_targeting, fatalities, geo_precision, tags, notes) plus 4 optional population_1km/2km/5km/best columns (35 total). Open-tier aggregated files are week × country × admin1 × sub_event_type (admin1, NOT admin2; 12 columns incl. centroid coords).
- **Access method**: Free myACLED registration with Terms acceptance, then OAuth (POST username/password to /oauth/token). Tier matrix (https://acleddata.com/myacled-faqs): Open = aggregated only; Research = aggregated + event data lagged 12 months (rolling); Partner/Enterprise = weekly disaggregated/unlimited (paid). Registration required: yes.
- **License**: Proprietary EULA (https://acleddata.com/eula, last updated 8 July 2025), NOT CC/open: "royalty-free, non-exclusive, non-transferable, non-sublicensable license…for non-commercial purposes." Externally published materials "must be transformative, such that they cannot be reverse engineered to recreate the Licensed Content"; merely supplemented/appended/excerpted/reorganized content is "not sufficient." Forbids providing direct access to Licensed Content and sharing credentials. "Commercial entities may not access or use the Content…without first obtaining a corporate license." Subject to Attribution Policy (https://acleddata.com/attributionpolicy).
- **Redistribution in public repo**: No for raw event data (EULA forbids direct access/republishing). Derived data only under conditions: a transformative derivative that "cannot be reverse engineered to recreate" the source may be published, but whether an admin2 × year count panel qualifies vs. mere "reorganized" data is a genuine gray area. Safest pattern: commit only download/aggregation scripts (each user pulls with own credentials); seek written confirmation (access@acleddata.com) before publishing a derived panel.
- **Required citation**: Raleigh, C., Kishi, R., & Linke, A. (2023). "Political instability patterns are obscured by conflict dataset scope conditions, sources, and coding choices." Humanities and Social Sciences Communications. https://doi.org/10.1057/s41599-023-01559-4. Plus in-data acknowledgment "ACLED, accessed on [DATE]. www.acleddata.com" stating access date, filters applied, and modifications.
- **Fit notes**:
  - Build admin2 × year by spatial-joining event coordinates to a fixed admin-2 shapefile (GADM/geoBoundaries) — recommended over grouping on ACLED's free-text admin2 names (no GADM/GAUL codes; names drift across versions).
  - Filter on `geo_precision` to drop events located only to admin1/country centroids.
  - Panel depth is region-staggered (Africa 1997+ longest; core S/SE Asia 2010+; most of world 2018+; US 2020+); a balanced global panel exists only from ~2021.
  - Free Research tier limits the panel to ~12 months before access date.
- **Gotchas**:
  1. Coverage starts are staggered by region — zero events before a country's start year means "not covered," not "no conflict"; a naive global panel fabricates pre-coverage zeros.
  2. 2025 platform relaunch replaced email+api_key with OAuth; old keys ran until 15 September 2025 (verbatim on https://acleddata.com/myacled-faqs). Free tiers no longer give current event-level data (Open = admin1-weekly aggregates; Research = event data lagged 12 months); real-time event data requires Partner/Enterprise.
  3. Tier is assigned to the member's organization by ACLED (via email domain/relationship); generic/public email (e.g. gmail) auto-gets Open. Universities usually land at Research, but it is organization-dependent, not automatic for any institutional domain.
  4. Numeric API rate limits/quotas are not published in current docs (pagination noted as not counting toward rate limits); default 5000 rows/request.
  5. Living dataset: back-revisions occur weekly — pin and record access date (attribution policy requires it); a deleted-events endpoint exists for syncing.
  6. Schema churn: inter1/inter2/interaction switched numeric→text on 26 Sept 2024 (`inter_num=1` restores numeric); new data structure/conflict categories arrived with the 2025 relaunch (https://acleddata.com/faq-codebook-tools).
  7. Reporting intensity varies across countries/years — ACLED cautions against raw cross-country count comparisons; fatality figures are estimates.
  8. Redistribution of raw data in a public repo is prohibited; even derived panels are a license gray area.
- **Implementation (verified live 2026-06-15)**: OAuth2 password grant confirmed working from a university account (`furman.edu`) — POST `https://acleddata.com/oauth/token` (username/password/grant_type=password/client_id=acled/scope=authenticated) → 24h `access_token`; `Authorization: Bearer` on `GET https://acleddata.com/api/acled/read`. Verified: `page` is 1-based with disjoint pages; default/max page size 5000; `fields=` is pipe-delimited; `event_date=A|B` + `event_date_where=BETWEEN`; `iso` numeric filter works; 1997 returns Africa-only (confirms staggered coverage). The pipeline (`src/acquisition/10_download_acled.py`) pulls GLOBALLY year-by-year (resumable, token-cached, retry/backoff), keeping 17 fields; the cleaner (`src/cleaning/10_acled.py`) keeps `geo_precision ∈ {1,2}`, spatial-joins to the spine, and aggregates to district-year by the six `event_type`s. Coverage mask at merge: zero-fill within each country's observed ACLED span, NaN outside (not-covered) — the observed first-event year tracks ACLED's published staggered start schedule (Africa 1997; Middle East 2016; S/SE Asia mixed 2010–2018; Europe/Latin America 2018; US 2020; Oceania 2021; exceptions incl. India 2016, Indonesia 2015, South Sudan 2011, Afghanistan/Syria 2017).
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages); 2026-06-15 (live OAuth + read-API verification, this build)


### Powell & Thyne — Global Instances of Coups, 1950–present (Coup d'état Dataset)
- **Provider**: Jonathan M. Powell (University of Central Florida) & Clayton L. Thyne (University of Kentucky). Project pages: https://www.jonathanmpowell.com/coups/ and Thyne's data mirror at uky.edu.
- **Role in panel**: Political-instability layer complementing UCDP GED — country-year counts of coup d'état attempts (successful vs failed), broadcast onto every district in the country (admin-0 covariate). Captures elite/military seizures of executive power, which UCDP GED (fatal-event geocoding) does not isolate.
- **Homepage**: https://www.jonathanmpowell.com/coups/
- **Download / API**: Single tab-separated text file, no auth: `https://www.uky.edu/~clthyn2/coup_data/powell_thyne_ccode_year.txt` (country-year format; ~708 KB; 12,384 data rows). A by-event ("coup-list") file also exists at the same directory; the panel uses the country-year file. (The `http://` form 301-redirects to `https://`.)
- **Coverage**: 1950–2025, annual, global (all sovereign states; one row per state-year). Living dataset, updated as coups occur — current snapshot is `version` string **V2026.01.13**. The companion JPR article documented 1950–2010; the live file extends to the present.
- **Spatial detail**: Country level (admin-0). No subnational content. Keyed by Correlates-of-War country code (`ccode`); also carries `ccode_gw` (Gleditsch-Ward, frequently blank), `ccode_polity`, a COW `abbrev`, and a full `country` name string.
- **Access method**: Anonymous HTTPS GET of one .txt; fully scriptable, no registration. Columns (tab-separated, quoted strings): `ccode`, `abbrev`, `country`, `year`, `ccode_gw`, `ccode_polity`, `coup1`–`coup4`, `date1`–`date4`, `version`. Each `coupN` cell codes one coup event that year: **2 = successful coup, 1 = failed/attempted coup, 0 = none**; up to four events per country-year. `dateN` gives each event's date.
- **License**: No explicit license statement on the project pages; distributed freely for academic use with a request to cite the JPR article and contact the authors with corrections. Treat as **academic-use, cite-required** — not an open CC license. Mirror the file via the acquisition script rather than asserting redistribution rights.
- **Redistribution in public repo**: Conditional / cautious. No open-license grant, so do **not** commit the raw file; ship the acquisition script + this registry entry so a third party re-obtains the identical file (consistent with the project's no-license-no-commit rule). Derived country-year coup counts are a transformation but, absent an explicit license, keep the layer download-on-build.
- **Required citation**: Powell, Jonathan M. & Clayton L. Thyne (2011) "Global instances of coups from 1950 to present: A new dataset", *Journal of Peace Research* 48(2): 249–259. https://doi.org/10.1177/0022343310397436. State the accessed `version` string (V2026.01.13).
- **Fit notes**:
  - Country-year layer: parse `coup1`–`coup4`, count nonzero cells per state-year as `coups_total`, cells == 2 as `coups_successful`, cells == 1 as `coups_failed`. Join onto the spine by **ISO3 + year** and zero-fill the panel window (the file is globally complete over 1950–present, so an unlisted state-year is a true zero, exactly like UCDP GED).
  - Key mapping: the file has no ISO3 column. Map the `country` name string → ISO3 with `country_converter` (regex matcher), NOT the COW `ccode` (country_converter has no COW class) and NOT `abbrev` (COW abbreviations differ from ISO3: BFO=Burkina Faso, CDI=Côte d'Ivoire, UKG=United Kingdom, etc.).
  - Coverage 1950–2025 spans the full panel window 1989–2025; no end-year trimming needed.
- **Gotchas**:
  1. COW `abbrev` ≠ ISO3 and COW `ccode` is unsupported by country_converter — map on the `country` name string and hard-guard that every in-window coup event resolves to a valid ISO3.
  2. Historical/non-sovereign entities in the file do not map to a modern ISO3: "Vietnam, Republic of" (South Vietnam, ended 1975), "German Democratic Republic"/"German Federal Republic" (pre-1990), "Yugoslavia", "Zanzibar", "Tibet", "Abkhazia", "South Ossetia". All 1989–2025 coup events fall on mapped states (the sole unmapped coup-country, South Vietnam, predates the panel); these names are dropped with logging via an explicit, documented override set.
  3. Living file with no versioned archive — record the `version` cell and the retrieval date/checksum in MANIFEST; counts for recent years can be revised in later snapshots.
  4. Counts coups, not deaths — a bloodless palace coup and a violent one both score one event; pair with UCDP GED for fatality intensity.
  5. Quoted string fields (`"USA"`, `"United States of America"`, `"V2026.01.13"`) — strip surrounding quotes on parse.
- **Facts verified**: 2026-06-15 (live download of the country-year file; format, version V2026.01.13, and 1950–2025 coverage confirmed directly)


## Panel spine: administrative boundaries


### Admin-2 boundary spine: geoBoundaries CGAZ v6.0.0 (recommended) vs GADM 4.1 (higher-detail, redistribution-blocked)
- **Provider**: geoBoundaries — William & Mary geoLab (wmgeolab) + community. GADM — GADM project (Robert Hijmans / UC Davis), distributed via geodata.ucdavis.edu.
- **Role in panel**: Supplies the fixed admin-2 polygon spine (cross-sectional key) onto which conflict-event points and agricultural-output data are spatially joined and stacked by year.
- **Homepage**: geoBoundaries https://www.geoboundaries.org/ | GADM https://gadm.org/
- **Download / API**: geoBoundaries CGAZ global ADM2 composite (recommended single spine): https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/CGAZ/geoBoundariesCGAZ_ADM2.zip (also _ADM0/_ADM1; .geojson/.gpkg variants at same path; 302-redirects to media.githubusercontent.com via Git-LFS). Per-country API: https://www.geoboundaries.org/api/current/gbOpen/ALL/ADM2/ or per-ISO3 e.g. .../gbOpen/NPL/ADM2/ (returns JSON with gjDownloadURL). GADM 4.1 six-layer GeoPackage (ADM2 is one layer): https://geodata.ucdavis.edu/gadm/gadm4.1/gadm_410-levels.zip (also gadm_410-gpkg.zip, gadm_410-gdb.zip).
- **Coverage**: Single contemporary snapshots, NOT time-varying. geoBoundaries latest = v6.0.0 "Modeg" (2023-09-14; priors v5.0.0 2022-12-19, v4.0.0 2021-08-31, v3.0.0 2020-06-05, v2.0.1 2019-12-07, v1.3.4 2018-11-11). GADM latest = 4.1; gadm.org/data.html states "Version 5 will be released in January 2026" — v5 has NOT shipped as of 2026-06-11. Cadence: irregular major releases, roughly annual/biennial.
- **Spatial detail**: Admin-2 vector polygons. geoBoundaries covers ADM0–ADM5, ~1M boundaries across 200+ entities incl. all UN member states (per current site). GADM 4.1 delimits 400,276 areas across levels 0–5. CGAZ ADM2 is generalized and clipped to US State Dept international boundaries (disputed areas removed); GADM polygons are higher-resolution but heavier.
- **Access method**: No account, fully scriptable. geoBoundaries: either (a) one bulk `curl -L` of the CGAZ global ADM2 zip (follow the 302 to media.githubusercontent.com), or (b) loop ISO3 codes against the JSON API, parse gjDownloadURL, fetch each country's gbOpen ADM2 geometry. GADM: `wget`/`curl` gadm_410-levels.zip, unzip, read the ADM2 layer (geopandas/fiona). All plain HTTPS GETs.
- **License**: geoBoundaries gbOpen = CC BY 4.0 ("allows for most commercial, noncommercial, and academic uses"; requires acknowledgement); per-boundary metadata carries a varying boundaryLicense field (e.g. NPL ADM2 "Public Domain", CAF ADM5 "CC BY 3.0 IGO"), with CC BY 4.0 as the blanket framing (README: "open license (CC BY 4.0 / ODbL)"). Non-open channels: gbAuthoritative (mirrored UN SALB, non-commercial only) and gbHumanitarian (mirrored UN OCHA, may have less open licensure) — use gbOpen. GADM 4.1 = restrictive: "freely available for academic use and other non-commercial use"; "Redistribution or commercial use is not allowed without prior permission"; academic-article maps allowed. (Austria's GADM data is CC BY-SA 2.0.)
- **Redistribution in public repo**: geoBoundaries gbOpen = YES — CC BY 4.0 permits committing the raw file with attribution. GADM 4.1 = NO — must script the geodata.ucdavis.edu download at build time, never vendor raw files. Use geoBoundaries CGAZ as the redistributable spine; treat GADM as download-on-build only.
- **Required citation**: geoBoundaries: Runfola, D., Anderson, A., Baier, H., et al. (2020). geoBoundaries: A global database of political administrative boundaries. PLoS ONE 15(4): e0231866. https://doi.org/10.1371/journal.pone.0231866 (v6.0.0 archive: Harvard Dataverse doi:10.7910/DVN/PGAIQY, "geoBoundaries Global Administrative Zones version 6.0.0"). GADM: Global Administrative Areas (GADM), version 4.1, 2022, University of California, Davis. https://gadm.org
- **Fit notes**:
  - Use ONE fixed admin-2 boundary spine and repeat the same units across every panel year; the geometry is time-invariant.
  - Recommended spine = geoBoundaries CGAZ ADM2 v6.0.0 — CC BY 4.0 allows committing the raw file, one bulk download gives global ADM2, and releases are stable and citable.
  - Each unit's shapeID/shapeName/ISO is the cross-sectional key; spatially join agricultural rasters/tables and conflict points (ACLED/UCDP) onto the polygons, then stack by year.
  - Use GADM 4.1 only if finer geometry or deeper levels (ADM3+) are needed and download-on-build is acceptable.
- **Gotchas**:
  1. Neither source is time-varying: admin-2 boundaries change (e.g. Nepal's 2017 federal restructuring; new districts in India/Africa) but both ship one present-day snapshot. Long historical panels suffer vintage mismatch (recent polygons on old data); accept fixed geography or hand-build crosswalks.
  2. GADM's redistribution ban blocks raw commits to a public repo — ship only a download script. geoBoundaries avoids this.
  3. CGAZ is simplified with disputed areas removed/replaced per US State Dept definitions — fine for joins, not for precise area/coastline; use per-country gbOpen files via API for full resolution. (The index-page blurb confusingly says "Disputed areas included"; the dedicated CGAZ globalDownloads page confirms removal.)
  4. The /raw/main/ CGAZ URL uses Git-LFS (302 to media.githubusercontent.com); full HTTPS git clones can hit LFS rate-limit errors — prefer the single-file `curl -L` or the API.
  5. /raw/main/ is a ROLLING build, not frozen v6.0.0 — API metadata shows buildDate "Dec 12, 2023", after the 2023-09-14 release, so main's releaseData was rebuilt. For a reproducible v6.0.0 spine, pin the release commit (tree 1289e40e366c7b320550be1ee0614a9472d572d4) or the Dataverse archive.
  6. GADM v5 (scheduled Jan 2026 per gadm.org/data.html) has NOT shipped as of 2026-06-11; the page still presents 4.1 (400,276 areas) as current.
  7. Unit counts are NOT comparable as admin-2 totals: GADM's 400,276 and geoBoundaries' ~1M are sums across all levels (0–5); the two projects also disagree on which level a country's units map to (definitional).
  8. GADM and geoBoundaries share no common unit ID and have no built-in crosswalk — pick one and stay with it.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


## Country classification


### World Bank Historical Country Income Classifications (OGHIST — "Country Analytical History")
- **Provider**: World Bank, Development Data Group (published via the World Bank Data Help Desk and the World Development Indicators entry, dataset 0037712, in the WB Data Catalog).
- **Role in panel**: Time-varying country-year development-level covariate (LEDC/MEDC, income group) broadcast onto every admin-2 district.
- **Homepage**: https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups
- **Download / API**: Canonical historical XLSX: https://ddh-openapi.worldbank.org/resources/DR0095334/download (linked as "Historical classification by income"; resource last updated 2026-03-10, file OGHIST_2026_03_10.xlsx). Current-year companion (FY26): https://ddh-openapi.worldbank.org/resources/DR0095333/download. Legacy mirror (STALE, frozen at FY23): https://databankfiles.worldbank.org/public/ddpext_download/site-content/OGHIST.xls
- **Coverage**: Classification columns FY89 through FY26 (38 fiscal years); each FY column is based on Atlas-method GNI per capita for calendar years 1987 through 2024. Updated annually, set each July 1.
- **Spatial detail**: Country level (admin-0): 224 unique economy codes (218 in the main alphabetical block plus 6 former entities). No subnational content.
- **Access method**: Bulk download, scriptable, no auth/registration. (1) `curl -L -o oghist.xlsx "https://ddh-openapi.worldbank.org/resources/DR0095334/download"`. (2) Parse sheet "Country Analytical History" (of 5 sheets: Parameters, Thresholds, Country Analytical History, Operational Category Change, Country Indebtedness History). (3) Headers on row 5 (FY89..FY26) and row 6 (1987..2024); thresholds rows 7-10; data starts row 12; col A = 3-letter code (plus 4-char YUGf), col B = name. (4) Cell values: L / LM / UM / H / ".." (unclassified) / "LM*" (pre-unification Yemen) / blank (recent unclassified gaps). (5) Melt to long (iso3, year, income_group).
- **License**: Creative Commons Attribution 4.0 International (CC BY 4.0), confirmed on the WB Terms of Use page (datasets are CC BY 4.0 "unless specifically labeled otherwise"; data may be extracted, downloaded, copied, and shared per the terms). Attribution format: "The World Bank: Dataset name: Data source (if known)." WDI catalog entry 0037712 carries license_id "Creative Commons Attribution 4.0".
- **Redistribution in public repo**: Yes — raw XLSX and derived CSVs may be committed under CC BY 4.0, provided attribution to The World Bank is included (README/data dictionary) and the same attribution requirement is passed to downstream users. WB-produced, not third-party-restricted.
- **Required citation**: World Bank. 2026. "World Bank Country and Lending Groups — Historical classification by income (OGHIST)." Washington, DC: World Bank. https://datahelpdesk.worldbank.org/knowledgebase/articles/906519. License: CC BY 4.0. Methodology: Fantom, Neil, and Umar Serajuddin. 2016. "The World Bank's Classification of Countries by Income." Policy Research Working Paper 7528, World Bank.
- **Fit notes**:
  - Melt "Country Analytical History" to long (iso3, year, income_group) and left-join onto every district by country code, making the LEDC/MEDC split time-varying (countries move across L/LM/UM/H over 1987-2024).
  - Standard splits: developed = H vs developing = L+LM+UM; low-income-only = L; LIC/LMIC = L+LM (most common "LEDC" proxy).
  - State the alignment choice: (a) align on the "Data for calendar year" row (1987-2024) so the class reflects that year's GNI, or (b) align on fiscal-year effectivity (FY column = class in force from July 1 of the prior calendar year).
  - For causal designs, optionally FIX classification at a baseline year (e.g., the FY column covering panel start) to avoid endogenous reclassification from conflict-driven income collapse; every vintage since FY89 is in one sheet, so both approaches are supported.
- **Gotchas**:
  1. Two-year offset: column FY89 is based on calendar-1987 GNI; use the "Data for calendar year" row (6) for data-year alignment to avoid shifting the panel by 2 years.
  2. The legacy databankfiles OGHIST.xls URL still resolves (HTTP 200) but was last saved 2022-07-02 and stops at FY23; use the ddh-openapi DR0095334 endpoint. The older siteresources OGHIST.xls URL is dead (502).
  3. The DDH endpoint serves an .xlsx despite the historical .xls name.
  4. Title cell B1 contains stray text ("fethio") — never key off title cells. Two distinct unclassified encodings: ".." (e.g., Albania pre-FY92) AND blank cells (e.g., Venezuela FY22+); handle both, do not coerce to NA-as-low. "LM*" flags pre-unification Yemen.
  5. The data block is interrupted: rows 230-232 are blank/footnote rows (incl. the Yemen "*" footnote) between the main list (rows 12-229) and the former-entities block (rows 233-238); row 240 is the July-1 note. A naive "read from row 12 until blank" parser truncates the 6 former entities — skip non-code rows instead.
  6. Former entities (CSK, SUN, YUG, YUGf, ANT, MYT) use codes that will not match modern boundary files (YUGf is non-ISO; several dissolve mid-panel) — a country-succession crosswalk is needed for 1987-1993.
  7. Income-group thresholds are revised every July 1, and FY24 onward also reflects Atlas-method revisions, so "high income" is not a constant real-income bar across the panel.
  8. The DDH resource ID (DR0095334) is a catalog artifact and may change in catalog migrations (an older duplicate ID DR0090754 still appears in DatasetView responses); keep the Help Desk article as discovery fallback and pin a repo copy.
  9. No official machine-readable (CSV/API) historical table exists: WB API v2 incomeLevel returns only the single current classification, and the catalog companion DR0094546 ("Historical classification by income, lending, and fragile status", CLASS_hist.xlsx) is still Excel — the XLSX is the only official historical source.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### World Bank World Development Indicators (WDI) — socioeconomic & agricultural covariates
- **Provider**: World Bank, Development Data Group (World Development Indicators). Several series are sourced by the WB from ILO (unemployment/employment, modelled estimates) and FAO (agricultural land/yield/food index).
- **Role in panel**: Country-year socioeconomic and agricultural covariates that the conflict and agricultural-production literature uses as explanators/controls — unemployment (incl. youth), GDP per capita and growth, inflation, population and age structure, urbanization, agricultural value-added/employment/land/yield/food-production. Broadcast onto every district by ISO3 + year (like income class and coups).
- **Homepage**: https://data.worldbank.org/ (indicator pages e.g. https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS)
- **Download / API**: WB Indicators REST API v2, no auth: `https://api.worldbank.org/v2/country/all/indicator/{CODE}?format=json&per_page=20000&date=1989:2025`. Returns `[meta, [rows]]`; each row has `countryiso3code`, `date` (year), `value`, and the indicator name. `per_page` large enough returns all rows in one page (≈266 economies × 37 years ≈ 9.8k rows < 20000); `meta.pages`/`meta.total` confirm. Also offers CSV/XML bulk and per-country queries. (Verified live 2026-06-15: SL.UEM.TOTL.ZS and NY.GDP.PCAP.KD return HTTP 200, total=266 for 2020.)
- **Curated indicator set (code → panel column)**:
  - `SL.UEM.TOTL.ZS` → `wb_unemployment` — Unemployment, total (% labor force, modelled ILO)
  - `SL.UEM.1524.ZS` → `wb_unemployment_youth` — Unemployment, youth 15–24 (% — youth-bulge conflict predictor)
  - `NY.GDP.PCAP.KD` → `wb_gdp_pc` — GDP per capita (constant 2015 US$; classic conflict predictor, Fearon-Laitin / Collier-Hoeffler)
  - `NY.GDP.MKTP.KD.ZG` → `wb_gdp_growth` — GDP growth (annual %)
  - `FP.CPI.TOTL.ZG` → `wb_inflation` — Inflation, consumer prices (annual %)
  - `SP.POP.TOTL` → `wb_population` — Population, total
  - `SP.POP.GROW` → `wb_pop_growth` — Population growth (annual %)
  - `SP.POP.0014.TO.ZS` → `wb_pop_0_14` — Population ages 0–14 (% of total; youth bulge)
  - `SP.URB.TOTL.IN.ZS` → `wb_urban_pct` — Urban population (% of total)
  - `NV.AGR.TOTL.ZS` → `wb_ag_valueadd_pct` — Agriculture/forestry/fishing value added (% GDP)
  - `SL.AGR.EMPL.ZS` → `wb_ag_employment_pct` — Employment in agriculture (% of employment, modelled ILO)
  - `AG.LND.AGRI.ZS` → `wb_ag_land_pct` — Agricultural land (% of land area)
  - `AG.YLD.CREL.KG` → `wb_cereal_yield` — Cereal yield (kg/ha)
  - `AG.PRD.FOOD.XD` → `wb_food_prod_index` — Food production index (2014–2016 = 100)
  - `AG.LND.ARBL.ZS` → `wb_arable_land_pct` — Arable land (% of land area)
- **Coverage**: country-year; series start years vary by indicator (most 1960/1990+; modelled ILO series ~1991+). Updated continuously; recent 1–2 years are often missing (reporting lag). `country/all` includes regional aggregates (e.g. WLD, ARB) which simply do not join to spine ISO3 and are harmless.
- **Spatial detail**: National (admin-0). `countryiso3code` is ISO 3166-1 alpha-3 (joins directly to the spine `iso3`; aggregates carry non-country codes that do not match).
- **Access method**: Anonymous HTTPS GET per indicator; fully scriptable, no key. JSON `[meta, rows]`; parse `countryiso3code`, `date`, `value`; pivot to wide (iso3, year) × indicator.
- **License**: CC BY 4.0 (World Bank Terms of Use; data "free to copy, distribute, adapt" with attribution). **Redistributable** — derived country-year tables may be committed with WB attribution. ILO/FAO-sourced series carry the WB CC BY 4.0 framing.
- **Redistribution in public repo**: Yes — CC BY 4.0; commit derived `wb_*` columns with "World Bank, World Development Indicators" attribution (and note ILO/FAO origin for the relevant series). Raw JSON is download-on-build (data/raw gitignored).
- **Required citation**: World Bank. World Development Indicators. Washington, DC: World Bank. https://data.worldbank.org/. Licence: CC BY 4.0. (For ILO-sourced series add: International Labour Organization, ILOSTAT modelled estimates; for FAO-sourced: FAO.)
- **Fit notes**: Left-join by (iso3, year); **not zero-filled** (continuous measures — absence is missing data, NaN, not zero). The recent-year reporting lag means 2024–2025 are largely NaN for many indicators; documented in the codebook. Each indicator is validated at download time (HTTP 200 + non-empty `total`) so a renamed/retired code fails loudly.
- **Gotchas**:
  1. `country/all` mixes economies and regional aggregates — keep only rows whose `countryiso3code` matches a spine ISO3 (aggregates harmlessly fail to join).
  2. `value` is null for missing observations and the JSON `date` is a string year — coerce types and drop nulls.
  3. Indicator codes occasionally change/retire across WDI vintages — pin the code list and assert each returns data.
  4. Some series (poverty, youth unemployment) are sparse for conflict-affected countries — expect high NaN density there; do not impute silently.
  5. Modelled ILO unemployment/employment are estimates, not survey counts — fine as covariates, flag as modelled.
- **Facts verified**: 2026-06-15 (live API check: WDI v2 endpoint, two indicator codes, JSON shape)


## Agricultural output


### FAOSTAT — Production: Crops and livestock products (QCL) + Producer Prices (PP, PA archive)
- **Provider**: FAO, Statistics Division (ESS); contact faostat@fao.org
- **Role in panel**: National (admin-0) agricultural backbone — country-year production/yield denominators and item-level price/quantity weights for the conflict-agriculture district-year panel.
- **Homepage**: https://www.fao.org/faostat/en/#data/QCL (production); https://www.fao.org/faostat/en/#data/PP (producer prices)
- **Download / API**: Bulk server (anonymous): manifest https://bulks-faostat.fao.org/production/datasets_E.xml ; QCL https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip (33,127 KB, 4,209,110 rows); PP https://bulks-faostat.fao.org/production/Prices_E_All_Data_(Normalized).zip (11,411 KB, 1,319,563 rows); PA archive https://bulks-faostat.fao.org/production/PricesArchive_E_All_Data_(Normalized).zip (1,086 KB, 139,713 rows). REST API https://faostatservices.fao.org/api/v1/... now returns HTTP 401 "Missing Authorization Header" without a JWT Bearer token.
- **Coverage**: QCL 1961-2024 (annual, ~December release; DateUpdate 2025-12-31). PP 1991-2025 (annual + monthly rows from 2010; DateUpdate 2026-01-09). PA "Producer Prices (old series)" 1966-1990 (discontinued). QCL/PP revised in full each release; files are unversioned snapshots.
- **Spatial detail**: National only (admin-0). QCL 244 areas, PP 182, PA 97; includes regional aggregates. No subnational detail.
- **Access method**: Fully scriptable, zero auth: (1) GET datasets_E.xml for FileLocation + DateUpdate per domain; (2) curl the zip; (3) unzip → long-format CSV (Area Code, Area Code (M49), Area, Item Code, Item Code (CPC), Item, Element Code, Element, Year Code, Year, Unit, Value, Flag, Note; PP replaces Note with Months Code/Months) plus companion AreaCodes/ItemCodes/Elements/Flags CSVs. Read as UTF-8 (or utf-8-sig). REST API alternative requires FAOSTAT Developer Portal registration for a JWT (60-min expiry) — avoid for reproducible pipelines. No registration for bulk.
- **License**: CC BY 4.0 under the FAO Database Terms of Use (https://www.fao.org/contact-us/terms/db-terms-of-use/en/). Access, download, adapt and re-disseminate permitted; attribution and licence statement required; FAO-specific clause: datasets shall not be used for or with the promotion of a commercial enterprise or its products/services; no warranty. Replaced the older CC BY-NC-SA 3.0 IGO terms.
- **Redistribution in public repo**: Yes — raw QCL/PP/PA CSVs may be committed to a public repo provided you (1) attribute FAO with the suggested citation, (2) state CC BY 4.0 and note modifications, (3) respect the non-promotional clause. Keep the zip's DateUpdate in the filename (in-place revisions).
- **Required citation**: FAO. 2024. FAOSTAT: Production: Crops and livestock products. [Accessed December 2024]. https://www.fao.org/faostat/en/#data/QCL. Licence: CC-BY-4.0. (Adapt year/access date; for prices: FAO. [year]. FAOSTAT: Prices: Producer Prices. [Accessed ...]. https://www.fao.org/faostat/en/#data/PP. Licence: CC-BY-4.0.)
- **Fit notes**:
  - Provides the country-year denominator (Production, Area harvested, Yield by CPC item, 1961-2024) that admin-2 values must sum to, plus item-level mix for crop-share and price weights (value-of-production via QV domain on the bulk server, or PP prices × QCL quantities).
  - For an admin-2 × year panel, downscale with a spatial allocation layer (SPAM/GAEZ-type crop rasters) or use for country-year fixed-effect normalization.
  - Join via the M49 column ("Area Code (M49)") to GADM/geoBoundaries country codes.
  - Build a successor-state concordance: Ethiopia PDR 1961-1992 vs Ethiopia 1993-; Sudan (former) -2011 vs Sudan + South Sudan 2012-; USSR, Yugoslav SFR, Czechoslovakia present as separate areas.
- **Gotchas**:
  1. QCL data quality is weakest exactly in conflict countries: only 43.7% of observations are flag A "Official figure"; 42.3% E "Estimated", 9.2% I "Imputed", 2.6% X external, 2.2% M missing. FAO model-fills where questionnaires aren't returned (e.g. Somalia/DRC) — keep the Flag column; consider official-only robustness checks.
  2. PP coverage fails where conflict is: Somalia, South Sudan and DR Congo entirely absent; CAR missing 13 years (1999-2011); PP starts 1991. Pre-1991 prices exist only in the discontinued PA archive (1966-1990, 97 areas, LCU/tonne only); splicing PA→PP crosses a methodology break and currency redenominations.
  3. Series breaks: Ethiopia starts 1993, Sudan/South Sudan 2012 (predecessors under separate area codes).
  4. Whole back-series revised every release with no versioned archive — snapshot the zip and record DateUpdate (current QCL 2025-12-31).
  5. Domain/code churn: old QC (crops) and QL (livestock) merged into QCL (~2021) and gone from the manifest (only QCL/QI/QV remain); item codes moved to CPC — old replication code breaks.
  6. REST API silently now requires a JWT (401 "Missing Authorization Header", Developer Portal announced 2026-04-13); old fenixservices.fao.org host is dead (HTTP 521) — many published FAOSTAT API scripts/R packages no longer work unauthenticated. Bulk server remains anonymous.
  7. PP file mixes annual and monthly rows — filter Months == 'Annual value' (943,427 rows) or you double-count.
  8. Current bulk CSVs are UTF-8 (e.g. "Maté leaves", "Côte d'Ivoire" as UTF-8 bytes); reading as latin-1 produces silent mojibake. Older FAOSTAT bulk files were latin-1 — verify encoding per snapshot.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### SPAM / MapSPAM — Spatial Production Allocation Model (global gridded crop production; latest global release SPAM 2020 v2.0 Release 2)
- **Provider**: International Food Policy Research Institute (IFPRI); SPAM 2005 co-authored with IIASA. Hosted on the IFPRI HarvestChoice Dataverse (Harvard Dataverse) and mapspam.info. Recent versions developed with University of Minnesota, MARI/HZAU, Land & Carbon Lab, and CGIAR initiatives.
- **Role in panel**: Baseline district crop-mix weighting layer — supplies per-crop harvested/physical area to derive admin-2 crop shares for combining crop-specific conflict/price/yield exposure in a district-year panel.
- **Homepage**: https://www.mapspam.info/ (Data Center: https://www.mapspam.info/data/)
- **Download / API**: No auth, fully scriptable. (A) Harvard Dataverse access API by DOI (canonical; per-file MD5 checksums, stable versioning): per-file `https://dataverse.harvard.edu/api/access/datafile/:persistentId?persistentId=<file-DOI>`; whole-dataset zip `https://dataverse.harvard.edu/api/access/dataset/:persistentId?persistentId=<dataset-DOI>`. Dataset DOIs — 2020 v2.0 R2 (latest, current Dataverse V6.0): doi:10.7910/DVN/SWPENT; 2010 v2.0 (V4.2; 16 files): doi:10.7910/DVN/PRFF8V; 2005 v3.2 (V9.4): doi:10.7910/DVN/DHXBJX; 2000 v3.0.7 (V2.2): doi:10.7910/DVN/A50I2T; 2017 SSA-only v2.1 (V3.1): doi:10.7910/DVN/FSSKBW. (B) Direct bulk-file zips on mapspam.info/data, e.g. 2010 harvested area `https://s3.amazonaws.com/mapspam-data/2010/v2.0/csv/spam2010v2r0_global_harv_area.csv.zip` (also _phys_area/_prod/_yield/_val_prod_agg; .dbf.zip and .geotiff.zip under /dbf/, /geotiff/); 2005 `https://s3.amazonaws.com/mapspam-data/2005/v3.2/csv/spam2005v3r2_global_harv_area.csv.zip`; 2000 `https://s3.amazonaws.com/mapspam-data/2000/v3.0.7/csv/spam2000v3.0.7_global_harv_area.csv.zip`; 2017-SSA single CSV `https://s3.amazonaws.com/mapspam-data/2017/ssa/v2.1/csv/spam2017v2r1_ssa.csv.zip`. SPAM 2020 v2.2 (mapspam.info, updated 2026-05-05) and v2r0 (2025-06-09) served from Dropbox direct links (`spam2020V2r2_global_*` / `spam2020V2r0_global_*`; set `dl=1`) — prefer the checksummed SWPENT DOI.
- **Coverage**: Discrete snapshot/reference years, not an annual series. Global snapshots: 2000, 2005, 2010, 2020 (usable global weight-years {2000, 2005, 2010, 2020}); each reflects circa-that-year FAO/sub-national statistics. 2017 is Sub-Saharan Africa ONLY (not global). No 2015 global release.
- **Spatial detail**: Gridded raster/point at ~10×10 km (5 arc-minute; ~0.0833°), global land, ~800,000 cropland pixels. Four modelled variables (physical area, harvested area, production, yield) per crop, split by production system (2020 v2: irrigated/rainfed/total; earlier versions add the high-input/low-input/subsistence split). 46 crops in 2020, ~42 in earlier versions. NOT natively admin-2 — zonally aggregate grid to district (GADM/GAUL admin-2) polygons.
- **Access method**: Direct HTTP download of zipped CSV/DBF/GeoTIFF via wget/curl/Python requests. Recommended: Dataverse REST access API by DOI (MD5 checksums, stable versions); alt: S3 or Dropbox bulk-file URLs from mapspam.info/data. No interactive portal step. Registration: no. Read the per-release ReadMe for exact column schema before aggregating.
- **License**: CC BY 4.0, per the Harvard Dataverse dataset "Terms" tab (IFPRI Dataverse Terms of Use). SWPENT (2020) Section 4 verbatim: materials "made available under the Creative Commons Attribution 4.0 International (CC-BY-4.0). This license contains permission to reuse, distribute, and reproduce content even for commercial purposes…"; PRFF8V (2010) terms explicitly link CC BY 4.0.
- **Redistribution in public repo**: Yes — CC BY 4.0 permits redistribution (incl. public GitHub) and commercial use, conditioned on (a) attribution/citation to IFPRI and named authors, and (b) for derivatives, adding after the citation (SWPENT Section 5): "This data was provided by the International Food Policy Research Institute (IFPRI). IFPRI bears no responsibility for the analyses or interpretations of the data presented here." Caveat: mapspam.info/terms still states a stale, more restrictive CC BY-NC 3.0 (with the old 2014 SPAM 2005 v2.0 citation); the file-attached Dataverse CC BY 4.0 governs — quote it, and ideally confirm with IFPRI.
- **Required citation**: 2020 — IFPRI, 2026, "Global Spatially-Disaggregated Crop Production Statistics Data for 2020 Version 2.0 Release 2", https://doi.org/10.7910/DVN/SWPENT, Harvard Dataverse, V6.0. 2010 — IFPRI, 2019, "…for 2010 Version 2.0", https://doi.org/10.7910/DVN/PRFF8V, V4.2 (methods: Yu, You, Wood-Sichra et al., "A cultivated planet in 2010: 2…", Earth Syst. Sci. Data, doi:10.5194/essd-2020-11). 2005 — IFPRI; IIASA, 2016, "…for 2005 Version 3.2", https://doi.org/10.7910/DVN/DHXBJX, V9.4. 2000 — IFPRI, 2019, "…for 2000 Version 3.0.7", https://doi.org/10.7910/DVN/A50I2T, V2.2. 2017-SSA — IFPRI, 2020, "Spatially-Disaggregated Crop Production Statistics Data in Africa South of the Sahara for 2017", https://doi.org/10.7910/DVN/FSSKBW, V3.1.
- **Fit notes**: Download SPAM harvested-area (or physical-area) GeoTIFFs per crop; zonally sum each crop within each admin-2 (GADM/GAUL) polygon; normalize to per-district crop shares → time-invariant (or coarse multi-year) weights to combine crop-specific exposure. Snapshot years 2000/2005/2010/2020 allow period-appropriate weights or weight-vintage sensitivity tests. Production/yield layers give baseline output level per district. 5-arcmin grid is fine enough that most admin-2 units contain many cells. Global, free, redistributable — ship derived district weights or a download script + checksums rather than the raw 100+ MB zips.
- **Gotchas**: 1) NOT annual — only snapshot years {2000, 2005, 2010, 2020} globally. 2) 2017 is SSA-only — exclude from a global build or treat as regional supplement. 3) Modelled allocation (cross-entropy downscaling of FAO + sub-national stats), not direct observation — district crop-mix is an estimate inheriting input-stats vintage; fine for relative weights, flag as such. 4) License discrepancy: Dataverse CC BY 4.0 vs stale mapspam.info/terms CC BY-NC 3.0 — Dataverse governs; document and ideally confirm with IFPRI. 5) Harvested area ≠ physical area (multi-cropped cell can have harvested > physical) — choose deliberately (harvested area usually best for output-mix). 6) Crop count and column schema differ across versions (46 crops in 2020 vs ~42 earlier; production-system splits) — parse each ReadMe, don't hardcode columns across years. 7) Version churn — mapspam.info advertises 2020 'v2.2' (Dropbox, 2026-05-05) while the citable DOI is 'Version 2.0 Release 2' (Dataverse V6.0); pin the exact DOI version and prefer the checksummed Dataverse path. 8) Large files (~130-170 MB per variable zip; full 2020 set hundreds of MB) — script downloads, don't commit raw data to git. 9) "CC BY 4.0 / 42 crops" wording seen on FAO Hand-in-Hand mirrors is unauthoritative — rely on IFPRI/Dataverse. 10) WebFetch returns HTTP 403 on mapspam.info and dataverse.harvard.edu — a headless browser (Playwright) is needed to read these pages for automated metadata scraping.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### GDHY — Global Dataset of Historical Yields v1.2 + v1.3 aligned version
- **Provider**: PANGAEA (Data Publisher for Earth & Environmental Science), hosting. Dataset author: Toshichika Iizumi (NARO / Institute for Agro-Environmental Sciences, Japan). Inputs: reported yield census statistics (including sub-national census where available, not solely FAOSTAT country-level) scaled to satellite crop-specific NDVI estimates.
- **Role in panel**: Agricultural-output layer — gridded staple-crop yield (t/ha) to be aggregated to admin-2 district x year and linked against conflict/political-violence variables.
- **Homepage**: https://doi.pangaea.de/10.1594/PANGAEA.909132 (landing page). Open-access describing paper: https://www.nature.com/articles/s41597-020-0433-7 (mirror: https://pmc.ncbi.nlm.nih.gov/articles/PMC7083933/).
- **Download / API**: Single direct ZIP, no API/auth: `curl -L -o gdhy.zip "https://store.pangaea.de/Publications/IizumiT_2019/gdhy_v1.2_v1.3_20190128.zip"` then unzip. ~15.2 MB (15,989,683 bytes), application/zip, last-modified 2020-01-28.
- **Coverage**: 1981–2016, annual (36 years). Static release; not updated to present.
- **Spatial detail**: 0.5° x 0.5° global lat/lon grid (gridded raster, NOT vector admin units). Unit = tonnes/hectare (t/ha). Crops/seasons: maize (major + second), rice (major + second), wheat (winter + spring), soybean (single season).
- **Access method**: Anonymous HTTP(S) download of one ZIP from PANGAEA's store host — no key, login, or form (registration: NO). ZIP contains 10 folders (per-season: maize_major, maize_second, rice_major, rice_second, wheat_winter, wheat_spring; plus bare-crop convenience folders maize, rice, wheat mirroring the primary season; plus soybean), each holding 36 annual NetCDF4/HDF5 files named yield_YYYY.nc4. Needs a netCDF/xarray-capable reader (pin those deps).
- **License**: Creative Commons Attribution 4.0 International (CC-BY-4.0), stated on the PANGAEA landing page ("Always quote citation above when using data!").
- **Redistribution in public repo**: Yes. CC-BY-4.0 permits redistribution and derivatives in any medium for any purpose (incl. commercial) with attribution, a license link, and indication of changes; no share-alike or non-commercial clause. Repo options: ship the .nc4 files (or a derived admin-2 panel) with a LICENSE/attribution note and both citations, or ship a scripted downloader that pulls the single ZIP at build time. The paper's "code available from corresponding author upon request" applies to PROCESSING CODE only — does not restrict data redistribution.
- **Required citation**: Dataset — Iizumi, Toshichika (2019): Global dataset of historical yields v1.2 and v1.3 aligned version [dataset]. PANGAEA. https://doi.org/10.1594/PANGAEA.909132. Paper — Iizumi, T. & Sakai, T. (2020). The global dataset of historical yields for major crops 1981–2016. Scientific Data, 7, 97. https://doi.org/10.1038/s41597-020-0433-7.
- **Fit notes**:
  - Strong global agricultural-output candidate: truly global, long (36 yr), open CC-BY (repo-redistributable), trivially scripted (one ZIP, no auth).
  - It is a 0.5° grid, not admin-2 polygons — zonal-aggregate to GAUL/GADM admin-2 boundaries yourself (area-weighted mean of t/ha; preferably crop-area-weighted using a harvested-area mask such as SPAM/MIRCA/GAEZ for production-weighted district yield). Document the mask chosen.
  - Covers only four staple crops (maize, rice, wheat, soybean) — not total agricultural value or other crops.
  - Coverage ends 2016, capping the panel's end year unless paired with another source.
  - ~50 km resolution means small districts may hold few or fractional grid cells — handle with care.
- **Gotchas**:
  1. Temporal end hard-capped at 2016; does not extend to present. Later GDHY-style products exist (e.g. ISIMIP-aligned, other 1982–2015 5-min ML yields) but are different datasets — verify separately.
  2. The 1981–2016 series is a SPLICE of v1.2 (1981–2011; GIMMS3g/JRA-25) and v1.3 (2000–2016; MOD15A2/JRA-55); documented methodological differences across versions (e.g. divergent El Niño yield-impact estimates) — treat a possible break/level-shift around the 2000–2011 overlap with caution if using levels rather than within-cell anomalies.
  3. "District-level" requires your own zonal aggregation; results depend on the crop-area weighting mask — document it.
  4. nature.com 303-redirects to an auth IdP (idp.nature.com); use the PMC mirror for the open-access article and data-availability wording.
  5. NetCDF4 (.nc4) ingestion needs a netCDF/xarray-capable reader — pin those deps in the reproducible pipeline.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### Long-run satellite NDVI agricultural-output proxy: PKU GIMMS NDVI V1.2 (1982–2022) + GIMMS-3G+ AVHRR (1982–2022) + MODIS MOD13Q1.061 (2000–present)
- **Provider**: (1) PKU GIMMS NDVI — Peking University (Li, Cao, Zhu, Wang, Myneni, Piao), hosted on Zenodo; (2) GIMMS-3G+ AVHRR NDVI — NASA GSFC (Pinzon, Pak, Tucker et al.), distributed by NASA ORNL DAAC; (3) MOD13Q1 MODIS Vegetation Indices — NASA/USGS LP DAAC (Didan). Legacy NDVI3g (NASA GIMMS) also mirrored on Google Earth Engine.
- **Role in panel**: Agricultural-output PROXY layer — cropland-masked, growing-season NDVI zonal-aggregated to admin-2 districts as the agriculture side of the conflict × agriculture district-year panel.
- **Homepage**: PKU GIMMS NDVI https://zenodo.org/records/8253971 (ESSD paper https://essd.copernicus.org/articles/15/4181/2023/) | GIMMS-3G+ AVHRR https://www.earthdata.nasa.gov/data/catalog/ornl-cloud-global-veg-greenness-gimms-3g-2187-1 | MOD13Q1 https://www.earthdata.nasa.gov/data/catalog/lpcloud-mod13q1-061
- **Download / API**: PKU GIMMS NDVI (RECOMMENDED, no auth): scripted TIFF download from Zenodo REST API https://zenodo.org/api/records/8253971 (DOI 10.5281/zenodo.8253971), per-file URLs in `links.self`, curl/wget. | GIMMS-3G+ AVHRR: NetCDF-4 from ORNL DAAC (DOI 10.3334/ORNLDAAC/2187) via Earthdata Search or ORNL THREDDS/OPeNDAP; Earthdata Login required. | MOD13Q1.061: HDF-EOS from LP DAAC (DOI 10.5067/MODIS/MOD13Q1.061) via `earthaccess` Python lib, AppEEARS API (point/area extraction with built-in masking), or the credentialed S3 bucket `lp-prod-protected/MOD13Q1.061` (us-west-2); Earthdata Login required. | Earth Engine alternative: `ee.ImageCollection("MODIS/061/MOD13Q1")` and legacy `ee.ImageCollection("NASA/GIMMS/3GV0")`.
- **Coverage**: PKU GIMMS NDVI: Jan 1982 – Dec 2022, half-month (twice-monthly) composites; AVHRR-only files cover 1982–2015, MODIS-consolidated files cover 1982–2022 (split confirmed on the Zenodo file manifest). | GIMMS-3G+ AVHRR: 1982-01-01 – 2022-12-31, twice-monthly max-NDVI composites (catalog title reads "1981-2022" but data start is 1982-01-01). | MOD13Q1.061: 2000-02-18 to present, updated every 16 days (GEE availability through 2026-05-09). | Legacy GEE NASA/GIMMS/3GV0 (NDVI3g): 1981-07-01 – 2013-12-16 only — superseded, do not use as the long series.
- **Spatial detail**: PKU GIMMS NDVI: 1/12° (0.0833°, ~9–10 km) global grid, GeoTIFF. | GIMMS-3G+ AVHRR: 0.0833° (~9.3 km at equator), NetCDF-4. | MOD13Q1: 250 m, Sinusoidal (SIN) grid, HDF-EOS. Native rasters are gridded, NOT admin-2 polygons — zonal-aggregate to district boundaries (e.g., GADM/GAUL) yourself. 250 m MODIS enables within-district cropland masking; ~9 km GIMMS/AVHRR is coarse for small districts.
- **Access method**: PKU GIMMS NDVI — public HTTPS direct download from Zenodo, NO account. GIMMS-3G+ and MOD13Q1 — NASA Earthdata authenticated download (Earthdata Login token / `.netrc`); registration required (free). Google Earth Engine server-side API is an alternative for the MODIS and legacy NDVI3g collections, allowing cropland-masked growing-season zonal means in-cloud with no local download.
- **License**: PKU GIMMS NDVI (Zenodo): CC-BY 4.0 (license id `cc-by-4.0`) — redistribution/reuse permitted with attribution. | MOD13Q1 (LP DAAC): verbatim "MODIS data and products acquired through the LP DAAC have no restrictions on subsequent use, sale, or redistribution" (the AWS Registry phrases the same product's license as CC-BY 4.0; both permit redistribution). | GIMMS-3G+ AVHRR (ORNL DAAC): EOSDIS "openly shared, without restriction" (US-government data). | Legacy GEE NASA/GIMMS/3GV0: public domain, without restriction on use and distribution.
- **Redistribution in public repo**: YES for all three. PKU GIMMS NDVI raw TIFFs redistributable with creator attribution (CC-BY 4.0); MOD13Q1 redistributable without restriction; GIMMS-3G+ redistributable with citation. Best practice for a reproducible repo: ship the download SCRIPT plus a small derived district panel rather than bulky raw rasters, though raw redistribution is legally permitted for all three.
- **Required citation**: PKU GIMMS NDVI: Li, M., Cao, S., Zhu, Z., Wang, Z., Myneni, R. B., & Piao, S. (2023). Spatiotemporally consistent global dataset of the GIMMS NDVI (PKU GIMMS NDVI) from 1982 to 2022 (V1.2). *Earth System Science Data*, 15, 4181–4203. https://doi.org/10.5194/essd-15-4181-2023 ; dataset DOI 10.5281/zenodo.8253971. | GIMMS-3G+: Pinzon, J. E., Pak, E. W., Tucker, C. J., Bhatt, U. S., Frost, G. V., & Macander, M. J. (2023). Global Vegetation Greenness (NDVI) from AVHRR GIMMS-3G+, 1981-2022 (V1). ORNL DAAC. https://doi.org/10.3334/ORNLDAAC/2187. | MOD13Q1: Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061 [Data set]. NASA LP DAAC. https://doi.org/10.5067/MODIS/MOD13Q1.061.
- **Fit notes**:
  1. Backbone: PKU GIMMS NDVI (1982–2022, CC-BY, no-auth Zenodo, orbital-drift/sensor-degradation corrected — longest spatiotemporally-consistent global series); optionally splice MOD13Q1 250 m from 2000 onward where finer cropland resolution matters (MODIS NDVI was designed for continuity with AVHRR NDVI).
  2. Apply a cropland mask so NDVI reflects agriculture only; for a global panel use a global cropland layer (ESA WorldCover/CCI-LC, Copernicus Global Land Cover, or GFSAD30 cropland).
  3. Aggregate over the GROWING SEASON, not calendar-year mean — the most common metric is seasonally-integrated NDVI (season-sum or peak/max-NDVI).
  4. Zonal-mean the masked growing-season metric to admin-2 polygons → one value per district per year.
  5. Google Earth Engine can do cropland mask + growing-season reduction + district zonal stats entirely server-side (cleanest reproducible path for MODIS).
- **Gotchas**:
  1. NDVI is a greenness PROXY, not measured yield — correlates with but does not equal production; treat as an instrument, not ground truth.
  2. Legacy GEE NASA/GIMMS/3GV0 (NDVI3g) ENDS 2013-12-16 (starts 1981-07) — do not mistake for the current long series; authoritative modern AVHRR product is GIMMS-3G+ (1982–2022, ORNL DAAC), corrected reprocessing is PKU GIMMS NDVI (Zenodo).
  3. GIMMS/AVHRR pixels are ~9 km — too coarse for small districts and clean cropland masking; prefer 250 m MOD13 for fine admin-2 work where its 2000+ window suffices.
  4. AVHRR↔MODIS splice introduces a sensor break (~2000); even the consolidated PKU version harmonizes, but control for a regime shift at the join (year/sensor fixed effects).
  5. Native data are gridded rasters in different CRSs (PKU/GIMMS = geographic 1/12°; MOD13 = sinusoidal) — reproject and zonal-aggregate to a chosen admin-2 set yourself; GADM vs GAUL vs national gazetteers change district counts and matching.
  6. Growing-season definition is region-specific (hemisphere, single vs double cropping); a fixed calendar window biases tropical/double-crop districts — use a phenology- or crop-calendar-driven season.
  7. Earthdata Login (free) is mandatory for ORNL DAAC and LP DAAC pulls, so a scripted-download repo must handle `.netrc`/token auth for those; PKU GIMMS NDVI on Zenodo needs NO auth, making it the most reproducible-without-credentials choice.
  8. The MOD13Q1 AWS bucket (`registry.opendata.aws/nasa-mod13q1`) is the PROTECTED `lp-prod-protected` bucket requiring NASA Earthdata-derived temporary AWS credentials — it is NOT anonymous/open S3.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


## Commodity prices (shock construction)


### World Bank "Pink Sheet" (Commodity Markets / CMO) + IMF Primary Commodity Price System (PCPS)
- **Provider**: World Bank Prospects Group (Pink Sheet / Commodity Markets Outlook); IMF Research Department (PCPS, dataflow IMF.RES:PCPS)
- **Role in panel**: Supplies the global "shift" (world commodity prices) for a district-year shift-share producer-price-shock index; the "share" is the user-supplied local crop mix.
- **Homepage**: https://www.worldbank.org/en/research/commodity-markets (Pink Sheet); https://data.imf.org/en/datasets/IMF.RES:PCPS (PCPS)
- **Download / API**: Pink Sheet monthly XLSX (1960M01-2026M05): https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx ; annual XLSX (1960-2025, nominal+real): .../CMO-Historical-Data-Annual.xlsx . IMF PCPS SDMX 2.1 REST (keyless): https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS/{COUNTRY}.{INDICATOR}.{DATA_TRANSFORMATION}.{FREQUENCY} e.g. .../G001.PCOFFOTM.USD.M?startPeriod=1990-01 ; CSV via header `Accept: application/vnd.sdmx.data+csv`; discovery via .../availableconstraint/IMF.RES,PCPS (1,270 series).
- **Coverage**: Pink Sheet: monthly nominal 1960M01-2026M05 (797 months) + annual nominal+real 1960-2025; updated monthly (next update July 2, 2026). PCPS: tested series (PCOFFOTM coffee, PALLFNF all-commodity) run 1992-M01 to 2026-M05 (practical start 1992, though constraint advertises 1946-01-01 to 2026-07-01); monthly cadence (UPDATE_DATE 2026-06-06).
- **Spatial detail**: None - single global/world benchmark price per commodity (PCPS COUNTRY=G001=World only). Spatial variation comes entirely from the local crop-mix shares.
- **Access method**: Bulk download + API, fully scriptable, no registration. (1) Pink Sheet: curl the two XLSX files; sheets "Monthly Prices"/"Monthly Indices" and "Annual Prices (Nominal)"/"(Real)". URL embeds a vintage segment (0050012026 now vs 0050012025 in 2025), so first scrape the commodity-markets landing page for the current CMO-Historical-Data-Monthly.xlsx link, then download. (2) PCPS: plain keyless GET to api.imf.org SDMX 2.1 (XML or CSV); key order COUNTRY.INDICATOR.DATA_TRANSFORMATION.FREQUENCY, DATA_TRANSFORMATION in {USD,INDEX,INDEX_PCH,INDEX_PCHY}, FREQUENCY in {A,Q,M}; codelists from .../dataflow/IMF.RES/PCPS?references=all.
- **License**: World Bank: CC BY 4.0 unless labeled otherwise (https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets), attribution format "The World Bank: Dataset name: Data source (if known)", with a carve-out that some third-party datasets may not be redistributed without the original provider's consent. IMF PCPS (embedded LICENSE string): "© International Monetary Fund Copyright. All Rights Reserved. https://www.imf.org/external/terms.htm"; metadata flags ACCESS_SHARING_LEVEL=PUBLIC_OPEN, SECURITY_CLASSIFICATION=PUB.
- **Redistribution in public repo**: Pink Sheet: yes with attribution (CC BY 4.0; CMO files carry no contrary label, but source notes credit third parties like Bloomberg/Datastream/Cotton Outlook, so keep the attribution sheet intact). IMF PCPS: no - despite the PUBLIC_OPEN flag, the IMF terms (https://www.imf.org/en/about/copyright-and-terms) permit only "free non-systematic downloading and/or printing... for personal, noncommercial usage only without any right to resell, redistribute, compile, or create derivative works" and require written permission to "copy or download IMF Content in any systematic way". Do not commit raw IMF data; script the keyless API fetch at build time.
- **Required citation**: World Bank, "World Bank Commodity Price Data (The Pink Sheet)", Washington, DC; attribute per WB dataset terms. IMF (suggested, from API metadata): "International Monetary Fund. Primary Commodity Price System (PCPS), https://data.imf.org/en/datasets//IMF.RES:PCPS. Accessed on [date]." Methodology: McGuirk & Burke (2020), "The Economic Origins of Conflict in Africa", JPE 128(10):3940-3997, doi:10.1086/709993; Ubilava, Hastings & Atalay (2023), "Agricultural Windfalls and the Seasonality of Political Violence in Africa", AJAE 105(5):1309-1332, doi:10.1111/ajae.12364.
- **Fit notes**:
  - These series are the "shift"; the "share" is a time-invariant local crop mix. PPI_lt = sum_j P_jt x N_jl, where N_jl are baseline-fixed district crop-area shares from a gridded crop map (M3/Monfreda, Ramankutty et al. 2008, 5-arcmin; or SPAM) aggregated to admin-2.
  - McGuirk-Burke (0.5-deg cells, Africa, 1989-2013): PPI over 11 traded crops using M3-Cropland circa-2000 shares, plus a consumer CPI from FAO Food Balance Sheet calorie shares (18 crops); their prices came from IMF IFS and World Bank GEM (indexed 100 in 2000), not the current PCPS portal or Pink Sheet file.
  - Ubilava et al. (1-deg cells, 51 African countries, 1997-2020): assign each cell its single major cereal (largest cropland fraction; harvest month from Sacks et al. 2010 calendars), use IMF-portal global prices (maize No.2 yellow Gulf, Thai 5% rice, sorghum No.2 yellow Gulf, No.1 HRW wheat Kansas City), mean-scaled/logged, interacting year-on-year price growth with harvest months.
  - For admin-2 x year: dot-product baseline district shares with annual (or crop-year-averaged monthly) Pink Sheet prices. Only the Pink Sheet (1960+) reaches before 1992; PCPS adds a clean monthly API from 1992 for Ubilava-style sub-annual harvest-timing designs.
- **Gotchas**:
  1. Pink Sheet URLs are vintage-stamped (current ...0050012026...; 2025 was ...0050012025...), so hard-coded links break roughly annually - scrape the landing page for the current link.
  2. No World Bank commodity API: api.worldbank.org/v2/sources (71 sources) has no commodity-price database, so the XLSX is the canonical programmatic artifact; databank.worldbank.org/databases/commodity-price-data is interactive only.
  3. PCPS tested series start 1992-M01 despite the 1946 constraint advertisement; papers using pre-1992 "IMF" prices used IFS, not PCPS - exact replication needs their replication archives.
  4. Legacy IMF bulk Excel is gone: https://www.imf.org/-/media/Files/Research/CommodityPrices/Monthly/ExternalData.ashx now 302-redirects to externaldata.pdf rather than serving the data.
  5. Units differ by commodity and source (USD/mt, cents/lb; indices 2010=100 at WB vs 2016=100 at IMF; pick PCPS DATA_TRANSFORMATION among USD/INDEX/INDEX_PCH/INDEX_PCHY); WB monthly prices are nominal, real series exist only in the annual file - deflator choice (e.g. MUV) is on you.
  6. PCPS key order is COUNTRY.INDICATOR.DATA_TRANSFORMATION.FREQUENCY with COUNTRY=G001 (not the legacy W00); wrong order or swapped dims returns a silent HTTP 200 with zero observations.
  7. Mapping WB/IMF commodity codes to crop-map crops needs a manual concordance (multiple coffee/rice/wheat benchmarks) - document which benchmark stands in for each crop.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


## Weather


### CHIRPS (Climate Hazards Group InfraRed Precipitation with Stations) v2.0
- **Provider**: Climate Hazards Center, University of California Santa Barbara (developed with USGS)
- **Role in panel**: Supplies the precipitation/climate covariate layer — district-year rainfall totals, anomalies, and SPI feeding the agricultural-output side of the conflict x agriculture panel.
- **Homepage**: https://www.chc.ucsb.edu/data/chirps (v3: https://www.chc.ucsb.edu/data/chirps3)
- **Download / API**: https://data.chc.ucsb.edu/products/CHIRPS-2.0/ — monthly: global_monthly/tifs/chirps-v2.0.YYYY.MM.tif.gz (~13.8 MiB); also global_monthly/netcdf/, global_annual/tifs/chirps-v2.0.YYYY.tif (~55 MiB), global_daily/, global_dekad/, global_pentad/. v3 at https://data.chc.ucsb.edu/products/CHIRPS/v3.0/ (monthly/daily/pentads/dekads/annual/prelim + README-CHIRPSv3.0.txt).
- **Coverage**: v2.0 January 1981 to near-present (monthly server files run 1981.01 through 2026.04 as of 2026-06-11; 544 monthly files total). Final monthly data arrives ~third week of the following month; a rapid/prelim product (GTS + Mexico stations only) appears 2 days after each pentad. v2 production ends after December 2026; v3 covers 1981 to near-present.
- **Spatial detail**: 0.05 degree (~5.5 km) raster, quasi-global 50S-50N, all longitudes (v2.0); v3.0 extends to 60S-60N at the same resolution.
- **Access method**: Bulk download via anonymous HTTPS directory listing — fully scriptable with wget/curl, no auth, no registration. Iterate YYYY=1981..2026, MM=01..12, GET the monthly .tif.gz, gunzip, run zonal stats against admin-2 polygons; or use the NetCDF under global_monthly/netcdf/. Also distributed via Google Earth Engine and ClimateSERV for server-side aggregation.
- **License**: Public domain — CHC page states "Pete Peterson has waived all copyright and related or neighboring rights to CHIRPS. CHIRPS data is in the public domain" (CC0-style). v3.0 page is dual-worded: public domain AND CC-BY 4.0.
- **Redistribution in public repo**: Yes — v2 is explicitly public domain, so raw rasters and derived admin-2 aggregates may be committed. For v3 outputs, attribute under CC-BY 4.0 to be safe. The full global monthly v2 archive is ~544 files x ~14 MiB (~7.5 GB), too large for GitHub: script the download and commit only the admin-2 x month/year aggregates.
- **Required citation**: Funk, C., Peterson, P., Landsfeld, M., Pedreros, D., Verdin, J., Shukla, S., Husak, G., Rowland, J., Harrison, L., Hoell, A., Michaelsen, J. (2015). "The climate hazards infrared precipitation with stations—a new environmental record for monitoring extremes." Scientific Data 2, 150066. doi:10.1038/sdata.2015.66. (README alternatively cites Funk et al. 2014, USGS Data Series 832.) For v3: Funk, C., Peterson, P., Harrison, L. et al. (2026), "The Climate Hazards Center Infrared Precipitation with Stations, Version 3." Sci Data 13, 718. doi:10.1038/s41597-026-07096-4.
- **Fit notes**:
  - Deterministic file-per-month URLs make the pipeline fully reproducible over 1981-present.
  - Compute area-weighted zonal means per admin-2 polygon from monthly tifs, then aggregate to calendar-year or growing-season totals/anomalies/SPI. Do not use the pre-made annual tifs (they lag and only support calendar years).
  - 0.05 deg is fine enough that even small districts contain multiple cells.
  - Coverage stops at 50S-50N (v2), excluding Canada, northern Europe (most of UK/Scandinavia/Baltics), Russia, northern Kazakhstan/Mongolia, southern Chile/Argentina. For a truly global panel, fill >50N (or >60N under v3) with ERA5 total precipitation from the Copernicus CDS (monthly means 1940 onwards, 0.25 x 0.25 deg, updated daily with ~5-day latency; monthly means ~6th of each month).
  - Add a source flag plus an overlap-zone calibration check, since gauge-satellite CHIRPS and reanalysis ERA5 differ in level.
- **Gotchas**:
  1. 50S-50N cutoff (v2) excludes high-latitude agriculture entirely; even v3's 60S-60N misses most of Canada/Russia/Scandinavia — use the ERA5 fallback.
  2. v2 production ends after December 2026: pin the version string now and plan a v3 migration. v2 and v3 values differ — never mix versions within the panel.
  3. Only use final files from global_monthly/; the rapid pentad product is not final.
  4. Pre-made annual tifs lag (chirps-v2.0.2024.tif still latest on 2026-06-11); v3's dual public-domain/CC-BY wording is internally inconsistent — attribute regardless.
  5. Monthly tifs are gzip-compressed (.tif.gz) and must be decompressed; ocean cells use a nodata sentinel that must be masked before zonal stats — read the exact nodata value from the raster metadata, do not guess.
  6. ERA5 fallback registration requirement and exact licence name are not stated on the CDS product page — verify the Copernicus licence-to-use terms before committing ERA5-derived data to a public repo.
  7. The peer-reviewed v2 citation (Funk et al. 2015 Sci Data) differs from the README's suggested USGS DS-832 citation; most journals expect the 2015 Sci Data one.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### ERA5 / ERA5-Land reanalysis (Copernicus CDS) + SPEIbase global drought index (SPEIbase v2.11 / DOI-citable v2.10)
- **Provider**: ERA5 & ERA5-Land: Copernicus Climate Change Service (C3S) / ECMWF, via the Climate Data Store (CDS). SPEIbase: EEAD-CSIC & IPE-CSIC (Beguería & Vicente-Serrano), Spain.
- **Role in panel**: Climate layer of the conflict-agriculture district-year panel — ERA5/ERA5-Land supply temperature and rainfall controls plus rainfall-shock instruments; SPEIbase supplies a ready-made, cross-region-comparable standardized drought index.
- **Homepage**: ERA5-Land: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land | ERA5 single levels: https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels | SPEIbase: https://spei.csic.es/database.html
- **Download / API**: ERA5/ERA5-Land via CDS API endpoint https://cds.climate.copernicus.eu/api (Python `cdsapi>=0.7.7`; collection ids `reanalysis-era5-single-levels`, `reanalysis-era5-land`). SPEIbase (no API): per-timescale global netCDF spei01.nc … spei48.nc — v2.11 direct HTTP from the viewer dir, e.g. https://spei.csic.es/spei_database_2_11/nc/spei01.nc (no account); DOI-citable v2.10 from DIGITAL.CSIC handle https://digital.csic.es/handle/10261/364137 (bitstreams digital.csic.es/bitstream/10261/364137/<n>/spei01.nc; DOI https://doi.org/10.20350/digitalcsic/16497).
- **Coverage**: ERA5 single levels: 1940–present, hourly, updated daily (~5-day latency; ERA5T provisional, revised ~2–3 months later). ERA5-Land: Jan 1950–present, hourly, updated daily (~5-day latency; consolidated lags 2–3 months). SPEIbase: site current v2.11 = Jan 1901–Dec 2024 (CRU TS 4.09); DOI-minted v2.10 = Jan 1901–Dec 2023 (CRU TS 4.08, issued 2024-07-19); ~annual updates.
- **Spatial detail**: ERA5 single levels 0.25° (~31 km) hourly; ERA5-Land 0.1° (~9 km) hourly; SPEIbase 0.5° (~55 km) monthly, multiscalar SPEI at 1–48-month windows.
- **Access method**: ERA5/ERA5-Land: register a free ECMWF/CDS account; manually accept each dataset's Terms of use once on its page (required before any API call); place Personal Access Token in $HOME/.cdsapirc (two lines: `url:`, `key:`); `pip install "cdsapi>=0.7.7"` and submit scripted requests by variable/year/month/area. SPEIbase: open bulk download, no account — fetch netCDF directly from the v2.11 viewer `nc/` directory (HTTP) or v2.10 DIGITAL.CSIC bitstreams. Registration: yes for ERA5/ERA5-Land, no for SPEIbase.
- **License**: ERA5/ERA5-Land: CC-BY-4.0 (replaced the "Licence to use Copernicus Products" on 2 July 2025); attribution = cite dataset DOI, credit Copernicus, carry the EC/ECMWF non-responsibility disclaimer. SPEIbase: Open Database License (ODbL) with contents under DbCL (attribution + share-alike) per the authoritative DIGITAL.CSIC/DataCite record; site texts/images under CC-BY 3.0.
- **Redistribution in public repo**: ERA5/ERA5-Land: yes — CC-BY-4.0 permits raw redistribution with attribution (DOIs 10.24381/cds.adbb2d47, 10.24381/cds.e2161bac), Copernicus credit, and disclaimer. SPEIbase: yes but conditional — ODbL requires attribution to SPEIbase/DIGITAL.CSIC, retaining ODbL share-alike on any redistributed/derived database, and no technical restrictions (a derived admin-2 panel may itself need ODbL).
- **Required citation**: Hersbach, H. et al. (2023), ERA5 hourly data on single levels from 1940 to present, C3S CDS, DOI 10.24381/cds.adbb2d47. Muñoz Sabater, J. (2019), ERA5-Land hourly data from 1950 to present, C3S CDS, DOI 10.24381/cds.e2161bac. Beguería, S.; Vicente-Serrano, S.M.; Reig-Gracia, F.; Latorre Garcés, B. (2024), SPEIbase v.2.10 [Dataset], DIGITAL.CSIC, DOI 10.20350/digitalcsic/16497; plus method paper Vicente-Serrano, S.M., Beguería, S., López-Moreno, J.I. (2010), J. Climate 23(7): 1696–1718, DOI 10.1175/2009JCLI2909.1.
- **Fit notes**:
  - All three are gridded rasters: zonally aggregate onto admin-2 polygons (GADM/GAUL), then collapse to year. Use area- or cropland/population-weighted cell means per district.
  - ERA5/ERA5-Land annual features: growing-season mean 2m temperature, total precipitation, degree-days/heat extremes; supply weather controls and rainfall-shock instruments.
  - SPEIbase: standardized drought anomaly (annual mean SPEI, min SPEI, or count of months with SPEI < −1.5) at a chosen window — SPEI-12 for annual hydrological drought, SPEI-3/6 for crop-season.
  - Temporal fit: SPEIbase (1901–2024) is the long-history drought workhorse; ERA5 (1940–) and ERA5-Land (1950–) give richer, higher-resolution weather controls for the post-1940/1950 window.
- **Gotchas**:
  1. SPEIbase 0.5° (~55 km) cells are coarse vs small admin-2 units — one cell can span several districts, giving little within-country variation and risking spatial autocorrelation; prefer ERA5-Land 0.1° where it covers the period.
  2. Version vs DOI: site advertises v2.11 (Dec 2024, CRU TS 4.09) but the latest minted DataCite/DIGITAL.CSIC DOI is v2.10 (Dec 2023, CRU TS 4.08); no DOI exists for v2.11 — pin the exact version/DOI downloaded.
  3. License discrepancy: Google Earth Engine catalog (CSIC_SPEI_2_10) labels SPEIbase CC-BY-4.0, but the authoritative DIGITAL.CSIC/DataCite metadata is ODbL + DbCL — treat ODbL share-alike as binding.
  4. ERA5 licence timing: CC-BY-4.0 took effect 2 July 2025; data pulled earlier fell under the older Copernicus licence — for a clean release, (re)download/accept under CC-BY-4.0 and keep attribution + EC/ECMWF disclaimer.
  5. ERA5 manual step: click-accept each dataset's Terms of use once on the website before the CDS API returns data — the one non-scriptable step.
  6. ERA5T vs ERA5: the most recent ~3 months are provisional (ERA5T) and can be revised; freeze a cutoff date.
  7. ERA5 total precipitation is an accumulated flux (m per accumulation step; hourly vs daily handling differs) — verify units before building rainfall shocks.
  8. ERA5-Land is land-only (no values over open ocean/large water bodies) — coastal/island admin-2 cells may be partly empty and need masking.
  9. SPEIbase pre-~1950 rests on sparse CRU TS station inputs, so historical SPEI in data-poor regions (much of Africa/interior Asia) is more uncertain than the 1901 start implies.
  10. DIGITAL.CSIC sits behind an Anubis (v1.25.0) anti-bot wall that blocks plain scripted GETs — use the v2.11 viewer `nc/` HTTP links or a browser-grade client/headers.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


## Controls


### Gridded population grids — HYDE 3.3/3.4 + WorldPop (Global_2000_2020) + GPWv4 Rev11
- **Provider**: HYDE: PBL Netherlands Environmental Assessment Agency / Utrecht University (Klein Goldewijk et al.). WorldPop: WorldPop Programme, University of Southampton. GPWv4: NASA SEDAC / CIESIN, Columbia University (now distributed via NASA Earthdata).
- **Role in panel**: Population denominator/control layer (per-capita normalization and population-weighted aggregation of conflict and agriculture variables) for the admin-2 x year panel.
- **Homepage**: HYDE: https://landuse.sites.uu.nl/hyde-project/ (PBL: https://www.pbl.nl/en/image/links/hyde) | WorldPop: https://hub.worldpop.org/project/categories?id=3 | GPWv4: https://www.earthdata.nasa.gov/data/projects/gpw
- **Download / API**: WorldPop (open Apache index, no login): https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/<year>/ (also 100m unconstrained under /GIS/Population/Global_2000_2020/, constrained 2020 under /GIS/Population/Global_2000_2020_Constrained/); GeoTIFFs via wget/curl. WorldPop REST API: https://api.worldpop.org/v1 . GPWv4 Rev11 Population Count: https://www.earthdata.nasa.gov/data/catalog/sedac-ciesin-sedac-gpwv4-popcount-r11-4.11 ; DOI https://doi.org/10.7927/H4JW8BX5 . HYDE 3.3: Utrecht Yoda DOI https://doi.org/10.24416/UU01-AEZZIT (landing https://public.yoda.uu.nl/geo/UU01/AEZZIT.html).
- **Coverage**: HYDE 3.3: 10,000 BCE–2023 CE; HYDE 3.4: 10,000 BCE–2025 CE (decadal pre-2000, annual from 2000; total/urban/rural/density layers); 3.5 in prep. WorldPop unconstrained annual 2000–2020 (21 layers); Global2 product covers 2015–2030. GPWv4 Rev11: 5 snapshots only — 2000, 2005, 2010, 2015, 2020 (no annual, nothing pre-2000). Cadence: HYDE versioned; WorldPop periodic; GPWv4 Rev11 no new revision planned.
- **Spatial detail**: GPWv4 Rev11: 30 arc-sec (~1 km) raster, with 2.5/15/30 arc-min and 1-degree aggregates. WorldPop: native 100 m (3 arc-sec) per-country, 1 km (30 arc-sec) global mosaics. HYDE: 5 arc-min (~85 km² per cell, ~10 km) global raster. All are gridded rasters; none natively admin-2.
- **Access method**: Fully scriptable bulk download. WorldPop (no auth): recursive wget/curl against the open directory index. GPWv4: search the collection/DOI on NASA Earthdata Search; programmatic pull needs a free NASA Earthdata Login token (curl bearer token or the earthaccess Python library); the legacy SEDAC portal is retired/unreliable, use Earthdata. HYDE: download zipped GeoTIFF/ASC archives from Utrecht Yoda via DOI 10.24416/UU01-AEZZIT (open, no login).
- **License**: WorldPop: CC BY 4.0 (verbatim on hub.worldpop.org). GPWv4: openly shared without restriction per EOSDIS Data Use and Citation Guidance (verbatim on Earthdata page). HYDE: Creative Commons Attribution (CC BY); exact CC BY version string for 3.3 not verbatim-confirmed (Yoda page behind anti-bot wall).
- **Redistribution in public repo**: Yes, with attribution and license notice (CC BY 4.0 / open EOSDIS terms permit redistribution and adaptation). Prefer Git LFS or release-asset/external hosting over committing large global rasters.
- **Required citation**: GPWv4: CIESIN, Columbia University. 2018. Gridded Population of the World, Version 4 (GPWv4): Population Count, Revision 11. NASA SEDAC. https://doi.org/10.7927/H4JW8BX5 . WorldPop: WorldPop, University of Southampton, Global High Resolution Population Denominators Project (Bondarenko et al., 2020; Gates Foundation OPP1134076). https://dx.doi.org/10.5258/SOTON/WP00660 . HYDE: Klein Goldewijk, K., A. Beusen, J. Doelman, E. Stehfest (2017). Anthropogenic land use estimates for the Holocene – HYDE 3.2. ESSD 9, 927–953. https://doi.org/10.5194/essd-9-927-2017 (provider instructs citing the 3.2 paper for 3.3; dataset DOI 10.24416/UU01-AEZZIT).
- **Fit notes**:
  - For a 1989–present span no single product fits; population is a denominator/control so coarse resolution is acceptable.
  - 1989–1999: use HYDE 5 arc-min grids (the only product reaching pre-2000); 1989 requires interpolation between the 1980 and 1990 steps.
  - 2000–2020: switch to WorldPop annual 1 km for better admin-2 fidelity; extend 2021–present with WorldPop Global2 (2015–2030) projections.
  - GPWv4 Rev11 (1 km, 5-year snapshots) is the cleanest census-anchored benchmark for cross-checking, not a continuous series.
  - Build the panel by zonal-summing each year's grid over time-consistent admin-2 polygons (GADM); the same grids give population weights for aggregating conflict/agriculture layers.
- **Gotchas**:
  1. Pre-2000 gap: neither GPWv4 nor WorldPop covers before 2000; the 1989–1999 segment must come from HYDE (decadal pre-2000; no discrete 1989 grid, interpolate 1980↔1990).
  2. Resolution mismatch at the 2000 splice: HYDE ~10 km vs WorldPop/GPWv4 ~1 km creates a discontinuity in zonal estimates — document and rescale/harmonize.
  3. GPWv4 is NOT annual (only 5-year snapshots); do not treat as continuous.
  4. GPWv4 access migrated SEDAC→Earthdata (migration ongoing through end-2026); programmatic download requires a free NASA Earthdata Login. The standalone SEDAC data-download portal is retired and effectively dead/timing out.
  5. WorldPop has constrained vs unconstrained and UN-adjusted vs not; the 2000–2020 annual series is unconstrained — prefer UN-adjusted (..._1km_UNadj) for cross-country denominators and pick one variant consistently.
  6. HYDE 3.3 CC BY version not verbatim-confirmed: the Yoda landing page is behind an Anubis anti-bot wall; verify the exact CC BY version before committing raw HYDE files publicly.
  7. All three are gridded, not admin-2; run your own zonal aggregation, and use a time-consistent boundary vintage to avoid spurious jumps.
  8. Large files: prefer Git LFS or external hosting over committing global rasters even though the licenses permit redistribution.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)


### Harmonized global DMSP-VIIRS nighttime lights, 1992-2024 (Li et al.; figshare v10)
- **Provider**: Xuecao Li, Yuyu Zhou, Min Zhao, Xia Zhao (harmonized dataset on figshare). Underlying raw series: Earth Observation Group (EOG), Payne Institute for Public Policy, Colorado School of Mines (DMSP via US Air Force Weather Agency; VIIRS via NOAA/NASA).
- **Role in panel**: Economic-activity / development proxy at the district-year level, a control for the agricultural-output layer of the conflict-agriculture panel.
- **Homepage**: https://figshare.com/articles/dataset/9828827 (record title now 1992-2024). Paper: https://doi.org/10.1038/s41597-020-0510-y. Raw: https://eogdata.mines.edu/products/dmsp/ and https://eogdata.mines.edu/products/vnl/
- **Download / API**: Figshare REST (no auth): https://api.figshare.com/v2/articles/9828827 (latest) or pinned https://api.figshare.com/v2/articles/9828827/versions/10 — JSON lists 34 files with download_url https://ndownloader.figshare.com/files/<file_id> (302 to signed S3, no login) + supplied MD5 per file. Examples: 1992 = files/17626052, 2024 = files/57065306. Download-all zip: https://ndownloader.figshare.com/articles/9828827/versions/10 (200, application/zip, 1,091,941,744 bytes).
- **Coverage**: Harmonized annual 1992-2024 (33 years) in v10 (posted 2025-08-10): temporally calibrated DMSP-OLS 1992-2013 (calDMSP) + DMSP-like converted VIIRS 2014-2024 (simVIIRS), plus an extra 2013 simVIIRS overlap file. Cadence: irregular figshare version bumps, roughly annual. Underlying EOG: DMSP v4 composites 1992-2013 (+pre-dawn F15/F16 extension to 2019); Annual VNL V2.x 2012-present.
- **Spatial detail**: Global GeoTIFF raster, 30 arc-seconds (~1 km at equator), extent 180W-180E, 65S-75N. Values are DMSP-style digital numbers (DN 0-63) for ALL years, including VIIRS-derived 2014-2024. DMSP satellites: F10 (1992-94), F12 (1995-96), F14 (1997-2003), F16 (2004-09), F18 (2010-13).
- **Access method**: Bulk download, fully scriptable, zero registration. (1) GET the versions/10 API JSON; (2) parse the files array; (3) curl/wget each download_url (follows 302 to signed S3); (4) verify against supplied_md5. ~21.8-38.8 MB per annual GeoTIFF (the 40.9 MB file is the extra 2013 overlap), ~1.09 GB total. Avoid the EOG raw route for reproducibility (login-gated; see Gotchas). A GEE mirror exists (projects/sat-io/open-datasets/Harmonized_NTL/dmsp and /viirs) but covers only 1992-2021 (figshare v7).
- **License**: CC BY 4.0 (figshare API license field "CC BY 4.0", https://creativecommons.org/licenses/by/4.0/); paper also CC BY 4.0. Underlying EOG products are CC BY 4.0 with required credit "Image and data processing by Earth Observation Group, Payne Institute for Public Policy, Colorado School of Mines. DMSP data collected by US Air Force Weather Agency."
- **Redistribution in public repo**: Yes for the harmonized GeoTIFFs (CC BY 4.0, with attribution to Li et al. + figshare DOI). Caveat: ~1.09 GB / 22-39 MB per file — under GitHub's 100 MB/file limit but heavy; prefer scripted download + MD5 verification, or commit only derived admin-2 zonal statistics. EOG raw files are CC BY 4.0 too, but access gating makes an EOG-based script non-reproducible without a paid subscription.
- **Required citation**: Paper: Li, X., Zhou, Y., Zhao, M. & Zhao, X. A harmonized global nighttime light dataset 1992-2018. Scientific Data 7, 168 (2020). https://doi.org/10.1038/s41597-020-0510-y. Dataset (pin version): Li, Xuecao; Zhou, Yuyu; Zhao, Min; Zhao, Xia (2025). Harmonization of DMSP and VIIRS nighttime light data from 1992-2024 at the global scale. figshare. https://doi.org/10.6084/m9.figshare.9828827.v10. If using EOG raw products, additionally cite EOG plus the product paper (e.g., Elvidge et al. 2017 for VNL).
- **Fit notes**:
  - A single internally consistent annual ~1 km global raster for 1992-2024 in one unit (DMSP-like DN 0-63): one zonal-statistics pass (sum and/or mean of DN) over admin-2 polygons (GADM/GAUL) yields the full panel — no user-side DMSP/VIIRS splicing, intercalibration, or unit conversion.
  - Mask DN<=7 as the authors recommend (dim pixels unreliable); apply consistently.
  - Overlaps UCDP GED (1989-) for all but 1989-91 and fully covers ACLED-era years; 65S-75N excludes only high-latitude areas irrelevant to agriculture.
  - Use DN_NTL_2013_simVIIRS.tif to test sensor-transition robustness (compare calDMSP vs simVIIRS zonal sums in 2013; add a post-2013 regime dummy).
- **Gotchas**:
  1. Version drift: DOI suffix changes per version (v7=1992-2021, v10=1992-2024); the GEE mirror is stuck at 1992-2021 (v7). Pin .v10 in scripts and citation.
  2. Peer-reviewed validation (Sci Data 2020) covers only 1992-2018; 2019-2024 layers were added via figshare version updates with no separately confirmed peer-reviewed validation.
  3. 2014-2024 values are SIMULATED DMSP-like DN from VIIRS via a sigmoid fit on 2013 overlap — top-coded at DN 63 (urban-core saturation across the whole series); VIIRS's superior dynamic range is discarded, so expect attenuated growth signals in bright districts.
  4. Authors instruct using DN>7 pixels; inconsistent masking shifts district sums.
  5. DMSP blooming/overglow spreads light into neighboring rural admin-2 units, a known source of spurious spatial correlation.
  6. Satellite changeovers (F10/F12/F14/F16/F18) leave residual intercalibration steps; year fixed effects absorb only the global component.
  7. The download-all zip endpoint ignores HTTP Range (returns full 1.09 GB, 200 not 206) — assume no resume; per-file downloads with MD5 checks are safer.
  8. Use api.figshare.com, not the figshare HTML article page (returns an anti-bot interstitial, HTTP 202, to script user-agents). Signed S3 URLs expire in ~10 s (X-Amz-Expires=10) — pipe the 302 directly rather than caching URLs.
  9. Raw EOG route: VNL file URLs 302 to a Keycloak login (free account with verified e-mail); effective 2026-06-01, programmatic OpenID access is restricted to paid subscribers (token endpoint https://eogauth-new.mines.edu/realms/eog/protocol/openid-connect/token, grant_type=password, 5-min tokens). Do not build the pipeline on EOG endpoints.
- **Facts verified**: 2026-06-11 (live re-fetch of provider pages)

## Colonial legacy (study-subset moderator layer)

Three small, static, country-level sources added 2026-07-09 for the
Africa + South America + Caribbean study subset (see docs/CODEBOOK.md,
"Colonial legacy layer"). All are TIME-INVARIANT country attributes broadcast
onto every district-year by `iso3` — moderators to interact with the
time-varying conflict/output shocks, never standalone within-country regressors.
Acquisition: `src/acquisition/12_download_colonial.py`; cleaning:
`src/cleaning/12_colonial.py`.

### COLDAT — Colonial Dates Dataset (Becker 2019, v3 2023)
- **Provider**: Bastian Becker (Univ. of Bremen, SOCIUM); Harvard Dataverse.
- **Role in panel**: colonizer identity (8 European powers) + colonial start/end
  years → `col_start_year`, `col_end_year`, `col_duration_years`,
  `coldat_colonizer_last`, `coldat_n_colonizers`.
- **Homepage / DOI**: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/T9SDEW
- **Download / API**: direct, no auth. `COLDAT_colonies.tab` (wide, one row per
  country) = Dataverse datafile id 7416946 (`/api/access/datafile/7416946?format=original`).
- **Coverage**: contemporary nation-states; 79/79 of our study countries match
  by name (regex). Ethiopia & Liberia coded not-colonized (all-zero dummies).
- **Unit**: country (time-invariant). Uses the `_mean` aggregation of dates
  (author-preferred for statistics).
- **License**: CC0 1.0 (public domain) — fully redistributable, raw or derived.
- **Redistribution in repo**: yes (CC0). Raw gitignored per repo convention;
  re-pulled by the acquisition script.
- **Citation**: Becker, Bastian (2019). "Introducing COLDAT: The Colonial Dates
  Dataset." SOCIUM/SFB 1342 WorkingPaper 02/2019.
- **Gotchas**: join is by COUNTRY NAME (no ISO in the .tab) — resolved via
  `country_converter` regex. "Last colonizer" (max `colend`) can reflect a brief
  post-war administration (Libya→British, Somalia→British, Morocco→Spanish); we
  therefore take colonizer identity from QoG `ht_colonial` (below) and keep
  COLDAT's `coldat_colonizer_last` only as a cross-check.
- **Facts verified**: 2026-07-09 (Dataverse API + live download).

### QoG Standard Cross-Section, version jan22 (ht_colonial + lp_legor)
- **Provider**: Quality of Government Institute, Univ. of Gothenburg.
- **Role in panel**: `ht_colonial` (Hadenius–Teorell colonizer identity, complete
  for our 79) → `colonizer`; `lp_legor` (La Porta legal origin) → `legal_origin`,
  `legal_origin_filled`, `civil_vs_common`. Also supplies the `ccodecow`↔`ccodealp`
  (COW code ↔ ISO3) bridge used to key the COW file.
- **Homepage**: https://www.qog.pol.gu.se/data/datadownloads/qogstandarddata
- **Download / API**: direct CSV https://www.qogdata.pol.gu.se/data/qog_std_cs_jan22.csv
- **Coverage**: `ht_colonial` 79/79; `lp_legor` 70/79 (9 blanks imputed from
  colonizer identity and flagged `legal_origin_imputed`).
- **Unit**: country cross-section (one row per country; time-invariant here).
- **License**: free academic/research use with citation (QoG terms). Ship derived
  columns with citation; do not re-host the full compiled bundle.
- **Citation**: Teorell, Jan et al. (2022). "The Quality of Government Standard
  Dataset, version Jan22." Univ. of Gothenburg, QoG Institute. Underlying:
  Hadenius & Teorell (colonial origin); La Porta et al. (1999, legal origins).
- **Gotchas**: **pin jan22** — `lp_legor` was dropped from QoG ≥ jan23.
  `ht_colonial` codes: 0 None,1 Dutch,2 Spanish,3 Italian,4 US,5 British,6 French,
  7 Portuguese,8 Belgian,9 British-French,10 Australian. `lp_legor`: 1 English,
  2 French,3 Socialist,4 German,5 Scandinavian.
- **Facts verified**: 2026-07-09 (live download; coverage checked vs the 79).

### Correlates of War — State System Membership (states2016, v2016)
- **Provider**: Correlates of War Project (correlatesofwar.org).
- **Role in panel**: `styear` (year the state entered the international system) →
  `independence_year` and the one time-VARYING colonial column
  `years_since_independence = year − independence_year`.
- **Homepage**: https://correlatesofwar.org/data-sets/state-system-membership/
- **Download / API**: direct CSV https://correlatesofwar.org/wp-content/uploads/states2016.csv
- **Coverage**: 79/79 via the QoG `ccodecow`→`iso3` bridge; current spell
  (`endyear==2016`), max `styear` for multi-spell states.
- **License**: free use, citation required, no paywalling of access.
- **Citation**: Correlates of War Project (2017). "State System Membership List,
  v2016." http://correlatesofwar.org
- **Gotchas**: COW state-system entry ≠ decolonization for a few countries
  (occupation/protectorate artifacts): e.g. Haiti entry 1934 (US-occupation end)
  vs COLDAT decolonization 1804; Ethiopia 1941. Use `col_end_year` (COLDAT) for
  "freed from colonial rule"; `independence_year` for "years in the state system."
  coco has no COW code class → bridged via QoG.
- **Facts verified**: 2026-07-09 (live download; bridge checked vs the 79).

## Pest / crop disease (Africa-only shock layer)

Two georeferenced, dated, plausibly-EXOGENOUS crop-pest sources added 2026-07-09
for the study subset (see docs/CODEBOOK.md, "Pest layer — Africa"). **By design
these cover Africa only** — no georeferenced desert-locust or fall-armyworm data
exists for South America or the Caribbean (species-range fact, not a data gap),
so the pest columns are NaN for all Americas rows. Both are MONITORING/SURVEY
feeds: a missing district-year is *not observed*, never *pest-free*, so they are
never zero-filled. Acquisition: `src/acquisition/13_download_faw.py`,
`14_download_locust.py`; cleaning: `src/cleaning/13_faw.py`, `14_locust.py`
(point-in-polygon to the CGAZ admin-2 spine).

### FAO FAMEWS — Fall Armyworm trap monitoring
- **Provider**: FAO Fall Armyworm Monitoring & Early Warning System (FAMEWS).
- **Role**: invasion-front timing of fall armyworm (Spodoptera frugiperda), a
  maize pest that spread across Africa from 2016 → `faw_first_detection_year`,
  `years_since_faw_arrival`, `faw_present`, `faw_confirmed_sum`, `faw_catch_rate`,
  `faw_n_trap_checks`. The district's first FAW year is driven by the continental
  invasion wave, not local politics → the cleaner exogenous pest shock.
- **Download / API**: FAO Open Data catalog, dataset UUID
  13a9fda3-7f3e-4e6d-86aa-13e8c73cc0e4; BigQuery-backed CSV, no key
  (`.../api/v2/bigquery?sql_url=...famews-...&dim_country=All%20Countries&period=all`).
- **Coverage**: 15,220 dated georeferenced trap checks, 2018-2025 (usable
  2018-2023; collapses after). **42 of our African countries monitored** (35 with
  a confirmed detection); **0 South America / Caribbean** (bar 2 zero-FAW Peru
  points, masked out).
- **Unit**: trap check (lat/lon + date) → district-year via point-in-polygon.
- **License**: stated CC-BY-3.0-IGO, but this is the same FAO Open Data /
  Hand-in-Hand platform whose desert-locust dataset carries a conflicting
  CC-BY-NC-SA-3.0-IGO statement (see locust entry) → **treat as NC-SA by default**;
  confirm before any *public* release of derived FAW columns.
- **Redistribution in repo**: raw gitignored, re-pulled by the acquisition script
  (repo convention); derived columns only, private/internal use.
- **Gotchas**: opt-in app + effort bias — normalize by `faw_n_trap_checks`, never
  read a monitored-but-negative district-year as pest-free vs an unmonitored NaN.
  It is trap monitoring (adult moth catches), a pest-pressure proxy, not crop
  damage. Pin/archive the pull (mutable endpoint).
- **Facts verified**: 2026-07-09 (live pull; 99.8% of points joined a district).

### FAO Locust Hub / RAMSES — Desert Locust swarms + hopper bands
- **Provider**: FAO Desert Locust Information Service (DLIS) / Locust Hub.
- **Role**: gregarious, crop-destroying desert-locust (Schistocerca gregaria)
  activity → `dl_present_flag`, `dl_swarm_obs`, `dl_band_obs`, `dl_gregarious_obs`,
  `dl_area_treated_ha`, `dl_first_gregarious_year`. Plague dynamics are
  wind/weather-driven (not conflict-caused) → an exogenous agricultural shock.
- **Download / API**: FAO Open Data catalog, "Desert locusts observations
  (Global)", UUID 088f29ea-6e33-4e9c-8779-9b64dd2450b0; BigQuery CSV with
  `cat=SWARM` / `cat=BAND`, no key.
- **Coverage**: 65,113 gregarious observations in the raw pull, dated 2004-**2026**
  (incl. the 2019-2022 upsurge, 2020 = the peak). The study panel caps at 2025, so
  7 out-of-window 2026 observations are dropped at merge (logged); **panel locust
  values are 2004-2025**. 20 of our African countries — the desert-locust belt
  (Sahel, Horn, N. Africa): DZA EGY LBY MAR TUN, MRT MLI NER TCD SEN, SDN SSD ERI
  DJI ETH SOM KEN UGA TZA COD. **0 South America / Caribbean.**
- **Unit**: field observation (lat/lon + date) → district-year via point-in-polygon.
- **License**: FAO. The Observations page states CC-BY-3.0-IGO while a sibling
  "Hand-in-Hand" page states CC-BY-NC-SA-3.0-IGO → **treat as NC-SA by default**;
  resolve before any *public* release of derived locust columns (private/internal
  use is low-risk).
- **Redistribution in repo**: raw gitignored, re-pulled by the acquisition script;
  derived columns only, private/internal use pending the license resolution above.
- **Gotchas**: the "smart-csv" preview endpoint hard-caps at 50,000 rows per
  request; only `cat=SWARM` (37k) and `cat=BAND` (28k) return COMPLETE — ADULT /
  HOPPER / NO-LOCUST each truncate at 50k and are excluded (also lower-intensity).
  So this layer is the **gregarious (damaging) phase only**, which is the
  agriculturally-relevant signal. Survey-effort bias: presence-only within the
  belt; unmonitored = NaN, not zero.
- **Facts verified**: 2026-07-09 (live pull; 98.2% of points joined a district).
