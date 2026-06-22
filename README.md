---
title: Police Resource Allocation
emoji: 🚓
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Police Resource Allocation Dashboard

Dashboard for the TU/e 4CBLW020 — Real-World Crime project.

It answers one question: is each police force resourced in line with the harm it
actually handles? For the 42 territorial forces of England and Wales, it compares
how funding (and officers) are distributed today against a *harm-weighted*
allocation built from the Cambridge Crime Harm Index (CCHI), and flags which
forces come out over- or under-resourced.

The project has three layers, all built on the same harm weighting:

1. **Diagnose.** Score the harm each force faces today from recorded crime
   (2024/25) and compare it to current funding and officers. That comparison is
   this dashboard's map.
2. **Predict.** A LightGBM model forecasts the next 12 months of crime for each
   force and category, which feeds the forecast panel.
3. **Optimise.** An integer linear program (ILP) reallocates the formula grant
   and the workforce toward forecast harm, driving the reallocation panel.

## What's in the dashboard

- **Choropleth map.** Every force is coloured by its *allocation gap*, meaning
  resource share minus harm share. Blue is over-resourced, red is
  under-resourced. A toggle switches the resource basis between funding (£) and
  officers (FTE).
- **Crime-profile radar.** The selected force's mix across the 13 recorded crime
  categories plus anti-social behaviour, normalised to the national average (the
  grey circle). Click any force on the map to update it, or pick *England & Wales
  (national)* for the national crime mix in absolute shares.
- **What the data suggests.** A plain-language read-out for the selected force:
  its resourcing position, the ILP's recommended change, and where its crime and
  officer mix sit against the national picture. It is descriptive only, a
  formatted summary of the panels above, with interpretation left to the report.
- **Officer function mix.** How the force splits its officers across the 12 wider
  CIPFA Police Objective Analysis (POA) functions, set against the national split.
- **Reallocation panel.** The ILP's recommended change for each force: formula
  grant (£) on the funding basis, or FTE for the chosen workforce pool (patrol,
  investigators, PCSOs, or all three combined) on the officer basis.
- **Crime forecast.** The LightGBM 12-month prediction (March 2026 to February
  2027) of total offences for the selected force.
- **Stop-and-search hotspots.** Every force's five busiest stop-and-search
  locations on a single England & Wales map (data.police.uk, 2023–2026), sized by
  search volume and coloured by find rate. The data covers 39 of the 42 forces.

The radar, function mix, forecast, and recommendations all update with the
selected force, including the England & Wales national option. The map highlights
the current selection, while the stop-and-search map shows every force at once.
The basis and workforce-pool toggles drive the map and the reallocation panel.

## Scope: 42 forces

The raw Home Office releases cover all 43 territorial forces of England and Wales.
The dashboard reports 42 of them. Greater Manchester is dropped across the whole
project because it is missing from the model team's forecast and ILP outputs, and
keeping it would leave gaps in the predict and optimise layers. Every headline
total is therefore over the 42 forces in scope: £16.69 bn of total funding and
138,331 officer FTE. (The Home Office national headline of 146,442 FTE includes
Greater Manchester.)

## How harm is scored

For each force, harm is its recorded crime weighted by the CCHI:

```
harm_force = Σ (category count × per-force CCHI)  +  ASB floor term
```

The CCHI weight is a starting-point sentence in days, taken from the Cambridge
2026 update. Nine of the 13 categories map to a single offence severity, so they
carry one national value that is identical for every force (Robbery 365,
Possession of weapons 273.75, Public order 7.5, down to Shoplifting 1). The other
four are composites that bundle offence subgroups of different severity: Violence
and sexual offences, Burglary, Criminal damage and arson, and Drugs. For these,
each force's value is the volume-weighted average of its subgroups under that
force's *own* offence mix, so it varies between forces. A force with more
residential burglary, or more homicide and rape within violence, earns a heavier
weight per offence.

These per-force weights live in `data/cchi_weights_by_force_category.csv`. It is
the same file the model team's ILP consumed, so the map's harm picture and the
optimiser's outputs come from the same place.

Anti-social behaviour has no CCHI score, since it is logged as incidents rather
than notifiable crime, and it does not appear in the recorded-crime tables. It is
also the single highest-volume thing a force handles. To include it without
distorting the totals, the dashboard puts it at the harm *floor*: CCHI = 1, the
value Cambridge gives the lowest notifiable offence, applied to forecast-derived
volumes. It shows up as a labelled 14th radar axis and a small additive harm term
(about 0.17% of national harm), and is never folded silently into the recorded
figures.

