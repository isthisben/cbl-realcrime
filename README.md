# Police Resource Allocation Dashboard

Mockup dashboard for **TU/e 4CBLW020 — Real-World Crime project**.

Compares the current officer distribution across the 43 territorial police
forces of England & Wales against a *harm-weighted* allocation derived from
the Cambridge Crime Harm Index (CCHI). Shows whether forces are
over- or under-resourced relative to the harm they handle.

## What's in the dashboard

1. **Choropleth map** — coloured by allocation gap (officer share minus
   harm share). Green = over-resourced, red = under-resourced.
2. **Radar chart** — selected force's crime mix across the 14 police.uk
   categories, normalised against the national average (grey reference).
3. **Toggle: Flat weight vs Subcategorised CCHI** — flips the violence
   weighting between a single 182 weight applied to every violence record
   and a force-specific weighted-average CCHI derived from the actual mix
   of offences (common assault, GBH, rape, homicide, etc.) inside each
   force. Watch the map redistribute colour when you flip it.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8050`.

The first run downloads a ~340KB GeoJSON of the Police Force Areas
(December 2023) from the ONS Open Geography Portal and caches it under
`data/`. Subsequent runs are offline.

## Data status

The figures shown are **mockup ratios** designed to demonstrate what the
finished dashboard will look like. They are plausible but not real:

- Officer FTE values are loosely based on published workforce totals.
- Crime counts and the violence/sexual subgroup mixes are generated
  procedurally with a fixed seed so the layout is reproducible.

Once validation is complete, the mockup generator (`data.py`) will be
replaced by an ingestion layer that reads the actual Home Office PRC
tables and Workforce tables.

## Files

```
app.py            Dash app — layout and callbacks
data.py           Mockup data generator
geo.py            ONS PFA boundaries (downloads + caches on first run)
build_assets.py   Generates standalone HTML exports for sharing
assets/style.css  Custom styling
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

- Boundaries: ONS Open Geography Portal, Police Force Areas (Dec 2023) BUC.
- CCHI weights: Sherman et al., Cambridge Crime Harm Index 2020.
- Police force list: data.police.uk / Home Office.
