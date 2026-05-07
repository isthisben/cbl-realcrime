"""
Mockup dataset for the police resource allocation dashboard.

The numbers here are not real. They are plausible ratios designed to
demonstrate what the final dashboard will look like once the actual
Home Office PRC tables and Workforce tables are wired in.

Where the realism comes from:
- Officer FTE figures are loosely based on published workforce totals
  (~130k national, ~26% Met, etc.), rounded and jittered.
- The 14 broad crime categories use the police.uk taxonomy.
- The 7 violence/sexual subgroups and their representative CCHI weights
  come from the Cambridge Crime Harm Index 2020 (Sherman et al.).
- Each force has a "violence severity" parameter on [0, 1] that drives
  its mix across the 7 subgroups. Urban forces lean severe (more rape,
  GBH, homicide); rural forces lean minor (mostly common assault).

Two harm scenarios are precomputed per force:
- "flat":    Every violence/sexual record gets a single weight of 182
             (the GBH starting point), regardless of actual severity.
- "sub":     Each force gets its own weighted-average CCHI based on its
             actual subgroup mix, so a force with mostly common assault
             scores ~75 and a force with heavy GBH/rape/homicide scores
             ~400.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Crime taxonomy and weights
# ---------------------------------------------------------------------------

# The 14 broad crime types from data.police.uk (order is the radar axis order)
CRIME_TYPES = [
    "Violence and sexual offences",
    "Anti-social behaviour",
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

# Shorter labels for the radar chart (full names overlap each other)
CRIME_TYPE_SHORT = {
    "Violence and sexual offences": "Violence/sexual",
    "Anti-social behaviour": "ASB",
    "Public order": "Public order",
    "Criminal damage and arson": "Damage/arson",
    "Shoplifting": "Shoplifting",
    "Other theft": "Other theft",
    "Vehicle crime": "Vehicle",
    "Burglary": "Burglary",
    "Drugs": "Drugs",
    "Theft from the person": "Theft (person)",
    "Robbery": "Robbery",
    "Possession of weapons": "Weapons",
    "Bicycle theft": "Bicycle theft",
    "Other crime": "Other",
}

# Single representative CCHI weight per non-violence type.
# Real CCHI varies offence-by-offence within these — these are the values
# we'd use as defaults until per-offence subcategorisation is extended
# beyond violence (out of scope for now).
NONVIOLENCE_CCHI = {
    "Anti-social behaviour": 1,        # often non-criminal, low harm baseline
    "Public order": 10,
    "Criminal damage and arson": 30,
    "Shoplifting": 5,
    "Other theft": 10,
    "Vehicle crime": 10,
    "Burglary": 91,                    # ~3 month starting point (residential)
    "Drugs": 60,                       # average across possession + supply
    "Theft from the person": 91,
    "Robbery": 547,                    # 18 months starting point
    "Possession of weapons": 365,
    "Bicycle theft": 5,
    "Other crime": 10,
}

# Single flat weight applied to every violence/sexual record under the
# "flat" toggle state. 182 days ≈ the GBH starting point.
FLAT_VIOLENCE_WEIGHT = 182

# The 7 violence/sexual subgroups and their representative CCHI weights.
# Values are the "most common offence" weight per subgroup, taken from
# the Cambridge Crime Harm Index 2020 mapping.
VIOLENCE_SUBGROUPS = {
    "Homicide": 5475,
    "Violence with injury": 547.5,
    "Violence without injury": 1,
    "Stalking and harassment": 10,
    "Death/serious injury - driving": 1460,
    "Rape": 1825,
    "Other sexual offences": 73,
}


# ---------------------------------------------------------------------------
# Force list with rough officer counts and a violence-severity score
# ---------------------------------------------------------------------------

# Each entry: (name, officer_fte, severity)
# - officer_fte is roughly proportional to published workforce data
# - severity in [0, 1] drives the violence subgroup mix (1 = severe urban
#   profile with more rape/GBH/homicide, 0 = rural with mostly common assault)
# Names match the brief's canonical list. The GeoJSON has two variants
# ("Devon & Cornwall", "London, City of") which are reconciled in geo.py.
FORCES = [
    # Mega-urban
    ("Metropolitan Police",   33500, 0.85),
    # Large urban
    ("Greater Manchester",     7900, 0.78),
    ("West Midlands",          7700, 0.80),
    ("West Yorkshire",         5800, 0.72),
    ("Merseyside",             4400, 0.75),
    ("Thames Valley",          4500, 0.55),
    ("Northumbria",            3500, 0.65),
    ("Kent",                   3700, 0.50),
    ("Essex",                  3700, 0.48),
    ("Hampshire",              3000, 0.45),
    ("Avon and Somerset",      3000, 0.50),
    ("Lancashire",             3300, 0.58),
    ("Devon and Cornwall",     3300, 0.35),
    ("South Wales",            3200, 0.55),
    ("Sussex",                 2800, 0.42),
    ("South Yorkshire",        2900, 0.62),
    ("Hertfordshire",          2300, 0.40),
    ("Nottinghamshire",        2400, 0.58),
    ("West Mercia",            2400, 0.40),
    ("Leicestershire",         2300, 0.55),
    ("Cheshire",               2300, 0.42),
    ("Surrey",                 2200, 0.38),
    ("Derbyshire",             2300, 0.45),
    ("Humberside",             2200, 0.55),
    ("Staffordshire",          2000, 0.50),
    ("Norfolk",                1900, 0.32),
    ("Cambridgeshire",         1800, 0.42),
    # Small/rural
    ("Northamptonshire",       1500, 0.50),
    ("Bedfordshire",           1500, 0.52),
    ("Suffolk",                1500, 0.30),
    ("North Yorkshire",        1500, 0.30),
    ("Cleveland",              1500, 0.70),
    ("Dorset",                 1500, 0.32),
    ("Gwent",                  1500, 0.42),
    ("North Wales",            1500, 0.25),
    ("Wiltshire",              1300, 0.30),
    ("Gloucestershire",        1300, 0.34),
    ("Cumbria",                1300, 0.22),
    ("Dyfed-Powys",            1300, 0.20),
    ("Durham",                 1200, 0.40),
    ("Lincolnshire",           1200, 0.28),
    ("Warwickshire",           1100, 0.36),
    ("City of London",          870, 0.55),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def violence_mix_for(severity: float) -> dict[str, float]:
    """
    Build the violence subgroup mix (proportions summing to 1) for a force
    with the given severity score. Linearly interpolates between a "minor"
    profile (severity=0) and a "severe" profile (severity=1), then normalises.
    """
    raw = {
        "Homicide":                       0.0005 + 0.005  * severity,
        "Violence with injury":           0.10   + 0.25   * severity,
        "Violence without injury":        0.75   - 0.50   * severity,
        "Stalking and harassment":        0.20   - 0.15   * severity,
        "Death/serious injury - driving": 0.005,
        "Rape":                           0.005  + 0.075  * severity,
        "Other sexual offences":          0.03   + 0.04   * severity,
    }
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def weighted_violence_cchi(mix: dict[str, float]) -> float:
    """Force-specific weighted-average CCHI, given a violence subgroup mix."""
    return sum(prop * VIOLENCE_SUBGROUPS[sg] for sg, prop in mix.items())


def crime_profile_for(severity: float, urban_score: float, rng: np.random.Generator) -> dict[str, float]:
    """
    Per-force proportions across the 14 broad crime types.

    urban_score in [0, 1] shifts the mix: urban forces have more violence,
    robbery, theft-from-person, drugs; rural forces have proportionally more
    ASB and criminal damage.

    A small amount of noise is added so the radar chart varies between
    forces with similar profiles, but the noise is scaled small enough that
    the urban vs rural pattern still dominates.
    """
    # Base national-ish proportions
    base = {
        "Violence and sexual offences": 0.30,
        "Anti-social behaviour":        0.18,
        "Public order":                 0.06,
        "Criminal damage and arson":    0.07,
        "Shoplifting":                  0.07,
        "Other theft":                  0.06,
        "Vehicle crime":                0.06,
        "Burglary":                     0.04,
        "Drugs":                        0.03,
        "Theft from the person":        0.025,
        "Robbery":                      0.013,
        "Possession of weapons":        0.012,
        "Bicycle theft":                0.012,
        "Other crime":                  0.013,
    }

    # Urban shift: amplify the city-typical categories, reduce the rural ones
    u = urban_score - 0.5  # centred at 0
    shifts = {
        "Violence and sexual offences":  0.05 * u,
        "Robbery":                       0.025 * u,
        "Theft from the person":         0.04 * u,
        "Drugs":                         0.02 * u,
        "Bicycle theft":                 0.015 * u,
        "Anti-social behaviour":        -0.06 * u,
        "Criminal damage and arson":    -0.025 * u,
        "Vehicle crime":                -0.01 * u,
    }
    profile = {k: max(0.002, base[k] + shifts.get(k, 0)) for k in base}

    # Add a touch of jitter (~5% multiplicative)
    profile = {k: v * rng.uniform(0.95, 1.05) for k, v in profile.items()}

    # Renormalise to 1.0
    total = sum(profile.values())
    return {k: v / total for k, v in profile.items()}


def resolution_rate_for(severity: float, rng: np.random.Generator) -> float:
    """
    Single overall resolution rate per force (5-13%, real-ish).
    Severe-mix forces tend to be slightly lower (overstretched),
    rural forces slightly higher.
    """
    base = 0.13 - 0.07 * severity        # 0.13 down to 0.06
    return float(np.clip(base + rng.uniform(-0.01, 0.01), 0.03, 0.18))


# ---------------------------------------------------------------------------
# Build the dataset
# ---------------------------------------------------------------------------

def build_dataset(seed: int = 4_242) -> pd.DataFrame:
    """
    Generate the per-force dataset as a pandas DataFrame.

    Columns:
        force, officer_fte, severity, urban_score,
        actual_share_pct,
        harm_share_pct_flat, allocation_gap_flat,
        harm_share_pct_sub,  allocation_gap_sub,
        weighted_violence_cchi,
        crime_profile (dict),
        violence_mix (dict),
        crime_counts (dict)

    The flat scenario uses a single weight of 182 for all violence;
    the sub scenario uses each force's own weighted-average CCHI.
    """
    rng = np.random.default_rng(seed)

    rows = []
    for name, fte, severity in FORCES:
        # Urban score is correlated with severity but not identical —
        # e.g. Cleveland is high severity but a small/medium force.
        urban_score = float(np.clip(0.4 * severity + 0.5 * (fte / 8000) + rng.uniform(-0.05, 0.05), 0.05, 0.95))

        profile = crime_profile_for(severity, urban_score, rng)
        mix     = violence_mix_for(severity)
        wcchi   = weighted_violence_cchi(mix)
        rrate   = resolution_rate_for(severity, rng)

        # Per-force total annual recorded crime count, scaled to officers.
        # Real counts are roughly 70-90 crimes per officer per year.
        per_officer = rng.uniform(72, 92)
        total_crimes = int(fte * per_officer)

        counts = {ct: int(total_crimes * profile[ct]) for ct in CRIME_TYPES}

        # Compute total harm under both scenarios.
        # Harm gap formula: count * weight * (1 - resolution_rate)
        nonv_harm = sum(
            counts[ct] * NONVIOLENCE_CCHI[ct] * (1 - rrate)
            for ct in CRIME_TYPES if ct != "Violence and sexual offences"
        )
        v_count = counts["Violence and sexual offences"]
        v_harm_flat = v_count * FLAT_VIOLENCE_WEIGHT * (1 - rrate)
        v_harm_sub  = v_count * wcchi               * (1 - rrate)

        rows.append({
            "force":                   name,
            "officer_fte":             fte,
            "severity":                severity,
            "urban_score":             urban_score,
            "resolution_rate":         rrate,
            "weighted_violence_cchi":  wcchi,
            "harm_total_flat":         nonv_harm + v_harm_flat,
            "harm_total_sub":          nonv_harm + v_harm_sub,
            "crime_profile":           profile,
            "violence_mix":            mix,
            "crime_counts":            counts,
        })

    df = pd.DataFrame(rows)

    # National shares
    total_fte       = df["officer_fte"].sum()
    total_harm_flat = df["harm_total_flat"].sum()
    total_harm_sub  = df["harm_total_sub"].sum()

    df["actual_share_pct"]      = df["officer_fte"]       / total_fte       * 100
    df["harm_share_pct_flat"]   = df["harm_total_flat"]   / total_harm_flat * 100
    df["harm_share_pct_sub"]    = df["harm_total_sub"]    / total_harm_sub  * 100

    # Allocation gap. Positive = over-resourced relative to harm. Negative = under.
    df["allocation_gap_flat"]   = df["actual_share_pct"] - df["harm_share_pct_flat"]
    df["allocation_gap_sub"]    = df["actual_share_pct"] - df["harm_share_pct_sub"]

    return df


def national_crime_profile(df: pd.DataFrame) -> dict[str, float]:
    """National baseline crime profile (proportions) — used as the radar reference."""
    totals = {ct: 0 for ct in CRIME_TYPES}
    for counts in df["crime_counts"]:
        for ct, v in counts.items():
            totals[ct] += v
    grand = sum(totals.values())
    return {ct: v / grand for ct, v in totals.items()}
