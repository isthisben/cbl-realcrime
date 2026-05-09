"""
Police resource allocation dataset.

Builds a per-force DataFrame with officer FTE, recorded crime counts across
13 broad categories, and harm totals under two violence-weighting scenarios:

    flat:  every violence/sexual offence given a single weight of 182
           (the GBH starting point under the Cambridge Crime Harm Index 2020).

    sub:   each force's violence/sexual harm uses a force-specific weighted
           average derived from its own mix across the 7 violence/sexual
           subgroups, weighted by the representative CCHI score per subgroup.

Inputs are loaded from the two Home Office open-data ODS files referenced
in data/raw/SOURCES.md:
    - prc-pfa-mar2013-onwards-tables-230426.ods
    - open-data-table-police-workforce-280126.ods

Two categories the original specification carried have no source in the
files we use here and are documented as known gaps:

    - Anti-social behaviour: not in police recorded crime; recorded as
      incidents rather than crimes. Dropped (radar shows 13 axes, not 14).

    - Resolution rate per force: outcomes-mar25 only publishes per-force
      breakdowns for fraud. Dropped from the harm formula. Harm is
      count * weight rather than count * weight * (1 - resolution_rate).
      Adding it back is one constant-multiplier line once per-force
      outcome data lands.
"""

from __future__ import annotations

import pandas as pd

import prc_loader
import workforce_loader


CRIME_TYPES = [
    "Violence and sexual offences",
    "Public order",
    "Criminal damage and arson",
    "Shoplifting",
    "Other theft",
    "Vehicle crime",
    "Burglary",
    "Drugs",
    "Theft from the person",
    "Robbery",
    "Possession of weapons",
    "Bicycle theft",
    "Other crime",
]

CRIME_TYPE_SHORT = {
    "Violence and sexual offences": "Violence/sexual",
    "Public order":                 "Public order",
    "Criminal damage and arson":    "Damage/arson",
    "Shoplifting":                  "Shoplifting",
    "Other theft":                  "Other theft",
    "Vehicle crime":                "Vehicle",
    "Burglary":                     "Burglary",
    "Drugs":                        "Drugs",
    "Theft from the person":        "Theft (person)",
    "Robbery":                      "Robbery",
    "Possession of weapons":        "Weapons",
    "Bicycle theft":                "Bicycle theft",
    "Other crime":                  "Other",
}

NONVIOLENCE_CCHI = {
    "Public order":              10,
    "Criminal damage and arson": 30,
    "Shoplifting":               5,
    "Other theft":               10,
    "Vehicle crime":             10,
    "Burglary":                  91,
    "Drugs":                     60,
    "Theft from the person":     91,
    "Robbery":                   547,
    "Possession of weapons":     365,
    "Bicycle theft":             5,
    "Other crime":               10,
}

FLAT_VIOLENCE_WEIGHT = 182

VIOLENCE_SUBGROUPS = {
    "Homicide":                       5475,
    "Violence with injury":           547.5,
    "Violence without injury":        1,
    "Stalking and harassment":        10,
    "Death/serious injury - driving": 1460,
    "Rape":                           1825,
    "Other sexual offences":          73,
}


def build_dataset() -> pd.DataFrame:
    fte_by_force        = workforce_loader.load_force_fte()
    counts_by_force_cat = prc_loader.load_force_crime_counts()
    violence_by_force   = prc_loader.load_force_violence_subgroups()

    fte_forces       = set(fte_by_force)
    count_forces     = set(counts_by_force_cat.index)
    violence_forces  = set(violence_by_force.index)
    common = fte_forces & count_forces & violence_forces
    if len(common) != 43:
        raise ValueError(
            f"Expected 43 territorial PFAs across all three sources, got {len(common)}. "
            f"FTE={len(fte_forces)}, counts={len(count_forces)}, violence={len(violence_forces)}."
        )

    counts_categories_set = set(counts_by_force_cat.columns)
    if counts_categories_set != set(CRIME_TYPES):
        missing = set(CRIME_TYPES) - counts_categories_set
        extra   = counts_categories_set - set(CRIME_TYPES)
        raise ValueError(f"Crime category mismatch. Missing from PRC: {missing}. Extra: {extra}.")

    violence_subgroups_set = set(violence_by_force.columns)
    if violence_subgroups_set != set(VIOLENCE_SUBGROUPS):
        missing = set(VIOLENCE_SUBGROUPS) - violence_subgroups_set
        extra   = violence_subgroups_set - set(VIOLENCE_SUBGROUPS)
        raise ValueError(f"Violence subgroup mismatch. Missing: {missing}. Extra: {extra}.")

    rows = []
    for force in sorted(common):
        fte    = fte_by_force[force]
        counts = {ct: int(counts_by_force_cat.loc[force, ct]) for ct in CRIME_TYPES}

        sub_counts = {sg: int(violence_by_force.loc[force, sg]) for sg in VIOLENCE_SUBGROUPS}
        sub_total  = sum(sub_counts.values())
        if sub_total == 0:
            raise ValueError(f"{force}: zero violence/sexual offences in source — unexpected.")
        violence_mix = {sg: n / sub_total for sg, n in sub_counts.items()}
        wcchi = sum(violence_mix[sg] * VIOLENCE_SUBGROUPS[sg] for sg in VIOLENCE_SUBGROUPS)

        nonv_harm = sum(
            counts[ct] * NONVIOLENCE_CCHI[ct]
            for ct in CRIME_TYPES if ct != "Violence and sexual offences"
        )
        v_count     = counts["Violence and sexual offences"]
        v_harm_flat = v_count * FLAT_VIOLENCE_WEIGHT
        v_harm_sub  = v_count * wcchi

        crime_total = sum(counts.values())
        crime_profile = (
            {ct: counts[ct] / crime_total for ct in CRIME_TYPES}
            if crime_total > 0
            else {ct: 0.0 for ct in CRIME_TYPES}
        )

        rows.append({
            "force":                  force,
            "officer_fte":            fte,
            "weighted_violence_cchi": wcchi,
            "harm_total_flat":        nonv_harm + v_harm_flat,
            "harm_total_sub":         nonv_harm + v_harm_sub,
            "crime_profile":          crime_profile,
            "violence_mix":           violence_mix,
            "crime_counts":           counts,
        })

    df = pd.DataFrame(rows)

    total_fte       = df["officer_fte"].sum()
    total_harm_flat = df["harm_total_flat"].sum()
    total_harm_sub  = df["harm_total_sub"].sum()

    df["actual_share_pct"]    = df["officer_fte"]     / total_fte       * 100
    df["harm_share_pct_flat"] = df["harm_total_flat"] / total_harm_flat * 100
    df["harm_share_pct_sub"]  = df["harm_total_sub"]  / total_harm_sub  * 100

    df["allocation_gap_flat"] = df["actual_share_pct"] - df["harm_share_pct_flat"]
    df["allocation_gap_sub"]  = df["actual_share_pct"] - df["harm_share_pct_sub"]

    return df


def national_crime_profile(df: pd.DataFrame) -> dict[str, float]:
    totals = {ct: 0 for ct in CRIME_TYPES}
    for counts in df["crime_counts"]:
        for ct, v in counts.items():
            totals[ct] += v
    grand = sum(totals.values())
    return {ct: v / grand for ct, v in totals.items()}
