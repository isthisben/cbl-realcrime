# Source data

Two Home Office Official Statistics releases. Both are open data published
under the Open Government Licence.

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
