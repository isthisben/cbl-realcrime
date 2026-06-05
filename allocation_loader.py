"""
Recommended resource allocation per force — the contract the ILP optimiser
output will fill, with a real proportional baseline until it lands. Works in
two bases:

    basis="fte"     officer FTE pool, reallocated by harm share
    basis="budget"  formula grant £, set so total funding tracks harm share

    load_allocation(df, basis)  ->  DataFrame indexed by force, columns:
        current, harm_share_pct, recommended, difference
    is_optimised(basis)         ->  True once the ILP output file for that
                                    basis is present; False while the
                                    proportional baseline is in use.

The column names are basis-agnostic ('current', 'recommended', 'difference')
so the dashboard can render the same panel under either basis by just
relabelling axes and tooltips. The unit is implied by the basis: FTE for
'fte', £ for 'budget'.

Two sources, one four-column contract
-------------------------------------
Real baseline (Option B — default now), computed from the live dashboard
dataset (the per-force-mix harm share, `harm_share_pct_sub`):

    fte:    recommended = harm_share_pct / 100 * total_fte
            Every force's recommended headcount is its harm share of the
            national officer pool.

    budget: the formula grant is set so each force's *total* funding tracks
            its harm share, holding precept and ring-fenced specific grants
            fixed (see _equalise_funding). Only the grant moves.

Both are real, not mockup, and double as a credible stand-in for the optimiser.
Each redistributes a fixed pool — the recommended values sum back to the
current national pool and the differences sum to ~0, not new resources.

ILP optimiser (Option A — later). Drop the optimiser output at one of:

    data/raw/allocation_ilp_fte.{parquet,csv}      (officer FTE basis)
    data/raw/allocation_ilp_budget.{parquet,csv}   (£ budget basis)

with the contract columns (`force, current, harm_share_pct, recommended,
difference`) and it is read instead of the baseline for that basis. The two
bases optimise independently; one can land before the other. Force names
must match the canonical 43.

`load_allocation` takes the already-built dashboard `df` (from
`data.build_dataset()`) rather than importing it, so this module stays cheap
to import and has no part in the startup ODS parse.
"""

from __future__ import annotations

import pathlib
from typing import Literal

import pandas as pd


Basis = Literal["fte", "budget"]

_RAW = pathlib.Path(__file__).parent / "data" / "raw"

# Per-basis ILP output paths. The optimiser can emit one or both; whichever
# is present overrides the proportional baseline for that basis.
_ILP_SOURCES: dict[Basis, tuple[pathlib.Path, pathlib.Path]] = {
    "fte":    (_RAW / "allocation_ilp_fte.parquet",
               _RAW / "allocation_ilp_fte.csv"),
    "budget": (_RAW / "allocation_ilp_budget.parquet",
               _RAW / "allocation_ilp_budget.csv"),
}

# Legacy single-file path kept for backward compatibility with anyone who
# already dropped an ILP file under the original name; treated as FTE.
_ILP_LEGACY_FTE = (
    _RAW / "allocation_ilp.parquet",
    _RAW / "allocation_ilp.csv",
)

CONTRACT_COLUMNS = [
    "force", "current", "harm_share_pct", "recommended", "difference",
]

# Per-basis source column on the dashboard df (the 'current' allocation).
_CURRENT_COL: dict[Basis, str] = {
    "fte":    "officer_fte",
    "budget": "grant",
}

# Which harm-share column the proportional baseline reallocates by. The
# per-force-mix scenario is the dashboard's headline; swap to
# "harm_share_pct_flat" here if the team prefers the national-mix basis.
_HARM_SHARE_COL = "harm_share_pct_sub"


def _ilp_paths(basis: Basis) -> list[pathlib.Path]:
    primary = list(_ILP_SOURCES[basis])
    if basis == "fte":
        # Legacy `allocation_ilp.{parquet,csv}` (no _fte suffix) also counts.
        primary.extend(_ILP_LEGACY_FTE)
    return primary


def is_optimised(basis: Basis) -> bool:
    return any(p.exists() for p in _ilp_paths(basis))


