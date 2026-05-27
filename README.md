# Police Resource Allocation Dashboard

Dashboard for **TU/e 4CBLW020 — Real-World Crime project**.

Compares the current officer distribution across the 43 territorial police
forces of England & Wales against a *harm-weighted* allocation derived from
the Cambridge Crime Harm Index (CCHI). Shows whether forces are
over- or under-resourced relative to the harm they handle.

## What's in the dashboard

1. **Choropleth map** — coloured by allocation gap (officer share minus
   harm share). Green = over-resourced, red = under-resourced.
2. **Radar chart** — selected force's crime mix across 13 Home Office
   recorded-crime categories, normalised against the national average
   (grey reference).
3. **Toggle: Single CCHI per category vs Subgroup-weighted per force** —
   flips the harm weighting between a single nationally-derived CCHI for
   each of the 13 categories and a per-force weighted-average CCHI
   derived from each force's actual subgroup mix (residential vs
   non-residential burglary, possession vs trafficking, common assault vs
   rape, etc.). The toggle only affects forces in the five multi-subgroup
   categories — Violence and sexual offences, Burglary, Criminal damage
   and arson, Drugs, Robbery. Watch the map redistribute colour for those
   forces whose mix differs from the national average.
4. **Officer function mix** — for the selected force, how its officers split
   across the wider CIPFA Police Objective Analysis (POA) functions versus
   the national average. Updates with the same force selection as the radar.
   Shows seeded placeholder per-force values for now (see Data).
5. **Proportional reallocation** — recommended change in officer numbers per
   force if the national pool were distributed by each force's share of harm
   instead of the current formula. A diverging bar per force, coloured to
   match the map (green = recommend fewer, red = recommend more).

## Setup

```bash
pip install -r requirements.txt
```

Then download the two Home Office source files into `data/raw/`:

- `prc-pfa-mar2013-onwards-tables-230426.ods` — Police Recorded Crime,
  Police Force Area open data tables (gov.uk).
- `open-data-table-police-workforce-280126.ods` — Police Workforce open
  data table (gov.uk).

The Cambridge CCHI 2026 spreadsheet (~400 KB) is committed to the
repository at `data/raw/Cambridge-CCHI-2026-update.xlsx`, so no
separate download is needed for harm weights.

See `data/raw/SOURCES.md` for release pages and licensing. The loaders
raise a clear `FileNotFoundError` pointing back to that file if any
source is missing.

```bash
python app.py
```

Then open `http://127.0.0.1:8050`.

The first run additionally downloads a ~340KB GeoJSON of the Police Force
Areas (December 2023) from the ONS Open Geography Portal and caches it
under `data/`. Subsequent runs are offline.

## Data

Every crime, harm, officer-FTE, and allocation figure is read from the
official Home Office and Cambridge releases listed below — none of those are
mocked, and the proportional reallocation is computed from that same real
data. The one exception is the officer function mix panel: until the Home
Office workforce-functions table is added to `data/raw/`, it shows seeded
placeholder per-force values (clearly badged in the app), built around the
published national function split.

- **Crime counts** — file `prc-pfa-mar2013-onwards-tables-230426.ods`,
  sheet `2024_25` (25,356 rows). Home Office Police Recorded Crime,
  Police Force Area open data tables, released 23 April 2026. PRC
  covers the financial year 2024/25 (Q1–Q4) summed per force and
  per Offence Subgroup. Action Fraud, CIFAS, UK Finance, and British
  Transport Police are filtered out as they are not territorial PFAs.
  The 23 PRC Offence Subgroups in scope roll up to 13 dashboard
  categories; the loader fails loudly if a subgroup goes unmapped
  (e.g. after a future taxonomy change).
- **Officer FTE** — file `open-data-table-police-workforce-280126.ods`,
  sheet `Data`. Home Office Police Workforce, England and Wales open
  data table, released 28 January 2026. The dashboard uses the
  snapshot at 31 March 2025 with `Worker type = "Police Officer"`,
  summed by Force name. 43 territorial forces; British Transport
  Police excluded.
- **Harm weights**: Cambridge Crime Harm Index, 2026 update
  (Sherman, Neyroud, Neyroud — Cambridge Centre for Evidence-Based
  Policing). One CCHI value per PRC Offence Subgroup, taken as the
  median of all Sherman 2026 entries that fall under it. Median is
  preferred over mean for robustness to rare-but-severe offences within
  a subgroup. Per-subgroup citations, mean-vs-median sensitivity, and
  documented deviations from the Sherman methodology are in
  `data/raw/CCHI_SOURCES.md`.

### Pipeline

