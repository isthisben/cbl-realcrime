# Cambridge Crime Harm Index: values used by the dashboard

This document records the CCHI weighting the dashboard applies, how the
per-force category weights are derived from the Cambridge index, and the
assumptions and limitations that come with the methodology.

The dashboard weights harm at the **per-force, per-category** level: for each
force and each of the 13 recorded-crime categories there is one CCHI value (in
days), read from `data/cchi_weights_by_force_category.csv`. This is the exact
weighting the project's ILP optimiser consumed, so the dashboard's harm picture
and the optimiser outputs rest on one shared file.

## Source

Cambridge Crime Harm Index, 2026 update. Cambridge Centre for
Evidence-Based Policing, Institute of Criminology, University of
Cambridge.

- File: `data/raw/Cambridge-CCHI-2026-update.xlsx`
- Sheet read: `CCHI 2026 values sheet` (1,266 rows covering 786 distinct
  Home Office offence classifications and 1,174 ATHENA URN codes; EXPIRED
  rows are dropped, see Coverage notes)
- Foundational paper: Sherman, L., Neyroud, P., Neyroud, E. (2016). *The
  Cambridge Crime Harm Index: Measuring Total Harm from Crime Based on
  Sentencing Guidelines.* Policing 10(3): 171–183.

The Sherman methodology assigns each offence a starting-point sentence, in
days, for a previously-unconvicted offender at the basic (least-aggravated)
tier of the relevant Sentencing Council guideline. Offender history,
aggravating factors, and mitigating factors are excluded by construction.

## Derivation (two steps)

Sherman publishes scores at the offence-code (ATHENA URN) level; the Home
Office Police Recorded Crime PFA tables publish counts at the *Offence
Subgroup* level. Subgroup is therefore the finest level at which Sherman
scores join to PRC volumes. The per-force category weight is built in two
steps:

1. **Median CCHI per PRC Offence Subgroup.** The median of all Sherman 2026
   entries under that subgroup (table below). Median is preferred over mean
   for robustness to right-tail outliers (firearms within `Possession of
   weapons`, GBH-with-intent within `Violence with injury`) and to match
   Sherman's "first rung of the ladder" principle.

2. **Volume-weighted average to the 13 categories, per force.** Each
   category's CCHI for a force is the count-weighted average of its subgroup
   medians, using that force's own 2024/25 subgroup mix. Nine categories map
   to a single offence severity, so they collapse to one national value
   identical for every force. Four composite categories bundle subgroups of
   different severity, so they vary per force. (Robbery bundles two subgroups
   but Cambridge scores both at 365, so it is constant.)

This is mathematically the per-offence harm `Σ count × subgroup-CCHI`,
re-expressed at category granularity. The dashboard reads the resulting
per-force file directly rather than recomputing, so it shows exactly the
numbers the ILP optimised against.

## Subgroup CCHI values (step 1)

For the PRC Offence Subgroup in column 1, pool Sherman rows whose `SUB_GROUP`
is in column 2; the value used is the median (bold).

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

## Per-force category weights (step 2)

`cchi_loader.load_force_category_cchi()` reads
`data/cchi_weights_by_force_category.csv`, one row per force × category. Nine
categories carry a single national weight; four vary per force:

| Category                     | Per force? | Value / range (days) | Notes                                                            |
|------------------------------|:----------:|---------------------:|------------------------------------------------------------------|
| Robbery                      |     no     |              365.00  | two subgroups, both 365, mix is irrelevant                      |
| Possession of weapons        |     no     |              273.75  | single subgroup                                                  |
| Other crime                  |     no     |               10.00  | single subgroup (Misc crimes against society)                    |
| Public order                 |     no     |                7.50  | single subgroup                                                  |
| Vehicle crime                |     no     |                5.00  | single subgroup                                                  |
| Other theft                  |     no     |                2.00  | single subgroup                                                  |
| Theft from the person        |     no     |                2.00  | single subgroup                                                  |
| Bicycle theft                |     no     |                2.00  | single subgroup                                                  |
| Shoplifting                  |     no     |                1.00  | single subgroup                                                  |
| Violence and sexual offences |   **yes**  |        159.07 – 235.12 | 7 subgroups, homicide 5,475 … harassment 10                     |
| Burglary                     |   **yes**  |        190.70 – 252.52 | residential 273.5 / non-residential 183.5                       |
| Criminal damage and arson    |   **yes**  |          4.94 – 18.19 | arson 185 / criminal damage 2                                   |
| Drugs                        |   **yes**  |           3.25 – 3.96 | trafficking 5 / possession 3                                    |

