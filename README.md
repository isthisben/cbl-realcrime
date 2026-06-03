# Police Resource Allocation Dashboard

Dashboard for **TU/e 4CBLW020 — Real-World Crime project**.

Compares the current funding and officer distribution across the 43
territorial police forces of England & Wales against a *harm-weighted*
allocation derived from the Cambridge Crime Harm Index (CCHI). Shows
whether forces are over- or under-resourced relative to the harm they
handle.

## What's in the dashboard

1. **Choropleth map** — coloured by allocation gap (resource share minus
   harm share). Green = over-resourced, red = under-resourced.
2. **Radar chart** — selected force's crime mix across 13 Home Office
   recorded-crime categories, normalised against the national average
   (grey reference).
3. **Toggle: Budget vs Officers** — flips the resource basis. *Budget*
   (default) compares each force's share of the £9.81 bn central
   government grant pool against its harm share — the recommended basis,
   because the evidence linking more officers to less crime is contested
   and reallocating funding is more flexible (equipment, training,
   specialist units, victim services, headcount). *Officers* compares
   share of officer FTE (146,442 across England & Wales) against harm.
4. **Toggle: Single CCHI per category vs Subgroup-weighted per force** —
   flips the harm weighting between a single nationally-derived CCHI for
   each of the 13 categories and a per-force weighted-average CCHI
   derived from each force's actual subgroup mix (residential vs
   non-residential burglary, possession vs trafficking, common assault vs
   rape, etc.). The toggle only affects forces in the five multi-subgroup
   categories — Violence and sexual offences, Burglary, Criminal damage
   and arson, Drugs, Robbery. Watch the map redistribute colour for those
   forces whose mix differs from the national average.
5. **Proportional reallocation panel** — diverging horizontal bars per
   force showing the recommended change (in £m under budget basis, FTE
   under officer basis) if the national pool were redistributed by harm
   share rather than the current formula. Capped axis, hover for exact
   figures.

## Setup

```bash
pip install -r requirements.txt
```

Then download the Home Office ODS files into `data/raw/` (gitignored
because of size and Open Government Licence redistribution constraints):

- `prc-pfa-mar2013-onwards-tables-230426.ods` — Police Recorded Crime,
  Police Force Area open data tables (gov.uk).
- `open-data-table-police-workforce-280126.ods` — Police Workforce open
  data table (gov.uk).
- `open-data-table-police-workforce-functions-280126.ods` — Police
  Workforce functions open data table (gov.uk).
- `police-funding-england-and-wales-2015-to-2026-tables.ods` — Home
  Office historical police funding tables (not wired into the dashboard
  yet — kept for future historical-year work).

The remaining sources are small enough to commit and do not need a
separate download:

- `data/raw/Cambridge-CCHI-2026-update.xlsx` (~400 KB) — Cambridge CCHI
  2026 update.
- `data/raw/police-grant-2025-26.csv` — central government grant per
  force, extracted from the Police Grant Report (England and Wales)
  2025-26.

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

The first run also parses the source spreadsheets to assemble the dataset,
which takes a few minutes, and caches the result under `data/cache/`. Every
later start loads that cache instantly; it is rebuilt automatically when a
source file changes, or on demand with `python data.py --refresh`.

## Data

Every figure shown is read from the official Home Office and Cambridge
releases listed above. No ratios are mocked or generated.

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
- **Central government grant** — file `police-grant-2025-26.csv`. Home
  Office Police Grant Report (England and Wales) 2025-26, 'Overall
  Total' column per force: Police Main Grant + ex-DCLG Formula Funding
  + Legacy Council Tax Grants + Welsh Top-Up. £9.81 bn national pool
  across the same 43 territorial forces. Council tax precept (locally
  raised, ~40 % of total force funding) is excluded by design — only
  the centrally-controlled pool is redistributable. Welsh forces carry
  £0 in the DCLG and legacy components (those streams are routed
  through the Welsh Government separately), so the Overall Total for
  the four Welsh forces reflects Police Main Grant + Welsh Top-Up only.
