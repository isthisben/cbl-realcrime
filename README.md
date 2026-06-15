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

Dashboard for the **TU/e 4CBLW020 — Real-World Crime project**.

It asks a single question: **is each police force resourced in line with the
harm it actually handles?** For the 42 territorial forces of England and Wales
it compares the current distribution of funding (and officers) against a
*harm-weighted* allocation derived from the Cambridge Crime Harm Index (CCHI),
and shows where forces are over- or under-resourced.

The project runs in three layers, all sharing one harm weighting:

1. **Diagnose** — score the harm each force faces today from recorded crime
   (2024/25) and compare it to current funding/officers (this dashboard's map).
2. **Predict** — a LightGBM model forecasts the next 12 months of crime per
   force and category (the forecast panel).
3. **Optimise** — an integer linear program (ILP) reallocates the formula grant
   and the workforce toward forecast harm (the reallocation panel).

## What's in the dashboard

- **Choropleth map** — every force coloured by its *allocation gap* (resource
  share − harm share). Blue = over-resourced, red = under-resourced. A toggle
  flips the resource basis between **funding (£)** and **officers (FTE)**.
- **Crime-profile radar** — the selected force's mix across the 13 recorded
  crime categories plus anti-social behaviour, normalised to the national
  average (the grey circle). Click any force on the map to update it.
- **Officer function mix** — how the force splits its officers across the 12
  wider CIPFA Police Objective Analysis (POA) functions, against the national
  split.
- **Reallocation panel** — the ILP's recommended change per force: in formula
  grant (£) on the funding basis, or in FTE for the chosen workforce pool
  (patrol / investigators / PCSOs, or all three combined) on the officer basis.
- **Crime forecast** — the LightGBM 12-month prediction (Mar 2026 – Feb 2027)
  of total offences for the selected force.

The map, radar and forecast all respond to the selected force; the basis and
workforce-pool toggles drive the map and the reallocation panel.

## Scope: 42 forces

The raw Home Office releases cover the 43 territorial forces of England and
Wales. The dashboard reports **42**: Greater Manchester is dropped project-wide
because it is missing from the model team's forecast and ILP outputs, so keeping
it would leave gaps in the predict/optimise layers. Headline totals are
therefore over the 42 in scope — £16.69 bn total funding and 138,331 officer FTE
(the Home Office national headline of 146,442 FTE includes Greater Manchester).

## How harm is scored

For each force, harm is its recorded crime weighted by the CCHI:

```
harm_force = Σ (category count × per-force CCHI)  +  ASB floor term
```

The CCHI weight is a starting-point sentence in days (Cambridge 2026 update).
Nine of the 13 categories map to a single offence severity, so they carry one
national value identical for every force (Robbery 365, Possession of weapons
273.75, Public order 7.5, ... Shoplifting 1). Four composite categories bundle
offence subgroups of different severity — Violence and sexual offences, Burglary,
Criminal damage and arson, Drugs — so each force's value is the volume-weighted
average of those subgroups under its *own* offence mix, and varies per force. A
force with more residential burglary, or more homicide/rape within violence,
earns a heavier weight per offence.

These per-force weights live in `data/cchi_weights_by_force_category.csv` — the
same file the model team's ILP consumed, so the map's harm picture and the
optimiser outputs rest on one source of truth.

**Anti-social behaviour** has no CCHI score (it is logged as incidents, not
notifiable crime) and is absent from the recorded-crime tables. It is the single
highest-volume thing a force handles, so it is represented at the harm *floor* —
CCHI = 1, the value Cambridge gives the lowest notifiable offence — using
forecast-derived volumes. It shows as a labelled 14th radar axis and a small
additive harm term (~0.17% of national harm), never folded silently into the
recorded figures.

Full per-subgroup citations, the median-vs-mean sensitivity, and every
documented deviation from the Sherman methodology are in
[`data/raw/CCHI_SOURCES.md`](data/raw/CCHI_SOURCES.md).

### Recorded now, forecast for allocation

The map and radar score harm on *recorded* crime (2024/25) — the harm forces
face today. The ILP was optimised against *forecast* harm (the predicted next 12
months) under the same weights. The two are close but not identical (≈0.998
correlation on harm share): diagnose on the actuals, optimise on the forecast.

## The two bases

- **Funding (£) — the headline.** Compares each force's share of *total* funding
  (government grant + council-tax precept + ring-fenced specific grants, £16.69
  bn) against its harm share. This is the recommended basis: the evidence linking
  more officers to less crime is contested, and money is more flexible than
  headcount (equipment, training, specialist units, victim services). The
  reallocation moves only the £9.23 bn redistributable *formula grant*, holding
  precept and specific grants fixed.
- **Officers (FTE).** Compares each force's share of officer headcount (138,331
  FTE) against harm, and reallocates the chosen workforce pool.

