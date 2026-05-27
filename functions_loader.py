"""
Police officer *function* mix per force — how each force distributes its
officers across the wider CIPFA Police Objective Analysis (POA) function
categories (Local Policing, Investigations, Public Protection, ...).

    load_force_function_shares(forces)  ->  DataFrame [force x function] of
                                            percentage shares (each row ~100)
    NATIONAL_SHARES                     ->  {function: national %} (published)
    FUNCTIONS                           ->  the 12 wider categories, in order
    IS_MOCKUP                           ->  True while the real source file is
                                            absent and seeded synthetic per-force
                                            shares are being used.

Data swap
---------
The real source is the Home Office Police Workforce Functions open data
table, `data/raw/open-data-table-police-workforce-functions-280126.ods`.
While that file is absent this module returns a *deterministic mockup*
generated from the published 2025 national breakdown, so the dashboard is
functional before the file lands. Dropping the file into `data/raw/` flips
`IS_MOCKUP` to False and routes through `_load_real`.

`_load_real` is written against the schema of the sibling workforce table
(`workforce_loader.py`) plus a function column, but it has NOT been run
against the real file yet — the column names and the set of function labels
are unverified. It therefore fails loud (raises with what it found) rather
than risk a silent mis-parse, so the schema gets confirmed the moment the
file is in hand. The two known reconciliation points are flagged inline:
the function-name column and the mapping of fine POA codes up to the 12
wider categories below.

National 2025 breakdown (146,442 police officers; source: handoff /
Home Office Police Workforce Functions, snapshot 31 March 2025):
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import random

import pandas as pd


SOURCE = (
    pathlib.Path(__file__).parent
    / "data" / "raw" / "open-data-table-police-workforce-functions-280126.ods"
)

# The 12 wider POA function categories, ordered by national share (largest
# first) so charts read top-to-bottom in order of size.
FUNCTIONS = [
    "Local Policing",
    "Investigations",
    "Public Protection",
    "Other",
    "Operational Support",
    "Support Functions",
    "National Policing",
    "Intelligence",
    "Road Policing",
    "Criminal Justice",
    "Dealing with Public",
    "Investigative Support",
]

# Published national split, 31 March 2025 (percent of 146,442 officers).
# Sums to 100.0. This is the official national reference shown as the
# comparison series in the dashboard, in both the mockup and real paths.
NATIONAL_SHARES: dict[str, float] = {
    "Local Policing":        39.6,
    "Investigations":        15.6,
    "Public Protection":     10.1,
    "Other":                  6.9,
    "Operational Support":    6.1,
    "Support Functions":      5.8,
    "National Policing":      4.4,
    "Intelligence":           3.7,
    "Road Policing":          2.8,
    "Criminal Justice":       2.5,
    "Dealing with Public":    2.2,
    "Investigative Support":  0.3,
}

# Per-force anchors quoted in the handoff. The mockup pins these exact
# values for the named force/function and rescales that force's remaining
# functions to fill the rest, so the synthetic data lines up with the few
# real figures we have to show against.
_OVERRIDES: dict[str, tuple[str, float]] = {
    "Dyfed-Powys":         ("Investigations",      28.1),
    "West Yorkshire":      ("Public Protection",   14.5),
    "Merseyside":          ("Operational Support", 16.8),
    "Metropolitan Police": ("National Policing",   10.8),
}

# Spread of the multiplicative per-force noise in the mockup. ~0.22 keeps
# most forces within roughly 0.7x-1.4x of the national share per function:
# visibly varied, never wild.
_MOCKUP_SIGMA = 0.22


IS_MOCKUP: bool = not SOURCE.exists()


def _seeded_rng(force: str) -> random.Random:
    """Deterministic per-force RNG, so the mockup is identical run to run."""
    digest = hashlib.md5(force.encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16) % (2**32))


def _mockup(forces: list[str]) -> pd.DataFrame:
    rows: dict[str, dict[str, float]] = {}
    for force in forces:
        rng = _seeded_rng(force)
        raw = {c: NATIONAL_SHARES[c] * math.exp(rng.gauss(0.0, _MOCKUP_SIGMA))
               for c in FUNCTIONS}
        total = sum(raw.values())
        vec = {c: raw[c] / total * 100.0 for c in FUNCTIONS}

        if force in _OVERRIDES:
            pin_cat, pin_val = _OVERRIDES[force]
            others = [c for c in FUNCTIONS if c != pin_cat]
            others_sum = sum(vec[c] for c in others)
            scale = (100.0 - pin_val) / others_sum
            for c in others:
                vec[c] *= scale
            vec[pin_cat] = pin_val

        rows[force] = vec

    df = pd.DataFrame.from_dict(rows, orient="index")[FUNCTIONS]
    df.index.name = "force"
    return df


# Candidate column names for the function label in the real file. The Home
# Office workforce releases are not consistent about this header across
# tables; the first one present wins, otherwise _load_real raises and lists
# what it actually found. ADJUST once the real file is in hand.
_FUNCTION_COL_CANDIDATES = [
    "Function", "Police Officer function", "Officer function",
    "POA function", "Wider function", "Function (wider)", "CIPFA function",
]

_SNAPSHOT_YEAR = 2025


def _load_real(forces: list[str]) -> pd.DataFrame:
    """Parse the real workforce-functions ODS. UNVERIFIED against the actual
    file — fails loud on any schema surprise so it can be reconciled rather
    than mis-parsed. See module docstring."""
    df = pd.read_excel(SOURCE, sheet_name="Data", engine="odf")

    force_col = "Force name" if "Force name" in df.columns else None
    fte_col   = "Total (FTE)" if "Total (FTE)" in df.columns else None
    func_col  = next((c for c in _FUNCTION_COL_CANDIDATES if c in df.columns), None)
    year_col  = "As at 31 March" if "As at 31 March" in df.columns else None

    if not all([force_col, fte_col, func_col]):
        raise ValueError(
            "functions_loader._load_real: the real file is present but its "
            "schema is unverified and does not match the expected columns. "
            f"Found columns: {list(df.columns)}. Need a force-name column "
            f"('Force name'), an FTE column ('Total (FTE)'), and a function "
            f"column (one of {_FUNCTION_COL_CANDIDATES}). Update functions_loader "
            "now that the file is available, then re-run."
        )

    if year_col is not None:
        df = df[df[year_col] == _SNAPSHOT_YEAR]

    # NOTE: the real file's function labels are likely finer POA codes
    # (e.g. '1a Neighbourhood') that must be rolled up to the 12 wider
    # categories in FUNCTIONS. Build that mapping here once the labels are
    # known; until then any label outside FUNCTIONS will surface in the
    # validation below.
    df = df.copy()
    df["Total (FTE)"] = pd.to_numeric(df[fte_col], errors="coerce")

    pivot = (
        df.groupby([force_col, func_col])["Total (FTE)"]
          .sum()
          .unstack(fill_value=0.0)
    )

    missing_funcs = set(FUNCTIONS) - set(pivot.columns)
    if missing_funcs:
        raise ValueError(
            "functions_loader._load_real: parsed function labels do not cover "
            f"the 12 wider categories. Missing {sorted(missing_funcs)}; got "
            f"{sorted(pivot.columns)}. A POA-code -> wider-category roll-up is "
            "probably needed — add it in _load_real."
        )

    shares = pivot[FUNCTIONS].div(pivot[FUNCTIONS].sum(axis=1), axis=0) * 100.0
    shares.index.name = "force"
    return shares.reindex(list(forces))


def load_force_function_shares(forces: list[str] | None = None) -> pd.DataFrame:
    """Per-force officer-function shares as percentages (each row ~100).

    `forces` pins the output to exactly the dashboard's canonical force list
    (pass `DF["force"]`) so the panel can never KeyError on a selected force.
    Defaults to the keys with published anchors if not supplied.
    """
    global IS_MOCKUP
    force_list = list(forces) if forces is not None else sorted(_OVERRIDES)

    if SOURCE.exists():
        IS_MOCKUP = False
        return _load_real(force_list)

    IS_MOCKUP = True
    return _mockup(force_list)
