"""
Recommended resource allocation per force — the contract the ILP optimiser
output will fill, with a real proportional baseline until it lands. Works in
two bases:

    basis="fte"     officer FTE pool, reallocated by harm share
    basis="budget"  central-grant £ pool, reallocated by harm share

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
Proportional baseline (Option B — default now). Every force's recommended
share is its harm share of the fixed national pool:

    recommended = harm_share_pct / 100 * total_current

This is real, not mockup: it is computed from the live dashboard dataset
(the per-force-mix harm share, `harm_share_pct_sub`). It is the "simpler
fallback" reallocation the team specified in the optimisation notes, and it
doubles as a credible stand-in for the optimiser. Because harm shares sum to
100 %, the recommended values sum back to the current national total and the
differences sum to ~0 — a redistribution of a fixed pool, not new resources.

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

# Per-basis source column on the dashboard df.
_CURRENT_COL: dict[Basis, str] = {
    "fte":    "officer_fte",
    "budget": "budget",
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


def _proportional(df: pd.DataFrame, basis: Basis) -> pd.DataFrame:
    current_col = _CURRENT_COL[basis]
    if current_col not in df.columns or _HARM_SHARE_COL not in df.columns:
        raise ValueError(
            f"allocation_loader._proportional: expected the dashboard dataset "
            f"with columns {current_col!r} and {_HARM_SHARE_COL!r}; got "
            f"{list(df.columns)}. Pass data.build_dataset()."
        )

    total_current = float(df[current_col].sum())
    out = pd.DataFrame({
        "force":          df["force"].values,
        "current":        df[current_col].values,
        "harm_share_pct": df[_HARM_SHARE_COL].values,
    })
    out["recommended"] = out["harm_share_pct"] / 100.0 * total_current
    out["difference"]  = out["recommended"] - out["current"]
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
    return _proportional(df, basis)
