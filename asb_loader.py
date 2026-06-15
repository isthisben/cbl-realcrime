"""
Per-force anti-social behaviour volume, in incidents per year.

    load_force_asb_counts()  ->  {force: asb_annual_count}

ASB isn't in the Home Office Police Recorded Crime tables — it is logged as
incidents, not notifiable crime — so there is no recorded count to use. The one
per-force ASB volume the project has is the model team's 12-month forecast,
summed to an annual figure, so the dashboard treats ASB as a forecast-derived
floor category weighted at the CCHI floor (`cchi_loader.ASB_FLOOR_CCHI`).

Source file: data/raw/asb_counts.csv (forecast-derived; see data/raw/SOURCES.md).
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "asb_counts.csv"


def load_force_asb_counts() -> dict[str, float]:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"ASB counts file not found at {SOURCE}. "
            "It is forecast-derived — see data/raw/SOURCES.md."
        )
    df = pd.read_csv(SOURCE)
    required = {"force", "asb_annual_count"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{SOURCE.name}: missing columns {missing}. Found {list(df.columns)}."
        )
    df["asb_annual_count"] = pd.to_numeric(df["asb_annual_count"], errors="coerce")
    if df["asb_annual_count"].isna().any():
        bad = df.loc[df["asb_annual_count"].isna(), "force"].tolist()
        raise ValueError(f"{SOURCE.name}: non-numeric asb_annual_count for {bad}.")
    return dict(zip(df["force"], df["asb_annual_count"].astype(float)))
