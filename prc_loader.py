"""
Reads the Home Office Police Recorded Crime PFA open data table and returns
per-force counts grouped two ways:

    load_force_crime_counts(year)
        force x 13 dashboard categories  ->  count

    load_force_violence_subgroups(year)
        force x 7 violence/sexual subgroups  ->  count

Forces that are not territorial PFAs (British Transport Police and the three
fraud-reporting bodies) are filtered out. Force names are normalised to the
canonical list in data.py.

Source file: data/raw/prc-pfa-mar2013-onwards-tables-230426.ods
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "prc-pfa-mar2013-onwards-tables-230426.ods"

DEFAULT_YEAR_SHEET = "2024_25"

# Entries in Force Name that are not one of the 43 territorial police forces.
NON_PFA_ENTRIES = {
    "Action Fraud",
    "CIFAS",
    "UK Finance",
    "British Transport Police",
}

# Canonical naming used by data.py and the ONS PFA geojson (after geo.py
# rewrites). The PRC source uses the same names except for City of London.
FORCE_NAME_FIXES = {
    "London, City of": "City of London",
}

# PRC Offence Subgroup -> dashboard crime category. Covers 13 of the 14
# dashboard categories. Anti-social behaviour is not in PRC and is omitted.
# When the burglary subdivision changed in 2017 the older subgroup names
# were retained for back-series consistency, so both old and new names are
# mapped here to keep the loader resilient across years.
SUBGROUP_TO_CATEGORY = {
    "Homicide":                                   "Violence and sexual offences",
    "Violence with injury":                       "Violence and sexual offences",
    "Violence without injury":                    "Violence and sexual offences",
    "Stalking and harassment":                    "Violence and sexual offences",
    "Death or serious injury - unlawful driving": "Violence and sexual offences",
    "Rape offences":                              "Violence and sexual offences",
    "Other sexual offences":                      "Violence and sexual offences",
    "Public order offences":                      "Public order",
    "Arson":                                      "Criminal damage and arson",
    "Criminal damage":                            "Criminal damage and arson",
    "Shoplifting":                                "Shoplifting",
    "Other theft offences":                       "Other theft",
    "Vehicle offences":                           "Vehicle crime",
    "Residential burglary":                       "Burglary",
    "Non-residential burglary":                   "Burglary",
    "Domestic burglary":                          "Burglary",
    "Non-domestic burglary":                      "Burglary",
    "Theft from the person":                      "Theft from the person",
    "Bicycle theft":                              "Bicycle theft",
    "Possession of drugs":                        "Drugs",
    "Trafficking of drugs":                       "Drugs",
    "Robbery of business property":               "Robbery",
    "Robbery of personal property":               "Robbery",
    "Possession of weapons offences":             "Possession of weapons",
    "Miscellaneous crimes against society":       "Other crime",
    "Fraud: Action Fraud":                        "Other crime",
    "Fraud: CIFAS":                               "Other crime",
    "Fraud: UK Finance":                          "Other crime",
}

# Subgroup name in PRC -> subgroup name in data.VIOLENCE_SUBGROUPS.
SUBGROUP_TO_VIOLENCE_KEY = {
    "Homicide":                                   "Homicide",
    "Violence with injury":                       "Violence with injury",
    "Violence without injury":                    "Violence without injury",
    "Stalking and harassment":                    "Stalking and harassment",
    "Death or serious injury - unlawful driving": "Death/serious injury - driving",
    "Rape offences":                              "Rape",
    "Other sexual offences":                      "Other sexual offences",
}


_cache: dict[str, pd.DataFrame] = {}


def _read_year(year_sheet: str) -> pd.DataFrame:
    if year_sheet in _cache:
        return _cache[year_sheet]

    if not SOURCE.exists():
        raise FileNotFoundError(
            f"PRC source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the gov.uk download link."
        )

    df = pd.read_excel(SOURCE, sheet_name=year_sheet, engine="odf")

    required = {"Force Name", "Offence Subgroup", "Number of Offences", "Financial Quarter"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"PRC sheet {year_sheet!r}: missing columns {missing}")

    df = df[~df["Force Name"].isin(NON_PFA_ENTRIES)].copy()
    df["Force Name"] = df["Force Name"].replace(FORCE_NAME_FIXES)

    quarters = sorted(df["Financial Quarter"].dropna().unique().tolist())
    if quarters != [1, 2, 3, 4]:
        raise ValueError(f"PRC sheet {year_sheet!r}: expected quarters [1,2,3,4], got {quarters}")

    _cache[year_sheet] = df
    return df


def load_force_crime_counts(year_sheet: str = DEFAULT_YEAR_SHEET) -> pd.DataFrame:
    df = _read_year(year_sheet)

    df = df.assign(category=df["Offence Subgroup"].map(SUBGROUP_TO_CATEGORY))
    unmapped = sorted(df.loc[df["category"].isna(), "Offence Subgroup"].unique().tolist())
    if unmapped:
        raise ValueError(
            f"PRC sheet {year_sheet!r}: unmapped Offence Subgroup values "
            f"(loader needs updating): {unmapped}"
        )

    counts = (
        df.groupby(["Force Name", "category"])["Number of Offences"]
          .sum()
          .unstack(fill_value=0)
    )
    counts.index.name = "force"
    counts.columns.name = None
    return counts


def load_force_violence_subgroups(year_sheet: str = DEFAULT_YEAR_SHEET) -> pd.DataFrame:
    df = _read_year(year_sheet)

    violence = df[df["Offence Subgroup"].isin(SUBGROUP_TO_VIOLENCE_KEY)].copy()
    violence["subgroup"] = violence["Offence Subgroup"].map(SUBGROUP_TO_VIOLENCE_KEY)

    counts = (
        violence.groupby(["Force Name", "subgroup"])["Number of Offences"]
                .sum()
                .unstack(fill_value=0)
    )
    counts.index.name = "force"
    counts.columns.name = None
    return counts
