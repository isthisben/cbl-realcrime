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
    - data/raw/police-grant-2025-26.csv (central gov grant per force)

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

import pathlib

import pandas as pd

import budget_loader
import cache
import cchi_loader
import prc_loader
import workforce_loader


# Bump when a change in this module alters the assembled dataset (new column,
# changed harm formula, different roll-up), so an existing on-disk cache is
# rebuilt instead of served stale. Source-file changes invalidate the cache
# automatically; this covers code changes that the files can't signal.
_CACHE_VERSION = 1

# Committed deploy snapshot. A host that ships only this snapshot (not the
# ~15 MB raw ODS files) reads it directly — see build_dataset. Regenerate with
# `python data.py --snapshot` after a data or logic change, then commit it.
_SNAPSHOT_DIR  = pathlib.Path(__file__).parent / "data" / "snapshot"
_SNAPSHOT_FILE = _SNAPSHOT_DIR / "dataset.pkl"


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


def _assemble_dataset() -> pd.DataFrame:
    """Parse the source files and assemble the per-force dataset. This is the
    expensive path (~3 min cold, dominated by the odfpy ODS reads); callers go
    through `build_dataset`, which caches the result to disk."""
    fte_by_force       = workforce_loader.load_force_fte()
    sg_counts_by_force = prc_loader.load_force_subgroup_counts()
    cchi_by_subgroup   = cchi_loader.load_subgroup_cchi()
    budget_by_force    = budget_loader.load_force_budget()

    fte_forces    = set(fte_by_force)
    count_forces  = set(sg_counts_by_force.index)
    budget_forces = set(budget_by_force)
    common = fte_forces & count_forces & budget_forces
    if len(common) != 43:
        raise ValueError(
            f"Expected 43 territorial PFAs in all three sources, got {len(common)}. "
            f"FTE={len(fte_forces)}, counts={len(count_forces)}, "
            f"budget={len(budget_forces)}."
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
        budget    = budget_by_force[force]
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
            "budget":          budget,
            "harm_total_flat": harm_flat,
            "harm_total_sub":  harm_sub,
            "crime_profile":   crime_profile,
            "crime_counts":    category_counts,
            "subgroup_counts": sg_counts,
        })

    df = pd.DataFrame(rows)

    total_fte       = df["officer_fte"].sum()
    total_budget    = df["budget"].sum()
    total_harm_flat = df["harm_total_flat"].sum()
    total_harm_sub  = df["harm_total_sub"].sum()

    df["actual_share_pct"]    = df["officer_fte"]     / total_fte       * 100
    df["budget_share_pct"]    = df["budget"]          / total_budget    * 100
    df["harm_share_pct_flat"] = df["harm_total_flat"] / total_harm_flat * 100
    df["harm_share_pct_sub"]  = df["harm_total_sub"]  / total_harm_sub  * 100

    df["allocation_gap_flat"] = df["actual_share_pct"] - df["harm_share_pct_flat"]
    df["allocation_gap_sub"]  = df["actual_share_pct"] - df["harm_share_pct_sub"]

    df["allocation_gap_budget_flat"] = df["budget_share_pct"] - df["harm_share_pct_flat"]
    df["allocation_gap_budget_sub"]  = df["budget_share_pct"] - df["harm_share_pct_sub"]

    return df


def build_dataset(*, refresh: bool = False, use_cache: bool = True) -> pd.DataFrame:
    """The per-force dataset, served from `data/cache/dataset.pkl` when the
    cache is warm and the source files are unchanged, else parsed fresh and
    re-cached. This is what the app calls at startup; a warm cache turns a
    ~3-minute cold parse into an instant load.

    refresh:   ignore any existing cache and re-parse (then overwrite it).
    use_cache: set False to bypass the cache entirely (read and write).

    The cache invalidates automatically when any of the four source files
    (PRC, workforce, CCHI, grant) changes or when `_CACHE_VERSION` is bumped.

    Deploy fallback: when the raw source files are absent (a host that ships
    only the committed snapshot), the snapshot at `data/snapshot/dataset.pkl`
    is served directly. With neither raw files nor a snapshot present, the
    loader's own FileNotFoundError surfaces.
    """
    if not use_cache:
        return _assemble_dataset()

    sources_sig = cache.file_signature(
        prc_loader.SOURCE,
        workforce_loader.SOURCE,
        cchi_loader.SOURCE,
        budget_loader.SOURCE,
    )
    if sources_sig is None:
        # Raw files absent (e.g. a deploy host). Serve the committed snapshot
        # if present; otherwise fall through so _assemble_dataset raises the
        # loader's pointing-to-SOURCES.md FileNotFoundError.
        if _SNAPSHOT_FILE.exists():
            return pd.read_pickle(_SNAPSHOT_FILE)
        return _assemble_dataset()

    signature = {"version": _CACHE_VERSION, "sources": sources_sig}
    return cache.cached("dataset", signature, _assemble_dataset, refresh=refresh)


def national_crime_profile(df: pd.DataFrame) -> dict[str, float]:
    totals = {ct: 0 for ct in CRIME_TYPES}
    for counts in df["crime_counts"]:
        for ct, v in counts.items():
            totals[ct] += v
    grand = sum(totals.values())
    return {ct: v / grand for ct, v in totals.items()}


def write_snapshot() -> list[pathlib.Path]:
    """Write the committed deploy snapshots (data/snapshot/) that a host reads
    in place of the raw ODS files: the assembled dataset and the officer-
    function shares. Run `python data.py --snapshot` after a data or logic
    change, then commit data/snapshot/."""
    import functions_loader

    df = build_dataset()
    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_pickle(_SNAPSHOT_FILE)
    fpath = functions_loader.write_snapshot(df["force"])
    return [_SNAPSHOT_FILE, fpath]


if __name__ == "__main__":
    # Warm/refresh the on-disk cache, or write the committed deploy snapshot:
    #   python data.py            build (or reuse) the cache, report timing
    #   python data.py --refresh  ignore any cache and re-parse the raw files
    #   python data.py --no-cache parse without reading or writing the cache
    #   python data.py --snapshot write data/snapshot/ for hosting, then exit
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="Build / refresh the dashboard dataset cache or snapshot.")
    parser.add_argument("--refresh", action="store_true",
                        help="Ignore any existing cache and re-parse the raw files.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Parse without reading or writing the cache.")
    parser.add_argument("--snapshot", action="store_true",
                        help="Write the committed deploy snapshot "
                             "(data/snapshot/) for hosting, then exit.")
    args = parser.parse_args()

    if args.snapshot:
        for p in write_snapshot():
            print(f"wrote {p} ({p.stat().st_size / 1024:.0f} KB)")
        raise SystemExit(0)

    t0 = time.perf_counter()
    df = build_dataset(refresh=args.refresh, use_cache=not args.no_cache)
    dt = time.perf_counter() - t0

    print(f"dataset: {len(df)} forces, {len(df.columns)} columns in {dt:.2f}s")
    cache_path = cache.CACHE_DIR / "dataset.pkl"
    if not args.no_cache and cache_path.exists():
        print(f"cache:   {cache_path} ({cache_path.stat().st_size / 1024:.0f} KB)")
