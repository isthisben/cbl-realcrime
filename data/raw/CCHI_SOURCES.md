# Cambridge Crime Harm Index — values used by the dashboard

This document records every CCHI value the dashboard applies to a Police
Recorded Crime Offence Subgroup, the source row(s) those values are
derived from, the aggregation rule used, and the assumptions and
limitations that come with the methodology.

## Source

Cambridge Crime Harm Index, 2026 update. Cambridge Centre for
Evidence-Based Policing, Institute of Criminology, University of
Cambridge.

- File: `data/raw/Cambridge-CCHI-2026-update.xlsx`
- Sheet read: `CCHI 2026 values sheet` (1,266 rows covering 786 distinct
  Home Office offence classifications and 1,174 ATHENA URN codes; six
  EXPIRED rows are dropped at load time, see Coverage notes below)
- Foundational paper: Sherman, L., Neyroud, P., Neyroud, E. (2016). *The
  Cambridge Crime Harm Index: Measuring Total Harm from Crime Based on
  Sentencing Guidelines.* Policing 10(3): 171–183.

The Sherman methodology assigns each offence a starting-point sentence,
in days, for a previously-unconvicted offender at the basic
(least-aggravated) tier of the relevant Sentencing Council guideline.
Custodial starting points are converted directly to days; community
orders use unpaid-work hours; fines use the number of minimum-wage days
needed to clear the fine. Offender history, aggravating factors, and
mitigating factors are excluded by construction.

## Granularity and the aggregation rule

Sherman publishes scores at the offence-code (ATHENA URN) level. The
Police Recorded Crime PFA tables published by the Home Office only
publish counts at the *Offence Subgroup* level. Subgroup is therefore
the finest level at which Sherman scores can be joined to PRC volumes.

For each PRC Offence Subgroup we use the **median** CCHI of all Sherman
2026 entries that fall under it. Median is preferred over mean for two
reasons:

1. **Robustness to right-tail outliers.** Several PRC subgroups contain a
   long-tailed distribution of severities — firearms-with-intent inside
   `Possession of weapons`, GBH-with-intent inside `Violence with
   injury`, class-A trafficking inside `Trafficking of drugs`. The mean
   of these distributions sits well above the typical reported offence,
   because the rare extremes pull it up. The median picks the central
   value of the distribution, which more closely reflects what an
   arbitrarily-selected reported offence in that subgroup looks like.

2. **Alignment with Sherman's "first rung of the ladder" principle.**
   The 2016 paper specifies the lowest starting point for an offence,
   not the average across severity tiers. Median per subgroup applies
   the same logic at the aggregation level.

A volume-weighted average across URNs *within* a subgroup would be more
rigorous than either median or mean, but requires URN-level offence
counts which the PRC PFA tables do not publish. The same row count and
mean are reported alongside the median below so the sensitivity of the
choice to median-vs-mean is auditable.

## Subgroup CCHI values

Read this table as: for the PRC Offence Subgroup in column 1, we pool
Sherman rows whose `SUB_GROUP` is in column 2, and the value used is the
median (column 4).

