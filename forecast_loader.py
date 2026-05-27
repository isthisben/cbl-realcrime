"""
12-month-ahead crime forecast per force x crime type — the contract the
SARIMAX model output will fill, with seeded synthetic data until it lands.

    load_forecast(forces)  ->  long DataFrame, columns:
        force, crime_type, month, y_pred
        (plus y_true, abs_err, sq_err when the real file carries them)
    IS_MOCKUP              ->  True while synthetic placeholder data is in use.

Real swap
---------
Drop the model output at `data/raw/forecast_sarimax.csv` or `.parquet` with
at least `force, crime_type, month, y_pred`. Optional validation columns
`y_true, abs_err, sq_err` are carried through when present. `crime_type`
values must be the 13 dashboard categories (`data.CRIME_TYPES`); `force`
the canonical 43; `month` a period the dashboard can parse (this mockup
emits "YYYY-MM" strings — a real datetime column is fine too).

The mockup is decoupled from the recorded-crime counts on purpose, so this
module imports cheaply (only the `data.CRIME_TYPES` constant) and plays no
part in the startup ODS parse. Magnitudes are plausible but synthetic; the
point of the stub is the schema and shape, which is why every surfaced value
must stay behind an IS_MOCKUP badge. Anchor the base levels to real PRC
volumes later if a more convincing placeholder is wanted.
"""

from __future__ import annotations

import hashlib
import math
import pathlib
import random

import pandas as pd

import data


_RAW = pathlib.Path(__file__).parent / "data" / "raw"
SOURCE_PARQUET = _RAW / "forecast_sarimax.parquet"
SOURCE_CSV     = _RAW / "forecast_sarimax.csv"

REQUIRED_COLUMNS = ["force", "crime_type", "month", "y_pred"]
OPTIONAL_COLUMNS = ["y_true", "abs_err", "sq_err"]

N_MONTHS = 12

# Rough relative monthly magnitude per category, so the synthetic series are
# not all the same size (violence dwarfs homicide, etc.). Synthetic — not a
# claim about real volumes.
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


def _seeded_rng(key: str) -> random.Random:
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return random.Random(int(digest, 16) % (2**32))


def _forecast_months() -> list[str]:
    """The next N_MONTHS calendar months as 'YYYY-MM', starting next month
    (a forecast is always forward-looking, so this tracks the clock)."""
    start = (pd.Timestamp.today().to_period("M") + 1)
    return [str(start + i) for i in range(N_MONTHS)]


def _mockup(forces: list[str]) -> pd.DataFrame:
    months = _forecast_months()
    rows = []
    for force in forces:
        for ct in data.CRIME_TYPES:
            rng   = _seeded_rng(f"{force}|{ct}")
            base  = _CATEGORY_SCALE[ct] * rng.uniform(0.4, 1.6)
            trend = rng.uniform(-0.04, 0.06)        # monthly drift
            amp   = rng.uniform(0.05, 0.20)         # seasonal amplitude
            phase = rng.uniform(0.0, 2 * math.pi)
            for i, month in enumerate(months):
                seasonal = 1.0 + amp * math.sin(2 * math.pi * i / 12 + phase)
                noise    = 1.0 + rng.gauss(0.0, 0.03)
                y = base * ((1.0 + trend) ** i) * seasonal * noise
                rows.append((force, ct, month, max(0, round(y))))

    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


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
    """Long-format 12-month forecast. Reads the model output if present, else
    returns seeded synthetic placeholder data for `forces` (defaults to the
    canonical 43 via `data` if not supplied)."""
    global IS_MOCKUP
    if SOURCE_PARQUET.exists() or SOURCE_CSV.exists():
        IS_MOCKUP = False
        return _read_real()

    IS_MOCKUP = True
    force_list = list(forces) if forces is not None else _default_forces()
    return _mockup(force_list)


def _default_forces() -> list[str]:
    """Canonical force list, derived from the live dataset only if no explicit
    list is given. Slow (triggers the ODS parse), so callers should pass
    `DF["force"]`."""
    return sorted(data.build_dataset()["force"])
