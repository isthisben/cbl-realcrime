"""
Police Resource Allocation Dashboard
TU/e 4CBLW020 — Real-World Crime project

Panels:
  1. Choropleth map of the allocation gap (resource share − harm share) per force
  2. Radar: the selected force's crime profile vs the national average
     (14 categories, including the anti-social-behaviour floor)
  3. Officer function mix: selected force vs national, across the CIPFA POA functions
  4. Reallocation: the ILP-recommended change in formula grant (£) or workforce FTE
  5. Crime forecast: the 12-month LightGBM prediction for the selected force

Controls: funding-vs-officers basis toggle, workforce-pool selector, force dropdown.

Run with:  python app.py
Then open: http://127.0.0.1:8050
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, dcc, html, no_update
import plotly.graph_objects as go

import allocation_loader
import data
import forecast_loader
import functions_loader
import geo


# ---------------------------------------------------------------------------
# Load data once at startup
# ---------------------------------------------------------------------------
DF              = data.build_dataset()
NATIONAL_PROFILE = data.national_crime_profile(DF)
PFA_GEOJSON     = geo.get_pfa_geojson()
FUNCTIONS_DF    = functions_loader.load_force_function_shares(DF["force"])
ALLOCATION_BUDGET = allocation_loader.load_allocation(DF, basis="budget")
# One reallocation table per workforce pool (plus the three combined),
# preloaded from the ILP output — small CSVs, cheap to hold in memory.
ALLOCATION_FTE = {
    pool: allocation_loader.load_allocation(DF, basis="fte", pool=pool)
    for pool in allocation_loader.POOL_KEYS + ["all"]
}
POOL_SUMMARY      = allocation_loader.pool_summary()
FORECAST_DF       = forecast_loader.load_forecast()

DEFAULT_FORCE = "Metropolitan Police"
DEFAULT_BASIS = "budget"
DEFAULT_POOL  = "all"

# Pool selector options (FTE basis): the three pools plus the combined view.
POOL_OPTIONS = (
    [{"label": "All workforce", "value": "all"}]
    + [{"label": lbl, "value": key}
       for key, (_f, lbl) in allocation_loader.POOL_META.items()]
)


# ---------------------------------------------------------------------------
# Figure builders
# ---------------------------------------------------------------------------

def build_map(basis: str, selected_force: str | None) -> go.Figure:
    """
    Choropleth coloured by allocation gap (resource share - harm share).

    basis: "budget" or "fte" — which resource share to compare against harm.
    selected_force: outline this force more heavily.
    """
    if basis == "budget":
        gap_col   = "allocation_gap_funding"
        share_col = "funding_share_pct"
    else:
        gap_col   = "allocation_gap"
        share_col = "actual_share_pct"
    harm_col = "harm_share_pct"

    # Cap the colour scale so the Metropolitan Police (the large over-resourced
    # outlier under either basis — about +6pp on funding, +7pp on officers)
    # doesn't dominate and leave every other force looking nearly white. The
    # Met saturates at full green and the rest of the country shows a useful
    # gradient; the hover always shows the true value. Funding gaps are tighter
    # than officer gaps, so the funding basis uses a tighter cap.
    cmax = 2.0 if basis == "budget" else 3.0

    if basis == "budget":
        custom = list(zip(
            DF["force"],
            DF[share_col].round(2),
            DF[harm_col].round(2),
            DF[gap_col].round(2),
            DF["total_funding"] / 1_000_000,   # display in £m
        ))
        hovertemplate = (
            "<b>%{customdata[0]}</b><br>"
            "Total funding: £%{customdata[4]:,.0f}m<br>"
            "Funding share: %{customdata[1]}%<br>"
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
            [1.0, "#2166ac"],   # over-resourced
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
    # hover always shows the true unclipped ratio. The 14th axis is the
    # anti-social-behaviour floor (forecast-derived volume).
    theta = [data.CRIME_TYPE_SHORT[ct] for ct in data.DISPLAY_CATEGORIES]
    raw_ratios = [profile[ct] / NATIONAL_PROFILE[ct] if NATIONAL_PROFILE[ct] > 0 else 0.0
                  for ct in data.DISPLAY_CATEGORIES]
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


def build_allocation(basis: str, pool: str = "all") -> go.Figure:
    """
    Diverging horizontal bars: recommended change per force under the model
    team's ILP optimiser (allocation_loader). Budget basis = formula-grant
    redistribution; FTE basis = the selected workforce pool, or all three
    combined.

    Colours match the map so a force keeps one colour story across the
    dashboard: blue = over-resourced (harm share below current share, so the
    model recommends fewer resources — bar points left); red = under-resourced
    (recommends more — points right).

    The x-axis is capped so a single large force (typically the Metropolitan
    Police) doesn't flatten everything else; any bar past the cap is truncated
    and called out, and every value is exact on hover.
    """
    if basis == "budget":
        alloc  = ALLOCATION_BUDGET.sort_values("difference")   # most shed first
        # Plot in £ millions so the axis numbers stay legible.
        diffs_plot   = (alloc["difference"]  / 1_000_000).tolist()
        current_plot = (alloc["current"]     / 1_000_000).tolist()
        rec_plot     = (alloc["recommended"] / 1_000_000).tolist()
        custom = list(zip(current_plot, rec_plot, alloc["harm_share_pct"]))
        hovertemplate = (
            "<b>%{y}</b><br>"
            "Current grant: £%{customdata[0]:,.1f}m<br>"
            "Recommended grant: £%{customdata[1]:,.1f}m<br>"
            "Harm share: %{customdata[2]:.2f}%<br>"
            "Recommended change: £%{x:+,.1f}m"
            "<extra></extra>"
        )
        cap        = 300          # £m
        axis_title = "Recommended change in formula grant (£ millions)"
        unit_fmt   = "£{:+,.0f}m"
    else:
        alloc  = ALLOCATION_FTE[pool].sort_values("difference")
        diffs_plot   = alloc["difference"].tolist()
        current_plot = alloc["current"].tolist()
        rec_plot     = alloc["recommended"].tolist()
        custom = list(zip(current_plot, rec_plot, alloc["harm_share_pct"]))
        hovertemplate = (
            "<b>%{y}</b><br>"
            "Current: %{customdata[0]:,.0f} FTE<br>"
            "Recommended: %{customdata[1]:,.0f} FTE<br>"
            "Share of harm-weighted demand: %{customdata[2]:.2f}%<br>"
            "Recommended change: %{x:+,.0f} FTE"
            "<extra></extra>"
        )
        # Dynamic cap: the second-largest absolute change (so one dominant
        # force can't flatten the rest), with a sensible floor.
        absdiff = sorted((abs(d) for d in diffs_plot), reverse=True)
        cap = max(50.0, (absdiff[1] if len(absdiff) > 1 else absdiff[0]) * 1.10)
        pool_label = ("all workforce pools" if pool == "all"
                      else allocation_loader.POOL_META[pool][1])
        axis_title = f"Recommended change in FTE — {pool_label}"
        unit_fmt   = "{:+,.0f} FTE"

    colors = ["#2166ac" if d < 0 else "#b2182b" for d in diffs_plot]
    forces = alloc.index.tolist()

    fig = go.Figure(go.Bar(
        y=forces,
        x=diffs_plot,
        orientation="h",
        marker_color=colors,
        marker_line_width=0,
        customdata=custom,
        hovertemplate=hovertemplate,
    ))

    # Truncate + annotate any force whose bar runs past the cap.
    annotations = []
    for force, d in zip(forces, diffs_plot):
        if abs(d) > cap:
            neg = d < 0
            annotations.append(dict(
                x=(cap * 0.04) * (-1 if not neg else 1),
                y=force, xref="x", yref="y",
                text=(f"◀ {force} {unit_fmt.format(d)} (truncated)" if neg
                      else f"{force} {unit_fmt.format(d)} ▶ (truncated)"),
                xanchor="left" if neg else "right",
                yanchor="middle", showarrow=False,
                font=dict(size=9, color="#2166ac" if neg else "#b2182b"),
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


def build_forecast(force_name: str) -> go.Figure:
    """
    12-month crime forecast (Mar 2026 – Feb 2027) for the selected force: total
    predicted offences per month, summed across the 14 categories (13 + ASB).
    Reads the model team's LightGBM output from data/raw/forecast_lgbm.csv.
    """
    rows   = FORECAST_DF[FORECAST_DF["force"] == force_name]
    months = sorted(rows["month"].unique())
    total_by_month = rows.groupby("month")["y_pred"].sum().reindex(months)

    fig = go.Figure(go.Scatter(
        x=list(months),
        y=list(total_by_month.values),
        mode="lines+markers",
        line=dict(color="#1f3a5f", width=2.5),
        marker=dict(size=5, color="#1f3a5f"),
        hovertemplate="<b>%{x}</b><br>Predicted recorded offences: %{y:,.0f}"
                      "<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=10, r=20, t=12, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=360,
        xaxis=dict(
            title=dict(text="Forecast month", font=dict(size=11)),
            tickfont=dict(size=10),
            gridcolor="#eef0f2",
        ),
        yaxis=dict(
            title=dict(text="Predicted recorded offences / month",
                       font=dict(size=11)),
            gridcolor="#eef0f2",
            rangemode="tozero",
            zeroline=False,
        ),
        font=dict(size=11),
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

# WSGI entrypoint for production hosting (e.g. `gunicorn app:server`). Local
# `python app.py` still serves via app.run() at the bottom of this file.
server = app.server

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
                        {"label": "Funding (£)",    "value": "budget"},
                        {"label": "Officers (FTE)", "value": "fte"},
                    ],
                    value=DEFAULT_BASIS,
                    className="scenario-radio",
                    inline=True,
                ),
            ], className="control-group"),

            html.Div([
                html.Label("Workforce pool", className="control-label"),
                dcc.RadioItems(
                    id="pool-toggle",
                    options=POOL_OPTIONS,
                    value=DEFAULT_POOL,
                    className="scenario-radio",
                    inline=True,
                ),
            ], className="control-group", id="pool-control-group"),

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
    ], className="controls-bar"),

    html.Section([
        html.P([
            html.Span("How harm is scored. ", className="bold"),
            "Each force's harm is its recorded crime weighted by the Cambridge "
            "Crime Harm Index, using the same per-force weights the model team's "
            "ILP optimiser consumed — so the map and the reallocation rest on "
            "one source. Anti-social behaviour is included at the harm floor. "
            "Full method below.",
        ], className="toggle-explainer"),

        html.Details([
            html.Summary("How the harm score is calculated"),
            html.Div([
                html.P([
                    "Per force, harm = Σ (category count × CCHI) across the 13 ",
                    "recorded-crime categories, plus an anti-social-behaviour ",
                    "floor term. Counts are Home Office Police Recorded Crime; ",
                    "each category's CCHI weight (in days) comes from the ",
                    "Cambridge Crime Harm Index 2026. This is the exact ",
                    "weighting the model team's ILP allocation consumed, read ",
                    "from the shared per-force weight file."
                ]),
                html.P([
                    html.Span("Nine categories carry one national weight. ", className="bold"),
                    "They map to a single offence severity, so the value is "
                    "identical for every force: Robbery 365, Possession of "
                    "weapons 273.75, Other crime 10, Public order 7.5, Vehicle "
                    "crime 5, Other theft 2, Theft from the person 2, Bicycle "
                    "theft 2, Shoplifting 1."
                ]),
                html.P([
                    html.Span("Four composite categories vary per force. ", className="bold"),
                    "These bundle offence subgroups of different severity, so "
                    "each force's weight is the volume-weighted average of those "
                    "subgroups under that force's own offence mix — a force with "
                    "more residential burglary, or more homicide and rape within "
                    "violence, earns a heavier weight per offence:"
                ]),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th("Composite category"),
                        html.Th("Bundles (CCHI days)"),
                        html.Th("Per-force range"),
                    ])),
                    html.Tbody([
                        html.Tr([html.Td("Violence and sexual offences"), html.Td("homicide 5,475 … harassment 10"),     html.Td("159 – 235")]),
                        html.Tr([html.Td("Burglary"),                      html.Td("residential 273.5 / non-res 183.5"), html.Td("191 – 253")]),
                        html.Tr([html.Td("Criminal damage and arson"),     html.Td("arson 185 / criminal damage 2"),     html.Td("5 – 18")]),
                        html.Tr([html.Td("Drugs"),                         html.Td("trafficking 5 / possession 3"),      html.Td("3.3 – 4.0")]),
                    ]),
                ], className="cchi-table"),
                html.P([
                    "Robbery also bundles two subgroups (business and personal), "
                    "but Cambridge scores both at 365, so its value is 365 for "
                    "every force — it does not vary. The per-force weights are "
                    "read from ",
                    html.Code("data/cchi_weights_by_force_category.csv"),
                    ", the file the model team built and ran their ILP on."
                ]),
                html.P([
                    html.Span("Anti-social behaviour — the floor. ", className="bold"),
                    "ASB is the single highest-volume category a force handles, "
                    "but it is logged as incidents, not notifiable crime, so it "
                    "has no Cambridge CCHI score and is absent from the "
                    "recorded-crime tables. To represent it without distorting a "
                    "harm total dominated by violence and burglary, it is set at "
                    "the harm floor — CCHI = 1, the value Cambridge gives the "
                    "lowest notifiable offence (shoplifting). ASB volumes are "
                    "forecast-derived (data.police.uk lineage), so it shows as a "
                    "labelled 14th radar axis and a small additive harm term "
                    "(~0.17% of national harm) — never folded silently into the "
                    "recorded figures."
                ]),
                html.P([
                    html.Span("Recorded now, forecast for allocation. ", className="bold"),
                    "The map and radar score harm on recorded crime (2024/25) — "
                    "the harm forces face today. The ILP allocation was optimised "
                    "against forecast harm (predicted next 12 months) under these "
                    "same weights, so the two track each other closely (≈0.998 "
                    "correlation on harm share) without being identical: diagnose "
                    "on actuals, optimise on the forecast."
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
                        html.Code("cchi_weights_by_force_category.csv"),
                        " — the per-force CCHI weight per category, derived "
                        "from the Cambridge index above. Nine categories carry "
                        "one national value; four composite categories carry a "
                        "volume-weighted per-force value. The shared file the "
                        "model team optimised against."
                    ]),
                    html.Li([
                        html.Code("police-grant-2025-26.csv"),
                        " — redistributable formula grant per force, 2025-26 ",
                        "(Home Office, Police Grant Report 2025-26). The ",
                        "'Overall Total' column: Police Main Grant + ex-DCLG ",
                        "Formula Funding + Legacy Council Tax Grants + Welsh ",
                        "Top-Up. £9.23 bn across 42 forces — the pool the ",
                        "reallocation moves."
                    ]),
                    html.Li([
                        html.Code("police-funding-england-and-wales-2015-to-"
                                  "2026-tables.ods"),
                        " — total funding per force, 2025-26 (Home Office, ",
                        "Police Funding Statistics, Table 4a). Government ",
                        "Funding + council-tax precept + ring-fenced specific ",
                        "grants = £16.69 bn across 42 forces. The allocation ",
                        "gap is measured on this total; precept (£5.84 bn) and ",
                        "specific grants are held fixed when reallocating."
                    ]),
                    html.Li([
                        html.Code("forecast_lgbm.csv"),
                        " — the model team's LightGBM 12-month crime forecast, "
                        "per force and category (incl. anti-social behaviour). "
                        "The predict layer; also the source of the ASB volumes."
                    ]),
                    html.Li([
                        html.Code("ilp/*_allocation_results.csv"),
                        ", ",
                        html.Code("ilp/grant_redistribution_result.csv"),
                        " — the team's ILP optimiser outputs: workforce "
                        "reallocation across three pools (patrol, investigators, "
                        "PCSOs) and formula-grant redistribution, each optimised "
                        "against forecast harm under the weights above."
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
            html.Summary("How the funding basis works"),
            html.Div([
                html.P([
                    "The funding basis compares each force's share of its ",
                    "total funding against its harm share, in place of the ",
                    "officer-headcount comparison. The reason: the evidence ",
                    "linking more officers to less crime is contested. ",
                    "Reallocating funding is more defensible and more flexible ",
                    "— a force can spend on equipment, training, specialist ",
                    "units, victim services, and so on, not only on headcount."
                ]),
                html.P([
                    html.Span("What the gap measures. ", className="bold"),
                    "Total funding is government grant + council-tax precept + "
                    "ring-fenced specific grants (£16.69 bn across the 42 "
                    "forces). Comparing each force's share of that against its "
                    "harm share answers the natural question — is a force "
                    "resourced in line with the harm it faces — and counts "
                    "money a force actually has, including locally-raised "
                    "precept."
                ]),
                html.P([
                    html.Span("What actually moves. ", className="bold"),
                    "Only the redistributable formula grant — the Police Grant "
                    "Report 'Overall Total' — can be reallocated. The "
                    "reallocation shown is the model team's ILP optimiser "
                    "solution: it moves each force's grant toward its harm "
                    "share, holding precept and specific grants fixed and never "
                    "cutting a grant below £0 (a force cannot hand back precept), "
                    "and the freed grant goes to under-resourced forces. The "
                    "grant model covers 41 forces — City of London is excluded "
                    "(see below)."
                ]),
                html.P([
                    html.Span("Why precept stays fixed. ", className="bold"),
                    "Council-tax precept (locally raised by each PCC, £5.84 bn ",
                    "across the 42 forces) is set locally and cannot be redistributed by ",
                    "the Home Office. It still counts toward a force's total ",
                    "funding in the gap, but the model never moves it — so a ",
                    "force that funds itself heavily through precept is shown ",
                    "as already-resourced rather than as needing more grant."
                ]),
                html.P([
                    html.Span("Welsh forces. ", className="bold"),
                    "Dyfed-Powys, Gwent, North Wales, and South Wales receive ",
                    "DCLG Formula Funding and Legacy Council Tax Grants via the ",
                    "Welsh Government, outside the Police Grant Report. The ",
                    "total-funding figures (Table 4a) include that Welsh-routed ",
                    "money, so the four Welsh forces now compare like-for-like ",
                    "with English peers — the under-count that affected the ",
                    "old grant-only basis is resolved."
                ]),
                html.P([
                    html.Span("City of London. ", className="bold"),
                    "City of London is a tiny geographic force with a small ",
                    "resident population, a large daytime workforce, and a ",
                    "national specialism in fraud and financial crime. Its ",
                    "harm-share comparison is structurally distorted because ",
                    "fraud volumes are not joinable to the PRC Offence ",
                    "Subgroup totals used here, so it is funded far above its ",
                    "joinable harm and its grant floors to £0 under ",
                    "reallocation; treat it as an outlier."
                ]),
                html.P([
                    html.Span("Sources: ", className="bold"),
                    html.Code("police-grant-2025-26.csv"),
                    " (formula grant, Police Grant Report 2025-26) for the ",
                    "redistributable pool, and ",
                    html.Code("police-funding-england-and-wales-2015-to-2026-"
                              "tables.ods"),
                    " Table 4a (Police Funding Statistics) for each force's ",
                    "precept and total funding. Full release pages and ",
                    "licensing in ",
                    html.Code("data/raw/SOURCES.md"),
                    "."
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
                "baseline (1.0× on every axis). The 14th axis, ASB (floor), is "
                "the forecast-derived anti-social-behaviour volume.",
                className="panel-caption",
            ),
            dcc.Graph(id="radar-graph", config={"displayModeBar": False}),
        ], className="panel panel-radar"),
    ], className="main-grid"),

    html.Section([
        html.Div([
            html.Div([html.H2(id="functions-title")], className="panel-header"),
            html.P(
                "How the selected force distributes its officers across the "
                "wider CIPFA Police Objective Analysis functions, compared "
                "with the national average. Click a force on the map or use "
                "the dropdown above.",
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
                           title="The model team's ILP optimiser output "
                                 "(data/raw/ilp/). Falls back to a proportional "
                                 "baseline only if those files are absent.")],
                className="panel-header",
            ),
            html.P(id="allocation-caption", className="panel-caption"),
            dcc.Graph(
                id="allocation-graph",
                config={"displayModeBar": False},
            ),
        ], className="panel panel-allocation"),
    ], className="allocation-row"),

    html.Section([
        html.Div([
            html.Div([html.H2(id="forecast-title")], className="panel-header"),
            html.P(
                f"12-month {forecast_loader.MODEL_NAME} forecast (Mar 2026 – "
                "Feb 2027) of total predicted offences for the selected force, "
                "summed across the 14 categories (13 recorded + anti-social "
                "behaviour). Use the dropdown or click a force on the map.",
                className="panel-caption",
            ),
            dcc.Graph(id="forecast-graph", config={"displayModeBar": False}),
        ], className="panel panel-forecast"),
    ], className="forecast-row"),

    html.Footer([
        html.P([
            "Crime counts: Home Office Police Recorded Crime, Police Force ",
            "Area open data tables (Mar 2013 onwards), released 23 April 2026. ",
            "Officer FTE: Home Office Police Workforce open data, snapshot ",
            "31 March 2025, released 28 January 2026. Central grant: Home ",
            "Office Police Grant Report 2025-26, 'Overall Total' per force. ",
            "Crime and workforce data reflect the 2024/25 financial year; the ",
            "grant figure is the 2025-26 settlement. 42 territorial forces of ",
            "England and Wales (Greater Manchester is excluded — absent from ",
            "the model outputs).",
        ]),
        html.P([
            "Harm weights: Cambridge Crime Harm Index, 2026 update ",
            "(Sherman, Neyroud, Neyroud — Cambridge Centre for Evidence-Based ",
            "Policing). One CCHI value per force and category — nine national, "
            "four volume-weighted per force — the shared weights the model "
            "team's ILP consumed. Anti-social behaviour is included at the harm "
            "floor (CCHI 1) on forecast-derived volumes. The Sherman formula "
            "multiplies count and weight by (1 − resolution rate); the Home "
            "Office outcomes table only publishes per-force breakdowns for "
            "fraud, so the resolution-rate term is dropped here. Forecast: "
            "model team's LightGBM, 12-month horizon. Allocation: model team's "
            "ILP optimiser (workforce pools + formula grant).",
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
    Input("force-dropdown", "value"),
)
def update_map(basis: str, force_name: str) -> go.Figure:
    return build_map(basis, force_name)


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
    Output("pool-control-group", "style"),
    Input("basis-toggle", "value"),
    Input("pool-toggle",  "value"),
)
def update_basis_dependent(basis: str, pool: str):
    """Everything that changes with the basis (and, on the FTE basis, the
    workforce pool): map formula / caption / footnote, the allocation panel
    figure + title + caption + badge, and the pool selector's visibility."""
    if basis == "budget":
        is_optimised = allocation_loader.IS_OPTIMISED_BUDGET
        national_pool = (f"£{ALLOCATION_BUDGET['current'].sum() / 1e9:,.2f} bn "
                         f"formula grant, 41 forces")
        formula = "gap  =  total funding share %  −  harm share %"

        caption = [
            html.Span("Blue", className="legend-blue"),
            " = more funding than harm suggests is needed (over-resourced). ",
            html.Span("Red",   className="legend-red"),
            " = less funding than harm suggests (under-resourced). ",
            "Total funding = government grant + precept + specific grants. "
            "Click a force to update the radar chart.",
        ]
        footnote = [
            html.Span("Notes. ", className="bold"),
            "The gap compares each force's share of total funding (grant + "
            "council-tax precept + ring-fenced specific grants) with its share "
            "of harm. City of London is a national fraud / financial-crime "
            "specialist with a tiny resident population, so it is funded far "
            "above its joinable-harm share and sits outside the team's grant "
            "model — treat it as an outlier.",
        ]
        footnote_style = {"display": "block"}
        title = "Grant reallocation — ILP optimiser"
        pool_style = {"display": "none"}

        allocation_caption = [
            "ILP-optimised change in formula grant ",
            html.Span(f"({national_pool})", className="bold"),
            " so each force's total funding moves toward its share of harm. "
            "Precept and specific grants are held fixed, so only the grant "
            "moves — a force funded above its harm share has its grant cut (to "
            "£0 at most). Same colours as the map: ",
            html.Span("blue", className="legend-blue"),
            " = over-resourced (recommend less grant), ",
            html.Span("red", className="legend-red"),
            " = under-resourced (recommend more). The Metropolitan Police bar "
            "is truncated; hover for exact figures.",
        ]
    else:
        is_optimised = allocation_loader.IS_OPTIMISED_FTE
        alloc = ALLOCATION_FTE[pool]
        pool_label = ("all workforce pools" if pool == "all"
                      else allocation_loader.POOL_META[pool][1])
        national_pool = f"{int(round(alloc['current'].sum())):,} FTE"
        formula = "gap  =  officer share %  −  harm share %"

        caption = [
            html.Span("Blue", className="legend-blue"),
            " = more officers than harm suggests is needed (over-resourced). ",
            html.Span("Red",   className="legend-red"),
            " = fewer officers than harm suggests (under-resourced). ",
            "The map gap uses warranted-officer headcount; the reallocation "
            "below optimises the selected workforce pool. Click a force to "
            "update the radar chart.",
        ]
        footnote = []
        footnote_style = {"display": "none"}
        title = f"Workforce reallocation — {pool_label} (ILP)"
        pool_style = {}

        allocation_caption = [
            "ILP-optimised change in ",
            html.Span(f"{pool_label} ({national_pool})", className="bold"),
            ", allocated by each force's share of forecast harm-weighted "
            "demand. Each pool's national total is conserved. Same colours as "
            "the map: ",
            html.Span("blue", className="legend-blue"),
            " = over-resourced (recommend fewer), ",
            html.Span("red", className="legend-red"),
            " = under-resourced (recommend more). Large outliers are truncated; "
            "hover for exact figures.",
        ]

    badge_text  = "ILP-optimised" if is_optimised else "baseline (ILP pending)"
    badge_style = {"display": "inline-block"}

    return (
        formula,
        caption,
        footnote,
        footnote_style,
        build_allocation(basis, pool),
        title,
        badge_text,
        badge_style,
        allocation_caption,
        pool_style,
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


@app.callback(
    Output("forecast-graph", "figure"),
    Output("forecast-title", "children"),
    Input("force-dropdown", "value"),
)
def update_forecast(force_name: str):
    title = f"Crime forecast — {force_name}"
    return build_forecast(force_name), title


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=8050)