Full per-subgroup citations, the median-versus-mean sensitivity, and every
documented deviation from the Sherman methodology are in
[`data/raw/CCHI_SOURCES.md`](data/raw/CCHI_SOURCES.md).

### Recorded now, forecast for allocation

The map and radar score harm on *recorded* crime (2024/25), the harm forces face
today. The ILP was optimised against *forecast* harm, the predicted next 12
months, under the same weights. The two are close but not identical (≈0.998
correlation on harm share): diagnose on the actuals, optimise on the forecast.

## The two bases

- **Funding (£), the headline basis.** Compares each force's share of *total*
  funding against its harm share. Total funding is government grant plus
  council-tax precept plus ring-fenced specific grants, £16.69 bn in all. This is
  the recommended basis for two reasons: the evidence linking more officers to
  less crime is contested, and money is more flexible than headcount (it can go to
  equipment, training, specialist units, or victim services). The reallocation
  moves only the £9.23 bn redistributable *formula grant*, holding precept and
  specific grants fixed.
- **Officers (FTE).** Compares each force's share of officer headcount (138,331
  FTE) against harm, then reallocates the chosen workforce pool.

The allocation gap is `resource share % − harm share %`: positive (blue) when a
force holds more than its harm suggests, negative (red) when it holds less. Both
gap columns sum to zero across the 42 forces by construction.

City of London is a structural outlier: a national fraud and financial-crime
specialist with a tiny resident population. It sits outside the grant ILP (which
covers 41 forces) and should be read as a special case.

## Data

Every figure comes from an official release or a committed model-team output.
Nothing is mocked or hand-typed. See
[`data/raw/SOURCES.md`](data/raw/SOURCES.md) for release pages, dates, and
licensing.

| Input | Source | Used for |
|---|---|---|
| `prc-pfa-mar2013-onwards-tables-230426.ods` | Home Office Police Recorded Crime, PFA tables (2024/25 sheet) | crime counts |
| `open-data-table-police-workforce-280126.ods` | Home Office Police Workforce, 31 Mar 2025 snapshot | officer FTE |
| `open-data-table-police-workforce-functions-280126.ods` | Home Office Police Workforce Functions | officer function mix |
| `police-funding-england-and-wales-2015-to-2026-tables.ods` | Home Office Police Funding Statistics, Table 4a | total funding + precept |
| `police-grant-2025-26.csv` | Home Office Police Grant Report 2025-26, 'Overall Total' | redistributable formula grant |
| `Cambridge-CCHI-2026-update.xlsx` | Cambridge Crime Harm Index, 2026 update | source of the harm weights |
| `cchi_weights_by_force_category.csv` | derived from the Cambridge index (see `CCHI_SOURCES.md`) | per-force CCHI weights |
| `forecast_lgbm.csv` | model team's LightGBM forecast | forecast panel + ASB volumes |
| `asb_counts.csv` | summed from the forecast | ASB floor term |
| `ilp/*.csv` | model team's ILP optimiser | reallocation panel |
| `hotspots.csv` | data.police.uk stop-and-search (2023–2026) | hotspots panel (39 forces) |

The raw Home Office ODS files (~20 MB) are committed so the pipeline reproduces
from source. They are excluded from the Docker image via `.dockerignore`, since
the deploy runs off the committed snapshot in `data/snapshot/` instead.

### Pipeline

`data.py` assembles the per-force dataset. It loads each source through its
loader, intersects the forces, drops Greater Manchester, rolls the PRC subgroups
up to the 13 categories, weights them by the per-force CCHI, adds the ASB floor,
and computes the share and gap columns. The cold parse re-reads several large ODS
files and takes a few minutes, so the result is pickled to `data/cache/` and
reused until a source file changes (or you run `python data.py --refresh`). A
trimmed copy is committed to `data/snapshot/` for hosts that don't ship the raw
files.

