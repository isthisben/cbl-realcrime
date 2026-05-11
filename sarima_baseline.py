"""
SARIMA baseline for data.police.uk monthly crime counts.

Self-contained: walks the raw data.police.uk folder, builds a
(force, crime_type, month) panel, holds out the last 12 months,
and fits per-series auto_arima.

Outputs match the snaive script's parquet schema for direct comparison.

Requires:
    pip install polars pmdarima joblib
"""

from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import polars as pl
import pmdarima as pm
from joblib import Parallel, delayed


# ---------------------------------------------------------------------------
# 1. Panel construction (raw CSVs -> long monthly panel)
# ---------------------------------------------------------------------------

def load_street_panel(
    root: Path,
    force_allowlist: list[str] | None = None,
) -> pl.DataFrame:
    """
    Walk the data.police.uk folder structure and return a long panel:
        force | crime_type | month (date) | n_crimes

    Standard layout: root/YYYY-MM/YYYY-MM-<force>-street.csv
    """
    root = Path(root)
    files = sorted(root.glob("**/*-street.csv"))
    if not files:
        raise FileNotFoundError(f"No *-street.csv files found under {root}")

    force_slugs: set[str] | None = None
    if force_allowlist is not None:
        _suffixes = ("-constabulary", "-police-force", "-police")
        def _to_slug(name: str) -> str:
            s = name.lower().replace(" ", "-").replace("'", "")
            for suf in _suffixes:
                if s.endswith(suf):
                    s = s[: -len(suf)]
            return s
        force_slugs = {_to_slug(f) for f in force_allowlist}

    frames: list[pl.DataFrame] = []
    for fp in files:
        if force_slugs is not None:
            fn = fp.stem.lower()
            if not any(slug in fn for slug in force_slugs):
                continue
        df = pl.read_csv(
            fp,
            columns=["Month", "Falls within", "Crime type"],
            schema_overrides={
                "Month": pl.Utf8,
                "Falls within": pl.Utf8,
                "Crime type": pl.Utf8,
            },
            ignore_errors=True,
        )
        if df.height == 0:
            continue
        frames.append(df)

    raw = pl.concat(frames, how="vertical_relaxed")

    raw = (
        raw.rename({"Falls within": "force", "Crime type": "crime_type"})
        .with_columns(
            month=pl.col("Month").str.strptime(pl.Date, "%Y-%m", strict=False),
        )
        .drop_nulls(["force", "crime_type", "month"])
        .drop("Month")
    )

    panel = (
        raw.group_by(["force", "crime_type", "month"])
        .agg(n_crimes=pl.len())
        .sort(["force", "crime_type", "month"])
    )
    return panel


def complete_panel(panel: pl.DataFrame) -> pl.DataFrame:
    """
    Reindex every (force, crime_type) to a complete monthly grid.
    Adds a `missing` flag; does NOT zero-fill silently.
    """
    min_m, max_m = panel["month"].min(), panel["month"].max()
    months = pl.DataFrame(
        {"month": pl.date_range(min_m, max_m, interval="1mo", eager=True)}
    )
    keys = panel.select(["force", "crime_type"]).unique()
    grid = keys.join(months, how="cross")

    full = (
        grid.join(panel, on=["force", "crime_type", "month"], how="left")
        .with_columns(
            missing=pl.col("n_crimes").is_null(),
            n_crimes=pl.col("n_crimes").fill_null(0),
        )
        .sort(["force", "crime_type", "month"])
    )
    return full


# ---------------------------------------------------------------------------
# 2. Per-series SARIMA fit + 12-step forecast
# ---------------------------------------------------------------------------

