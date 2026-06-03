"""
Reads the per-force central government grant allocation for 2025-26 from
the Police Grant Report 2025-26 (Home Office) and returns it keyed by the
dashboard's canonical 43 force names.

    load_force_budget()  ->  {force_name: budget_gbp}

The source CSV lists the 'Overall Total' column from the Police Grant Report
per-force table — Police Main Grant + ex-DCLG Formula Funding + Legacy
Council Tax Grants + Welsh Top-Up. Council tax precept (~40% of total force
funding) is locally raised and excluded by design: only the centrally-
controlled grant pool is redistributable.

Welsh forces (Dyfed-Powys, Gwent, North Wales, South Wales) carry £0 in the
DCLG Formula Funding and Legacy Council Tax Grants components — those
streams are routed through the Welsh Government separately — so the Overall
Total reflects Police Main Grant + Welsh Top-Up only. This makes Welsh
forces look smaller than English peers of comparable size and is surfaced
as a caveat in the dashboard.

The CSV uses the dashboard's canonical force names directly; no name
normalisation is needed. The loader fails loud on row-count != 43 or on
a total that does not reconcile to £9,806,553,489 (within £100 rounding).

Source file: data/raw/police-grant-2025-26.csv
Provenance:  data/raw/SOURCES.md (Home Office, gov.uk — Police Grant
             Report 2025-26)
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "police-grant-2025-26.csv"

EXPECTED_FORCES = 43
EXPECTED_TOTAL_GBP = 9_806_553_489
TOTAL_TOLERANCE_GBP = 100


def load_force_budget() -> dict[str, float]:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Budget source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the gov.uk download link."
        )

    df = pd.read_csv(SOURCE, comment="#")

    required = {"force", "budget_gbp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"police-grant-2025-26.csv: missing required columns {missing}. "
            f"Found {list(df.columns)}."
        )

    if len(df) != EXPECTED_FORCES:
        raise ValueError(
            f"Budget CSV: expected {EXPECTED_FORCES} territorial forces, "
            f"got {len(df)}."
        )

    df["budget_gbp"] = pd.to_numeric(df["budget_gbp"], errors="coerce")
    nan_rows = df["budget_gbp"].isna().sum()
    if nan_rows:
        affected = df.loc[df["budget_gbp"].isna(), "force"].tolist()
        raise ValueError(
            f"Budget CSV: {nan_rows} rows have non-numeric budget. "
            f"Forces affected: {affected}"
        )

    total = int(df["budget_gbp"].sum())
    if abs(total - EXPECTED_TOTAL_GBP) > TOTAL_TOLERANCE_GBP:
        raise ValueError(
            f"Budget CSV: total £{total:,} does not reconcile to "
            f"expected £{EXPECTED_TOTAL_GBP:,} (tolerance £{TOTAL_TOLERANCE_GBP})."
        )

    return dict(zip(df["force"], df["budget_gbp"].astype(float)))
