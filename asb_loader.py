"""
Per-force anti-social behaviour volume, in incidents per year.

    load_force_asb_counts()  ->  {force: asb_annual_count}

ASB is not in the Home Office Police Recorded Crime tables the rest of the
dashboard counts from — it is logged as incidents, not notifiable crime — so
there is no recorded-crime figure to use. The only per-force ASB volume the
project has is the model team's 12-month forecast (data.police.uk lineage),
summed to an annual figure. The dashboard therefore treats ASB as a
forecast-derived floor category: every panel that surfaces it carries that
caveat, and it is weighted at the CCHI floor (`cchi_loader.ASB_FLOOR_CCHI`).

Source file: data/raw/asb_counts.csv  (built by .claude/ingest_model_outputs.py
from the LightGBM forecast; see data/raw/CCHI_SOURCES.md)
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "asb_counts.csv"


def load_force_asb_counts() -> dict[str, float]:
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"ASB counts file not found at {SOURCE}. "
            "Build it with .claude/ingest_model_outputs.py (forecast-derived)."
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
