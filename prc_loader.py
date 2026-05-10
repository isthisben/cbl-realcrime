"""
Reads the Home Office Police Recorded Crime PFA open data table and returns
per-force counts at PRC Offence Subgroup granularity:

    load_force_subgroup_counts(year)
        force x 23 PRC Offence Subgroups  ->  count

This is the granularity the harm pipeline operates at — every CCHI weight
is assigned per subgroup. Roll-ups to the 13 dashboard categories happen
in `data.py` via `SUBGROUPS_BY_CATEGORY`.

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
# mapped here to keep the loader resilient across years; the load function
# drops any subgroup whose 2024/25 count is zero, so the legacy names fall
# out cleanly without further bookkeeping.
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


def load_force_subgroup_counts(year_sheet: str = DEFAULT_YEAR_SHEET) -> pd.DataFrame:
    """Force x PRC Offence Subgroup counts. Subgroups whose only rows are
    filtered out at the force-name step (Action Fraud / CIFAS / UK Finance
    fraud bookkeeping) are dropped. Pre-2017 burglary subgroups (Domestic /
    Non-domestic) are also dropped here because they carry zero counts in
    2024/25 — the active labels in scope are Residential / Non-residential.
    """
    df = _read_year(year_sheet)

    df = df.assign(category=df["Offence Subgroup"].map(SUBGROUP_TO_CATEGORY))
    unmapped = sorted(df.loc[df["category"].isna(), "Offence Subgroup"].unique().tolist())
    if unmapped:
        raise ValueError(
            f"PRC sheet {year_sheet!r}: unmapped Offence Subgroup values "
            f"(loader needs updating): {unmapped}"
        )

    counts = (
        df.groupby(["Force Name", "Offence Subgroup"])["Number of Offences"]
          .sum()
          .unstack(fill_value=0)
    )
    counts = counts.loc[:, (counts.sum(axis=0) > 0)]
    counts.index.name = "force"
    counts.columns.name = None
    return counts