When `python app.py` starts, it runs the steps below once, caches the
result in memory, and then serves the same dataset to every browser
request. Nothing is transcribed by hand; every figure on the dashboard
traces back to one of three open-data spreadsheets through the loaders.

1. **Load PRC counts** — `prc_loader.load_force_subgroup_counts()`.
   Reads the `2024_25` sheet of the PRC ODS, drops the four
   non-territorial entries (BTP, Action Fraud, CIFAS, UK Finance),
   normalises force-name spellings (`London, City of` → `City of London`),
   verifies that all four financial quarters are present, and pivots to
   a 43 × 23 force × Offence Subgroup matrix. Pre-2017 burglary labels
   (Domestic / Non-domestic) are dropped automatically because their
   2024/25 totals are zero.
2. **Load officer FTE** — `workforce_loader.load_force_fte()`.
   Reads the `Data` sheet of the workforce ODS, filters to the 31 March
   2025 snapshot with `Worker type = "Police Officer"`, normalises
   `Hampshire and Isle of Wight` → `Hampshire`, and sums Total (FTE) by
   force. Returns a dict.
3. **Load CCHI per subgroup** — `cchi_loader.load_subgroup_cchi()`.
   Reads `CCHI 2026 values sheet` from the Cambridge XLSX, drops rows
   whose `FULL_OFFENCE_TITLE` is flagged `EXPIRED` (six retired offence
   codes with cutoffs spanning 31/03/17 to 31/03/25 — they no longer
   appear in the PRC tables and so should not be allowed to weight the
   active codes), and applies the PRC → Sherman SUB_GROUP mapping.
   Fourteen of the twenty-three PRC subgroups match a Sherman
   SUB_GROUP exactly; the remaining nine are resolved by pooling 2–4
   Sherman labels (Residential burglary, Public order, Vehicle), by
   label renames (trailing `offences` dropped, `BURGLARY - BUSINESS
   AND COMMUNITY`, `MISC` abbreviation), or by `FULL_OFFENCE_TITLE`
   pattern (Death/driving — no dedicated Sherman SUB_GROUP). Returns
   the median CCHI per PRC subgroup.
4. **Build the per-force dataset** — `data.build_dataset()`.
   For each of the 43 territorial forces, computes harm under both
   scenarios (sum of count × CCHI, with subgroup mix either per-force
   or set to the national share), the officer / harm shares, and the
   allocation gap. Also produces a per-force category mix profile for
   the radar.
5. **Cache the ONS PFA GeoJSON** — `geo.get_pfa_geojson()`.
   On first run downloads the ~340 KB Police Force Areas (December
   2023, ultra-generalised) boundary file from the ONS Open Geography
   Portal, rewrites two force-name variants (`Devon & Cornwall` and
   `London, City of`), and caches to `data/pfa_2023_buc.geojson`.
   Subsequent runs read from disk.
6. **Render** — `app.py`.
   Dash builds the choropleth from the dataset and the GeoJSON, keyed
   on force name. The CCHI toggle switches between the two
   `allocation_gap_*` columns. Clicking a force on the map fires a
   callback that updates the radar chart with that force's crime mix
   against the national baseline.

### Toolkit

- `pandas` — data wrangling, joins, group-by aggregations
- `dash` + `plotly` — interactive web app and charts
- `openpyxl`, `odfpy` — XLSX and ODS spreadsheet readers
- `requests` — fetches the ONS GeoJSON on first run

### Methodology

For each force F, harm is summed at the subgroup level:

```
harm_F = Σ_subgroup (count_{F,subgroup} × CCHI_subgroup)
```

`CCHI_subgroup` is built in two aggregation layers, each using the rule
that the available data supports:

1. **Sherman URN → PRC subgroup — median.** Sherman 2026 publishes
   scores at offence-code (ATHENA URN) level. PRC publishes counts at
   subgroup level only, so URN-level volume weighting is not possible.
   Each PRC subgroup's CCHI is therefore the median of all Sherman
   entries that map to it — robust to rare-but-severe offences
   (firearms within Possession of weapons; GBH-with-intent within
   Violence with injury) that would otherwise pull a mean far above the
   typical reported offence.
2. **PRC subgroup → dashboard category — volume-weighted average.**
   Eight of the 13 dashboard categories contain a single PRC subgroup;
   their category CCHI is just the subgroup median. The other five
   (Violence and sexual offences, Burglary, Drugs, Robbery, Criminal
   damage and arson) take a volume-weighted average of their subgroup
   medians, with PRC counts as the weights. The toggle picks which
   counts:

