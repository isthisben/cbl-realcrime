"""
Police resource allocation dataset.

Builds a per-force DataFrame with officer FTE, recorded crime counts across
23 PRC Offence Subgroups (rolled up to 13 dashboard categories), and harm
totals under two CCHI weighting scenarios:

    flat:  per-force harm uses each category's *national-mix* CCHI — for
           every multi-subgroup category we replace the force's actual
           subgroup share with the national share. Single-subgroup
           categories are unaffected.

    sub:   per-force harm uses each force's own subgroup mix. Forces with
           a more severe mix (e.g. heavier residential vs non-residential
           burglary, or higher rape/homicide share within violence) get a
           heavier effective weight per offence.

Inputs:
    - data/raw/prc-pfa-mar2013-onwards-tables-230426.ods  (PRC counts)
    - data/raw/open-data-table-police-workforce-280126.ods (officer FTE)
    - data/raw/Cambridge-CCHI-2026-update.xlsx (CCHI per offence)

Methodology and per-subgroup CCHI provenance: data/raw/CCHI_SOURCES.md.

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

import cchi_loader
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

# Each dashboard category's constituent PRC Offence Subgroups. The harm
# pipeline operates at subgroup granularity; the dashboard rolls up to
# the 13 categories above only for display (radar axes, hover labels).
SUBGROUPS_BY_CATEGORY: dict[str, list[str]] = {
    "Violence and sexual offences": [
        "Homicide", "Violence with injury", "Violence without injury",
        "Stalking and harassment", "Death or serious injury - unlawful driving",
        "Rape offences", "Other sexual offences",
    ],
    "Public order":              ["Public order offences"],
    "Criminal damage and arson": ["Criminal damage", "Arson"],
    "Shoplifting":               ["Shoplifting"],
    "Other theft":               ["Other theft offences"],
    "Vehicle crime":             ["Vehicle offences"],
    "Burglary":                  ["Residential burglary", "Non-residential burglary"],
    "Drugs":                     ["Possession of drugs", "Trafficking of drugs"],
    "Theft from the person":     ["Theft from the person"],
    "Robbery":                   ["Robbery of business property", "Robbery of personal property"],
    "Possession of weapons":     ["Possession of weapons offences"],
    "Bicycle theft":             ["Bicycle theft"],
    "Other crime":               ["Miscellaneous crimes against society"],
}

# Categories with more than one PRC subgroup — these are where the toggle
# (national-mix vs per-force mix) actually changes anything.
MULTI_SUBGROUP_CATEGORIES = [
    cat for cat, sgs in SUBGROUPS_BY_CATEGORY.items() if len(sgs) > 1
]


def _category_cchi_under_national_mix(
    cchi_by_subgroup: dict[str, float],
    national_volume_by_subgroup: dict[str, int],
) -> dict[str, float]:
    """For each dashboard category, the volume-weighted CCHI when the
    subgroup mix is fixed at the national share. Used for the 'flat'
    scenario, where forces no longer get credit/penalty for a mix that
    differs from the country as a whole."""
    out = {}
    for cat, sgs in SUBGROUPS_BY_CATEGORY.items():
        cat_total = sum(national_volume_by_subgroup[sg] for sg in sgs)
        if cat_total == 0:
            out[cat] = 0.0
            continue
        out[cat] = sum(
            (national_volume_by_subgroup[sg] / cat_total) * cchi_by_subgroup[sg]
            for sg in sgs
        )
    return out


def build_dataset() -> pd.DataFrame:
    fte_by_force       = workforce_loader.load_force_fte()
    sg_counts_by_force = prc_loader.load_force_subgroup_counts()
    cchi_by_subgroup   = cchi_loader.load_subgroup_cchi()

    fte_forces   = set(fte_by_force)
    count_forces = set(sg_counts_by_force.index)
    common = fte_forces & count_forces
    if len(common) != 43:
        raise ValueError(
            f"Expected 43 territorial PFAs in both sources, got {len(common)}. "
            f"FTE={len(fte_forces)}, counts={len(count_forces)}."
        )

    expected_subgroups = set()
    for sgs in SUBGROUPS_BY_CATEGORY.values():
        expected_subgroups.update(sgs)
    counts_subgroups = set(sg_counts_by_force.columns)
    cchi_subgroups   = set(cchi_by_subgroup)
    if counts_subgroups != expected_subgroups:
        missing = expected_subgroups - counts_subgroups
        extra   = counts_subgroups - expected_subgroups
        raise ValueError(
            f"PRC subgroup count columns do not match the dashboard taxonomy. "
            f"Missing from PRC: {missing}. Extra: {extra}."
        )
    if cchi_subgroups != expected_subgroups:
        missing = expected_subgroups - cchi_subgroups
        extra   = cchi_subgroups - expected_subgroups
        raise ValueError(
            f"CCHI lookup does not cover the dashboard taxonomy. "
            f"Missing CCHI: {missing}. Extra: {extra}."
        )

    national_volume = {sg: int(sg_counts_by_force[sg].sum()) for sg in expected_subgroups}
    cchi_by_cat_natmix = _category_cchi_under_national_mix(cchi_by_subgroup, national_volume)

    rows = []
    for force in sorted(common):
        fte       = fte_by_force[force]
        sg_counts = {sg: int(sg_counts_by_force.loc[force, sg]) for sg in expected_subgroups}

        # Per-force harm under the per-force-mix scenario: every offence
        # weighted by its own subgroup's CCHI.
        harm_sub = sum(sg_counts[sg] * cchi_by_subgroup[sg] for sg in expected_subgroups)

        # Per-force harm under the national-mix scenario: each category
        # carries one national-mix-weighted CCHI; force-specific subgroup
        # mix has been levelled.
        category_counts = {
            cat: sum(sg_counts[sg] for sg in sgs)
            for cat, sgs in SUBGROUPS_BY_CATEGORY.items()
        }
        harm_flat = sum(category_counts[cat] * cchi_by_cat_natmix[cat] for cat in CRIME_TYPES)

        crime_total = sum(sg_counts.values())
        crime_profile = (
            {cat: category_counts[cat] / crime_total for cat in CRIME_TYPES}
            if crime_total > 0
            else {cat: 0.0 for cat in CRIME_TYPES}
        )

        rows.append({
            "force":           force,
            "officer_fte":     fte,
            "harm_total_flat": harm_flat,
            "harm_total_sub":  harm_sub,
            "crime_profile":   crime_profile,
            "crime_counts":    category_counts,
            "subgroup_counts": sg_counts,
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