# Module-level flags so the app can read them once at startup for badge
# rendering. Recomputed at import time; refreshed on every load_allocation
# call too in case files appear later.
IS_OPTIMISED_FTE:    bool = is_optimised("fte")
IS_OPTIMISED_BUDGET: bool = is_optimised("budget")

# Backwards-compatible alias for the existing app.py reference.
IS_OPTIMISED: bool = IS_OPTIMISED_FTE


def _baseline(df: pd.DataFrame, basis: Basis) -> pd.DataFrame:
    """Real (non-optimiser) reallocation baseline for the given basis."""
    if basis == "budget":
        return _equalise_funding(df)
    return _proportional_fte(df)


def _proportional_fte(df: pd.DataFrame) -> pd.DataFrame:
    """Each force's recommended headcount is its harm share of the national
    officer pool. Harm shares sum to 100 %, so the recommendation sums back to
    the current pool and the differences net to ~0."""
    if "officer_fte" not in df.columns or _HARM_SHARE_COL not in df.columns:
        raise ValueError(
            f"allocation_loader: expected the dashboard dataset with columns "
            f"'officer_fte' and {_HARM_SHARE_COL!r}; got {list(df.columns)}. "
            f"Pass data.build_dataset()."
        )
    total_current = float(df["officer_fte"].sum())
    out = pd.DataFrame({
        "force":          df["force"].values,
        "current":        df["officer_fte"].values,
        "harm_share_pct": df[_HARM_SHARE_COL].values,
    })
    out["recommended"] = out["harm_share_pct"] / 100.0 * total_current
    out["difference"]  = out["recommended"] - out["current"]
    return out.set_index("force")


def _equalise_funding(df: pd.DataFrame) -> pd.DataFrame:
    """Grant-equalisation baseline (basis='budget').

    The allocation gap is measured on *total* funding, but only the formula
    grant can move; precept and ring-fenced specific grants are fixed. So each
    force's grant is set to push its total funding toward its harm share:

        fixed_i  = total_funding_i - grant_i        (precept + specific grants)
        target_i = harm_share_i / 100 * total_funding_national
        grant_i* = max(0, target_i - fixed_i)

    grant_i* cannot be negative (a force cannot hand back more than its whole
    grant). Flooring at zero leaves the recommended grants summing to more than
    the fixed grant pool, so they are rescaled back down to it — the
    reallocation redistributes the existing pool, it does not invent new money.
    The ILP optimiser handles the same constraints more rigorously; this is the
    credible stand-in until it lands."""
    need = {"force", "grant", "total_funding", _HARM_SHARE_COL}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(
            f"allocation_loader._equalise_funding: missing columns "
            f"{sorted(missing)}; got {list(df.columns)}. Pass data.build_dataset()."
        )

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
        "harm_share_pct": harm_share,
        "recommended":    rec,
        "difference":     rec - grant,
    })
    return out.set_index("force")


def _read_optimised(basis: Basis) -> pd.DataFrame:
    path = next(p for p in _ilp_paths(basis) if p.exists())
    df = (pd.read_parquet(path) if path.suffix == ".parquet"
          else pd.read_csv(path))

    missing = set(CONTRACT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"allocation_loader: ILP output {path.name} is missing contract "
            f"columns {sorted(missing)}. Found {list(df.columns)}. The "
            f"optimiser must emit {CONTRACT_COLUMNS}."
        )
    return df[CONTRACT_COLUMNS].set_index("force")


def load_allocation(df: pd.DataFrame, basis: Basis = "fte") -> pd.DataFrame:
    """Recommended vs current allocation per force for the given basis.
    Reads the ILP output if present, else returns the real proportional
    (Option B) baseline computed from `df`.

    Columns are basis-agnostic: 'current', 'recommended', 'difference' are
    in FTE units for basis='fte' and £ for basis='budget'.
    """
    global IS_OPTIMISED_FTE, IS_OPTIMISED_BUDGET, IS_OPTIMISED
    optimised = is_optimised(basis)
    if basis == "fte":
        IS_OPTIMISED_FTE = optimised
        IS_OPTIMISED = optimised
    else:
        IS_OPTIMISED_BUDGET = optimised

    if optimised:
        return _read_optimised(basis)
    return _baseline(df, basis)