The allocation gap is `resource share % − harm share %`: positive (blue) when a
force has more than its harm suggests, negative (red) when it has less. Both gap
columns sum to zero across the 42 forces by construction.

City of London is a structural outlier — a national fraud/financial-crime
specialist with a tiny resident population — so it sits outside the grant ILP
(which covers 41 forces) and should be read as a special case.

## Data

Every figure is read from an official release or a committed model-team output;
nothing is mocked or hand-typed. See
[`data/raw/SOURCES.md`](data/raw/SOURCES.md) for release pages, dates and
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

The raw Home Office ODS files (~20 MB) are committed so the pipeline reproduces
from source. They are excluded from the Docker image (`.dockerignore`) — the
deploy runs off the committed snapshot in `data/snapshot/` instead.

### Pipeline

`data.py` assembles the per-force dataset: it loads each source through its
loader, intersects the forces, drops Greater Manchester, rolls the PRC subgroups
up to the 13 categories, weights them by the per-force CCHI, adds the ASB floor,
and computes the share and gap columns. The cold parse re-reads several large
ODS files and takes a few minutes, so the result is pickled to `data/cache/` and
reused until a source file changes (or `python data.py --refresh`). A trimmed
copy is committed to `data/snapshot/` for hosts that don't ship the raw files.

Every loader fails loud — a missing file, an unmapped crime subgroup, a total
that doesn't reconcile, a force missing from one source — rather than silently
producing a wrong number. The reconciliation checks (officer FTE, grant total,
precept total, gaps summing to zero) are listed in `CCHI_SOURCES.md` and
`SOURCES.md`.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8050`.

On first run the app downloads a ~340 KB GeoJSON of the Police Force Areas
(December 2023) from the ONS Open Geography Portal and caches it under `data/`;
later runs are offline. The first dataset build parses the source spreadsheets
(a few minutes) and caches the result — every later start is instant.

## Deploy

The app is hosted on Hugging Face Spaces (Docker SDK). The `Dockerfile` serves
it with gunicorn on port 7860, off the committed snapshot, so the host needs
none of the raw ODS files. The Hugging Face front-matter is at the top of this
file (`app_port` must match the bind in the `Dockerfile`).

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

assets/style.css       Styling
data/raw/SOURCES.md    Provenance + download links for every source
data/raw/CCHI_SOURCES.md  Harm-weighting methodology and limitations
model/police_workforce_ilp.py  The team's ILP (see below)
```

## Model team's work

The forecast and the ILP are the predictor/optimisation teammates' deliverables.
The dashboard reads their **committed outputs** (`data/raw/forecast_lgbm.csv`,
`data/raw/ilp/*.csv`); it does not run their models. `model/police_workforce_ilp.py`
is included as the reference implementation of the workforce ILP — it documents
how the `ilp/` outputs were produced. It is run by the model team against their
own inputs and needs `pulp` + `matplotlib` (not in this dashboard's
`requirements.txt`).

## Sharable assets

```bash
python build_assets.py
```

Writes `exports/comparison.html` — side-by-side maps of the allocation gap under
the officer and funding bases on one colour scale. Open in a browser and
screenshot for the report or slides.

## Known gaps and next steps

- **Crime hotspots** — five hotspots per force are planned as a later addition;
  they are not in the dashboard yet.
- **Resolution rate** — the full Sherman formula multiplies harm by
  `(1 − clearance rate)`. The Home Office outcomes table only publishes per-force
  clearance for fraud, so the dashboard uses `count × weight` and treats clearance
  as uniform. Reintroducing it is a one-line change once per-force data lands.
- **Proactive offences are included** (drug/traffic arrests, shoplifting). Sherman
  2016 recommends excluding them; the dashboard keeps them because it measures
  police *workload*-relevant harm. A documented, deliberate deviation — see
  `CCHI_SOURCES.md`.
- **Subgroup-level CCHI** — PRC publishes counts at offence-subgroup level, not
  URN level, so the harm weighting joins at subgroup granularity.

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
