"""
12-month crime forecast per force and crime type — the model team's LightGBM
output, served in long format.

    load_forecast()  ->  long DataFrame with columns force, crime_type, month, y_pred

Source: data/raw/forecast_lgbm.csv (force, crime_type, month, y_pred), normalised
from the team's forecast extract — see data/raw/SOURCES.md. It covers the 42
forces across the 13 recorded categories plus anti-social behaviour, over the
window March 2026 - February 2027.

This is the "predict" layer of the project's diagnose / predict / optimise
story; the ILP allocation (allocation_loader) was optimised against this exact
forecast.
"""

from __future__ import annotations

import pathlib

import pandas as pd


SOURCE = pathlib.Path(__file__).parent / "data" / "raw" / "forecast_lgbm.csv"

REQUIRED_COLUMNS = ["force", "crime_type", "month", "y_pred"]

MODEL_NAME = "LightGBM"


def load_forecast() -> pd.DataFrame:
    """Long-format 12-month forecast from the committed LightGBM output."""
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Forecast file not found at {SOURCE}. "
            "See data/raw/SOURCES.md for how the model outputs are produced."
        )

    df = pd.read_csv(SOURCE)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"forecast_lgbm.csv is missing columns {sorted(missing)}. "
            f"Found {list(df.columns)}."
        )
    return df[REQUIRED_COLUMNS]
