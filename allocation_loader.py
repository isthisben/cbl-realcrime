"""
Recommended resource allocation per force — the model team's ILP optimiser
output, with a real proportional baseline as a deploy-safety fallback.

    load_allocation(df, basis, pool)  ->  DataFrame indexed by force, columns:
        current, recommended, difference, harm_share_pct  (+ pool extras)
    is_optimised(basis)               ->  True when the ILP output for that
                                          basis is present (it is, committed
                                          under data/raw/ilp/).

Two bases, and the FTE basis has three workforce pools
------------------------------------------------------
    basis="budget"          formula-grant redistribution (grant_redistribution_result.csv)
    basis="fte", pool=...    one workforce pool, or the three combined:
        "patrol"            Warranted officers (patrol)
        "investigators"     Police staff & designated officers (investigators)
        "pcsos"             PCSOs (community)
        "all"               the three pools summed per force

The ILP was optimised against *forecast* harm under the shared per-force CCHI
weights (cchi_loader); each pool's allocation conserves that pool's national
FTE total, and the grant redistribution conserves the formula-grant pool.

The column names are basis-agnostic ('current', 'recommended', 'difference')
so the dashboard renders the same panel under either basis by relabelling axes
and tooltips. Units: FTE for 'fte', £ for 'budget'. `harm_share_pct` is the
force's share of harm (budget) or of the pool's harm-weighted demand (fte).

`load_allocation` takes the already-built dashboard `df` (from
`data.build_dataset()`) only for the fallback baseline; the ILP path reads the
committed result files and ignores `df`.
"""

from __future__ import annotations

import pathlib
from typing import Literal

import pandas as pd


Basis = Literal["fte", "budget"]

_ILP_DIR = pathlib.Path(__file__).parent / "data" / "raw" / "ilp"
_GRANT_FILE = _ILP_DIR / "grant_redistribution_result.csv"

# pool key -> (result filename, display label). Order is the workforce size
# order the dashboard offers in the pool selector.
POOL_META: dict[str, tuple[str, str]] = {
    "patrol":        ("Pool_1_Patrol_allocation_results.csv",        "Warranted officers (patrol)"),
    "investigators": ("Pool_2_Investigators_allocation_results.csv", "Police staff (investigators)"),
    "pcsos":         ("Pool_3_PCSOs_allocation_results.csv",         "PCSOs (community)"),
}
POOL_KEYS = list(POOL_META)

CONTRACT_COLUMNS = ["current", "recommended", "difference", "harm_share_pct"]

# Which harm-share column the fallback proportional baseline reallocates by.
_HARM_SHARE_COL = "harm_share_pct"


# ---------------------------------------------------------------------------
# ILP readers
# ---------------------------------------------------------------------------

