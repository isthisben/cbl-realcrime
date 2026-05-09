"""
Reads the Home Office Police Workforce open data table and returns the
police-officer FTE per territorial force at the most recent 31 March
snapshot.

    load_force_fte(year)  ->  {force_name: fte}

The source covers 44 forces (43 territorial + British Transport Police);
BTP is filtered out. Some force names differ from the dashboard canonical
list and are normalised here.

Source file: data/raw/open-data-table-police-workforce-280126.ods
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "open-data-table-police-workforce-280126.ods"

DEFAULT_SNAPSHOT_YEAR = 2025

NON_PFA_ENTRIES = {"British Transport Police"}

FORCE_NAME_FIXES = {
    "London, City of":             "City of London",
    "Hampshire and Isle of Wight": "Hampshire",
}


def load_force_fte(snapshot_year: int = DEFAULT_SNAPSHOT_YEAR) -> dict[str, float]:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Workforce source file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for the gov.uk download link."
        )

    df = pd.read_excel(SOURCE, sheet_name="Data", engine="odf")

    required = {"As at 31 March", "Force name", "Worker type", "Total (FTE)"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Workforce sheet 'Data': missing columns {missing}")

    df = df[df["As at 31 March"] == snapshot_year]
    if df.empty:
        years = sorted(pd.read_excel(SOURCE, sheet_name="Data", engine="odf")["As at 31 March"].unique())
        raise ValueError(f"Workforce: no rows for snapshot year {snapshot_year}. Available: {years}")

    df = df[df["Worker type"] == "Police Officer"]
    df = df[~df["Force name"].isin(NON_PFA_ENTRIES)].copy()
    df["Force name"] = df["Force name"].replace(FORCE_NAME_FIXES)

    df["Total (FTE)"] = pd.to_numeric(df["Total (FTE)"], errors="coerce")
    nan_rows = df["Total (FTE)"].isna().sum()
    if nan_rows:
        suppressed = df.loc[df["Total (FTE)"].isna(), "Force name"].unique().tolist()
        raise ValueError(
            f"Workforce {snapshot_year}: {nan_rows} rows have non-numeric FTE "
            f"(e.g. suppressed cells). Forces affected: {suppressed}"
        )

    fte = df.groupby("Force name")["Total (FTE)"].sum()
    return fte.to_dict()
