"""
Generate shareable static + animated HTML assets from the dashboard data.

Outputs (written to exports/):
    comparison.html   Side-by-side maps: single CCHI per category vs
                      subgroup-weighted per force. Same colour scale,
                      single shared colourbar. Open in browser, then
                      screenshot for chat / slides / report.
    animated.html     Single map that toggles between the two scenarios.
                      Has a slider + play button. Drag the slider to flip
                      manually, or hit play to auto-transition.

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

# Match the dashboard's colour scale and cap exactly so the assets and the
# live app show the same colours.
COLORSCALE = [
    [0.0, "#b2182b"],   # under-resourced
    [0.5, "#f7f7f7"],
    [1.0, "#1a9850"],   # over-resourced
]
CMAX = 3.0

FONT_FAMILY = '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

HOVER = (
    "<b>%{customdata[0]}</b><br>"
    "Officers: %{customdata[4]:,} FTE<br>"
    "Officer share: %{customdata[1]}%<br>"
    "Harm share: %{customdata[2]}%<br>"
    "Allocation gap: %{customdata[3]:+.2f} pp<br>"
    "Weighted violence CCHI: %{customdata[5]}"
    "<extra></extra>"
)


def _customdata(df, gap_col, harm_col):
    return list(zip(
        df["force"],
        df["actual_share_pct"].round(2),
        df[harm_col].round(2),
        df[gap_col].round(2),
        df["officer_fte"],
        df["weighted_violence_cchi"].round(0),
    ))


# ---------------------------------------------------------------------------
# Asset A — side-by-side comparison
# ---------------------------------------------------------------------------

def build_comparison(df, geojson) -> go.Figure:
    """Two choropleths in one figure, sharing a colour scale."""
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "geo"}, {"type": "geo"}]],
        subplot_titles=("<b>Single CCHI per category</b>",
                        "<b>Subgroup-weighted per force</b>"),
        horizontal_spacing=0.02,
    )

    flat_custom = _customdata(df, "allocation_gap_flat", "harm_share_pct_flat")
    sub_custom  = _customdata(df, "allocation_gap_sub",  "harm_share_pct_sub")

    fig.add_trace(go.Choropleth(
        geojson=geojson,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=df["force"],
        z=df["allocation_gap_flat"],
        zmin=-CMAX, zmax=CMAX,
        colorscale=COLORSCALE,
        showscale=False,                 # hide on the left, share with right
        marker_line_color="#666",
        marker_line_width=0.4,
        customdata=flat_custom,
        hovertemplate=HOVER,
    ), row=1, col=1)

    fig.add_trace(go.Choropleth(
        geojson=geojson,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=df["force"],
        z=df["allocation_gap_sub"],
        zmin=-CMAX, zmax=CMAX,
        colorscale=COLORSCALE,
        marker_line_color="#666",
        marker_line_width=0.4,
        colorbar=dict(
            title=dict(text="Allocation gap<br>(% pts)", side="top"),
            thickness=14, len=0.62, x=1.01,
        ),
        customdata=sub_custom,
        hovertemplate=HOVER,
    ), row=1, col=2)

    fig.update_geos(fitbounds="locations", visible=False,
                    bgcolor="rgba(0,0,0,0)")

    # Lift the subplot titles a little so they don't crowd the main title.
    for ann in fig.layout.annotations[:2]:
        ann.update(font=dict(size=14, color="#1f3a5f"), y=ann.y - 0.015)

    fig.update_layout(
        title=dict(
            text=("<b>Allocation gap by force — single CCHI vs "
                  "subgroup-weighted</b><br>"
                  "<span style='font-size:12px;color:#555'>"
                  "gap = officer share % − harm share %  ·  "
                  "<span style='color:#1a9850;font-weight:600'>green</span> "
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
                text=("Same colour scale across both maps, capped at ±3 pp. "
                      "The Metropolitan Police saturates at full green under "
                      "the per-force-mix scenario (true gap ≈ +7.2 pp) — "
                      "hover any force for actual values. "
                      "<i>Crime counts: Home Office PRC 2024/25. "
                      "Officer FTE: Home Office Workforce 31 March 2025. "
                      "Harm weights: Cambridge CCHI 2026.</i>"),
                x=0.5, y=-0.06,
                xref="paper", yref="paper",
                xanchor="center", yanchor="top",
                showarrow=False,
                font=dict(size=11, color="#777"),
            ),
        ],
    )
    return fig


# ---------------------------------------------------------------------------
# Asset B — single map that animates between flat and sub
# ---------------------------------------------------------------------------

def build_animated(df, geojson) -> go.Figure:
    """Single choropleth, two frames, slider + play button to flip between them."""
    flat_custom = _customdata(df, "allocation_gap_flat", "harm_share_pct_flat")
    sub_custom  = _customdata(df, "allocation_gap_sub",  "harm_share_pct_sub")

    common = dict(
        geojson=geojson,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=df["force"],
        zmin=-CMAX, zmax=CMAX,
        colorscale=COLORSCALE,
        marker_line_color="#666",
        marker_line_width=0.4,
        colorbar=dict(
            title=dict(text="Allocation gap<br>(% pts)", side="top"),
            thickness=14, len=0.7, x=0.94,
        ),
        hovertemplate=HOVER,
    )

    # Frames hold the per-state z values + a state-specific subtitle in the
    # title block. We bake a rich HTML title so each frame visibly relabels
    # itself during the transition.
    def title_for(label):
        return (f"<b>Allocation gap by force</b><br>"
                f"<span style='font-size:13px;color:#555'>{label}</span>")

    frame_flat = go.Frame(
        name="flat",
        data=[go.Choropleth(z=df["allocation_gap_flat"],
                            customdata=flat_custom, **common)],
        layout=go.Layout(title=dict(text=title_for("Weighting: single CCHI per category"),
                                    x=0.5, xanchor="center", y=0.96)),
    )
    frame_sub = go.Frame(
        name="sub",
        data=[go.Choropleth(z=df["allocation_gap_sub"],
                            customdata=sub_custom, **common)],
        layout=go.Layout(title=dict(text=title_for("Weighting: subgroup-weighted per force"),
                                    x=0.5, xanchor="center", y=0.96)),
    )

    initial = go.Choropleth(z=df["allocation_gap_flat"],
                            customdata=flat_custom, **common)

    play_args = dict(
        frame=dict(duration=2200, redraw=True),
        transition=dict(duration=1100, easing="cubic-in-out"),
        fromcurrent=True,
        mode="immediate",
    )

    slider_args = lambda: dict(
        frame=dict(duration=1100, redraw=True),
        transition=dict(duration=700, easing="cubic-in-out"),
        mode="immediate",
    )

    fig = go.Figure(
        data=[initial],
        frames=[frame_flat, frame_sub],
        layout=go.Layout(
            title=dict(text=title_for("Weighting: single CCHI per category"),
                       x=0.5, xanchor="center", y=0.96),
            margin=dict(l=10, r=20, t=110, b=120),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(family=FONT_FAMILY, size=12, color="#222"),
            height=760, width=920,
            geo=dict(fitbounds="locations", visible=False,
                     bgcolor="rgba(0,0,0,0)"),
            updatemenus=[dict(
                type="buttons",
                showactive=False,
                direction="left",
                x=0.01, y=-0.02,
                xanchor="left", yanchor="top",
                pad=dict(t=4, r=10),
                buttons=[
                    dict(label="▶ Play", method="animate",
                         args=[None, play_args]),
                    dict(label="❚❚ Pause", method="animate",
                         args=[[None], dict(frame=dict(duration=0, redraw=False),
                                            mode="immediate",
                                            transition=dict(duration=0))]),
                ],
            )],
            sliders=[dict(
                active=0,
                x=0.16, y=-0.02, len=0.8,
                pad=dict(t=4, b=10),
                currentvalue=dict(prefix="", font=dict(size=12, color="#1f3a5f")),
                steps=[
                    dict(label="Single CCHI per category", method="animate",
                         args=[["flat"], slider_args()]),
                    dict(label="Subgroup-weighted per force", method="animate",
                         args=[["sub"], slider_args()]),
                ],
            )],
            annotations=[dict(
                text=("gap = officer share % − harm share %  ·  "
                      "drag the slider or hit play to flip between weightings  ·  "
                      "<i>Home Office PRC 2024/25 + Workforce 31 Mar 2025 + "
                      "Cambridge CCHI 2026</i>"),
                x=0.5, y=-0.18, xref="paper", yref="paper",
                xanchor="center", showarrow=False,
                font=dict(size=11, color="#777"),
            )],
        ),
    )

    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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

    anim = build_animated(df, geojson)
    anim_path = OUT_DIR / "animated.html"
    anim.write_html(
        anim_path,
        include_plotlyjs="cdn",
        config={"displayModeBar": False},
        auto_play=False,
    )
    print(f"  wrote {anim_path}")


if __name__ == "__main__":
    main()