A force with a more severe within-category mix (more residential burglary, or
more homicide/rape within violence) earns a heavier weight per offence.

## Anti-social behaviour: the floor

ASB is the single highest-volume category a force handles, but it is logged as
incidents, not notifiable crime, so it has no Cambridge CCHI score and is
absent from the PRC tables. To represent it without distorting a harm total
dominated by violence and burglary, the dashboard sets it at the harm **floor**: CCHI = 1 day per incident (`cchi_loader.ASB_FLOOR_CCHI`), the value Cambridge
gives the lowest notifiable offence (shoplifting). ASB volumes are
forecast-derived (`asb_loader`, from the LightGBM forecast, data.police.uk
lineage), so ASB appears as a labelled 14th radar axis and a small additive
harm term (~0.17% of national harm), never folded silently into the recorded
figures.

## Recorded now, forecast for allocation

The map and radar score harm on **recorded** crime (PRC 2024/25), the harm
forces face today. The ILP allocation was optimised against **forecast** harm
(predicted next 12 months) under these same weights. The two track each other
closely (≈0.998 correlation on harm share) without being identical, because the
optimiser ran on the team's own forecast extract: diagnose on actuals, optimise
on the forecast.

## Coverage notes

- The `Expired offences` sheet (17 rows) lists Home Office classifications
  retired before the 2024/25 PRC reporting period (e.g. pre-2017 burglary
  classifications). These do not appear in the 2024/25 PRC data and are
  excluded.
- Six rows in the main values sheet carry `EXPIRED` in `FULL_OFFENCE_TITLE`
  and are filtered out so a retired offence code's CCHI cannot pull the median
  for the active codes that share its subgroup. The Residential burglary median
  in particular falls from 365 (with the expired pre-2017 row at CCHI = 730
  included) to 273.5 (n = 12, active codes only).
- The `Offences need clarity` sheet (3 rows) carries no resolved subgroup
  mapping in Sherman 2026 and is excluded.
- The PRC subgroup → dashboard category roll-up lives in
  `prc_loader.SUBGROUP_TO_CATEGORY`. The subgroup-median values in the table
  above were derived from the Cambridge file with that mapping; the live
  pipeline now reads the per-force category file produced from them.

## Documented deviations from the Sherman methodology

1. **Proactively-detected offences are included.** Sherman 2016 (p. 172)
   recommends excluding drug arrests, traffic arrests, and shop-detective
   shoplifting, on the grounds their volume reflects police resourcing rather
   than crime patterns. The dashboard includes these because its purpose is to
   measure police *workload*-relevant harm. This is a deliberate departure from
   Sherman's recommended scope and should be defended on its own merits, not
   presented as Sherman-pure.

2. **Resolution-rate term is dropped.** The full Sherman formula is
   `count × CCHI × (1 − clearance_rate)`. The Home Office Outcomes Open Data
   Tables only publish per-force breakdowns for fraud, so the dashboard uses
   `count × CCHI` and treats clearance as uniform across forces. Reintroducing
   it is a one-line change once per-force clearance data lands.

3. **Subgroup-level rather than URN-level aggregation.** Sherman's index is
   most rigorous at URN level. PRC PFA tables do not publish URN counts, so
   subgroup is the finest available joinable level.

## Known limitations

- **Anti-social behaviour volumes are forecast-derived**, not recorded crime
  (see the floor section). They are the one input not drawn from a Home Office
  recorded-crime table, which is why the ASB axis/term is labelled as such
  everywhere it appears.
- **Single-CCHI-per-subgroup compromises** are unavoidable for subgroups with
  bimodal severity (Drugs: class A vs B/C; Possession of weapons: bladed vs
  firearms). Median is robust but understates harm where rare-but-severe
  offences carry meaningful volume; the mean column above quantifies this gap.
- **Sherman's CCHI** uses sentencing-day equivalents as a transparent,
  reproducible *proxy* for harm, not a victim-experience scale.
- **English & Welsh-only.** Sentencing Council guidelines do not cover
  Scotland, so the index would not transfer to Police Scotland data.
