"""
Police Resource Allocation Dashboard
TU/e 4CBLW020 — Real-World Crime project

Components:
  1. Choropleth map of allocation gap (resource share - harm share) per force
  2. Radar chart: crime profile of selected force vs national average
  3. Toggle: single CCHI per category vs subgroup-weighted per force
  4. Toggle: budget basis (central grant £) vs officer basis (FTE)
  5. Officer function mix: selected force vs national across CIPFA POA functions
  6. Proportional reallocation: recommended change in budget £ or officer FTE

Run with:  python app.py
Then open: http://127.0.0.1:8050
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, dcc, html, no_update
import plotly.graph_objects as go

import allocation_loader
import data
import functions_loader
import geo


# ---------------------------------------------------------------------------
# Load data once at startup
# ---------------------------------------------------------------------------
DF              = data.build_dataset()
NATIONAL_PROFILE = data.national_crime_profile(DF)
PFA_GEOJSON     = geo.get_pfa_geojson()
FUNCTIONS_DF    = functions_loader.load_force_function_shares(DF["force"])
ALLOCATION_FTE    = allocation_loader.load_allocation(DF, basis="fte")
ALLOCATION_BUDGET = allocation_loader.load_allocation(DF, basis="budget")

DEFAULT_FORCE = "Metropolitan Police"
DEFAULT_BASIS = "budget"

# Welsh territorial forces. In the Police Grant Report, their Overall Total
# reflects Police Main Grant + Welsh Top-Up only — DCLG Formula Funding and
# Legacy Council Tax Grants for Welsh forces flow through the Welsh
# Government separately and are not part of the redistributable English-and-
# Welsh pool. Surfaced as a footnote on the map when basis="budget".
WELSH_FORCES = {"Dyfed-Powys", "Gwent", "North Wales", "South Wales"}


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def build_map(basis: str, scenario: str, selected_force: str | None) -> go.Figure:
    """
    Choropleth coloured by allocation gap.

    basis: "budget" or "fte" — which resource share to compare against harm.
    scenario: "flat" or "sub" — which CCHI weighting to use.
    selected_force: outline this force more heavily.
    """
    if basis == "budget":
        gap_col   = f"allocation_gap_budget_{scenario}"
        share_col = "budget_share_pct"
    else:
        gap_col   = f"allocation_gap_{scenario}"
        share_col = "actual_share_pct"
    harm_col = f"harm_share_pct_{scenario}"

    # Cap the colour scale at ±3 percentage points. The Metropolitan Police
    # sits around +7pp under the per-force-mix scenario and would otherwise
    # dominate the scale, leaving every other force looking nearly white.
    # With a tighter cap the Met saturates at full green and the rest of
    # the country shows a useful gradient. The hover always shows the true
    # value.
    cmax = 3.0

    if basis == "budget":
        custom = list(zip(
            DF["force"],
            DF[share_col].round(2),
            DF[harm_col].round(2),
            DF[gap_col].round(2),
            DF["budget"] / 1_000_000,   # display in £m
        ))
        hovertemplate = (
            "<b>%{customdata[0]}</b><br>"
            "Budget: £%{customdata[4]:,.1f}m<br>"
            "Budget share: %{customdata[1]}%<br>"
            "Harm share: %{customdata[2]}%<br>"
            "Allocation gap: %{customdata[3]:+.2f} pp"
            "<extra></extra>"
        )
    else:
        custom = list(zip(
            DF["force"],
            DF[share_col].round(2),
            DF[harm_col].round(2),
            DF[gap_col].round(2),
            DF["officer_fte"],
        ))
        hovertemplate = (
            "<b>%{customdata[0]}</b><br>"
            "Officers: %{customdata[4]:,.0f} FTE<br>"
            "Officer share: %{customdata[1]}%<br>"
            "Harm share: %{customdata[2]}%<br>"
            "Allocation gap: %{customdata[3]:+.2f} pp"
            "<extra></extra>"
        )

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
        hovertemplate=hovertemplate,
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
    13-axis radar of the force's crime mix vs the national average.
    National average shows up as a unit circle (1.0 on every axis);
    force values are ratios of force_share / national_share.
    """
    row = DF[DF["force"] == force_name].iloc[0]
    profile = row["crime_profile"]

    # Ratios vs national average. The polygon radius is clipped at 2.5 so a
    # single outlier axis doesn't squash the polygon for everything else; the
    # hover always shows the true unclipped ratio.
    theta = [data.CRIME_TYPE_SHORT[ct] for ct in data.CRIME_TYPES]
    raw_ratios = [profile[ct] / NATIONAL_PROFILE[ct] if NATIONAL_PROFILE[ct] > 0 else 0.0
                  for ct in data.CRIME_TYPES]
    ratios = [min(r, 2.5) for r in raw_ratios]

    # Close both polygons by repeating the first point
    theta_closed   = theta + [theta[0]]
    ratios_closed  = ratios + [ratios[0]]
    raw_closed     = raw_ratios + [raw_ratios[0]]
    nat_closed     = [1.0] * (len(theta) + 1)

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
        customdata=raw_closed,
        name=force_name,
        mode="lines+markers",
        line=dict(color="#1f3a5f", width=2),
        marker=dict(size=5, color="#1f3a5f"),
        fill="toself",
        fillcolor="rgba(31,58,95,0.25)",
        hovertemplate="<b>%{theta}</b><br>%{customdata:.2f}× national<extra></extra>",
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


