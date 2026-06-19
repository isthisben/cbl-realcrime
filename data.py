"""
Builds the per-force allocation dataset.

Per force: officer FTE, recorded crime across the 13 categories, the funding
figures, and a harm total = Σ (category count × per-force CCHI) + an ASB floor
term. The CCHI weights come from `cchi_loader` (nine national-value categories,
four per-force composites) and are the same weights the model team's ILP used,
so the map and the optimiser rest on one source.

ASB has no CCHI score and isn't in the recorded-crime tables, so it sits at the
harm floor (CCHI = 1) on forecast-derived volumes — a 14th radar axis and a
small additive harm term, always flagged as forecast-derived.

Two allocation gaps are produced, both `resource share − harm share`: officer
headcount, and total funding (the headline). Only the formula grant is
redistributable; precept and specific grants are held fixed. Harm here is
*recorded* crime (2024/25) — today's picture; the ILP was optimised against the
*forecast* under the same weights (diagnose / predict / optimise). Resolution
rate is dropped from the formula because the Home Office only publishes
per-force clearance for fraud.

Inputs:
    data/raw/prc-pfa-mar2013-onwards-tables-230426.ods    PRC crime counts
    data/raw/open-data-table-police-workforce-280126.ods  officer FTE
    data/cchi_weights_by_force_category.csv               per-force CCHI weights
    data/raw/asb_counts.csv                               forecast-derived ASB
    data/raw/police-grant-2025-26.csv                     formula grant
    data/raw/police-funding-...-2026-tables.ods           total funding + precept

Methodology and provenance: data/raw/CCHI_SOURCES.md.
"""

from __future__ import annotations

import pathlib

import pandas as pd

import allocation_loader
import asb_loader
import cache
import cchi_loader
import funding_loader
import grant_loader
import prc_loader
import workforce_loader


# Bump when a change in this module alters the assembled dataset (new column,
# changed harm formula, different roll-up), so an existing on-disk cache is
# rebuilt instead of served stale. Source-file changes invalidate the cache
# automatically; this covers code changes that the files can't signal.
_CACHE_VERSION = 5

# Committed deploy snapshot. A host that ships only this snapshot (not the
# ~15 MB raw ODS files) reads it directly — see build_dataset. Regenerate with
# `python data.py --snapshot` after a data or logic change, then commit it.
_SNAPSHOT_DIR  = pathlib.Path(__file__).parent / "data" / "snapshot"
_SNAPSHOT_FILE = _SNAPSHOT_DIR / "dataset.pkl"


# The 13 data.police.uk categories the recorded-crime harm is built from.
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

# Anti-social behaviour is the forecast-derived floor category — not recorded
# crime, so it sits outside CRIME_TYPES and is handled separately, but it is a
# 14th axis on the crime-profile radar.
ASB_CATEGORY = "Anti-social behaviour"
DISPLAY_CATEGORIES = CRIME_TYPES + [ASB_CATEGORY]

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
    "Anti-social behaviour":        "ASB (floor)",
}

# Each dashboard category's constituent PRC Offence Subgroups. The PRC tables
# publish counts at subgroup granularity; the dashboard rolls them up to the
# 13 categories the CCHI weight file (and data.police.uk) use.
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

# Forces excluded from the dashboard. Greater Manchester is absent from the
# team's forecast and allocation model outputs (a known data.police.uk gap), so
# it is dropped project-wide for consistency — the dashboard reports 42 forces.
EXCLUDED_FORCES = {"Greater Manchester"}


