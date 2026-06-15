"""
12-month crime forecast per force x crime type — the model team's LightGBM
output, served long-format, with seeded synthetic data only as a fallback if
the file is absent.

    load_forecast(forces)  ->  long DataFrame, columns:
        force, crime_type, month, y_pred
    IS_MOCKUP              ->  True only if the real file is missing.

Real source: data/raw/forecast_lgbm.csv (force, crime_type, month, y_pred),
built from the team's `forecast_2026_03_to_2027_02.csv` by
.claude/ingest_model_outputs.py — long force names normalised to the canonical
42, covering the 13 recorded categories plus anti-social behaviour over the
forecast window March 2026 – February 2027. This is the *predict* layer of the
project's diagnose / predict / optimise story; the ILP allocation
(allocation_loader) was optimised against this exact forecast — its harm
reproduces the ILP's to a share correlation of 1.0000.

The mockup is decoupled from the recorded-crime counts on purpose, so this
module imports cheaply (only the `data.CRIME_TYPES` constant) and plays no
part in the startup ODS parse.
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import random

import pandas as pd

import data


_RAW = pathlib.Path(__file__).parent / "data" / "raw"
SOURCE_CSV     = _RAW / "forecast_lgbm.csv"
SOURCE_PARQUET = _RAW / "forecast_lgbm.parquet"

REQUIRED_COLUMNS = ["force", "crime_type", "month", "y_pred"]
OPTIONAL_COLUMNS = ["y_true", "abs_err", "sq_err"]

N_MONTHS = 12

MODEL_NAME = "LightGBM"

# Rough relative monthly magnitude per category for the fallback mockup only.
_CATEGORY_SCALE = {
    "Violence and sexual offences": 18000,
    "Public order":                  3600,
    "Criminal damage and arson":     3600,
    "Shoplifting":                   4400,
    "Other theft":                   3600,
    "Vehicle crime":                 2900,
    "Burglary":                      2000,
    "Drugs":                         1700,
    "Theft from the person":         1100,
    "Robbery":                        650,
    "Possession of weapons":          470,
    "Bicycle theft":                  460,
    "Other crime":                   1000,
}

IS_MOCKUP: bool = not (SOURCE_PARQUET.exists() or SOURCE_CSV.exists())


def _read_real() -> pd.DataFrame:
    path = SOURCE_PARQUET if SOURCE_PARQUET.exists() else SOURCE_CSV
    df = (pd.read_parquet(path) if path.suffix == ".parquet"
          else pd.read_csv(path))

    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            f"forecast_loader: {path.name} is missing required columns "
            f"{sorted(missing)}. Found {list(df.columns)}. The model must "
            f"emit at least {REQUIRED_COLUMNS}."
        )
    keep = REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in df.columns]
    return df[keep]


def load_forecast(forces: list[str] | None = None) -> pd.DataFrame:
    """Long-format 12-month forecast. Reads the LightGBM output if present,
    else returns seeded synthetic placeholder data for `forces`."""
    global IS_MOCKUP
    if SOURCE_PARQUET.exists() or SOURCE_CSV.exists():
        IS_MOCKUP = False
        return _read_real()

    IS_MOCKUP = True
    force_list = list(forces) if forces is not None else _default_forces()
    return _mockup(force_list)


def _seeded_rng(key: str) -> random.Random:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16) % (2**32))


def _forecast_months() -> list[str]:
    start = (pd.Timestamp.today().to_period("M") + 1)
    return [str(start + i) for i in range(N_MONTHS)]


def _mockup(forces: list[str]) -> pd.DataFrame:
    months = _forecast_months()
    rows = []
    for force in forces:
        for ct in data.CRIME_TYPES:
            rng   = _seeded_rng(f"{force}|{ct}")
            base  = _CATEGORY_SCALE[ct] * rng.uniform(0.4, 1.6)
            trend = rng.uniform(-0.04, 0.06)
            amp   = rng.uniform(0.05, 0.20)
            phase = rng.uniform(0.0, 2 * math.pi)
            for i, month in enumerate(months):
                seasonal = 1.0 + amp * math.sin(2 * math.pi * i / 12 + phase)
                noise    = 1.0 + rng.gauss(0.0, 0.03)
                y = base * ((1.0 + trend) ** i) * seasonal * noise
                rows.append((force, ct, month, max(0, round(y))))
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def _default_forces() -> list[str]:
    return sorted(data.build_dataset()["force"])