def _read_grant() -> pd.DataFrame:
    df = pd.read_csv(_GRANT_FILE)
    need = {"force", "harm_share", "grant_old", "grant_new", "delta"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(
            f"{_GRANT_FILE.name}: missing columns {sorted(missing)}. "
            f"Found {list(df.columns)}."
        )
    out = pd.DataFrame({
        "force":          df["force"],
        "current":        df["grant_old"].astype(float),
        "recommended":    df["grant_new"].astype(float),
        "difference":     df["delta"].astype(float),
        "harm_share_pct": df["harm_share"].astype(float) * 100.0,
    })
    return out.set_index("force")


def _read_pool(pool: str) -> pd.DataFrame:
    fname, _ = POOL_META[pool]
    df = pd.read_csv(_ILP_DIR / fname)
    need = {"force", "current_fte", "allocated_fte", "harm_weighted_demand",
            "demand_pressure_index_pct", "reallocation_pct"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(
            f"{fname}: missing columns {sorted(missing)}. Found {list(df.columns)}."
        )
    hwd_total = df["harm_weighted_demand"].sum()
    out = pd.DataFrame({
        "force":          df["force"],
        "current":        df["current_fte"].astype(float),
        "recommended":    df["allocated_fte"].astype(float),
        "difference":     df["allocated_fte"].astype(float) - df["current_fte"].astype(float),
        # Share of this pool's harm-weighted demand — the pool analogue of harm share.
        "harm_share_pct": df["harm_weighted_demand"] / hwd_total * 100.0,
        "demand_pressure_index_pct": df["demand_pressure_index_pct"].astype(float),
        "reallocation_pct":          df["reallocation_pct"].astype(float),
    })
    return out.set_index("force")


def _read_pools_combined() -> pd.DataFrame:
    """The three workforce pools summed per force (total FTE reallocation)."""
    parts = [_read_pool(p)[["current", "recommended", "difference"]] for p in POOL_KEYS]
    combined = sum(parts[1:], parts[0])
    # Harm-share analogue for the combined view: share of total recommended FTE
    # (the optimiser's harm-weighted target, realised).
    combined["harm_share_pct"] = combined["recommended"] / combined["recommended"].sum() * 100.0
    return combined


# ---------------------------------------------------------------------------
# Optimised-vs-baseline status
# ---------------------------------------------------------------------------

def is_optimised(basis: Basis) -> bool:
    if basis == "budget":
        return _GRANT_FILE.exists()
    return all((_ILP_DIR / fname).exists() for fname, _ in POOL_META.values())


IS_OPTIMISED_FTE:    bool = is_optimised("fte")
IS_OPTIMISED_BUDGET: bool = is_optimised("budget")


# ---------------------------------------------------------------------------
# Fallback baseline (only used if the ILP files are absent)
# ---------------------------------------------------------------------------

def _proportional_fte(df: pd.DataFrame) -> pd.DataFrame:
    total_current = float(df["officer_fte"].sum())
    out = pd.DataFrame({
        "force":          df["force"].values,
        "current":        df["officer_fte"].values,
        "harm_share_pct": df[_HARM_SHARE_COL].values,
    })
    out["recommended"] = out["harm_share_pct"] / 100.0 * total_current
    out["difference"]  = out["recommended"] - out["current"]
    return out.set_index("force")[CONTRACT_COLUMNS]


def _equalise_funding(df: pd.DataFrame) -> pd.DataFrame:
    grant         = df["grant"].astype(float).to_numpy()
    total_funding = df["total_funding"].astype(float).to_numpy()
    harm_share    = df[_HARM_SHARE_COL].astype(float).to_numpy()

    grant_pool        = grant.sum()
    total_funding_nat = total_funding.sum()
    fixed             = total_funding - grant

    target = harm_share / 100.0 * total_funding_nat
    rec = (target - fixed).clip(min=0.0)
    s = rec.sum()
    if s > 0:
        rec = rec * (grant_pool / s)

    out = pd.DataFrame({
        "force":          df["force"].values,
        "current":        grant,
        "recommended":    rec,
        "difference":     rec - grant,
        "harm_share_pct": harm_share,
    })
    return out.set_index("force")[CONTRACT_COLUMNS]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load_allocation(df: pd.DataFrame, basis: Basis = "fte",
                    pool: str = "all") -> pd.DataFrame:
    """Recommended vs current allocation per force.

    basis="budget"  -> ILP grant redistribution (41 forces; City of London,
                       a fraud specialist, is outside the team's grant model).
    basis="fte"     -> workforce pool `pool` (one of POOL_KEYS) or "all"
                       (the three summed). 42 forces.

    Reads the committed ILP output. Falls back to the proportional /
    grant-equalisation baseline computed from `df` only if the ILP files are
    absent (e.g. a deploy that did not ship them)."""
    global IS_OPTIMISED_FTE, IS_OPTIMISED_BUDGET
    optimised = is_optimised(basis)
    if basis == "budget":
        IS_OPTIMISED_BUDGET = optimised
        if optimised:
            return _read_grant()
        return _equalise_funding(df)

    IS_OPTIMISED_FTE = optimised
    if optimised:
        if pool == "all":
            return _read_pools_combined()
        if pool not in POOL_META:
            raise ValueError(f"unknown pool {pool!r}; expected one of {POOL_KEYS} or 'all'.")
        return _read_pool(pool)
    return _proportional_fte(df)


def pool_summary() -> pd.DataFrame:
    """Per-pool reallocation headline stats, recomputed from the result files
    (not the team's comparison_summary.csv, which belongs to a different run):
    pool size, forces up/down, FTE reallocated, % of the pool moved."""
    rows = []
    for key in POOL_KEYS:
        a = _read_pool(key)
        moved = a["difference"].clip(lower=0).sum()   # FTE into growing forces
        pool_total = a["current"].sum()
        rows.append({
            "pool":            POOL_META[key][1],
            "total_fte":       int(round(pool_total)),
            "forces_up":       int((a["difference"] > 0).sum()),
            "forces_down":     int((a["difference"] < 0).sum()),
            "fte_reallocated": int(round(moved)),
            "pct_moved":       round(moved / pool_total * 100, 1) if pool_total else 0.0,
        })
    return pd.DataFrame(rows).set_index("pool")