def build_functions(force_name: str) -> go.Figure:
    """
    Horizontal grouped bar of the selected force's officer-function mix
    against the national average, across the 12 wider CIPFA POA functions.

    Grouped (not stacked) bars: comparing one segment between a force and
    the national split is the whole point here, and segments are far easier
    to read side by side than stacked. The force bar carries the difference
    from national in its hover so over-/under-investment reads at a glance.
    """
    row = FUNCTIONS_DF.loc[force_name]

    # FUNCTIONS is ordered largest-share-first; horizontal bars stack from
    # the bottom up, so reverse to put the biggest function at the top.
    cats       = list(reversed(functions_loader.FUNCTIONS))
    force_vals = [row[c] for c in cats]
    nat_vals   = [functions_loader.NATIONAL_SHARES[c] for c in cats]
    force_custom = [(n, f - n) for f, n in zip(force_vals, nat_vals)]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=cats, x=force_vals,
        orientation="h",
        name=force_name,
        marker_color="#1f3a5f",
        customdata=force_custom,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "This force: %{x:.1f}%<br>"
            "National: %{customdata[0]:.1f}%<br>"
            "Difference: %{customdata[1]:+.1f} pp"
            "<extra></extra>"
        ),
    ))

    fig.add_trace(go.Bar(
        y=cats, x=nat_vals,
        orientation="h",
        name="National average",
        marker_color="#c7ccd1",
        hovertemplate="<b>%{y}</b><br>National: %{x:.1f}%<extra></extra>",
    ))

    fig.update_layout(
        barmode="group",
        bargap=0.22,
        bargroupgap=0.06,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=10),
        ),
        margin=dict(l=10, r=20, t=28, b=34),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=460,
        xaxis=dict(
            title=dict(text="Share of officers (%)", font=dict(size=11)),
            ticksuffix="%",
            gridcolor="#eef0f2",
            zeroline=False,
        ),
        yaxis=dict(automargin=True, tickfont=dict(size=10, color="#333")),
        font=dict(size=11),
    )
    return fig


