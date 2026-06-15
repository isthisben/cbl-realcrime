# Source data

Five releases from the Home Office (Official Statistics + the Police Grant
Report) and one harm-weight release from the University of Cambridge — all open
data published under the Open Government Licence (Home Office) or Creative
Commons (Cambridge). Two further inputs are produced inside the project: the
per-force CCHI weight file (derived from the Cambridge index — see
`CCHI_SOURCES.md`) and the model team's forecast + ILP outputs (see "Model team
outputs" below).

**Scope note.** The raw Home Office releases cover the 43 territorial police
forces of England and Wales. The dashboard reports **42** of them — Greater
Manchester is dropped project-wide because it is absent from the model team's
forecast and ILP outputs. So where a file below is described as covering "43
forces" that is the raw release; the assembled dashboard totals (e.g. £16.69 bn
total funding, 138,331 officer FTE) are over the 42 forces in scope.

## prc-pfa-mar2013-onwards-tables-230426.ods

Police recorded crime — Police Force Area open data tables.
Year ending March 2013 through year ending December 2025 (Q1–Q3 of 2025/26).

- Release page: https://www.gov.uk/government/statistical-data-sets/police-recorded-crime-and-outcomes-open-data-tables
- Release date: 23 April 2026
- Next update: July 2026
- Statistician: John Flatley, Home Office

Long format, one sheet per financial year. Columns:
Financial Year, Financial Quarter, Force Name, Offence Description,
Offence Group, Offence Subgroup, Offence Code, Number of Offences.

The 2024/25 sheet contains 25,356 rows covering 47 entries — 43 territorial
police forces of England & Wales, plus British Transport Police and three
fraud-reporting bodies (Action Fraud, CIFAS, UK Finance) which do not have
police force areas. The dashboard filters to the 43 territorial forces.

## open-data-table-police-workforce-280126.ods

Police workforce, England and Wales — workforce open data table.
Snapshots at 31 March each year, 2007 through 2025.

- Release page: https://www.gov.uk/government/statistics/police-workforce-england-and-wales-31-march-2025
- Release date: 28 January 2026 (revised; supersedes the October 2025 publication)
- Next update: July 2026
- Statistician: Jodie Hargreaves, Home Office

Single Data sheet, 33,529 rows. Columns:
As at 31 March, Geocode, Force name, Region, Sex, Rank, Worker type,
Total (Headcount), Total (FTE).

44 forces (43 territorial + British Transport Police). The dashboard uses
Worker type = "Police Officer" only and the most recent snapshot (31 March
2025).

## open-data-table-police-workforce-functions-280126.ods

Police workforce, England and Wales — functions open data table. Officers and
staff categorised by their primary role under the CIPFA Police Objective
Analysis (POA) framework. Snapshots at 31 March each year, 2015 through 2025.

- Release page: https://www.gov.uk/government/statistics/police-workforce-england-and-wales-31-march-2025
- Release date: 28 January 2026 (revised; supersedes the October 2025 publication)
- Next update: July 2026
- Statistician: Jodie Hargreaves, Home Office

Single Data sheet, 84,957 rows. Columns:
As at 31 March, Geocode, Force name, Region, Worker type, Ethnicity (5+1),
Ethnicity (3+1), Sex, Function subgroup number, Function subgroup name,
Wider function number, Wider function name, Frontline type, Total (FTE).