def _assemble_dataset() -> pd.DataFrame:
    """Parse the source files and assemble the per-force dataset. This is the
    expensive path (~3 min cold, dominated by the odfpy ODS reads); callers go
    through `build_dataset`, which caches the result to disk."""
    fte_by_force       = workforce_loader.load_force_fte()
    sg_counts_by_force = prc_loader.load_force_subgroup_counts()
    cchi_by_force_cat  = cchi_loader.load_force_category_cchi()
    asb_by_force       = asb_loader.load_force_asb_counts()
    grant_by_force     = grant_loader.load_force_grant()
    funding_by_force   = funding_loader.load_force_funding()

    common = (
        set(fte_by_force) & set(sg_counts_by_force.index) & set(grant_by_force)
        & set(funding_by_force.index) & set(cchi_by_force_cat) & set(asb_by_force)
    ) - EXCLUDED_FORCES
    if len(common) != 42:
        raise ValueError(
            f"Expected 42 PFAs (43 territorial minus {sorted(EXCLUDED_FORCES)}) in "
            f"all sources, got {len(common)}. FTE={len(fte_by_force)}, "
            f"counts={len(sg_counts_by_force.index)}, grant={len(grant_by_force)}, "
            f"funding={len(funding_by_force.index)}, cchi={len(cchi_by_force_cat)}, "
            f"asb={len(asb_by_force)}."
        )

    # PRC subgroup columns must cover (only) the dashboard taxonomy, so the
    # roll-up to the 13 categories below can't silently drop or mis-bucket.
    expected_subgroups = set()
    for sgs in SUBGROUPS_BY_CATEGORY.values():
        expected_subgroups.update(sgs)
    counts_subgroups = set(sg_counts_by_force.columns)
    if counts_subgroups != expected_subgroups:
        raise ValueError(
            f"PRC subgroup count columns do not match the dashboard taxonomy. "
            f"Missing from PRC: {expected_subgroups - counts_subgroups}. "
            f"Extra: {counts_subgroups - expected_subgroups}."
        )

    rows = []
    for force in sorted(common):
        fte           = fte_by_force[force]
        grant         = grant_by_force[force]
        total_funding = float(funding_by_force.loc[force, "total_funding_gbp"])
        precept       = float(funding_by_force.loc[force, "precept_gbp"])
        weights       = cchi_by_force_cat[force]
        asb_count     = asb_by_force[force]

        category_counts = {
            cat: int(sum(sg_counts_by_force.loc[force, sg] for sg in sgs))
            for cat, sgs in SUBGROUPS_BY_CATEGORY.items()
        }

        # Harm = recorded crime weighted by the shared per-force CCHI, plus the
        # ASB floor (forecast volume × CCHI 1). One scenario — the weighting the
        # ILP consumed.
        harm_recorded = sum(category_counts[cat] * weights[cat] for cat in CRIME_TYPES)
        harm_asb      = asb_count * cchi_loader.ASB_FLOOR_CCHI
        harm_total    = harm_recorded + harm_asb

        # Crime mix for the radar, over the 14 display categories (recorded +
        # the ASB floor). Shares of all logged demand including ASB.
        demand_total = sum(category_counts.values()) + asb_count
        if demand_total > 0:
            crime_profile = {cat: category_counts[cat] / demand_total for cat in CRIME_TYPES}
            crime_profile[ASB_CATEGORY] = asb_count / demand_total
        else:
            crime_profile = {cat: 0.0 for cat in DISPLAY_CATEGORIES}

        rows.append({
            "force":           force,
            "officer_fte":     fte,
            "grant":           grant,
            "precept":         precept,
            "total_funding":   total_funding,
            # Everything that is not the redistributable formula grant —
            # precept plus ring-fenced specific grants — is held fixed when
            # the model reallocates.
            "fixed_funding":   total_funding - grant,
            "harm_total":      harm_total,
            "harm_recorded":   harm_recorded,
            "harm_asb":        harm_asb,
            "asb_count":       asb_count,
            "crime_profile":   crime_profile,
            "crime_counts":    category_counts,
        })

    df = pd.DataFrame(rows)

    total_fte     = df["officer_fte"].sum()
    total_funding = df["total_funding"].sum()
    total_harm    = df["harm_total"].sum()

    df["actual_share_pct"]  = df["officer_fte"]   / total_fte     * 100
    df["funding_share_pct"] = df["total_funding"] / total_funding * 100
    df["harm_share_pct"]    = df["harm_total"]    / total_harm    * 100

    # Funding allocation gap: resource share - harm share. The formula grant is
    # a single pool redistributed on total harm, so total-harm share is the
    # right benchmark. Total funding is grant + precept + specific grants, so a
    # force well funded locally (high precept) no longer looks under-resourced
    # on grant alone.
    df["allocation_gap_funding"] = df["funding_share_pct"] - df["harm_share_pct"]

    # Officer allocation gap: current workforce share - the ILP's recommended
    # workforce share (all three pools combined, per force). Officers are
    # allocated *per pool* against that pool's harm — patrol against high-volume
    # crime, investigators against serious crime — so comparing officer share to
    # *total* harm mixes the pools and mislabels high-volume forces: the Met
    # carries ~a third of national patrol demand but a smaller share of total
    # severity-weighted harm, so total harm wrongly flags it over-resourced even
    # though the ILP adds it officers. Benchmarking against the optimiser's own
    # recommendation keeps the map consistent with the reallocation it drives:
    # blue = more officers than the model recommends, red = fewer.
    fte_alloc = allocation_loader.load_allocation(df, basis="fte", pool="all")
    cur = fte_alloc["current"].reindex(df["force"]).to_numpy()
    rec = fte_alloc["recommended"].reindex(df["force"]).to_numpy()
    if pd.isna(cur).any() or pd.isna(rec).any():
        missing = sorted(set(df["force"]) - set(fte_alloc.index))
        raise ValueError(f"FTE allocation is missing forces from the dataset: {missing}")
    fte_pool_total = cur.sum()
    df["fte_current"]           = cur
    df["fte_recommended"]       = rec
    df["fte_current_share_pct"] = cur / fte_pool_total * 100
    df["fte_target_share_pct"]  = rec / fte_pool_total * 100
    df["allocation_gap"]        = df["fte_current_share_pct"] - df["fte_target_share_pct"]

    return df


def build_dataset(*, refresh: bool = False, use_cache: bool = True) -> pd.DataFrame:
    """The per-force dataset, served from `data/cache/dataset.pkl` when the
    cache is warm and the source files are unchanged, else parsed fresh and
    re-cached. This is what the app calls at startup; a warm cache turns a
    ~3-minute cold parse into an instant load.

    refresh:   ignore any existing cache and re-parse (then overwrite it).
    use_cache: set False to bypass the cache entirely (read and write).

    The cache invalidates automatically when any source file changes or when
    `_CACHE_VERSION` is bumped.

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
        asb_loader.SOURCE,
        grant_loader.SOURCE,
        funding_loader.SOURCE,
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
    """National crime mix over the 14 display categories (recorded + ASB
    floor), the radar's grey baseline."""
    totals = {ct: 0.0 for ct in DISPLAY_CATEGORIES}
    for counts in df["crime_counts"]:
        for ct, v in counts.items():
            totals[ct] += v
    totals[ASB_CATEGORY] += float(df["asb_count"].sum())
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
