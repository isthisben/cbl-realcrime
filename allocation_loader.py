"""
Recommended officer allocation per force — the contract the ILP optimiser
output will fill, with a real proportional baseline until it lands.

    load_allocation(df)  ->  DataFrame indexed by force, columns:
        current_fte, harm_share_pct, recommended_fte, difference
    IS_OPTIMISED         ->  True once the ILP output file is present;
                             False while the proportional (Option B) baseline
                             is in use.

Two sources, one five-column contract
-------------------------------------
Proportional baseline (Option B — default now). Every force's recommended
FTE is its harm share of the fixed national officer pool:

    recommended_fte = harm_share_pct / 100 * total_current_fte

This is real, not mockup: it is computed from the live dashboard dataset
(the per-force-mix harm share, `harm_share_pct_sub`). It is the "simpler
fallback" reallocation the team specified in the optimisation notes, and it
doubles as a credible stand-in for the optimiser. Because harm shares sum to
100 %, the recommended FTEs sum back to the current national total and the
differences sum to ~0 — a redistribution of a fixed pool, not new hiring.

ILP optimiser (Option A — later). Drop the optimiser output at
`data/raw/allocation_ilp.csv` or `.parquet` with the contract columns
(`force, current_fte, harm_share_pct, recommended_fte, difference`) and it is
read instead of the baseline. Force names must match the canonical 43.

`load_allocation` takes the already-built dashboard `df` (from
`data.build_dataset()`) rather than importing it, so this module stays cheap
to import and has no part in the startup ODS parse.
"""

from __future__ import annotations

import pathlib

import pandas as pd


_RAW = pathlib.Path(__file__).parent / "data" / "raw"
SOURCE_PARQUET = _RAW / "allocation_ilp.parquet"
SOURCE_CSV     = _RAW / "allocation_ilp.csv"

CONTRACT_COLUMNS = [
    "force", "current_fte", "harm_share_pct", "recommended_fte", "difference",
]

# Which dashboard harm-share column the proportional baseline reallocates by.
# The per-force-mix scenario is the dashboard's headline; switch to
# "harm_share_pct_flat" here if the team prefers the national-mix basis.
_HARM_SHARE_COL = "harm_share_pct_sub"

IS_OPTIMISED: bool = SOURCE_PARQUET.exists() or SOURCE_CSV.exists()


def _proportional(df: pd.DataFrame) -> pd.DataFrame:
    if _HARM_SHARE_COL not in df.columns or "officer_fte" not in df.columns:
        raise ValueError(
            "allocation_loader._proportional: expected the dashboard dataset "
            f"with columns 'officer_fte' and {_HARM_SHARE_COL!r}; got "
            f"{list(df.columns)}. Pass data.build_dataset()."
        )

    total_fte = float(df["officer_fte"].sum())
    out = pd.DataFrame({
        "force":           df["force"].values,
        "current_fte":     df["officer_fte"].values,
        "harm_share_pct":  df[_HARM_SHARE_COL].values,
    })
    out["recommended_fte"] = out["harm_share_pct"] / 100.0 * total_fte
    out["difference"]      = out["recommended_fte"] - out["current_fte"]
    return out.set_index("force")


def _read_optimised() -> pd.DataFrame:
    path = SOURCE_PARQUET if SOURCE_PARQUET.exists() else SOURCE_CSV
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


def load_allocation(df: pd.DataFrame) -> pd.DataFrame:
    """Recommended vs current officer allocation per force. Reads the ILP
    output if present, else returns the real proportional (Option B) baseline
    computed from `df`."""
    global IS_OPTIMISED
    if SOURCE_PARQUET.exists() or SOURCE_CSV.exists():
        IS_OPTIMISED = True
        return _read_optimised()

    IS_OPTIMISED = False
    return _proportional(df)