| PRC Offence Subgroup                       | Sherman SUB_GROUP                                                                                    |   n |  min |  **median** |    mean |    max |
|--------------------------------------------|------------------------------------------------------------------------------------------------------|----:|-----:|---:|--------:|-------:|
| Homicide                                   | HOMICIDE                                                                                             |   3 |  730 | **5,475** | 3,893.3 |  5,475 |
| Violence with injury                       | VIOLENCE WITH INJURY                                                                                 |  73 |    2 |   **365** |   943.5 |  4,380 |
| Violence without injury                    | VIOLENCE WITHOUT INJURY                                                                              |  49 |    1 |    **10** |   437.4 |  5,475 |
| Stalking and harassment                    | STALKING AND HARASSMENT                                                                              |  23 |    2 |    **10** |    35.0 |    252 |
| Rape offences                              | RAPE                                                                                                 |  17 | 1,825| **2,555** | 2,726.8 |  4,745 |
| Other sexual offences                      | OTHER SEXUAL OFFENCES                                                                                | 138 |    5 | **182.25**|   395.6 |  2,555 |
| Death or serious injury - unlawful driving | (matched by FULL_OFFENCE_TITLE pattern across VIOLENCE AGAINST THE PERSON)                           |  11 |   10 |   **365** |   380.4 |  1,095 |
| Residential burglary                       | BURGLARY - RESIDENTIAL, BURGLARY IN A DWELLING                                                       |  12 |    2 | **273.5** |   275.7 |    730 |
| Non-residential burglary                   | BURGLARY - BUSINESS AND COMMUNITY                                                                    |   4 |    2 | **183.5** |   183.5 |    365 |
| Shoplifting                                | SHOPLIFTING                                                                                          |   2 |    1 |     **1** |     1.0 |      1 |
| Other theft offences                       | OTHER THEFT                                                                                          |  22 |    1 |     **2** |    20.8 |    182 |
| Theft from the person                      | THEFT FROM THE PERSON                                                                                |   2 |    2 |     **2** |     2.0 |      2 |
| Bicycle theft                              | BICYCLE THEFT                                                                                        |   4 |    2 |     **2** |     2.0 |      2 |
| Robbery of business property               | ROBBERY OF BUSINESS PROPERTY                                                                         |   4 |  365 |   **365** |   365.0 |    365 |
| Robbery of personal property               | ROBBERY OF PERSONAL PROPERTY                                                                         |   4 |  365 |   **365** |   365.0 |    365 |
| Criminal damage                            | CRIMINAL DAMAGE                                                                                      |  30 |    1 |     **2** |    86.3 |    365 |
| Arson                                      | ARSON                                                                                                |   4 |    5 |   **185** |   185.0 |    365 |
| Public order offences                      | OTHER OFFENCES PUBLIC ORDER, PUBLIC FEAR ALARM OR DISTRESS, RACE OR RELIGIOUS AGG, VIOLENT DISORDER  |  50 |    1 |   **7.5** |    52.7 |    730 |
| Vehicle offences                           | AGGRAVATED VEHICLE TAKING, INTERFERING WITH A MOTOR VEHICLE, THEFT FROM A VEHICLE, THEFT/UNAUTH      |  15 |    2 |     **5** |     6.4 |     10 |
| Possession of drugs                        | POSSESSION OF DRUGS                                                                                  |  39 |    1 |     **3** |    17.4 |  547.5 |
| Trafficking of drugs                       | TRAFFICKING OF DRUGS                                                                                 |  68 |    1 |     **5** |   236.2 |  547.5 |
| Possession of weapons offences             | POSSESSION OF WEAPONS                                                                                |  40 |    1 | **273.75**|   541.2 |  2,190 |
| Miscellaneous crimes against society       | MISC CRIMES AGAINST SOCIETY                                                                          | 145 |    1 |    **10** |    73.7 |  1,460 |

These numbers are reproduced live by `cchi_loader.load_subgroup_cchi()`
from the source spreadsheet — the dashboard does not hold a hard-coded
copy of them, so future Sherman updates are picked up by re-running.

## National-mix CCHI per dashboard category

For the "single CCHI per category" mode the dashboard computes one CCHI
per category as the volume-weighted average of its subgroup CCHIs,
weighted by national 2024/25 PRC counts:

| Category                     | National-mix CCHI | Notes                                                                                |
|------------------------------|------------------:|--------------------------------------------------------------------------------------|
| Violence and sexual offences |            194.21 | 7 subgroups; weighted heavily by violence-without-injury and stalking volume         |
| Burglary                     |            244.68 | residential 68% / non-residential 32% nationally                                     |
| Robbery                      |            365.00 | both subgroups carry the same CCHI; mix is irrelevant                                |
| Possession of weapons        |            273.75 | single subgroup                                                                      |
| Criminal damage and arson    |             11.18 | criminal damage 95% / arson 5% nationally; arson dominates harm despite low volume   |
| Public order                 |              7.50 | single subgroup                                                                      |
| Other crime                  |             10.00 | single subgroup (Misc crimes against society)                                        |
| Vehicle crime                |              5.00 | single subgroup                                                                      |
| Drugs                        |              3.66 | possession 67% / trafficking 33% nationally; both subgroups have low median CCHIs    |
| Other theft                  |              2.00 | single subgroup                                                                      |
| Theft from the person        |              2.00 | single subgroup                                                                      |
| Bicycle theft                |              2.00 | single subgroup                                                                      |
| Shoplifting                  |              1.00 | single subgroup                                                                      |

For the eight single-subgroup categories the national-mix CCHI is
identical to the subgroup CCHI; the toggle between "single CCHI per
category" and "subgroup-weighted per force" has no effect on those.
The toggle only meaningfully differs for the five multi-subgroup
categories: Violence and sexual offences, Burglary, Criminal damage and
arson, Drugs, Robbery.

## Coverage notes

- The `Expired offences` sheet (17 rows) lists Home Office classifications
  retired before the 2024/25 PRC reporting period (e.g. pre-2017 burglary
  classifications expired 31/03/17, aggravated burglary residential
  expired 2023-05-01). These offences do not appear in the 2024/25 PRC
  data and are excluded.