Every loader fails loud rather than silently producing a wrong number, whether
the cause is a missing file, an unmapped crime subgroup, a total that doesn't
reconcile, or a force missing from one source. The reconciliation checks (officer
FTE, grant total, precept total, and gaps summing to zero) are listed in
`CCHI_SOURCES.md` and `SOURCES.md`.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8050`.

On first run, the app downloads a ~340 KB GeoJSON of the Police Force Areas
(December 2023) from the ONS Open Geography Portal and caches it under `data/`;
later runs work offline. The first dataset build parses the source spreadsheets
(a few minutes) and caches the result, so every later start is instant.

## Deploy

The app is hosted on Hugging Face Spaces using the Docker SDK. The `Dockerfile`
serves it with gunicorn on port 7860, running off the committed snapshot, so the
host needs none of the raw ODS files. The Hugging Face front-matter sits at the
top of this file, and its `app_port` must match the bind in the `Dockerfile`.

## Files

```
app.py                 Dash app — layout, figures and callbacks
data.py                Builds the per-force dataset (disk-cached + snapshot)
cache.py               On-disk cache for the expensive startup parses
geo.py                 ONS PFA boundaries (downloads + caches on first run)
build_assets.py        Generates a static comparison map for slides/report

prc_loader.py          Police Recorded Crime counts per force x subgroup
workforce_loader.py    Officer FTE per force (31 Mar 2025)
functions_loader.py    Officer function mix per force (CIPFA POA functions)
grant_loader.py        Redistributable formula grant per force
funding_loader.py      Total funding + precept per force (Table 4a)
cchi_loader.py         Per-force CCHI weights + the ASB floor constant
asb_loader.py          Forecast-derived ASB volumes per force
forecast_loader.py     LightGBM 12-month forecast (long format)
allocation_loader.py   Reads the ILP outputs (grant + workforce pools)
hotspots_loader.py     Top-5 stop-and-search hotspots per force

assets/style.css       Styling
data/raw/SOURCES.md    Provenance + download links for every source
data/raw/CCHI_SOURCES.md  Harm-weighting methodology and limitations
model/police_workforce_ilp.py  The team's ILP (see below)
```

## Model team's work

The forecast and the ILP are the predictor and optimisation teammates'
deliverables. The dashboard reads their committed outputs
(`data/raw/forecast_lgbm.csv`, `data/raw/ilp/*.csv`); it does not run their
models. `model/police_workforce_ilp.py` is included as the reference
implementation of the workforce ILP, documenting how the `ilp/` outputs were
produced. The model team runs it against their own inputs, and it needs `pulp`
and `matplotlib` (neither is in this dashboard's `requirements.txt`).

## Sharable assets

```bash
python build_assets.py
```

Writes `exports/comparison.html`, side-by-side maps of the allocation gap under
the officer and funding bases on a single colour scale. Open it in a browser and
screenshot for the report or slides.

## Known gaps and next steps

- **Stop-and-search hotspots** appear for 39 of the 42 forces. The three without
  published data (Gwent, South Yorkshire, and Warwickshire) show a "no data" note
  in the panel.
- **Resolution rate.** The full Sherman formula multiplies harm by
  `(1 − clearance rate)`. The Home Office outcomes table only publishes per-force
  clearance for fraud, so the dashboard uses `count × weight` and treats clearance
  as uniform. Reintroducing it is a one-line change once per-force data lands.
- **Proactive offences are included** (drug and traffic arrests, shoplifting).
  Sherman 2016 recommends excluding them; the dashboard keeps them because it
  measures police *workload*-relevant harm. This is a documented, deliberate
  deviation, set out in `CCHI_SOURCES.md`.
- **Subgroup-level CCHI.** PRC publishes counts at offence-subgroup level rather
  than URN level, so the harm weighting joins at subgroup granularity.

## Source attribution

- Crime counts: Home Office, *Police Recorded Crime, PFA open data tables*
  (released 23 April 2026), Open Government Licence.
- Officer FTE and functions: Home Office, *Police Workforce, England and Wales:
  31 March 2025* (released 28 January 2026), Open Government Licence.
- Funding: Home Office, *Police Grant Report 2025-26* and *Police Funding
  Statistics* (Table 4a), Open Government Licence.
- Harm weights: Cambridge Centre for Evidence-Based Policing, *Cambridge Crime
  Harm Index, 2026 update*. Foundational paper: Sherman, Neyroud, Neyroud (2016),
  Policing 10(3): 171–183.
- Boundaries: ONS Open Geography Portal, Police Force Areas (December 2023) BUC.
- Forecast and allocation: the project's own LightGBM and ILP model outputs.