def fit_one(
    force: str,
    ctype: str,
    months: np.ndarray,
    y: np.ndarray,
    miss: np.ndarray,
    horizon: int = 12,
    season: int = 12,
) -> dict | None:
    """
    Fit auto_arima on y[:-horizon] and forecast `horizon` steps ahead.
    Returns a dict of forecasts + per-series metrics, or None to skip.
    """
    if len(y) < 2 * season + horizon:
        return None

    train, test = y[:-horizon], y[-horizon:]
    train_miss = miss[:-horizon]
    test_months = months[-horizon:]

    if train_miss[-season:].all():
        return None
    if np.std(train) == 0:
        return None  # constant series — nothing for SARIMA to learn

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = pm.auto_arima(
                train,
                seasonal=True,
                m=season,
                d=None, D=None,
                max_p=2, max_q=2,
                max_P=1, max_Q=1,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
                with_intercept="auto",
                information_criterion="aicc",
            )
            y_hat = np.asarray(model.predict(n_periods=horizon), dtype=float)
    except Exception as e:
        return {
            "force": force, "crime_type": ctype,
            "failed": True, "error": str(e)[:200],
        }

    abs_err = np.abs(test - y_hat)
    sq_err = (test - y_hat) ** 2

    # Seasonal naïve on the actual test period (predict last season of train).
    y_snaive = train[-season:][:horizon]
    snaive_abs_err = np.abs(test - y_snaive)
    snaive_sq_err = (test - y_snaive) ** 2
    snaive_mae = float(snaive_abs_err.mean())
    snaive_rmse = float(np.sqrt(snaive_sq_err.mean()))
    rel_mae = float(abs_err.mean() / snaive_mae) if snaive_mae > 0 else None

    # MASE denominator: in-sample seasonal-naive MAE on training set.
    if len(train) > season:
        scale = np.abs(train[season:] - train[:-season]).mean()
    else:
        scale = np.nan
    mase = abs_err.mean() / scale if scale and scale > 0 else np.nan

    return {
        "force": force, "crime_type": ctype, "failed": False,
        "order": str(model.order),
        "seasonal_order": str(model.seasonal_order),
        "MAE": float(abs_err.mean()),
        "RMSE": float(np.sqrt(sq_err.mean())),
        "MASE": float(mase) if not np.isnan(mase) else None,
        "snaive_MAE": snaive_mae,
        "snaive_RMSE": snaive_rmse,
        "rel_MAE": rel_mae,
        "n_obs": int(len(y)),
        "forecasts": [
            (force, ctype, m.astype("datetime64[D]").item(), float(yt), float(yp), float(ae), float(se))
            for m, yt, yp, ae, se in zip(test_months, test, y_hat, abs_err, sq_err)
        ],
    }


# ---------------------------------------------------------------------------
# 3. Parallel driver
# ---------------------------------------------------------------------------