- Six rows in the main values sheet also carry `EXPIRED` in
  `FULL_OFFENCE_TITLE` (one in `BURGLARY IN A DWELLING`, one in
  `VIOLENCE WITHOUT INJURY`, one in `NON-NOTIFIABLE`, three with no
  `SUB_GROUP`). These are filtered out globally in
  `cchi_loader._load_values_sheet` so a retired offence code's CCHI
  cannot pull the median for the active codes that share its subgroup.
  The Residential burglary median in particular falls from 365 (with
  the expired pre-2017 "burglary in a dwelling with intent" row at
  CCHI = 730 included) to 273.5 (n = 12, the active codes only).
- The `Offences need clarity` sheet (3 rows: Magistrates' Courts Act,
  Prison Act, Local Government Misc Provisions Acts catch-alls) carries
  no resolved subgroup mapping in Sherman 2026 and is excluded.
- Sherman's `SUB_GROUP` column matches the PRC Offence Subgroup label
  exactly for 14 of the 23 subgroups. The remaining 9 are resolved by:
    1. Pooling multiple Sherman SUB_GROUPs — Residential burglary
       (`BURGLARY - RESIDENTIAL` + `BURGLARY IN A DWELLING`), Public
       order offences (4 labels), Vehicle offences (4 labels).
    2. Dropping a trailing `offences` from the PRC label — Rape
       offences → `RAPE`, Other theft offences → `OTHER THEFT`,
       Possession of weapons offences → `POSSESSION OF WEAPONS`.
    3. Other label restructures — Non-residential burglary →
       `BURGLARY - BUSINESS AND COMMUNITY`; Miscellaneous crimes
       against society → `MISC CRIMES AGAINST SOCIETY` (abbreviation).
    4. `FULL_OFFENCE_TITLE` pattern — Death or serious injury -
       unlawful driving (no dedicated Sherman SUB_GROUP).

  The mapping lives in `cchi_loader.PRC_TO_SHERMAN_SUBGROUP`.

## Documented deviations from the Sherman methodology

1. **Proactively-detected offences are included.** Sherman 2016 (page
   172) recommends excluding drug arrests, traffic arrests, and
   shop-detective shoplifting from the harm count base, on the grounds
   that their volume reflects police resourcing rather than crime
   patterns. The dashboard includes these because its purpose is to
   measure police *workload*-relevant harm — drug enforcement and
   shoplifting are real demands on police time even if they would bias a
   citizen-reported harm index. This is a deliberate departure from
   Sherman's recommended scope; it should be defended on its own merits
   in any methodological discussion rather than presented as
   Sherman-pure.

2. **Resolution-rate term is dropped.** The full Sherman formula is
   `count × CCHI × (1 − clearance_rate)`. The Home Office Outcomes Open
   Data Tables only publish per-force breakdowns for fraud offences, not
   for the categories the dashboard reports against. The dashboard
   therefore uses `count × CCHI` and treats the resolution-rate term as
   uniform across forces. Reintroducing it is a one-line change once
   per-force clearance data lands (data.police.uk record-level outcomes
   pipeline).

3. **Subgroup-level rather than URN-level aggregation.** Sherman's index
   is most rigorous at the URN level. PRC PFA tables do not publish URN
   counts, so subgroup is the finest available joinable level. Going to
   URN granularity would require pulling data.police.uk record-level
   data — out of scope for this dashboard but documented as a future
   improvement.

## Known limitations

- **Anti-social behaviour** is not in PRC; it is recorded as an incident
  rather than a notifiable crime. The radar carries 13 axes rather than
  14 for this reason. ASB exists in the data.police.uk record-level data
  and could be added with a separate harm weight if that pipeline is
  integrated.
- **Single-CCHI-per-subgroup compromises** are unavoidable for subgroups
  with bimodal severity distributions (Drugs: class A vs class B/C;
  Possession of weapons: bladed article vs firearms). Median is robust
  but understates harm where rare-but-severe offences carry meaningful
  volume share. The mean column above quantifies this gap per subgroup.
- **Sherman's CCHI itself** uses sentencing-day equivalents as a proxy
  for harm, which is philosophically debatable — a victim of an
  18-month-tariff offence may experience harm differently from a
  sentencing-day-equivalent suggests. The CCHI is a transparent and
  reproducible *proxy*, not a victim-experience scale.
- **English & Welsh-only.** Sentencing Council guidelines do not cover
  Scotland, so the index would not transfer to Police Scotland data.
