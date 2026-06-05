"""
Reads the per-force central government grant allocation for 2025-26 from
the Police Grant Report 2025-26 (Home Office) and returns it keyed by the
dashboard's canonical 43 force names.

    load_force_grant()  ->  {force_name: grant_gbp}

This is the *redistributable formula grant* — the pool the dashboard
reallocates. The source CSV lists the 'Overall Total' column from the Police
Grant Report per-force table: Police Main Grant + ex-DCLG Formula Funding +
Legacy Council Tax Grants + Welsh Top-Up. It is deliberately narrower than the
'Government Funding' figure in the Police Funding Statistics tables
(`funding_loader`), which also bundles ring-fenced specific grants (pensions,
the Met's capital-city grant, etc.) that cannot be freely redistributed.

Council tax precept (~40% of total force funding) is locally raised and is not
in this pool; it enters the dashboard via `funding_loader` as a *fixed*
component of each force's total funding, never as something to reallocate.

Welsh forces (Dyfed-Powys, Gwent, North Wales, South Wales) carry £0 in the
DCLG Formula Funding and Legacy Council Tax Grants components — those streams
are routed through the Welsh Government separately — so this grant figure
understates their funding. The dashboard's allocation gap is measured on total
funding (`funding_loader`), which includes the Welsh-routed money, so that
under-count does not distort the gap; it only limits how much of a Welsh
force's funding the model can move.

The CSV uses the dashboard's canonical force names directly; no name
normalisation is needed. The loader fails loud on row-count != 43 or on a
total that does not reconcile to £9,806,553,489 (within £100 rounding).

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


def load_force_grant() -> dict[str, float]:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Grant source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the gov.uk download link."
        )

    df = pd.read_csv(SOURCE, comment="#")

    # The CSV column header is the legacy name `budget_gbp`; it holds the
    # formula grant 'Overall Total'. Kept as-is to avoid editing raw data.
    required = {"force", "budget_gbp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"police-grant-2025-26.csv: missing required columns {missing}. "
            f"Found {list(df.columns)}."
        )

    if len(df) != EXPECTED_FORCES:
        raise ValueError(
            f"Grant CSV: expected {EXPECTED_FORCES} territorial forces, "
            f"got {len(df)}."
        )

    df["budget_gbp"] = pd.to_numeric(df["budget_gbp"], errors="coerce")
    nan_rows = df["budget_gbp"].isna().sum()
    if nan_rows:
        affected = df.loc[df["budget_gbp"].isna(), "force"].tolist()
        raise ValueError(
            f"Grant CSV: {nan_rows} rows have non-numeric grant. "
            f"Forces affected: {affected}"
        )

    total = int(df["budget_gbp"].sum())
    if abs(total - EXPECTED_TOTAL_GBP) > TOTAL_TOLERANCE_GBP:
        raise ValueError(
            f"Grant CSV: total £{total:,} does not reconcile to "
            f"expected £{EXPECTED_TOTAL_GBP:,} (tolerance £{TOTAL_TOLERANCE_GBP})."
        )

    return dict(zip(df["force"], df["budget_gbp"].astype(float)))