- **Harm weights**: Cambridge Crime Harm Index, 2026 update
  (Sherman, Neyroud, Neyroud — Cambridge Centre for Evidence-Based
  Policing). One CCHI value per PRC Offence Subgroup, taken as the
  median of all Sherman 2026 entries that fall under it. Median is
  preferred over mean for robustness to rare-but-severe offences within
  a subgroup. Per-subgroup citations, mean-vs-median sensitivity, and
  documented deviations from the Sherman methodology are in
  `data/raw/CCHI_SOURCES.md`.

### Pipeline

When `python app.py` starts it assembles the per-force dataset through the
steps below, caches the result to `data/cache/` (pickled), and serves it to
every browser request. The cold assembly re-parses several large Home Office
ODS / XLSX files and takes a few minutes; the cache turns every subsequent
start into an instant load. It rebuilds automatically whenever a source file
in `data/raw/` changes, and `python data.py --refresh` forces a rebuild.
Nothing is transcribed by hand; every figure on the dashboard traces back to
an open-data release through the loaders.

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
3. **Load central grant per force** — `budget_loader.load_force_budget()`.
   Reads the 43-row `police-grant-2025-26.csv` (canonical force names,
   integer £ values), validates that the national total reconciles to
   £9,806,553,489 within £100 rounding, and returns a dict.
4. **Load CCHI per subgroup** — `cchi_loader.load_subgroup_cchi()`.
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
5. **Build the per-force dataset** — `data.build_dataset()`.
   For each of the 43 territorial forces, computes harm under both
   scenarios (sum of count × CCHI, with subgroup mix either per-force
   or set to the national share), the officer / budget / harm shares,
   and the four allocation-gap columns (officer or budget × flat or
   subgroup-weighted). Also produces a per-force category mix profile
   for the radar.
6. **Cache the ONS PFA GeoJSON** — `geo.get_pfa_geojson()`.
   On first run downloads the ~340 KB Police Force Areas (December
   2023, ultra-generalised) boundary file from the ONS Open Geography
   Portal, rewrites two force-name variants (`Devon & Cornwall` and
   `London, City of`), and caches to `data/pfa_2023_buc.geojson`.
   Subsequent runs read from disk.
7. **Render** — `app.py`.
   Dash builds the choropleth from the dataset and the GeoJSON, keyed
   on force name. The basis toggle switches between the budget and
   officer columns; the CCHI toggle switches between flat and
   subgroup-weighted harm shares. Clicking a force on the map fires a
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

The allocation gap (resource share % − harm share %) is positive when a
force has more resources than harm suggests is needed, negative when it
has fewer. Both the budget basis (budget share − harm share) and the
officer basis (officer share − harm share) gap columns sum to zero across
the 43 territorial forces by construction.

### Sanity checks

- 43 territorial PFAs in all three sources (PRC, workforce, central
  grant), with identical naming after normalisation (`London, City of`
  → `City of London`, `Hampshire and Isle of Wight` → `Hampshire`).
- Total officer FTE sums to 146,442, matching the Home Office published
  headline for 31 March 2025.
- Total central grant reconciles to £9,806,553,489, matching the
  published Police Grant Report 2025-26 national total within £100
  rounding.
- Allocation gaps sum to zero under both bases (officer / budget /
  harm shares each sum to 100 %).
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
data.py                   Builds the per-force allocation dataset (disk-cached)
cache.py                  On-disk cache for the assembled dataset + function mix
prc_loader.py             Reads the Home Office Police Recorded Crime ODS
workforce_loader.py       Reads the Home Office Police Workforce ODS
budget_loader.py          Reads the Police Grant Report 2025-26 per-force CSV
functions_loader.py       Officer function mix per force (CIPFA POA categories)
allocation_loader.py      Recommended vs current allocation per force (FTE or £)
cchi_loader.py            Reads the Cambridge CCHI 2026 spreadsheet and
                          computes one median CCHI per PRC Offence Subgroup
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
- Central grant: Home Office, *Police Grant Report (England and Wales)
  2025-26* (statutory instrument laid 5 February 2025), Open Government
  Licence. Per-force 'Overall Total' column.
- Harm weights: Cambridge Centre for Evidence-Based Policing,
  *Cambridge Crime Harm Index, 2026 update*. Foundational paper:
  Sherman, Neyroud, Neyroud (2016), Policing 10(3): 171–183.
- Boundaries: ONS Open Geography Portal, Police Force Areas (December
  2023) BUC.
- Police force list: data.police.uk / Home Office.
