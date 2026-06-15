"""
Generate a shareable static comparison map from the dashboard data.

Output (written to exports/):
    comparison.html   Side-by-side maps of the allocation gap under the two
                      bases the dashboard offers — officer (headcount) vs
                      total funding — on one shared colour scale. Open in a
                      browser, then screenshot for chat / slides / report.

Both maps use the same per-force CCHI harm weighting; the left compares officer
share to harm share, the right compares total-funding share to harm share.

Re-run any time the dashboard data changes:
    python build_assets.py
"""

from __future__ import annotations

import pathlib

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data
import geo


OUT_DIR = pathlib.Path(__file__).parent / "exports"

# Match the dashboard's colour scale and cap so the assets and the live app
# show the same colours.
COLORSCALE = [
    [0.0, "#b2182b"],   # under-resourced
    [0.5, "#f7f7f7"],
    [1.0, "#2166ac"],   # over-resourced
]
CMAX = 3.0

FONT_FAMILY = '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

HOVER_OFFICER = (
    "<b>%{customdata[0]}</b><br>"
    "Officers: %{customdata[4]:,.0f} FTE<br>"
    "Officer share: %{customdata[1]}%<br>"
    "Harm share: %{customdata[2]}%<br>"
    "Allocation gap: %{customdata[3]:+.2f} pp"
    "<extra></extra>"
)
HOVER_FUNDING = (
    "<b>%{customdata[0]}</b><br>"
    "Total funding: £%{customdata[4]:,.0f}m<br>"
    "Funding share: %{customdata[1]}%<br>"
    "Harm share: %{customdata[2]}%<br>"
    "Allocation gap: %{customdata[3]:+.2f} pp"
    "<extra></extra>"
)


def _customdata(df, share_col, gap_col, resource):
    return list(zip(
        df["force"],
        df[share_col].round(2),
        df["harm_share_pct"].round(2),
        df[gap_col].round(2),
        resource,
    ))


def build_comparison(df, geojson) -> go.Figure:
    """Two choropleths in one figure (officer vs funding basis), shared scale."""
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "geo"}, {"type": "geo"}]],
        subplot_titles=("<b>Officer (headcount) basis</b>",
                        "<b>Total-funding basis</b>"),
        horizontal_spacing=0.02,
    )

    officer_custom = _customdata(df, "actual_share_pct", "allocation_gap",
                                 df["officer_fte"])
    funding_custom = _customdata(df, "funding_share_pct", "allocation_gap_funding",
                                 df["total_funding"] / 1_000_000)

    fig.add_trace(go.Choropleth(
        geojson=geojson,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=df["force"],
        z=df["allocation_gap"],
        zmin=-CMAX, zmax=CMAX,
        colorscale=COLORSCALE,
        showscale=False,                 # hide on the left, share with right
        marker_line_color="#666",
        marker_line_width=0.4,
        customdata=officer_custom,
        hovertemplate=HOVER_OFFICER,
    ), row=1, col=1)

    fig.add_trace(go.Choropleth(
        geojson=geojson,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=df["force"],
        z=df["allocation_gap_funding"],
        zmin=-CMAX, zmax=CMAX,
        colorscale=COLORSCALE,
        marker_line_color="#666",
        marker_line_width=0.4,
        colorbar=dict(
            title=dict(text="Allocation gap<br>(% pts)", side="top"),
            thickness=14, len=0.62, x=1.01,
        ),
        customdata=funding_custom,
        hovertemplate=HOVER_FUNDING,
    ), row=1, col=2)

    fig.update_geos(fitbounds="locations", visible=False,
                    bgcolor="rgba(0,0,0,0)")

    for ann in fig.layout.annotations[:2]:
        ann.update(font=dict(size=14, color="#1f3a5f"), y=ann.y - 0.015)

    fig.update_layout(
        title=dict(
            text=("<b>Allocation gap by force — officer vs total-funding "
                  "basis</b><br>"
                  "<span style='font-size:12px;color:#555'>"
                  "gap = resource share % − harm share %  ·  "
                  "<span style='color:#2166ac;font-weight:600'>blue</span> "
                  "over-resourced  ·  "
                  "<span style='color:#b2182b;font-weight:600'>red</span> "
                  "under-resourced</span>"),
            x=0.5, xanchor="center", y=0.97,
        ),
        margin=dict(l=10, r=80, t=110, b=60),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family=FONT_FAMILY, size=12, color="#222"),
        height=720, width=1400,
        annotations=[
            *fig.layout.annotations,
            dict(
                text=("Same colour scale across both maps, capped at ±3 pp; "
                      "hover any force for actual values. "
                      "<i>Crime counts: Home Office PRC 2024/25. "
                      "Officer FTE: Home Office Workforce 31 March 2025. "
                      "Harm weights: per-force Cambridge CCHI 2026.</i>"),
                x=0.5, y=-0.06,
                xref="paper", yref="paper",
                xanchor="center", yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#777"),
            ),
        ],
    )
    return fig


def main():
    df = data.build_dataset()
    geojson = geo.get_pfa_geojson()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    comp = build_comparison(df, geojson)
    comp_path = OUT_DIR / "comparison.html"
    comp.write_html(
        comp_path,
        include_plotlyjs="cdn",
        config={"displayModeBar": False},
    )
    print(f"  wrote {comp_path}")


if __name__ == "__main__":
    main()
