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
3. **Toggle: Flat weight vs Subcategorised CCHI** — flips the violence
   weighting between a single 182 weight applied to every violence record
   and a force-specific weighted-average CCHI derived from the actual mix
   of offences (common assault, GBH, rape, homicide, etc.) inside each
   force. Watch the map redistribute colour when you flip it.

## Setup

```bash
pip install -r requirements.txt
```

Then download the two Home Office source files into `data/raw/`:

- `prc-pfa-mar2013-onwards-tables-230426.ods` — Police Recorded Crime,
  Police Force Area open data tables (gov.uk).
- `open-data-table-police-workforce-280126.ods` — Police Workforce open
  data table (gov.uk).

See `data/raw/SOURCES.md` for the gov.uk release pages and licensing. The
loaders raise a clear `FileNotFoundError` pointing back to that file if
either source is missing.

```bash
python app.py
```

Then open `http://127.0.0.1:8050`.

The first run additionally downloads a ~340KB GeoJSON of the Police Force
Areas (December 2023) from the ONS Open Geography Portal and caches it
under `data/`. Subsequent runs are offline.

## Data

Every figure shown is read from the official Home Office releases listed
above. No ratios are mocked or generated.

- **Crime counts** — file `prc-pfa-mar2013-onwards-tables-230426.ods`,
  sheet `2024_25` (25,356 rows). Home Office Police Recorded Crime,
  Police Force Area open data tables, released 23 April 2026. PRC
  covers the financial year 2024/25 (Q1–Q4) summed per force and
  per Offence Subgroup. Action Fraud, CIFAS, UK Finance, and British
  Transport Police are filtered out as they are not territorial PFAs.
  Each PRC Offence Subgroup maps to one of 13 dashboard categories;
  the loader fails loudly if a subgroup goes unmapped (e.g. after a
  future taxonomy change).
- **Officer FTE** — file `open-data-table-police-workforce-280126.ods`,
  sheet `Data`. Home Office Police Workforce, England and Wales open
  data table, released 28 January 2026. The dashboard uses the
  snapshot at 31 March 2025 with `Worker type = "Police Officer"`,
  summed by Force name. 43 territorial forces; British Transport
  Police excluded.
- **Harm weights**: Cambridge Crime Harm Index 2020 (Sherman et al.).
  Non-violence categories use single representative scores; violence and
  sexual offences are weighted via the seven PRC subgroups under the
  "Subcategorised CCHI" scenario.

### Sanity checks

- 43 territorial PFAs in both sources, with identical naming after
  normalisation (`London, City of` → `City of London`,
  `Hampshire and Isle of Wight` → `Hampshire`).
- Total officer FTE sums to 146,442, matching the Home Office published
  headline for 31 March 2025.
- Allocation gaps sum to zero across England & Wales (officer shares
  and harm shares each sum to 100%).
- Per-force crime profiles each sum to 1.0.

### Known gaps

- **Anti-social behaviour** is not in PRC (it is recorded as incidents
  rather than crimes), so the radar has 13 axes rather than 14. ASB
  exists in the data.police.uk record-level data and could be added as
  a 14th axis once that pipeline is integrated.
- **Per-force resolution rate** is not published in the Home Office
  outcomes table for non-fraud offences. The Sherman formula
  `count × weight × (1 − resolution_rate)` is therefore reduced to
  `count × weight` here. Reintroducing it is one constant-multiplier
  line once per-force outcome data lands.

## Files

```
app.py                Dash app — layout and callbacks
data.py               Builds the per-force allocation dataset
prc_loader.py         Reads the Home Office Police Recorded Crime ODS
workforce_loader.py   Reads the Home Office Police Workforce ODS
geo.py                ONS PFA boundaries (downloads + caches on first run)
build_assets.py       Generates standalone HTML exports for sharing
assets/style.css      Custom styling
data/raw/SOURCES.md   Provenance and gov.uk download links
requirements.txt
```

## Sharable assets

Generate two static HTML exports for slides, screenshots, or chat:

```bash
python build_assets.py
```

Outputs:

- `exports/comparison.html` — side-by-side flat vs subcategorised maps,
  same colour scale. Open in browser, then screenshot.
- `exports/animated.html` — single map that animates between the two
  weightings. Drag the slider or hit play.

Re-run after any change to `data.py` to refresh both files.

## Source attribution

- Crime counts: Home Office, *Police Recorded Crime, Police Force Area
  open data tables* (released 23 April 2026), Open Government Licence.
- Officer FTE: Home Office, *Police Workforce, England and Wales: 31
  March 2025* (released 28 January 2026), Open Government Licence.
- Harm weights: Sherman et al., *Cambridge Crime Harm Index 2020*.
- Boundaries: ONS Open Geography Portal, Police Force Areas (December
  2023) BUC.
- Police force list: data.police.uk / Home Office.