43 territorial forces (no British Transport Police). The officer function mix
panel uses Worker type = "Police Officer" at the 31 March 2025 snapshot,
summed by Force name and Wider function name (12 wider POA categories). Rows
are cross-tabbed by sex / ethnicity / frontline type; per-force percentage
shares are unaffected because that crossing is uniform across functions. Note
the file carries year-to-year case variants of some labels (e.g. "Local
Policing" vs "Local policing"), which the loader merges case-insensitively.

## police-grant-2025-26.csv

Central government grant per police force, 2025-26 financial year.
Hand-extracted from the Home Office *Police Grant Report (England and Wales)
2025-26* per-force table — the 'Overall Total' column, which is the sum of:

- Police Main Grant
- ex-DCLG Formula Funding (English forces only — Welsh forces receive
  equivalent funding via the Welsh Government)
- Legacy Council Tax Grants (English forces only — same Welsh-routing note)
- Welsh Top-Up (Welsh forces only)

- Release page: https://www.gov.uk/government/publications/police-grant-report-england-and-wales-2025-to-2026
- Statutory instrument laid: 5 February 2025
- Statistician: Police Resources Unit, Home Office

43 rows: force name (canonical dashboard spelling), `budget_gbp` (the column
header is legacy; it holds the formula grant). National total reconciles to
£9,806,553,489. This is the redistributable pool the model reallocates.
Council tax precept (locally raised, not redistributable) is not in this
figure; it enters the dashboard via `funding_loader` (below) as a fixed
component of each force's total funding.

Welsh forces (Dyfed-Powys, Gwent, North Wales, South Wales) appear lower
than English peers here because two of the four component grants flow through
the Welsh Government separately. That under-count does not distort the
allocation gap, which is measured on total funding from
`police-funding-england-and-wales-2015-to-2026-tables.ods` (below) — those
totals include the Welsh-routed money.

## police-funding-england-and-wales-2015-to-2026-tables.ods

Home Office Police Funding England and Wales tables, 2015-16 through
2025-26. Companion publication to the Police Grant Report — published
annually as the Police Funding Statistics release.

- Release page: https://www.gov.uk/government/statistics/police-funding-england-and-wales-2015-to-2026
- Release date: April 2025
- Statistician: Police Resources Unit, Home Office

Thirteen sheets covering eleven financial years of total police funding by
stream. Per-force splits live in `Table_4a` (nominal) and `Table_4b` (real
terms): one row per force, columns grouped by year as Government Funding |
Precept | Total, in £ million. `Table_1a/1b` give national funding by stream;
the rest are breakdowns of wider-system and counter-terrorism funding.

`funding_loader.py` reads `Table_4a` for 2025-26 (the final three data
columns). It keeps the 43 territorial PFAs (ONS codes E23*/W15*, dropping the
E12* region / E92/W92 country / K04 England-and-Wales aggregate rows), reads
City of London's blank precept as £0, and converts £ million to whole pounds.
The dashboard's allocation gap is measured on the `Total` column (grant +
precept + ring-fenced specific grants, £17.57 bn across the 43 forces); the
`Precept` column (£6.06 bn) and the specific grants are held fixed when the
model reallocates. `Government Funding` here is broader than the Police Grant
Report 'Overall Total' (it bundles ring-fenced specific grants such as the
Met's National & International Capital City grant), which is why only the
narrower grant report figure (`police-grant-2025-26.csv`) is treated as the
redistributable pool. Loader validation reconciles national precept to
£6,057,626,419.

## Cambridge-CCHI-2026-update.xlsx

Cambridge Crime Harm Index, 2026 update.

- Release page: https://www.cambridge-ebp.co.uk/crime-harm-index
- Maintainer: Cambridge Centre for Evidence-Based Policing, Institute of
  Criminology, University of Cambridge
- Foundational paper: Sherman, L., Neyroud, P., Neyroud, E. (2016).
  *The Cambridge Crime Harm Index: Measuring Total Harm from Crime Based
  on Sentencing Guidelines.* Policing 10(3): 171–183.
  https://academic.oup.com/policing/article/10/3/171/1753592

Four sheets. The dashboard reads only `CCHI 2026 values sheet`.

`CCHI 2026 values sheet` (1,266 rows × 18 substantive columns + CJS code
spillover): per-offence harm scores covering 786 distinct Home Office
classifications and 1,174 ATHENA URN codes. Columns used: ATHENA URN,
FULL_OFFENCE_TITLE, CCHI Score, Starting Point, GROUP, SUB_GROUP,
SUB_SUB_GROUP, HOME_OFFICE_CLASSIFICATION, HO_CODE, HO_SUB_CODE,
HO_SUB_SUB_CODE.

`Expired offences` (17 rows): Home Office classifications retired before
the 2024/25 PRC reporting period (e.g. pre-2017 burglary classifications
expired 31/03/17, aggravated burglary residential variants expired
2023-05-01). Out of scope — these codes do not appear in the PRC tables
the dashboard uses.

`Offences need clarity` (3 rows): residual ambiguities flagged by the
Cambridge team where the offence-to-code mapping could not be resolved
(Magistrates' Courts Act, Prison Act, Local Government Misc Provisions
Acts catch-alls). Out of scope — these are not the dominant offences in
any PRC subgroup.

`Cover page`: licensing notice, no data.

The CCHI assigns each offence a starting-point sentence in days for a
first-time offender at the basic (least-aggravated) tier of the
Sentencing Council guideline. Custodial sentences are converted directly
to days; community orders use unpaid-work hours; fines use the number of
minimum-wage days needed to clear the fine. The methodology and
aggregation rule used by the dashboard are documented in
`data/raw/CCHI_SOURCES.md`.

## Model team outputs (forecast + ILP)

Produced inside the project by the predictor / optimisation teammates, not
downloaded. They are committed so the dashboard and its deploy ship with them.
The raw deliverables were normalised into the files below — long force names
("X Constabulary" / "X Police") mapped to the canonical 42, and the monthly
forecast kept in long format.

### data/raw/forecast_lgbm.csv

12-month crime forecast per force × category, from a LightGBM model
(`force, crime_type, month, y_pred`; 42 forces × 14 categories × 12 months over
the window March 2026 – February 2027). Normalised from the team's
`forecast_2026_03_to_2027_02.csv` (Vlad) — long force names mapped to the
canonical 42. Covers the 13 recorded categories plus anti-social behaviour.
The "predict" layer of the project; also the source of ASB volumes; the exact
forecast the ILP optimised against. Read by `forecast_loader.py`.

### data/raw/asb_counts.csv

Per-force annual anti-social-behaviour volume (`force, asb_annual_count`),
summed from the ASB rows of the forecast above. ASB has no CCHI score and is
absent from the PRC tables, so it is the one harm input that is
forecast-derived; it is weighted at the CCHI floor (1). Read by `asb_loader.py`.

### data/raw/ilp/

The team's ILP optimiser outputs, optimised against forecast harm under the
per-force CCHI weights. Read by `allocation_loader.py` for the reallocation
panels.

- `Pool_1_Patrol_…`, `Pool_2_Investigators_…`, `Pool_3_PCSOs_…`,
  `all_pools_allocation_results.csv` — workforce reallocation across three
  pools (42 forces; each pool's national FTE total is conserved).
- `grant_redistribution_result.csv` — formula-grant redistribution toward harm
  share (41 forces; City of London, a fraud specialist, sits outside the grant
  model).

### data/raw/hotspots.csv

Top-five stop-and-search hotspots per force, extracted from the data.police.uk
stop-and-search records (2023–2026): for each force, the five locations with the
most recorded searches. Columns `force, rank, Latitude, Longitude, searches,
linked_finds, find_rate`, where `find_rate = linked_finds / searches` is the
share of searches at that location that led to a linked outcome. Stop-and-search
data is published for 39 of the 42 forces, so Gwent, South Yorkshire and
Warwickshire are absent. Force names are data.police.uk slugs, normalised to the
canonical names in `hotspots_loader.py`. Read by `hotspots_loader.py`.
