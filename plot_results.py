"""
Presentation-ready plots for SARIMA vs Seasonal Naïve forecasting.

Generates two PNG files:
    plot_forecasts.png   — time-series overlay (SARIMA + snaive vs actual)
    plot_metrics.png     — performance comparison charts

Requires: matplotlib, polars, numpy, pandas
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import polars as pl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import warnings

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
NAVY    = "#1B2A4A"
RED     = "#C0392B"
STEEL   = "#2471A3"
SILVER  = "#BDC3C7"
CREAM   = "#F4F6F8"
WHITE   = "#FFFFFF"
LGREY   = "#E5E8EC"

plt.rcParams.update({
    "font.family":      "sans-serif",
    "font.size":        11,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "axes.edgecolor":   NAVY,
    "axes.labelcolor":  NAVY,
    "xtick.color":      NAVY,
    "ytick.color":      NAVY,
    "figure.facecolor": WHITE,
    "axes.facecolor":   WHITE,
    "axes.grid":        True,
    "grid.color":       LGREY,
    "grid.linewidth":   0.6,
})

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
HOME          = Path(r"c:\Users\20231149")
DATA_ROOT     = Path(r"c:\Users\20231149\OneDrive - TU Eindhoven\Desktop\crime_data")
FORECASTS_PQ  = HOME / "sarima_forecasts.parquet"
METRICS_PQ    = HOME / "sarima_metrics_per_series.parquet"

# Force & crime types to highlight in the time-series plot
SHOWCASE_FORCE  = "West Yorkshire Police"
SHOWCASE_TYPES  = ["Burglary", "Theft from the person",
                   "Violence and sexual offences", "Drugs"]


# ---------------------------------------------------------------------------
# Panel loader (minimal copy from sarima_baseline.py)
# ---------------------------------------------------------------------------
def _load_panel(force_name: str) -> pl.DataFrame:
    slug_suffixes = ("-constabulary", "-police-force", "-police-service", "-police")
    def _slug(name: str) -> str:
        s = name.lower().replace(" ", "-").replace("'", "")
        for suf in slug_suffixes:
            if s.endswith(suf):
                s = s[: -len(suf)]
        return s

    slug = _slug(force_name)
    files = [fp for fp in sorted(DATA_ROOT.glob("**/*-street.csv"))
             if slug in fp.stem.lower()]
    if not files:
        raise FileNotFoundError(f"No files for slug '{slug}'")

    frames = []
    for fp in files:
        df = pl.read_csv(fp,
                         columns=["Month", "Falls within", "Crime type"],
                         schema_overrides={"Month": pl.Utf8,
                                           "Falls within": pl.Utf8,
                                           "Crime type": pl.Utf8},
                         ignore_errors=True)
        if df.height:
            frames.append(df)

    raw = (pl.concat(frames, how="vertical_relaxed")
           .rename({"Falls within": "force", "Crime type": "crime_type"})
           .with_columns(
               month=pl.col("Month").str.strptime(pl.Date, "%Y-%m", strict=False))
           .drop_nulls(["force", "crime_type", "month"])
           .drop("Month"))

    panel = (raw.group_by(["force", "crime_type", "month"])
             .agg(n_crimes=pl.len())
             .sort(["force", "crime_type", "month"]))

    min_m, max_m = panel["month"].min(), panel["month"].max()
    months_df = pl.DataFrame(
        {"month": pl.date_range(min_m, max_m, interval="1mo", eager=True)})
    keys  = panel.select(["force", "crime_type"]).unique()
    grid  = keys.join(months_df, how="cross")
    full  = (grid.join(panel, on=["force", "crime_type", "month"], how="left")
             .with_columns(n_crimes=pl.col("n_crimes").fill_null(0))
             .sort(["force", "crime_type", "month"]))
    return full


# ---------------------------------------------------------------------------
# Figure 1 — Time-series: SARIMA & snaive vs Actual
# ---------------------------------------------------------------------------
def plot_forecasts(forecasts: pl.DataFrame, panel: pl.DataFrame,
                   force: str, crime_types: list[str], out: Path,
                   layout: str = "vertical") -> None:

    fc_df = (forecasts
             .filter((pl.col("force") == force) &
                     (pl.col("crime_type").is_in(crime_types)))
             .to_pandas()
             .assign(month=lambda d: pd.to_datetime(d["month"])))

    pan_df = (panel
              .filter((pl.col("force") == force) &
                      (pl.col("crime_type").is_in(crime_types)))
              .to_pandas()
              .assign(month=lambda d: pd.to_datetime(d["month"])))

    if layout == "grid":
        fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
        axes = axes.flatten()
    else:
        fig, axes = plt.subplots(len(crime_types), 1,
                                 figsize=(13, 5 * len(crime_types)),
                                 constrained_layout=True)
    fig.suptitle(f"SARIMA vs Seasonal Naïve — {force}",
                 fontsize=15, fontweight="bold", color=NAVY)

    for ax, ctype in zip(axes, crime_types):
        hist = pan_df[pan_df["crime_type"] == ctype].sort_values("month")
        test = fc_df[fc_df["crime_type"] == ctype].sort_values("month")

        if hist.empty or test.empty:
            ax.set_visible(False)
            continue

        test_start  = test["month"].min()
        train       = hist[hist["month"] < test_start]
        snaive_pred = train["n_crimes"].values[-12:]

        # History
        ax.plot(train["month"], train["n_crimes"],
                color=NAVY, lw=1.4, alpha=0.55, label="History")
        # Actual test
        ax.plot(test["month"], test["y_true"],
                color=NAVY, lw=2.2, marker="o", ms=4, label="Actual")
        # SARIMA forecast
        ax.plot(test["month"], test["y_pred"],
                color=RED, lw=2.2, ls="--", marker="s", ms=4,
                label="SARIMA forecast")
        # Seasonal naïve forecast
        if len(snaive_pred) == len(test):
            ax.plot(test["month"], snaive_pred,
                    color=STEEL, lw=2.0, ls=":", marker="^", ms=4,
                    label="Seasonal naïve")

        # Shade test region
        ax.axvspan(test["month"].min(), test["month"].max(),
                   alpha=0.06, color=RED, lw=0)
        ax.axvline(test_start, color=SILVER, lw=1.2, ls="-")

        ax.set_title(ctype, fontsize=12, fontweight="bold", color=NAVY, pad=6)
        ax.set_xlabel("")
        ax.set_ylabel("Crime count", color=NAVY)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{int(x):,}"))
        ax.tick_params(axis="x", rotation=30)

    # Shared legend
    handles = [
        mpatches.Patch(color=NAVY,  label="Actual"),
        mpatches.Patch(color=RED,   label="SARIMA forecast"),
        mpatches.Patch(color=STEEL, label="Seasonal naïve"),
        mpatches.Patch(color=SILVER, alpha=0.4, label="Test window"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4,
               frameon=False, fontsize=10,
               bbox_to_anchor=(0.5, -0.04))

    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor=WHITE)
    print(f"Saved → {out}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2 — Performance comparison charts
# ---------------------------------------------------------------------------
def plot_metrics(metrics: pl.DataFrame, out: Path) -> None:

    by_type = (metrics.group_by("crime_type")
               .agg(rel_MAE=pl.col("rel_MAE").median())
               .sort("rel_MAE"))
    types    = by_type["crime_type"].to_list()
    rmae_t   = by_type["rel_MAE"].to_list()
    colors_t = [NAVY if v < 1 else RED for v in rmae_t]

    fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
    fig.suptitle("SARIMA vs Seasonal Naïve — Relative MAE by Crime Type",
                 fontsize=13, fontweight="bold", color=NAVY)

    bars = ax.barh(types, rmae_t, color=colors_t, edgecolor=WHITE, height=0.6)
    ax.axvline(1.0, color=SILVER, lw=1.5, ls="--")
    ax.set_xlabel("rel_MAE  (SARIMA / Seasonal Naïve)", color=NAVY)
    ax.set_xlim(0, max(rmae_t) + 0.15)
    for bar, val in zip(bars, rmae_t):
        ax.text(val + 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}", ha="left", va="center", fontsize=8.5, color=NAVY)

    ax.legend(handles=[
        mpatches.Patch(color=NAVY, label="SARIMA wins (rel_MAE < 1)"),
        mpatches.Patch(color=RED,  label="Naïve wins  (rel_MAE ≥ 1)"),
        mpatches.Patch(color=SILVER, label="Break-even"),
    ], frameon=False, fontsize=9, loc="lower center",
               bbox_to_anchor=(0.5, -0.12), ncol=3)

    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor=WHITE)
    print(f"Saved → {out}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    forecasts = pl.read_parquet(FORECASTS_PQ)
    metrics   = pl.read_parquet(METRICS_PQ)

    print(f"Loaded {forecasts.height:,} forecast rows | {metrics.height} series metrics")

    print(f"\nLoading panel for '{SHOWCASE_FORCE}' (for snaive reconstruction)...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        panel = _load_panel(SHOWCASE_FORCE)

    plot_forecasts(forecasts, panel, SHOWCASE_FORCE, SHOWCASE_TYPES,
                   out=HOME / "plot_forecasts_vertical.png")

    plot_forecasts(forecasts, panel, SHOWCASE_FORCE, SHOWCASE_TYPES,
                   out=HOME / "plot_forecasts_grid.png", layout="grid")

    plot_metrics(metrics, out=HOME / "plot_metrics.png")

    print("\nDone. Files saved to:", HOME)