- **Subgroup-weighted per force**: weights are each force's own
  subgroup counts. A force with a heavier residential-burglary share
  scores higher per offence in the Burglary category than a force whose
  burglary mix tilts non-residential.
- **Single CCHI per category**: weights are the national subgroup
  counts. One nationally-derived CCHI per category, applied identically
  to every force. This isolates the effect of crime *volume* alone
  (forces are no longer rewarded or penalised for category mix). The
  toggle only changes anything for the five multi-subgroup categories.

The allocation gap (officer share % − harm share %) is positive when a
force has more officers than harm suggests is needed, negative when it
has fewer. Allocation gaps sum to zero across the 43 territorial forces
by construction.

### Sanity checks

- 43 territorial PFAs in both sources, with identical naming after
  normalisation (`London, City of` → `City of London`,
  `Hampshire and Isle of Wight` → `Hampshire`).
- Total officer FTE sums to 146,442, matching the Home Office published
  headline for 31 March 2025.
- Allocation gaps sum to zero across England & Wales (officer shares
  and harm shares each sum to 100%).
- Per-force crime profiles each sum to 1.0.

### Known gaps and documented deviations

- **Anti-social behaviour** is not in PRC (it is recorded as incidents
  rather than crimes), so the radar has 13 axes rather than 14. ASB
  exists in the data.police.uk record-level data and could be added as
  a 14th axis once that pipeline is integrated.
- **Per-force resolution rate** is not published in the Home Office
  outcomes table for non-fraud offences. The Sherman formula
  `count × weight × (1 − resolution_rate)` is therefore reduced to
  `count × weight` here. Reintroducing it is one constant-multiplier
  line once per-force outcome data lands.
- **Proactive offences are included.** Sherman 2016 recommends excluding
  drug arrests, traffic arrests, and shop-detective shoplifting from the
  harm count base on the grounds that their volume reflects police
  resourcing rather than crime patterns. The dashboard includes these
  because its purpose is to measure police *workload*-relevant harm —
  drug enforcement and shoplifting are real demands on police time. This
  is a deliberate deviation from Sherman's recommended scope, fully
  documented in `data/raw/CCHI_SOURCES.md`.
- **Subgroup-level (not URN-level) CCHI aggregation.** PRC PFA tables
  publish counts at the Offence Subgroup level only. URN-level counts
  would allow more rigorous within-subgroup volume weighting, but
  require record-level data from data.police.uk that is not currently in
  the pipeline.

## Files

```
app.py                    Dash app — layout and callbacks
data.py                   Builds the per-force allocation dataset
prc_loader.py             Reads the Home Office Police Recorded Crime ODS
workforce_loader.py       Reads the Home Office Police Workforce ODS
cchi_loader.py            Reads the Cambridge CCHI 2026 spreadsheet and
                          computes one median CCHI per PRC Offence Subgroup
functions_loader.py       Officer function mix per force (seeded placeholder
                          until the workforce-functions table is added)
allocation_loader.py      Recommended allocation per force — proportional
                          baseline now, optimiser output when available
forecast_loader.py        Forecast schema (force x crime type x month) for the
                          predictor output; placeholder until it lands
geo.py                    ONS PFA boundaries (downloads + caches on first run)
build_assets.py           Generates standalone HTML exports for sharing
assets/style.css          Custom styling
data/raw/SOURCES.md       Provenance and download links for all source files
data/raw/CCHI_SOURCES.md  Methodology document for the harm weighting:
                          per-subgroup citation chain, aggregation rule,
                          documented deviations, known limitations
requirements.txt
```

## Sharable assets

Generate two static HTML exports for slides, screenshots, or chat:

```bash
python build_assets.py
```

Outputs:

- `exports/comparison.html` — side-by-side maps: single CCHI per category
  vs subgroup-weighted per force, same colour scale. Open in browser,
  then screenshot.
- `exports/animated.html` — single map that animates between the two
  scenarios. Drag the slider or hit play.

Re-run after any change to `data.py` to refresh both files.

## Source attribution

- Crime counts: Home Office, *Police Recorded Crime, Police Force Area
  open data tables* (released 23 April 2026), Open Government Licence.
- Officer FTE: Home Office, *Police Workforce, England and Wales: 31
  March 2025* (released 28 January 2026), Open Government Licence.
- Harm weights: Cambridge Centre for Evidence-Based Policing,
  *Cambridge Crime Harm Index, 2026 update*. Foundational paper:
  Sherman, Neyroud, Neyroud (2016), Policing 10(3): 171–183.
- Boundaries: ONS Open Geography Portal, Police Force Areas (December
  2023) BUC.
- Police force list: data.police.uk / Home Office.
