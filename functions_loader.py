"""
Police officer *function* mix per force — how each force spreads its officers
across the wider CIPFA Police Objective Analysis (POA) function categories
(Local Policing, Investigations, Public Protection, ...).

    load_force_function_shares(forces)  ->  DataFrame [force x function] of
                                            percentage shares (each row ~100)
    NATIONAL_SHARES                     ->  {function: national %} (published)
    FUNCTIONS                           ->  the 12 wider categories, in order

The numbers come from the Home Office Police Workforce Functions open data
table (data/raw/open-data-table-police-workforce-functions-280126.ods). The
loader reads the `Data` sheet, filters to police officers at the 31 March 2025
snapshot, and groups the `Wider function name` column into the 12 categories
below. Labels carry year-to-year case variants ('Local Policing' vs 'Local
policing') which are merged case-insensitively; `Criminal Justice Arrangements`
and `Dealing with the Public` map to the shorter dashboard names; the small
'Not stated' bucket folds into 'Other'. Percentage shares are unaffected by the
file's sex/ethnicity/frontline cross-tabbing because that crossing is uniform
across functions. It fails loud on any unmapped label or missing column.

For hosts that ship only the committed snapshot (data/snapshot/functions.pkl)
and not the ~4 MB ODS, the snapshot is read instead.
"""

from __future__ import annotations

import pathlib

import pandas as pd

import cache


SOURCE = (
    pathlib.Path(__file__).parent
    / "data" / "raw" / "open-data-table-police-workforce-functions-280126.ods"
)

# Committed deploy snapshot, read when the raw ODS is absent. Written by
# write_snapshot() / `python data.py --snapshot`.
_SNAPSHOT_FILE = (
    pathlib.Path(__file__).parent / "data" / "snapshot" / "functions.pkl"
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
# Sums to 100.0 — the national reference shown as the comparison series.
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

# Force names in the file that differ from the dashboard's canonical list.
_FORCE_NAME_FIXES = {
    "London, City of":             "City of London",
    "Hampshire and Isle of Wight": "Hampshire",
}

# The file's 'Wider function name' values (lowercased) -> dashboard category.
# Lowercasing merges the file's year-to-year case variants; 2025 uses the
# lowercase forms. 'Not stated' carries no officer FTE in 2025 but is mapped
# to 'Other' defensively so a stray row can never go unmapped.
_WIDER_FUNCTION_MAP = {
    "local policing":                "Local Policing",
    "investigations":                "Investigations",
    "public protection":             "Public Protection",
    "other":                         "Other",
    "operational support":           "Operational Support",
    "support functions":             "Support Functions",
    "national policing":             "National Policing",
    "intelligence":                  "Intelligence",
    "road policing":                 "Road Policing",
    "criminal justice arrangements": "Criminal Justice",
    "dealing with the public":       "Dealing with Public",
    "investigative support":         "Investigative Support",
    "not stated":                    "Other",
}

_SNAPSHOT_YEAR = 2025

# Bump when _load_real's parsing changes the returned shares, so an existing
# on-disk cache is rebuilt. The source-file signature handles a data refresh;
# this covers code changes the file can't signal.
_CACHE_VERSION = 1


def _load_real(forces: list[str]) -> pd.DataFrame:
    """Per-force officer-function shares from the workforce-functions ODS.
    Filters to police officers at the 2025 snapshot, maps `Wider function name`
    to the 12 categories, sums FTE per force x category, and normalises to
    percentage shares."""
    df = pd.read_excel(SOURCE, sheet_name="Data", engine="odf")

    required = {"As at 31 March", "Force name", "Worker type",
                "Wider function name", "Total (FTE)"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"functions_loader._load_real: {SOURCE.name} is missing expected "
            f"columns {sorted(missing)}. Found {list(df.columns)}."
        )

    df = df[(df["Worker type"] == "Police Officer")
            & (df["As at 31 March"] == _SNAPSHOT_YEAR)].copy()
    if df.empty:
        raise ValueError(
            f"functions_loader._load_real: no 'Police Officer' rows for "
            f"{_SNAPSHOT_YEAR} in {SOURCE.name}."
        )

    df["Force name"] = df["Force name"].replace(_FORCE_NAME_FIXES)
    df["category"] = (df["Wider function name"].astype(str).str.strip()
                      .str.lower().map(_WIDER_FUNCTION_MAP))

    unmapped = sorted(df.loc[df["category"].isna(), "Wider function name"].unique())
    if unmapped:
        raise ValueError(
            f"functions_loader._load_real: unmapped 'Wider function name' "
            f"values {unmapped} — add them to _WIDER_FUNCTION_MAP."
        )

    df["Total (FTE)"] = pd.to_numeric(df["Total (FTE)"], errors="coerce").fillna(0.0)
    pivot = (df.groupby(["Force name", "category"])["Total (FTE)"]
               .sum().unstack(fill_value=0.0))

    for cat in FUNCTIONS:                       # guarantee all 12 columns exist
        if cat not in pivot.columns:
            pivot[cat] = 0.0
    pivot = pivot[FUNCTIONS]

    shares = pivot.div(pivot.sum(axis=1), axis=0) * 100.0
    shares.index.name = "force"
    return shares.reindex(list(forces))


def load_force_function_shares(forces: list[str], *,
                               refresh: bool = False) -> pd.DataFrame:
    """Per-force officer-function shares as percentages (each row ~100).

    `forces` pins the output to exactly the dashboard's canonical force list
    (pass `DF["force"]`) so the panel can never KeyError on a selected force.

    The parse of a large ODS is cached to disk (keyed on the source file and
    the requested force list); pass `refresh=True` to re-parse. If the raw ODS
    is absent the committed snapshot is read instead.
    """
    force_list = list(forces)

    if SOURCE.exists():
        src_sig = cache.file_signature(SOURCE)
        signature = (None if src_sig is None
                     else {"version": _CACHE_VERSION, "source": src_sig,
                           "forces": force_list})
        return cache.cached("functions", signature,
                            lambda: _load_real(force_list), refresh=refresh)

    if _SNAPSHOT_FILE.exists():
        return pd.read_pickle(_SNAPSHOT_FILE).reindex(force_list)

    raise FileNotFoundError(
        f"Workforce-functions source not found at {SOURCE}, and no snapshot at "
        f"{_SNAPSHOT_FILE}. See data/raw/SOURCES.md for the gov.uk download."
    )


def write_snapshot(forces: list[str]) -> pathlib.Path:
    """Write the committed deploy snapshot of per-force function shares
    (data/snapshot/functions.pkl) from the raw ODS, for hosts that don't ship
    the ODS. Called by data.write_snapshot(); requires the ODS present."""
    shares = load_force_function_shares(list(forces))
    _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    shares.to_pickle(_SNAPSHOT_FILE)
    return _SNAPSHOT_FILE
