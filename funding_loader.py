"""
Reads Table 4a of the Home Office Police Funding tables and returns each
territorial force's 2025-26 total funding and its components:

    load_force_funding()  ->  DataFrame indexed by force, columns:
        gov_funding_gbp, precept_gbp, total_funding_gbp

Why this sits alongside grant_loader
------------------------------------
`grant_loader` reads the *Police Grant Report* 'Overall Total' (£9.81 bn) —
the formally redistribution-eligible core grant, and the only pool the
dashboard reallocates. This file reads the *Police Funding Statistics*
Table 4a, a broader cut that additionally carries, per force:

    Government Funding  central funding INCLUDING ring-fenced specific grants
                        (e.g. the Met's National & International Capital City
                        grant) — larger than the Grant Report 'Overall Total'.
    Precept             council tax precept income, set locally by each PCC.
    Total               Government Funding + Precept = a force's full funding.

The dashboard compares each force's share of *Total* funding to its share of
harm (the allocation gap), and treats everything that is not the redistributable
formula grant — precept plus ring-fenced specific grants — as fixed when it
reallocates. So only Precept and Total are consumed downstream; Government
Funding is surfaced for provenance/reconciliation.

Using this table (rather than deriving total = grant + precept) also resolves
the Welsh under-count that affects `grant_loader`: the Welsh Government's
contribution is inside these Total figures, so the four Welsh forces compare
like-for-like with English peers.

Table 4a layout
---------------
One header block per financial year (2015-16 ... 2025-26), each three columns
wide: Government Funding | Precept | Total. Figures are in £ MILLION. Data rows
carry an ONS PFA code in column 0 — E23* (English) and W15* (Welsh) are the 43
territorial forces; E12* (regions), E92/W92 (countries) and K04 (England &
Wales) are aggregates and are dropped. City of London carries a blank precept
(read as £0).

Source file: data/raw/police-funding-england-and-wales-2015-to-2026-tables.ods
Provenance:  data/raw/SOURCES.md
"""

from __future__ import annotations

import pathlib
import re

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "police-funding-england-and-wales-2015-to-2026-tables.ods"

SHEET = "Table_4a"

# Column positions in Table 4a. Columns 0/1 are the PFA code/name; each year
# block is three columns wide. 2025-26 is the final block: 32/33/34.
_COL_CODE, _COL_NAME = 0, 1
_COL_GOV, _COL_PRECEPT, _COL_TOTAL = 32, 33, 34
_FIRST_DATA_ROW = 5

# ONS PFA codes for the 43 territorial forces; E12*/E92/W92/K04 are aggregates.
_FORCE_CODE_RE = re.compile(r"^(E23|W15)\d+$")

EXPECTED_FORCES = 43

# National precept summed across the 43 forces, £. Matches the £6,058 m
# council-tax-precept line in the 2025-26 police funding settlement, and the
# England-and-Wales (K04) precept cell of this table to the £.
EXPECTED_PRECEPT_GBP = 6_057_626_419
PRECEPT_TOLERANCE_GBP = 1_000_000

# Canonical force names — match grant_loader / prc_loader / workforce_loader.
FORCE_NAME_FIXES = {
    "London, City of":             "City of London",
    "Hampshire and Isle of Wight": "Hampshire",
}


def load_force_funding() -> pd.DataFrame:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Police funding source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the gov.uk download link."
        )

    raw = pd.read_excel(SOURCE, sheet_name=SHEET, engine="odf", header=None)

    df = raw.iloc[_FIRST_DATA_ROW:,
                  [_COL_CODE, _COL_NAME, _COL_GOV, _COL_PRECEPT, _COL_TOTAL]].copy()
    df.columns = ["code", "force", "gov_m", "precept_m", "total_m"]

    # Keep only the 43 territorial PFAs; drop region/country aggregate rows.
    df = df[df["code"].astype(str).str.match(_FORCE_CODE_RE)].copy()
    df["force"] = df["force"].replace(FORCE_NAME_FIXES)

    # City of London carries a blank precept; read it as £0. Government Funding
    # and Total must be present for all 43.
    df["precept_m"] = pd.to_numeric(df["precept_m"], errors="coerce").fillna(0.0)
    for col in ("gov_m", "total_m"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if len(df) != EXPECTED_FORCES:
        raise ValueError(
            f"Police funding Table 4a: expected {EXPECTED_FORCES} territorial "
            f"forces (E23*/W15* codes), got {len(df)}."
        )

    bad = df.loc[df[["gov_m", "total_m"]].isna().any(axis=1), "force"].tolist()
    if bad:
        raise ValueError(
            f"Police funding Table 4a: non-numeric Government Funding/Total for "
            f"{bad}. The 2025-26 column block (32-34) may have shifted."
        )

    # Table 4a is in £ million; convert to whole pounds to match grant_loader.
    out = pd.DataFrame(
        {
            "gov_funding_gbp":   (df["gov_m"]     * 1_000_000).to_numpy(),
            "precept_gbp":       (df["precept_m"] * 1_000_000).to_numpy(),
            "total_funding_gbp": (df["total_m"]   * 1_000_000).to_numpy(),
        },
        index=pd.Index(df["force"].to_numpy(), name="force"),
    )

    # Internal consistency: Government Funding + Precept must equal Total.
    resid = (out["gov_funding_gbp"] + out["precept_gbp"]
             - out["total_funding_gbp"]).abs()
    if (resid > 1_000).any():   # within £1k of source rounding
        off = out.index[resid > 1_000].tolist()
        raise ValueError(
            f"Police funding Table 4a: Government Funding + Precept != Total for "
            f"{off}. Column positions have likely shifted — re-check the sheet."
        )

    precept_total = out["precept_gbp"].sum()
    if abs(precept_total - EXPECTED_PRECEPT_GBP) > PRECEPT_TOLERANCE_GBP:
        raise ValueError(
            f"Police funding Table 4a: national precept £{precept_total:,.0f} "
            f"does not reconcile to expected £{EXPECTED_PRECEPT_GBP:,} "
            f"(tolerance £{PRECEPT_TOLERANCE_GBP:,}). Wrong column or year block."
        )

    return out
