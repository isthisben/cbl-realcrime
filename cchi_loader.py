"""
Cambridge Crime Harm Index (CCHI) weight per force and dashboard crime
category, in days.

    load_force_category_cchi()  ->  {force: {category: cchi_days}}

This is the harm weighting the whole project shares — the model team ran their
ILP allocation on these exact weights, so the dashboard reads them from the
same file rather than recomputing, guaranteeing the harm picture and the ILP
outputs rest on one source of truth.

How the weights are built (data/cchi_weights_by_force_category.csv)
------------------------------------------------------------------
Each of the 13 data.police.uk crime categories carries a CCHI value in days,
the Cambridge 2026 starting-point sentence for the underlying offence. Nine
categories map to a single offence severity, so they take one national value
that is identical for every force:

    Robbery 365, Possession of weapons 273.75, Other crime 10, Public order
    7.5, Vehicle crime 5, Other theft 2, Theft from the person 2, Bicycle
    theft 2, Shoplifting 1.

(Robbery bundles business + personal robbery, but Cambridge scores both at 365,
so its volume-weighted value is 365 for every force — it does not vary.)

The other four categories bundle PRC offence subgroups of *different* severity,
so each force's value is the volume-weighted average of those subgroup CCHIs
using that force's own offence mix. These vary per force:

    Violence and sexual offences  (homicide 5,475 ... harassment 10)   159 - 235
    Burglary                      (residential 273.5 vs non-res 183.5) 191 - 253
    Criminal damage and arson     (arson 185 vs criminal damage 2)     5 - 18
    Drugs                         (trafficking 5 vs possession 3)      3.3 - 4.0

A force with a more severe within-category mix (more residential burglary, more
homicide/rape within violence) earns a heavier effective weight per offence.

Anti-social behaviour floor
---------------------------
ASB carries no Cambridge CCHI score (it is logged as incidents, not notifiable
crime) and is absent from this file. It is the single highest-volume category a
force handles, so the dashboard represents it at the harm floor, CCHI = 1 day
per incident (`ASB_FLOOR_CCHI`), the same value Cambridge assigns the lowest
notifiable offences (shoplifting). ASB volumes are forecast-derived (see
`asb_loader`) because they are not in the recorded-crime tables.

Source file: data/cchi_weights_by_force_category.csv
Provenance:  data/raw/CCHI_SOURCES.md
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "cchi_weights_by_force_category.csv"

# The harm floor for anti-social behaviour (days). One day per incident — the
# value Cambridge gives the lowest notifiable offences — so ASB is represented
# without overwhelming a harm total dominated by violence and burglary.
ASB_FLOOR_CCHI = 1.0

# The 13 data.police.uk categories the file (and the dashboard) report against.
EXPECTED_CATEGORIES = {
    "Violence and sexual offences", "Public order", "Criminal damage and arson",
    "Shoplifting", "Other theft", "Vehicle crime", "Burglary", "Drugs",
    "Theft from the person", "Robbery", "Possession of weapons",
    "Bicycle theft", "Other crime",
}

_cache: dict[str, dict[str, dict[str, float]]] = {}


def load_force_category_cchi() -> dict[str, dict[str, float]]:
    """Per-force CCHI (days) for each of the 13 dashboard categories, keyed
    {force: {category: cchi_days}}. Fails loud if the file is missing a
    category for any force, so a silently-dropped weight can never zero out a
    force's harm without notice."""
    if "weights" in _cache:
        return _cache["weights"]

    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Per-force CCHI weight file not found at {SOURCE}. "
            "See data/raw/CCHI_SOURCES.md for how it is built."
        )

    df = pd.read_csv(SOURCE)
    required = {"force", "crime_type", "cchi_days"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{SOURCE.name}: missing columns {missing}. Found {list(df.columns)}."
        )

    df["cchi_days"] = pd.to_numeric(df["cchi_days"], errors="coerce")
    if df["cchi_days"].isna().any():
        bad = df.loc[df["cchi_days"].isna(), ["force", "crime_type"]].to_dict("records")
        raise ValueError(f"{SOURCE.name}: non-numeric cchi_days rows: {bad}")

    out: dict[str, dict[str, float]] = {}
    for force, sub in df.groupby("force"):
        cats = dict(zip(sub["crime_type"], sub["cchi_days"].astype(float)))
        missing_cats = EXPECTED_CATEGORIES - set(cats)
        if missing_cats:
            raise ValueError(
                f"{SOURCE.name}: force {force!r} is missing categories {missing_cats}."
            )
        out[force] = {c: cats[c] for c in EXPECTED_CATEGORIES}

    _cache["weights"] = out
    return out