def build_allocation(basis: str) -> go.Figure:
    """
    Diverging horizontal bars: recommended change per force under the
    proportional (harm-share) reallocation — Option B from
    allocation_loader.

    basis: "budget" plots £m, "fte" plots officer FTE.

    Colours match the map so a force keeps one colour story across the
    dashboard: green = over-resourced (harm share below current share, so the
    model recommends fewer resources — bar points left); red = under-resourced
    (recommends more — points right).

    The x-axis is capped so the Metropolitan Police (which sits well past
    both caps under either basis — the same outlier the map caps for) doesn't
    flatten everything else. The Met bar is truncated and called out, and
    every value is exact on hover.
    """
    if basis == "budget":
        alloc  = ALLOCATION_BUDGET.sort_values("difference")   # most shed first
        forces = alloc.index.tolist()
        # Plot in £ millions so the axis numbers stay legible.
        diffs_plot   = (alloc["difference"]  / 1_000_000).tolist()
        current_plot = (alloc["current"]     / 1_000_000).tolist()
        rec_plot     = (alloc["recommended"] / 1_000_000).tolist()
        colors = ["#1a9850" if d < 0 else "#b2182b" for d in diffs_plot]
        custom = list(zip(current_plot, rec_plot, alloc["harm_share_pct"]))
        hovertemplate = (
            "<b>%{y}</b><br>"
            "Current: £%{customdata[0]:,.1f}m<br>"
            "Recommended: £%{customdata[1]:,.1f}m<br>"
            "Harm share: %{customdata[2]:.2f}%<br>"
            "Recommended change: £%{x:+,.1f}m"
            "<extra></extra>"
        )
        cap          = 150        # £m
        axis_title   = "Recommended change in funding (£ millions)"
        met_unit_fmt = "£{:+,.0f}m"
    else:
        alloc  = ALLOCATION_FTE.sort_values("difference")
        forces = alloc.index.tolist()
        diffs_plot   = alloc["difference"].tolist()
        current_plot = alloc["current"].tolist()
        rec_plot     = alloc["recommended"].tolist()
        colors = ["#1a9850" if d < 0 else "#b2182b" for d in diffs_plot]
        custom = list(zip(current_plot, rec_plot, alloc["harm_share_pct"]))
        hovertemplate = (
            "<b>%{y}</b><br>"
            "Current: %{customdata[0]:,.0f} FTE<br>"
            "Recommended: %{customdata[1]:,.0f} FTE<br>"
            "Harm share: %{customdata[2]:.2f}%<br>"
            "Recommended change: %{x:+,.0f} FTE"
            "<extra></extra>"
        )
        cap          = 2000       # FTE
        axis_title   = "Recommended change in officers (FTE)"
        met_unit_fmt = "{:+,.0f} FTE"

    fig = go.Figure(go.Bar(
        y=forces,
        x=diffs_plot,
        orientation="h",
        marker_color=colors,
        marker_line_width=0,
        customdata=custom,
        hovertemplate=hovertemplate,
    ))

    annotations = []
    if "Metropolitan Police" in alloc.index:
        met_diff_plot = (alloc.loc["Metropolitan Police", "difference"]
                         / (1_000_000 if basis == "budget" else 1))
        if met_diff_plot < -cap:
            label = met_unit_fmt.format(met_diff_plot)
            annotations.append(dict(
                x=cap * 0.06, y="Metropolitan Police",
                xref="x", yref="y",
                text=f"◀ Metropolitan Police {label} (bar truncated)",
                xanchor="left", yanchor="middle",
                showarrow=False,
                font=dict(size=9, color="#1a9850"),
            ))

    fig.update_layout(
        margin=dict(l=10, r=20, t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=900,
        bargap=0.18,
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(size=9, color="#333"),
            automargin=True,
        ),
        xaxis=dict(
            title=dict(text=axis_title, font=dict(size=11)),
            range=[-cap, cap],
            zeroline=True, zerolinecolor="#888", zerolinewidth=1,
            gridcolor="#eef0f2",
        ),
        font=dict(size=11),
        annotations=annotations,
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
            "Comparing current funding and officer distribution against a ",
            "harm-weighted allocation using the Cambridge Crime Harm Index. ",
            html.Span("TU/e 4CBLW020", className="subtitle"),
        ]),
    ], className="app-header"),

    html.Section([
        html.Div([
            html.Div([
                html.Label("Compare allocation by", className="control-label"),
                dcc.RadioItems(
                    id="basis-toggle",
                    options=[
                        {"label": "Budget (£)",     "value": "budget"},
                        {"label": "Officers (FTE)", "value": "fte"},
                    ],
                    value=DEFAULT_BASIS,
                    className="scenario-radio",
                    inline=True,
                ),
            ], className="control-group"),

            html.Div([
                html.Label("CCHI weighting", className="control-label"),
                dcc.RadioItems(
                    id="scenario-toggle",
                    options=[
                        {"label": "Single CCHI per category",     "value": "flat"},
                        {"label": "Subgroup-weighted per force",  "value": "sub"},
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
            html.Span("Single CCHI per category: ", className="bold"),
            "every force is treated as having the national mix of subgroups "
            "within each category. One nationally-derived CCHI per category, "
            "applied identically to every force. ",
            html.Span("Subgroup-weighted per force: ", className="bold"),
            "each force's CCHI per category reflects that force's own mix of "
            "PRC Offence Subgroups — residential vs non-residential burglary, "
            "common assault vs GBH, possession vs trafficking, and so on. "
            "Forces with a more severe within-category mix score higher.",
        ], className="toggle-explainer"),

        html.Details([
            html.Summary("How the harm score is calculated"),
            html.Div([
                html.P([
                    "Per force, harm = Σ (count × CCHI) across the 23 PRC ",
                    "Offence Subgroups in scope. Each subgroup carries one ",
                    "CCHI value (in days), taken as the median of all ",
                    "Cambridge Crime Harm Index 2026 entries that fall under ",
                    "that subgroup. The 23 subgroups roll up to the 13 ",
                    "dashboard categories used on the radar."
                ]),
                html.P([
                    html.Span("Multi-subgroup categories. ", className="bold"),
                    "Five of the 13 categories have more than one PRC ",
                    "subgroup. These are where the toggle changes the picture:"
                ]),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Category"),
                        html.Th("Subgroup"),
                        html.Th("CCHI (days)"),
                    ])),
                    html.Tbody([
                        html.Tr([html.Td("Violence and sexual offences"), html.Td("Homicide"),                                   html.Td("5,475")]),
                        html.Tr([html.Td(""),                              html.Td("Rape offences"),                              html.Td("2,555")]),
                        html.Tr([html.Td(""),                              html.Td("Other sexual offences"),                      html.Td("182.25")]),
                        html.Tr([html.Td(""),                              html.Td("Violence with injury"),                       html.Td("365")]),
                        html.Tr([html.Td(""),                              html.Td("Death/serious injury — unlawful driving"),    html.Td("365")]),
                        html.Tr([html.Td(""),                              html.Td("Violence without injury"),                    html.Td("10")]),
                        html.Tr([html.Td(""),                              html.Td("Stalking and harassment"),                    html.Td("10")]),
                        html.Tr([html.Td("Burglary"),                      html.Td("Residential burglary"),                       html.Td("273.5")]),
                        html.Tr([html.Td(""),                              html.Td("Non-residential burglary"),                   html.Td("183.5")]),
                        html.Tr([html.Td("Criminal damage and arson"),     html.Td("Arson"),                                      html.Td("185")]),
                        html.Tr([html.Td(""),                              html.Td("Criminal damage"),                            html.Td("2")]),
                        html.Tr([html.Td("Drugs"),                         html.Td("Trafficking of drugs"),                       html.Td("5")]),
                        html.Tr([html.Td(""),                              html.Td("Possession of drugs"),                        html.Td("3")]),
                        html.Tr([html.Td("Robbery"),                       html.Td("Robbery of business property"),               html.Td("365")]),
                        html.Tr([html.Td(""),                              html.Td("Robbery of personal property"),               html.Td("365")]),
                    ]),
                ], className="cchi-table"),
                html.P([
                    html.Span("Single-subgroup categories. ", className="bold"),
                    "The remaining eight categories each contain one PRC ",
                    "subgroup; the subgroup CCHI is the category CCHI and ",
                    "the toggle has no effect on them. Possession of weapons "
                    "273.75, Public order 7.5, Vehicle crime 5, Other theft "
                    "2, Theft from the person 2, Bicycle theft 2, Shoplifting "
                    "1, Other crime 10."
                ]),
                html.P([
                    html.Span("Subgroup-weighted per force: ", className="bold"),
                    "for every multi-subgroup category, each force's effective ",
                    "category CCHI is the volume-weighted average of its ",
                    "subgroup CCHIs, using that force's actual subgroup share. "
                    "A force with more residential burglaries scores higher ",
                    "per offence in Burglary than a force whose burglary mix ",
                    "is mostly non-residential."
                ]),
                html.P([
                    html.Span("Single CCHI per category: ", className="bold"),
                    "the volume-weighted average is computed once nationally ",
                    "and applied identically to every force, removing the ",
                    "effect of force-level mix. The toggle compares the two: ",
                    "forces whose mix is more severe than the national average ",
                    "show a larger negative gap under the per-force-mix view ",
                    "than under the single-CCHI view."
                ]),
                html.P([
                    html.Span("Why subgroup-level, not per-offence-code: ", className="bold"),
                    "Sherman 2026 publishes CCHI scores at the offence-code ",
                    "(ATHENA URN) level, but the Police Recorded Crime PFA ",
                    "tables only publish counts at the Offence Subgroup level. "
                    "Subgroup is therefore the finest joinable granularity. ",
                    "The subgroup CCHI is the median across all Sherman URNs ",
                    "in that subgroup; choice of median over mean is robust ",
                    "to rare-but-severe offences (firearms within Possession ",
                    "of weapons, GBH-with-intent within Violence with injury) ",
                    "whose CCHIs would otherwise pull the mean far above the "
                    "typical reported offence."
                ]),
                html.P([
                    html.Span("Source files: ", className="bold"),
                    "three open-data tables, Open Government Licence ",
                    "(Home Office) and Creative Commons (Cambridge):"
                ]),
                html.Ul([
                    html.Li([
                        html.Code("prc-pfa-mar2013-onwards-tables-230426.ods"),
                        " — Police Recorded Crime, Police Force Area open ",
                        "data tables. Year ending March 2013 onwards; ",
                        "released 23 April 2026. The 2024/25 sheet ",
                        "(25,356 rows) is what the dashboard uses, summed ",
                        "across Q1–Q4 by force and Offence Subgroup."
                    ]),
                    html.Li([
                        html.Code("open-data-table-police-workforce-280126.ods"),
                        " — Police Workforce, England and Wales open data. ",
                        "Snapshots at 31 March each year, 2007–2025; ",
                        "released 28 January 2026. The dashboard uses the ",
                        "31 March 2025 snapshot, ",
                        html.Code("Worker type = \"Police Officer\""),
                        ", summed by Force name."
                    ]),
                    html.Li([
                        html.Code("Cambridge-CCHI-2026-update.xlsx"),
                        " — Cambridge Crime Harm Index, 2026 update. ",
                        "1,266 rows in the values sheet covering 786 ",
                        "distinct Home Office offence classifications. ",
                        "Cambridge Centre for Evidence-Based Policing, ",
                        "Institute of Criminology."
                    ]),
                    html.Li([
                        html.Code("police-grant-2025-26.csv"),
                        " — central government grant per force, 2025-26 ",
                        "(Home Office, Police Grant Report 2025-26). The ",
                        "'Overall Total' column from the per-force table: ",
                        "Police Main Grant + ex-DCLG Formula Funding + ",
                        "Legacy Council Tax Grants + Welsh Top-Up. £9.81 bn ",
                        "across 43 forces; council tax precept (locally ",
                        "raised, ~40 % of total force funding) is excluded ",
                        "by design."
                    ]),
                ], className="source-list"),
                html.P([
                    "Provenance for every CCHI value, sensitivity check ",
                    "against the mean, and documented limitations live in ",
                    html.Code("data/raw/CCHI_SOURCES.md"),
                    ". Full release pages and licensing in ",
                    html.Code("data/raw/SOURCES.md"),
                    "."
                ]),
            ], className="methodology-body"),
        ], className="methodology"),

        html.Details([
            html.Summary("How the budget basis works"),
            html.Div([
                html.P([
                    "The budget basis compares each force's share of the ",
                    "central government grant against its harm share, in ",
                    "place of the officer-headcount comparison. The reason: ",
                    "the evidence linking more officers to less crime is ",
                    "contested. Reallocating funding is more defensible and ",
                    "more flexible — a force can spend extra budget on ",
                    "equipment, training, specialist units, victim services, ",
                    "and so on, not only on headcount."
                ]),
                html.P([
                    html.Span("What is in the pool. ", className="bold"),
                    "The £9.81 bn national pool is the Police Grant Report ",
                    "2025-26 'Overall Total' summed across the 43 territorial ",
                    "forces: Police Main Grant, ex-DCLG Formula Funding, ",
                    "Legacy Council Tax Grants, and the Welsh Top-Up. This is ",
                    "roughly 60 % of total English-and-Welsh police funding."
                ]),
                html.P([
                    html.Span("What is excluded — and why. ", className="bold"),
                    "Council tax precept (the locally-raised portion, ~40 % ",
                    "of total funding) is excluded by design. The Home Office ",
                    "cannot redistribute precept across forces, so only the ",
                    "centrally-controlled pool can sensibly back a national ",
                    "reallocation recommendation. Pensions grants, NI ",
                    "contributions, the officer-maintenance ringfence, and the ",
                    "wider-system grants are also outside this pool — they are ",
                    "either earmarked or do not flow to PCCs as discretionary ",
                    "spend."
                ]),
                html.P([
                    html.Span("Welsh forces. ", className="bold"),
                    "Dyfed-Powys, Gwent, North Wales, and South Wales carry £0 ",
                    "in DCLG Formula Funding and Legacy Council Tax Grants — ",
                    "those streams are routed through the Welsh Government ",
                    "separately. The Police Grant Report's Overall Total for ",
                    "them therefore reflects Police Main Grant + Welsh Top-Up ",
                    "only, which makes Welsh forces appear lower than English ",
                    "peers of comparable size. Any like-for-like comparison ",
                    "should treat the four Welsh entries as a known under-count."
                ]),
                html.P([
                    html.Span("City of London. ", className="bold"),
                    "City of London is a tiny geographic force with a small ",
                    "resident population, a large daytime workforce, and a ",
                    "national specialism in fraud and financial crime. Its ",
                    "harm-share comparison is structurally distorted because ",
                    "fraud volumes are not joinable to the PRC Offence ",
                    "Subgroup totals used here; treat it as an outlier."
                ]),
                html.P([
                    html.Span("Source: ", className="bold"),
                    html.Code("data/raw/police-grant-2025-26.csv"),
                    ", a 43-row extract from the Home Office Police Grant ",
                    "Report 2025-26 'Overall Total' column. The Police Funding ",
                    "England and Wales 2015-2026 tables (",
                    html.Code("police-funding-england-and-wales-2015-to-2026-"
                              "tables.ods"),
                    ") are also in ",
                    html.Code("data/raw/"),
                    " for future historical-year work; only 2025-26 is wired ",
                    "into the dashboard for now."
                ]),
            ], className="methodology-body"),
        ], className="methodology"),
    ], className="controls"),

    html.Section([
        html.Div([
            html.Div([
                html.H2("Allocation gap by force"),
                html.Code(id="map-formula", className="formula"),
            ], className="panel-header"),
            html.P(id="map-caption", className="panel-caption"),
            html.P(id="map-footnote", className="panel-footnote"),
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

    html.Section([
        html.Div([
            html.Div(
                [html.H2(id="functions-title")]
                + ([html.Span(
                        "placeholder data",
                        className="mockup-badge",
                        title="Synthetic per-force mix — the real workforce-"
                              "functions table is not yet in data/raw/.",
                    )] if functions_loader.IS_MOCKUP else []),
                className="panel-header",
            ),
            html.P(
                ["How the selected force distributes its officers across the "
                 "wider CIPFA Police Objective Analysis functions, compared "
                 "with the national average. Click a force on the map or use "
                 "the dropdown above."]
                + ([html.Span(
                        " Per-force values are synthetic placeholders pending "
                        "the real workforce-functions data; the national split "
                        "is the published 2025 figure.",
                        className="mockup-note",
                    )] if functions_loader.IS_MOCKUP else []),
                className="panel-caption",
            ),
            dcc.Graph(id="functions-graph", config={"displayModeBar": False}),
        ], className="panel panel-functions"),
    ], className="functions-row"),

    html.Section([
        html.Div([
            html.Div(
                [html.H2(id="allocation-title"),
                 html.Span(id="allocation-badge",
                           className="baseline-badge",
                           title="Proportional reallocation (Option B). "
                                 "Real figures from the live dataset; the ILP "
                                 "optimiser output replaces this when ready.")],
                className="panel-header",
            ),
            html.P(id="allocation-caption", className="panel-caption"),
            dcc.Graph(
                id="allocation-graph",
                config={"displayModeBar": False},
            ),
        ], className="panel panel-allocation"),
    ], className="allocation-row"),

    html.Footer([
        html.P([
            "Crime counts: Home Office Police Recorded Crime, Police Force ",
            "Area open data tables (Mar 2013 onwards), released 23 April 2026. ",
            "Officer FTE: Home Office Police Workforce open data, snapshot ",
            "31 March 2025, released 28 January 2026. Central grant: Home ",
            "Office Police Grant Report 2025-26, 'Overall Total' per force. ",
            "Crime and workforce data reflect the 2024/25 financial year; the ",
            "grant figure is the 2025-26 settlement. 43 territorial forces of ",
            "England and Wales.",
        ]),
        html.P([
            "Harm weights: Cambridge Crime Harm Index, 2026 update ",
            "(Sherman, Neyroud, Neyroud — Cambridge Centre for Evidence-Based ",
            "Policing). One CCHI value per PRC Offence Subgroup, taken as the ",
            "median of all Sherman 2026 entries in that subgroup. The Sherman ",
            "formula multiplies count and weight by (1 − resolution rate); ",
            "the Home Office outcomes table only publishes per-force ",
            "breakdowns for fraud, so the resolution-rate term is dropped ",
            "here pending integration of the data.police.uk record-level ",
            "outcomes pipeline.",
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
    Input("basis-toggle", "value"),
    Input("scenario-toggle", "value"),
    Input("force-dropdown", "value"),
)
def update_map(basis: str, scenario: str, force_name: str) -> go.Figure:
    return build_map(basis, scenario, force_name)


@app.callback(
    Output("map-formula", "children"),
    Output("map-caption",  "children"),
    Output("map-footnote", "children"),
    Output("map-footnote", "style"),
    Output("allocation-graph",   "figure"),
    Output("allocation-title",   "children"),
    Output("allocation-badge",   "children"),
    Output("allocation-badge",   "style"),
    Output("allocation-caption", "children"),
    Input("basis-toggle", "value"),
)
def update_basis_dependent(basis: str):
    """Single callback for everything that changes when the basis toggle
    flips: formula text, map caption / footnote, allocation panel figure +
    title + caption + optimised-badge visibility."""
    if basis == "budget":
        alloc          = ALLOCATION_BUDGET
        is_optimised   = allocation_loader.IS_OPTIMISED_BUDGET
        national_pool  = (f"£{alloc['current'].sum() / 1_000_000_000:,.2f} bn "
                          f"in central government grant")
        formula        = "gap  =  budget share %  −  harm share %"
        resource_word  = "funding"
        cap_text       = "±£150 m"

        caption = [
            html.Span("Green", className="legend-green"),
            f" = more {resource_word} than harm suggests is needed (over-resourced). ",
            html.Span("Red",   className="legend-red"),
            f" = less {resource_word} than harm suggests (under-resourced). ",
            "Click a force to update the radar chart.",
        ]
        footnote = [
            html.Span("Notes. ", className="bold"),
            "Welsh forces (Dyfed-Powys, Gwent, North Wales, South Wales) "
            "appear lower than English peers of comparable size — their "
            "DCLG Formula Funding and Legacy Council Tax Grants flow "
            "through the Welsh Government separately and are not in the "
            "redistributable pool. City of London is a national fraud / "
            "financial-crime specialist with a tiny resident population, "
            "so its harm-share comparison is structurally distorted.",
        ]
        footnote_style = {"display": "block"}
        title = "Proportional reallocation — budget"
    else:
        alloc          = ALLOCATION_FTE
        is_optimised   = allocation_loader.IS_OPTIMISED_FTE
        national_pool  = f"{int(alloc['current'].sum()):,} officer FTE"
        formula        = "gap  =  officer share %  −  harm share %"
        resource_word  = "officers"
        cap_text       = "±2,000 FTE"

        caption = [
            html.Span("Green", className="legend-green"),
            f" = more {resource_word} than harm suggests is needed (over-resourced). ",
            html.Span("Red",   className="legend-red"),
            f" = fewer {resource_word} than harm suggests (under-resourced). ",
            "Click a force to update the radar chart.",
        ]
        footnote = []
        footnote_style = {"display": "none"}
        title = "Proportional reallocation — officers"

    badge_text  = "" if is_optimised else "proportional baseline"
    badge_style = {"display": "none"} if is_optimised else {"display": "inline-block"}

    allocation_caption = [
        f"Recommended change in {resource_word} if the national pool ",
        html.Span(f"({national_pool})", className="bold"),
        " were distributed by each force's share of harm rather than the "
        "current formula. Same colours as the map: ",
        html.Span("green", className="legend-green"),
        " = over-resourced (recommend fewer), ",
        html.Span("red", className="legend-red"),
        f" = under-resourced (recommend more). Axis capped at {cap_text}; "
        "hover for exact figures.",
    ]

    return (
        formula,
        caption,
        footnote,
        footnote_style,
        build_allocation(basis),
        title,
        badge_text,
        badge_style,
        allocation_caption,
    )


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


@app.callback(
    Output("functions-graph", "figure"),
    Output("functions-title", "children"),
    Input("force-dropdown", "value"),
)
def update_functions(force_name: str):
    title = f"Officer function mix — {force_name}"
    return build_functions(force_name), title


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)
