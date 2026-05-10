"""
Reads the Cambridge Crime Harm Index 2026 values sheet and returns a
representative CCHI weight (in days) for each Home Office Police Recorded
Crime Offence Subgroup the dashboard reports against.

    load_subgroup_cchi()  ->  {prc_subgroup_name: cchi_days}

Aggregation rule
----------------
Sherman 2026 publishes scores at the offence-code (ATHENA URN) level —
1,266 active rows across ~700 distinct offences. PRC publishes counts at
the Offence Subgroup level. To collapse Sherman URNs to a single value
per PRC subgroup we use the *median* CCHI of all Sherman rows whose
SUB_GROUP maps to the PRC subgroup.

Median is preferred over mean because most PRC subgroups contain a small
number of rare-but-severe offences (firearms within 'Possession of
weapons offences', GBH-with-intent within 'Violence with injury') whose
high CCHI scores pull the mean far above the typical reported offence.
The median picks a representative central value that is robust to those
tails. Both statistics are surfaced in `data/raw/CCHI_SOURCES.md` so the
sensitivity to this choice is auditable.

Notes on coverage
-----------------
- The 'Expired offences' sheet of the source file lists Home Office codes
  retired before the 2024/25 PRC reporting period and is excluded.
- The 'Offences need clarity' sheet (3 rows) is excluded as those rows
  carry no resolved subgroup mapping.
- 'Death or serious injury - unlawful driving' has no dedicated Sherman
  SUB_GROUP; the 12 driving-death and serious-injury offences live under
  GROUP = 'VIOLENCE AGAINST THE PERSON' with various SUB_SUB_GROUP names.
  They are matched by FULL_OFFENCE_TITLE pattern.

Source file: data/raw/Cambridge-CCHI-2026-update.xlsx
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "Cambridge-CCHI-2026-update.xlsx"

VALUES_SHEET = "CCHI 2026 values sheet"

# PRC Offence Subgroup -> Sherman SUB_GROUP value(s).
# Where the right-hand side has more than one entry, the PRC subgroup spans
# multiple Sherman SUB_GROUP labels; rows are pooled before taking the median.
# 'Death or serious injury - unlawful driving' is resolved by title pattern
# rather than SUB_GROUP and is handled below.
PRC_TO_SHERMAN_SUBGROUP: dict[str, list[str]] = {
    # Violence and sexual
    "Homicide":                  ["HOMICIDE"],
    "Violence with injury":      ["VIOLENCE WITH INJURY"],
    "Violence without injury":   ["VIOLENCE WITHOUT INJURY"],
    "Stalking and harassment":   ["STALKING AND HARASSMENT"],
    "Rape offences":             ["RAPE"],
    "Other sexual offences":     ["OTHER SEXUAL OFFENCES"],

    # Burglary — Sherman labels differ from PRC slightly
    "Residential burglary":      ["BURGLARY - RESIDENTIAL", "BURGLARY IN A DWELLING"],
    "Non-residential burglary":  ["BURGLARY - BUSINESS AND COMMUNITY"],

    # Theft family
    "Shoplifting":               ["SHOPLIFTING"],
    "Other theft offences":      ["OTHER THEFT"],
    "Theft from the person":     ["THEFT FROM THE PERSON"],
    "Bicycle theft":             ["BICYCLE THEFT"],

    # Robbery
    "Robbery of business property": ["ROBBERY OF BUSINESS PROPERTY"],
    "Robbery of personal property": ["ROBBERY OF PERSONAL PROPERTY"],

    # Damage / arson
    "Criminal damage":           ["CRIMINAL DAMAGE"],
    "Arson":                     ["ARSON"],

    # Public order — Sherman splits this PRC subgroup across four labels
    "Public order offences":     ["OTHER OFFENCES PUBLIC ORDER",
                                  "PUBLIC FEAR, ALARM OR DISTRESS",
                                  "RACE OR RELIGIOUS AGG PUBLIC FEAR",
                                  "VIOLENT DISORDER"],

    # Vehicle — Sherman splits this PRC subgroup across four labels
    "Vehicle offences":          ["AGGRAVATED VEHICLE TAKING",
                                  "INTERFERING WITH A MOTOR VEHICLE",
                                  "THEFT FROM A VEHICLE",
                                  "THEFT OR UNAUTH TAKING OF A MOTOR VEH"],

    # Drugs
    "Possession of drugs":       ["POSSESSION OF DRUGS"],
    "Trafficking of drugs":      ["TRAFFICKING OF DRUGS"],

    # Other
    "Possession of weapons offences":         ["POSSESSION OF WEAPONS"],
    "Miscellaneous crimes against society":   ["MISC CRIMES AGAINST SOCIETY"],
}


_cache: dict[str, dict[str, float]] = {}


def _load_values_sheet() -> pd.DataFrame:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Sherman CCHI source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the cambridge-ebp.co.uk download link."
        )

    df = pd.read_excel(SOURCE, sheet_name=VALUES_SHEET, engine="openpyxl")

    required = {"FULL_OFFENCE_TITLE", "CCHI Score", "GROUP", "SUB_GROUP"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Sherman sheet {VALUES_SHEET!r}: missing columns {missing}")

    df["CCHI Score"] = pd.to_numeric(df["CCHI Score"], errors="coerce")
    df = df.dropna(subset=["CCHI Score"]).copy()
    return df


def _driving_death_rows(df: pd.DataFrame) -> pd.DataFrame:
    """The PRC subgroup 'Death or serious injury - unlawful driving' has no
    dedicated Sherman SUB_GROUP. The matching offences live under
    GROUP = 'VIOLENCE AGAINST THE PERSON' (or, for a few rows, missing GROUP)
    with FULL_OFFENCE_TITLE describing causing death or serious injury by
    driving. We match by title pattern."""
    title = df["FULL_OFFENCE_TITLE"].astype(str).str.lower()
    is_outcome = (
        title.str.contains("death by", na=False)
        | title.str.contains("serious injury by", na=False)
        | title.str.contains("causing serious injury", na=False)
    )
    is_driving = (
        title.str.contains("driv", na=False)
        | title.str.contains("vehicle", na=False)
    )
    is_expired = title.str.contains("expired", na=False)
    return df[is_outcome & is_driving & ~is_expired]


def load_subgroup_cchi() -> dict[str, float]:
    if "values" in _cache:
        return _cache["values"]

    df = _load_values_sheet()

    cchi: dict[str, float] = {}
    for prc_sg, sherman_sgs in PRC_TO_SHERMAN_SUBGROUP.items():
        rows = df[df["SUB_GROUP"].isin(sherman_sgs)]
        if rows.empty:
            raise ValueError(
                f"No Sherman rows matched SUB_GROUP(s) {sherman_sgs!r} for "
                f"PRC subgroup {prc_sg!r}. Cambridge may have renamed labels — "
                "update PRC_TO_SHERMAN_SUBGROUP."
            )
        cchi[prc_sg] = float(rows["CCHI Score"].median())

    driving = _driving_death_rows(df)
    if driving.empty:
        raise ValueError(
            "No Sherman rows matched the driving-death pattern. The "
            "FULL_OFFENCE_TITLE conventions in Sherman 2026 may have changed — "
            "review _driving_death_rows()."
        )
    cchi["Death or serious injury - unlawful driving"] = float(
        driving["CCHI Score"].median()
    )

    _cache["values"] = cchi
    return cchi


def load_subgroup_cchi_with_diagnostics() -> pd.DataFrame:
    """Per-PRC-subgroup table including row counts and mean for the
    methodology document. Not used in the live dashboard pipeline."""
    df = _load_values_sheet()

    rows = []
    for prc_sg, sherman_sgs in PRC_TO_SHERMAN_SUBGROUP.items():
        sel = df[df["SUB_GROUP"].isin(sherman_sgs)]
        rows.append({
            "prc_subgroup":      prc_sg,
            "sherman_subgroups": ", ".join(sherman_sgs),
            "n":                 len(sel),
            "min":               float(sel["CCHI Score"].min()),
            "median":            float(sel["CCHI Score"].median()),
            "mean":              round(float(sel["CCHI Score"].mean()), 2),
            "max":               float(sel["CCHI Score"].max()),
        })

    driving = _driving_death_rows(df)
    rows.append({
        "prc_subgroup":      "Death or serious injury - unlawful driving",
        "sherman_subgroups": "(matched by title pattern across VIOLENCE AGAINST THE PERSON)",
        "n":                 len(driving),
        "min":               float(driving["CCHI Score"].min()),
        "median":            float(driving["CCHI Score"].median()),
        "mean":              round(float(driving["CCHI Score"].mean()), 2),
        "max":               float(driving["CCHI Score"].max()),
    })

    return pd.DataFrame(rows)
