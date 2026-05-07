"""
Police Resource Allocation Dashboard
TU/e 4CBLW020 — Real-World Crime project

Three components:
  1. Choropleth map of allocation gap (officer share - harm share) per force
  2. Radar chart: crime profile of selected force vs national average
  3. Toggle: flat 182 violence weight vs subcategorised CCHI per force

Run with:  python app.py
Then open: http://127.0.0.1:8050
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, dcc, html, no_update
import plotly.graph_objects as go

import data
import geo


# ---------------------------------------------------------------------------
# Load data once at startup
# ---------------------------------------------------------------------------
DF              = data.build_dataset()
NATIONAL_PROFILE = data.national_crime_profile(DF)
PFA_GEOJSON     = geo.get_pfa_geojson()

DEFAULT_FORCE = "Metropolitan Police"


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def build_map(scenario: str, selected_force: str | None) -> go.Figure:
    """
    Choropleth coloured by allocation gap.

    scenario: "flat" or "sub" — which weighting to use.
    selected_force: outline this force more heavily.
    """
    gap_col = f"allocation_gap_{scenario}"
    harm_col = f"harm_share_pct_{scenario}"

    # Cap the colour scale at ±3 percentage points. The Met sits around
    # -12pp under the subcategorised scenario and would otherwise dominate
    # the scale, leaving every other force looking nearly white. With a
    # tighter cap the Met saturates at full red and the rest of the country
    # shows a useful gradient. The hover always shows the true value.
    cmax = 3.0

    custom = list(zip(
        DF["force"],
        DF["actual_share_pct"].round(2),
        DF[harm_col].round(2),
        DF[gap_col].round(2),
        DF["officer_fte"],
        DF["weighted_violence_cchi"].round(0),
    ))

    fig = go.Figure(go.Choropleth(
        geojson=PFA_GEOJSON,
        featureidkey=f"properties.{geo.NAME_FIELD}",
        locations=DF["force"],
        z=DF[gap_col],
        zmin=-cmax,
        zmax=cmax,
        colorscale=[
            [0.0, "#b2182b"],   # under-resourced
            [0.5, "#f7f7f7"],
            [1.0, "#1a9850"],   # over-resourced
        ],
        colorbar=dict(
            title=dict(text="Allocation gap<br>(% pts)", side="top"),
            thickness=14,
            len=0.7,
            x=0.92,
        ),
        marker_line_color="#666",
        marker_line_width=0.4,
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Officers: %{customdata[4]:,} FTE<br>"
            "Officer share: %{customdata[1]}%<br>"
            "Harm share: %{customdata[2]}%<br>"
            "Allocation gap: %{customdata[3]:+.2f} pp<br>"
            "Weighted violence CCHI: %{customdata[5]}"
            "<extra></extra>"
        ),
    ))

    # Highlight the selected force with a darker border
    if selected_force is not None:
        fig.add_trace(go.Choropleth(
            geojson=PFA_GEOJSON,
            featureidkey=f"properties.{geo.NAME_FIELD}",
            locations=[selected_force],
            z=[0],
            showscale=False,
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            marker_line_color="#111",
            marker_line_width=2.0,
            hoverinfo="skip",
        ))

    fig.update_geos(
        fitbounds="locations",
        visible=False,
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=620,
        dragmode=False,
    )
    return fig


def build_radar(force_name: str) -> go.Figure:
    """
    14-axis radar of the force's crime mix vs the national average.
    National average shows up as a unit circle (1.0 on every axis);
    force values are ratios of force_share / national_share.
    """
    row = DF[DF["force"] == force_name].iloc[0]
    profile = row["crime_profile"]

    # Ratios vs national average. Clipped at 2.5 so a single outlier axis
    # doesn't squash the polygon for everything else.
    theta = [data.CRIME_TYPE_SHORT[ct] for ct in data.CRIME_TYPES]
    ratios = [min(profile[ct] / NATIONAL_PROFILE[ct], 2.5) for ct in data.CRIME_TYPES]

    # Close both polygons by repeating the first point
    theta_closed  = theta + [theta[0]]
    ratios_closed = ratios + [ratios[0]]
    nat_closed    = [1.0] * (len(theta) + 1)

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=nat_closed,
        theta=theta_closed,
        name="National average",
        mode="lines",
        line=dict(color="#888", width=1, dash="dot"),
        fill="toself",
        fillcolor="rgba(160,160,160,0.18)",
        hoverinfo="skip",
    ))

    fig.add_trace(go.Scatterpolar(
        r=ratios_closed,
        theta=theta_closed,
        name=force_name,
        mode="lines+markers",
        line=dict(color="#1f3a5f", width=2),
        marker=dict(size=5, color="#1f3a5f"),
        fill="toself",
        fillcolor="rgba(31,58,95,0.25)",
        hovertemplate="<b>%{theta}</b><br>%{r:.2f}× national<extra></extra>",
    ))

    fig.update_layout(
        polar=dict(
            bgcolor="#fafafa",
            radialaxis=dict(
                visible=True,
                range=[0, 2.5],
                tickvals=[0.5, 1.0, 1.5, 2.0],
                gridcolor="#dcdcdc",
                tickfont=dict(size=9, color="#666"),
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color="#333"),
                gridcolor="#e5e5e5",
            ),
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.18,
            xanchor="center", x=0.5,
            font=dict(size=10),
        ),
        margin=dict(l=40, r=40, t=20, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        height=460,
    )
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    title="Police Allocation — Harm vs PAF",
    update_title=None,
)

app.layout = html.Div([
    html.Header([
        html.H1("Police Resource Allocation"),
        html.P([
            "Comparing current officer distribution against a harm-weighted ",
            "allocation using the Cambridge Crime Harm Index. ",
            html.Span("TU/e 4CBLW020 — mockup data", className="subtitle"),
        ]),
    ], className="app-header"),

    html.Section([
        html.Div([
            html.Div([
                html.Label("Violence weighting", className="control-label"),
                dcc.RadioItems(
                    id="scenario-toggle",
                    options=[
                        {"label": "Flat weight (182)",     "value": "flat"},
                        {"label": "Subcategorised CCHI",   "value": "sub"},
                    ],
                    value="sub",
                    className="scenario-radio",
                    inline=True,
                ),
            ], className="control-group"),

            html.Div([
                html.Label("Selected force", className="control-label"),
                dcc.Dropdown(
                    id="force-dropdown",
                    options=[{"label": f, "value": f} for f in sorted(DF["force"])],
                    value=DEFAULT_FORCE,
                    clearable=False,
                    className="force-dropdown",
                ),
            ], className="control-group"),
        ], className="control-row"),

        html.P([
            html.Span("Flat weight (182): ", className="bold"),
            "every violence/sexual offence record is given the same score "
            "(roughly the GBH starting point), regardless of whether the actual "
            "offence was a common assault or a murder. ",
            html.Span("Subcategorised CCHI: ", className="bold"),
            "each force gets its own weighted-average CCHI based on the actual "
            "mix of offences inside its violence/sexual category — common assault, "
            "GBH, rape, homicide, etc. Forces with a more severe mix score higher.",
        ], className="toggle-explainer"),
    ], className="controls"),

    html.Section([
        html.Div([
            html.Div([
                html.H2("Allocation gap by force"),
                html.Code("gap  =  officer share %  −  harm share %",
                          className="formula"),
            ], className="panel-header"),
            html.P([
                html.Span("Green", className="legend-green"),
                " = more officers than harm suggests is needed (over-resourced). ",
                html.Span("Red", className="legend-red"),
                " = fewer officers than harm suggests (under-resourced). ",
                "Click a force to update the radar chart.",
            ], className="panel-caption"),
            dcc.Graph(
                id="map-graph",
                config={"displayModeBar": False},
                clear_on_unhover=True,
            ),
        ], className="panel panel-map"),

        html.Div([
            html.H2(id="radar-title"),
            html.P(
                "Each axis is the share of crime in that category, normalised "
                "to the national average. The grey circle is the national "
                "baseline (1.0× on every axis).",
                className="panel-caption",
            ),
            dcc.Graph(id="radar-graph", config={"displayModeBar": False}),
        ], className="panel panel-radar"),
    ], className="main-grid"),

    html.Footer([
        html.P([
            "Mockup ratios for visualisation. Officer FTE figures, crime ",
            "counts, and the violence subgroup mixes are plausible but not ",
            "real — they will be replaced with the Home Office PRC tables ",
            "(Mar 2013 onwards) and Workforce tables once validation is ",
            "complete.",
        ]),
        html.P([
            "Boundaries: ONS Open Geography Portal — ",
            "Police Force Areas (December 2023) BUC.",
        ], className="data-credit"),
    ], className="app-footer"),
], className="app-container")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output("map-graph", "figure"),
    Input("scenario-toggle", "value"),
    Input("force-dropdown", "value"),
)
def update_map(scenario: str, force_name: str) -> go.Figure:
    return build_map(scenario, force_name)


@app.callback(
    Output("radar-graph", "figure"),
    Output("radar-title", "children"),
    Input("force-dropdown", "value"),
)
def update_radar(force_name: str):
    title = f"Crime profile — {force_name}"
    return build_radar(force_name), title


@app.callback(
    Output("force-dropdown", "value"),
    Input("map-graph", "clickData"),
    State("force-dropdown", "value"),
    prevent_initial_call=True,
)
def map_click_to_dropdown(click_data, current):
    """Sync the dropdown when a force is clicked on the map."""
    if not click_data:
        return no_update
    clicked = click_data["points"][0].get("location")
    if clicked and clicked != current:
        return clicked
    return no_update


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)
