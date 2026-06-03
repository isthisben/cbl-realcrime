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

`_load_real` is reconciled against the 31 March 2025 release: it reads the
`Data` sheet, filters to `Worker type == "Police Officer"` at the 2025
snapshot, and groups the `Wider function name` column into the 12 categories
below. The file's labels carry year-to-year case variants ('Local Policing'
vs 'Local policing') which are merged case-insensitively; `Criminal Justice
Arrangements` and `Dealing with the Public` map to the shorter dashboard
names; the small 'Not stated' bucket folds into 'Other'. Percentage shares
are unaffected by the file's sex/ethnicity/frontline cross-tabbing because
that crossing is uniform across functions. It still fails loud on any
unmapped label or missing column so a future schema change can't pass
silently.

National 2025 breakdown (146,442 police officers; source: handoff /
Home Office Police Workforce Functions, snapshot 31 March 2025):
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import random

import pandas as pd

import cache


SOURCE = (
    pathlib.Path(__file__).parent
    / "data" / "raw" / "open-data-table-police-workforce-functions-280126.ods"
)

# Committed deploy snapshot, read when the raw ODS is absent (a host that
# ships only the snapshot). Written by write_snapshot() / `python data.py
# --snapshot`.
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


# Force names in the file that differ from the dashboard's canonical list.
_FORCE_NAME_FIXES = {
    "London, City of":             "City of London",
    "Hampshire and Isle of Wight": "Hampshire",
}

# The file's 'Wider function name' values (lowercased) -> dashboard category.
# Lowercasing merges the file's year-to-year case variants ('Local Policing'
# vs 'Local policing'; 2025 uses the lowercase forms). 'Criminal Justice
# Arrangements' and 'Dealing with the Public' map to the shorter dashboard
# names. The 2025 police-officer data carries no 'Not stated' FTE, but it is
# mapped to 'Other' defensively so a stray row can never go unmapped.
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

# Bump when _load_real's parsing / mapping changes the returned shares, so an
# existing on-disk cache is rebuilt. The source-file signature handles a data
# refresh; this covers code changes the file can't signal.
_CACHE_VERSION = 1


def _load_real(forces: list[str]) -> pd.DataFrame:
    """Per-force officer-function shares from the real Home Office workforce-
    functions ODS, reconciled against the 31 March 2025 release. Filters to
    police officers at the 2025 snapshot, maps `Wider function name` to the 12
    dashboard categories (case-insensitive, so the file's case-variant labels
    merge), sums FTE per force x category, and normalises to percentage shares.
    Fails loud on a missing column or an unmapped function label."""
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


def load_force_function_shares(forces: list[str] | None = None, *,
                               refresh: bool = False) -> pd.DataFrame:
    """Per-force officer-function shares as percentages (each row ~100).

    `forces` pins the output to exactly the dashboard's canonical force list
    (pass `DF["force"]`) so the panel can never KeyError on a selected force.
    Defaults to the keys with published anchors if not supplied.

    The real-data path parses a large workforce-functions ODS, so its result
    is cached to disk (keyed on the source file and the requested force list);
    pass `refresh=True` to re-parse. The synthetic mockup path is cheap and
    never cached.
    """
    global IS_MOCKUP
    force_list = list(forces) if forces is not None else sorted(_OVERRIDES)

    if SOURCE.exists():
        IS_MOCKUP = False
        src_sig = cache.file_signature(SOURCE)
        signature = (None if src_sig is None
                     else {"version": _CACHE_VERSION, "source": src_sig,
                           "forces": force_list})
        return cache.cached("functions", signature,
                            lambda: _load_real(force_list), refresh=refresh)

    # Raw functions ODS absent (e.g. a deploy host). Prefer the committed
    # snapshot — real shares — over the synthetic mockup.
    if _SNAPSHOT_FILE.exists():
        IS_MOCKUP = False
        return pd.read_pickle(_SNAPSHOT_FILE).reindex(force_list)

    IS_MOCKUP = True
    return _mockup(force_list)


def write_snapshot(forces: list[str]) -> pathlib.Path:
    """Write the committed deploy snapshot of per-force function shares
    (data/snapshot/functions.pkl) from the raw ODS, for hosts that don't ship
    the ODS. Called by data.write_snapshot(); requires the ODS present."""
    shares = load_force_function_shares(list(forces))
    _SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    shares.to_pickle(_SNAPSHOT_FILE)
    return _SNAPSHOT_FILE