def sarima_holdout(
    panel: pl.DataFrame,
    horizon: int = 12,
    season: int = 12,
    n_jobs: int = -1,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Returns (forecasts, metrics, failures).
    """
    df = panel.to_pandas().sort_values(["force", "crime_type", "month"])

    series = []
    for (force, ctype), g in df.groupby(["force", "crime_type"], sort=False):
        series.append((
            force, ctype,
            g["month"].to_numpy(),
            g["n_crimes"].to_numpy(dtype=float),
            g["missing"].to_numpy(),
        ))

    print(f"Fitting SARIMA on {len(series)} series with n_jobs={n_jobs}...")
    results = Parallel(n_jobs=n_jobs, verbose=10)(
        delayed(fit_one)(f, c, m, y, miss, horizon, season)
        for f, c, m, y, miss in series
    )
    results = [r for r in results if r is not None]

    forecast_rows, metric_rows, failure_rows = [], [], []
    for r in results:
        if r["failed"]:
            failure_rows.append((r["force"], r["crime_type"], r["error"]))
            continue
        forecast_rows.extend(r["forecasts"])
        metric_rows.append((
            r["force"], r["crime_type"], r["order"], r["seasonal_order"],
            r["MAE"], r["RMSE"], r["MASE"],
            r["snaive_MAE"], r["snaive_RMSE"], r["rel_MAE"], r["n_obs"],
        ))

    forecasts = pl.DataFrame(
        forecast_rows,
        schema=["force", "crime_type", "month", "y_true", "y_pred", "abs_err", "sq_err"],
        orient="row",
    )
    metrics = pl.DataFrame(
        metric_rows,
        schema=["force", "crime_type", "order", "seasonal_order",
                "MAE", "RMSE", "MASE",
                "snaive_MAE", "snaive_RMSE", "rel_MAE", "n_obs"],
        orient="row",
    )
    failures = pl.DataFrame(
        failure_rows,
        schema=["force", "crime_type", "error"],
        orient="row",
    )
    return forecasts, metrics, failures


# ---------------------------------------------------------------------------
# 4. Aggregations
# ---------------------------------------------------------------------------

def summarise(metrics: pl.DataFrame) -> dict[str, pl.DataFrame]:
    by_type = (
        metrics.group_by("crime_type")
        .agg(
            sarima_MAE=pl.col("MAE").mean(),
            snaive_MAE=pl.col("snaive_MAE").mean(),
            rel_MAE=pl.col("rel_MAE").median(),
            MASE=pl.col("MASE").median(),
            n_series=pl.len(),
        )
        .sort("rel_MAE", nulls_last=True)
    )
    overall = metrics.select(
        sarima_MAE=pl.col("MAE").mean(),
        snaive_MAE=pl.col("snaive_MAE").mean(),
        rel_MAE_median=pl.col("rel_MAE").median(),
        MASE_median=pl.col("MASE").median(),
        n_series=pl.len(),
    )
    return {"by_crime_type": by_type, "overall": overall}


# ---------------------------------------------------------------------------
# 5. Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    DATA_ROOT = Path(r"c:\Users\20231149\OneDrive - TU Eindhoven\Desktop\crime_data")
    OUT_DIR   = Path(r"c:\Users\20231149")

    # Discover all forces from filenames without loading any data.
    all_files = sorted(DATA_ROOT.glob("**/*-street.csv"))
    all_forces_slugs = sorted({fp.stem.rsplit("-", 1)[0].split("-", 2)[-1]
                                for fp in all_files})
    print(f"Found {len(all_forces_slugs)} force slugs in {DATA_ROOT}")

    forecast_parts, metric_parts, failure_parts = [], [], []

    for i, slug in enumerate(all_forces_slugs, 1):
        print(f"\n[{i}/{len(all_forces_slugs)}] {slug}")
        try:
            panel = load_street_panel(DATA_ROOT, force_allowlist=[slug])
            panel = complete_panel(panel)
        except Exception as e:
            print(f"  panel build failed: {e}")
            continue

        fc, mt, fa = sarima_holdout(panel, horizon=12, season=12, n_jobs=-1)
        forecast_parts.append(fc)
        metric_parts.append(mt)
        failure_parts.append(fa)
        print(f"  fit {mt.height}/{mt.height + fa.height} series")

    forecasts = pl.concat(forecast_parts, how="vertical_relaxed") if forecast_parts else pl.DataFrame()
    metrics   = pl.concat(metric_parts,   how="vertical_relaxed") if metric_parts   else pl.DataFrame()
    failures  = pl.concat(failure_parts,  how="vertical_relaxed") if failure_parts  else pl.DataFrame()

    summaries = summarise(metrics)
    n_attempted = metrics.height + failures.height
    print(f"\nFit: {metrics.height}/{n_attempted} series "
          f"({failures.height} failures, "
          f"{100 * failures.height / max(n_attempted, 1):.1f}%)")
    print("\n=== Overall ===")
    print(summaries["overall"])
    print("\n=== By crime type (sorted by rel_MAE = SARIMA/snaive, < 1 means SARIMA wins) ===")
    print(summaries["by_crime_type"])

    forecasts.write_parquet(str(OUT_DIR / "sarima_forecasts.parquet"))
    metrics.write_parquet(str(OUT_DIR / "sarima_metrics_per_series.parquet"))
    failures.write_parquet(str(OUT_DIR / "sarima_failures.parquet"))