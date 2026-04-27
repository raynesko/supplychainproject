"""
NJ Transit Sustainability Dashboard — FIFA 2026  (v2)
KPI-driven: CO2 Emissions, Total Cost, Lead Time, MOQ Impact.

Run:
  pip install dash plotly pandas numpy openpyxl
  python dashboard_v2.py
  Open http://127.0.0.1:8050

CHANGES FROM v1:
─────────────────────────────────────────────────────────────────────────────
  [DASH-1] DYNAMIC SIMULATION: the simulation now re-runs on every scenario
           change using scenario-specific vendor assignments.

           _build_vendor_override(ranked_vendor_names) — new helper that walks
           the scorecard ranking top-to-bottom and, for each part, picks the
           highest-ranked vendor that actually supplies it. This override dict
           is passed to simulate_procurement(vendor_override=...).

           Result: warehouse utilization, cost, CO2, and penalty KPI tiles
           all respond to pillar weight changes. Previously all four were
           frozen at their startup baseline values regardless of scenario.

  [DASH-2] BASELINE: a lightweight n=100 baseline runs at startup for the
           console printout. The callback always runs n=500.

  [DASH-3] RELATIVE-SCORING DISCLAIMER: yellow notice strip added below the
           KPI formula note. Also added as a chart annotation on the composite
           bar chart. Explains that 0=worst vendor and 100=best vendor in this
           set — raw KPI charts provide absolute context.

  [DASH-4] Social pillar label in radar and control panel updated to reflect
           the four-KPI social model (Labor, Safety/TRIR, Community,
           Transparency). Transport mode pie replaced by a grouped social KPI
           bar chart showing all four dimensions per vendor.

  [DASH-5] Stockout chart now uses the dynamic sim_df from the per-scenario
           simulation rather than the stale startup baseline.
"""

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from vendor_data_v2 import VENDORS, PARTS, WAREHOUSE
from scorecard_v2 import score_vendors
from simulation_v2 import simulate_procurement, get_best_vendor_for_part

# CHANGE [DASH-2]: lightweight baseline at startup (console info only)
_base_sim, base_util, base_cost, base_penalty, base_co2 = simulate_procurement(n_simulations=100)

app = dash.Dash(__name__, title="NJ Transit — Sustainability Dashboard")

TEAL   = "#1D9E75"; BLUE  = "#378ADD"; AMBER = "#EF9F27"
CORAL  = "#D85A30"; GRAY  = "#888780"; GREEN = "#639922"
PURPLE = "#7F77DD"; PINK  = "#D4537E"
VENDOR_COLORS = [TEAL, BLUE, AMBER, CORAL, GRAY, GREEN, PURPLE, PINK, "#BA7517", "#5DCAA5"]

card   = {"background": "white", "border": "0.5px solid #D3D1C7", "borderRadius": "12px",
          "padding": "1rem 1.25rem", "marginBottom": "12px"}
metric = {"background": "#F1EFE8", "borderRadius": "8px", "padding": "0.65rem 1rem", "textAlign": "center"}
slabel = {"marginBottom": "5px", "fontSize": "12px", "color": "#5F5E5A"}

SCENARIOS = {
    "balanced": (0.33, 0.33, 0.34),
    "green":    (0.70, 0.15, 0.15),
    "fast":     (0.20, 0.60, 0.20),
    "cheap":    (0.15, 0.70, 0.15),
}

KPI_NOTE = html.Div(
    style={"background": "#E8F4FD", "borderRadius": "8px", "padding": "0.5rem 0.85rem",
           "marginBottom": "8px", "fontSize": "11px", "color": "#2C5F8A", "lineHeight": "1.6"},
    children=[
        html.Strong("KPI Formulas — "),
        "① CO₂ = CO₂/kg × Weight × Qty  ·  "
        "② Total Cost = (Price × Qty) + (Ship/kg × Weight × Qty) + In-Transit  ·  "
        "③ Lead Time (days)  ·  ④ MOQ Impact = MOQ ÷ Qty  ·  ",
        html.Strong("Monte Carlo: "),
        "500 simulations · 90-day FIFA window · reorder point = 30 days",
    ]
)

# CHANGE [DASH-3]: relative-scoring disclaimer
RELATIVE_NOTE = html.Div(
    style={"background": "#FFF9E6", "border": "1px solid #F0D080", "borderRadius": "8px",
           "padding": "0.45rem 0.85rem", "marginBottom": "12px",
           "fontSize": "11px", "color": "#7A5C00", "lineHeight": "1.7"},
    children=[
        html.Strong("⚠ Scorecard is relative, not absolute. "),
        "normalize() always maps the worst vendor to 0 and the best to 100, "
        "regardless of how large or small the real-unit gaps are between them. "
        "Rankings are meaningful; score gaps are not proportional to actual KPI differences. "
        "Use the raw KPI bar charts below for absolute comparisons.",
    ]
)

available_m3 = (
    WAREHOUSE["total_capacity_m3"]
    - WAREHOUSE["current_used_m3"]
    - WAREHOUSE["fifa_reserved_m3"]
)

app.layout = html.Div(
    style={"fontFamily": "system-ui,sans-serif", "maxWidth": "1140px", "margin": "0 auto", "padding": "1.5rem"},
    children=[
        html.Div(style={"borderBottom": f"2px solid {TEAL}", "paddingBottom": "0.75rem", "marginBottom": "1rem"},
                 children=[
            html.Div(style={"display": "flex", "justifyContent": "space-between",
                            "alignItems": "center", "flexWrap": "wrap", "gap": "8px"}, children=[
                html.H1("NJ Transit — Vendor Sustainability Dashboard",
                        style={"fontSize": "18px", "fontWeight": "500", "margin": 0}),
                html.Div(style={"display": "flex", "gap": "6px"}, children=[
                    html.Span("FIFA 2026", style={"background": "#E1F5EE", "color": "#0F6E56",
                              "fontSize": "11px", "fontWeight": "500", "padding": "3px 10px", "borderRadius": "20px"}),
                    html.Span("10 vendors · 8 parts", style={"background": "#F1EFE8", "color": "#5F5E5A",
                              "fontSize": "11px", "padding": "3px 10px", "borderRadius": "20px"}),
                ]),
            ]),
            html.P("Select a scenario to reweight sustainability pillars — simulation re-runs and all KPI tiles update live.",
                   style={"fontSize": "13px", "color": "#888780", "margin": "4px 0 0"}),
        ]),

        KPI_NOTE,
        RELATIVE_NOTE,  # CHANGE [DASH-3]

        html.Div(style={"display": "grid", "gridTemplateColumns": "0.9fr 1fr",
                        "gap": "12px", "marginBottom": "12px"}, children=[
            html.Div(style=card, children=[
                html.P("Scenario preset", style={**slabel, "fontWeight": "500", "fontSize": "13px"}),
                dcc.RadioItems(
                    id="scenario",
                    options=[
                        {"label": "  Balanced (33 / 33 / 34)",              "value": "balanced"},
                        {"label": "  Lowest carbon — KPI 1 (70/15/15)",     "value": "green"},
                        {"label": "  Fastest lead time — KPI 3 (20/60/20)", "value": "fast"},
                        {"label": "  Lowest cost — KPI 2 (15/70/15)",       "value": "cheap"},
                    ],
                    value="balanced",
                    labelStyle={"display": "block", "marginBottom": "12px", "fontSize": "13px", "cursor": "pointer"},
                ),
                # CHANGE [DASH-4]: updated social pillar description
                html.Div(style={"marginTop": "12px", "fontSize": "11px", "color": "#888780", "lineHeight": "1.7"},
                         children=[
                    html.Strong("Pillars: "),
                    "Env = CO₂ (70%) + On-time (30%)  ·  ",
                    "Econ = Cost (45%) + MOQ (20%) + Carrying (20%) + Penalty (15%)  ·  ",
                    "Social = Labor (30%) + Safety/TRIR↓ (30%) + Community (25%) + Transparency (15%) + Domestic bonus",
                ]),
            ]),

            html.Div(style={"display": "flex", "flexDirection": "column", "gap": "8px"}, children=[
                html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}, children=[
                    html.Div(style=metric, children=[
                        html.P("Warehouse utilization", style={"fontSize": "11px", "color": "#5F5E5A", "margin": 0}),
                        html.P(id="kpi-util", style={"fontSize": "24px", "fontWeight": "500", "margin": 0}),
                        html.P(f"of {WAREHOUSE['total_capacity_m3']:,} m³ total",
                               style={"fontSize": "10px", "color": "#888780", "margin": 0}),
                    ]),
                    html.Div(style=metric, children=[
                        html.P("KPI 2 · Procurement cost", style={"fontSize": "11px", "color": "#5F5E5A", "margin": 0}),
                        html.P(id="kpi-cost", style={"fontSize": "24px", "fontWeight": "500", "margin": 0}),
                        html.P("90-day horizon (Monte Carlo)", style={"fontSize": "10px", "color": "#888780", "margin": 0}),
                    ]),
                ]),
                html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"}, children=[
                    html.Div(style=metric, children=[
                        html.P("KPI 1 · CO₂ emissions", style={"fontSize": "11px", "color": "#5F5E5A", "margin": 0}),
                        html.P(id="kpi-co2", style={"fontSize": "24px", "fontWeight": "500", "margin": 0, "color": GREEN}),
                        html.P("assigned vendors only", style={"fontSize": "10px", "color": "#888780", "margin": 0}),
                    ]),
                    html.Div(style=metric, children=[
                        html.P("Penalty exposure (Monte Carlo)", style={"fontSize": "11px", "color": "#5F5E5A", "margin": 0}),
                        html.P(id="kpi-penalty", style={"fontSize": "24px", "fontWeight": "500", "margin": 0, "color": CORAL}),
                        html.P("stockout-driven", style={"fontSize": "10px", "color": "#888780", "margin": 0}),
                    ]),
                ]),
                html.Div(style={**metric, "background": "#E1F5EE"}, children=[
                    html.P("Top-ranked vendor (composite score)", style={"fontSize": "11px", "color": "#5F5E5A", "margin": 0}),
                    html.P(id="kpi-top", style={"fontSize": "14px", "fontWeight": "500", "margin": 0, "color": TEAL}),
                ]),
            ]),
        ]),

        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "marginBottom": "12px"}, children=[
            html.Div(style=card, children=[dcc.Graph(id="chart-composite", style={"height": "300px"})]),
            html.Div(style=card, children=[dcc.Graph(id="chart-radar",     style={"height": "300px"})]),
        ]),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "marginBottom": "12px"}, children=[
            html.Div(style=card, children=[dcc.Graph(id="chart-co2",  style={"height": "280px"})]),
            html.Div(style=card, children=[dcc.Graph(id="chart-cost", style={"height": "280px"})]),
        ]),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "marginBottom": "12px"}, children=[
            html.Div(style=card, children=[dcc.Graph(id="chart-leadtime", style={"height": "260px"})]),
            html.Div(style=card, children=[dcc.Graph(id="chart-moq",      style={"height": "260px"})]),
        ]),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"}, children=[
            html.Div(style=card, children=[dcc.Graph(id="chart-stockout", style={"height": "260px"})]),
            html.Div(style=card, children=[dcc.Graph(id="chart-social",   style={"height": "260px"})]),
        ]),
    ]
)

LB   = dict(l=10, r=10, t=35, b=10)
BG   = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
FONT = dict(family="system-ui,sans-serif", size=12)
GC   = "#F1EFE8"


# CHANGE [DASH-1]: helper — picks highest-ranked vendor that supplies each part
def _build_vendor_override(ranked_vendor_names: list) -> dict:
    override = {}
    for _, part in PARTS.iterrows():
        best = get_best_vendor_for_part(part["name"], ranked_vendor_names)
        override[part["name"]] = best["name"]
    return override


@app.callback(
    Output("chart-composite", "figure"),
    Output("chart-radar",     "figure"),
    Output("chart-co2",       "figure"),
    Output("chart-cost",      "figure"),
    Output("chart-leadtime",  "figure"),
    Output("chart-moq",       "figure"),
    Output("chart-stockout",  "figure"),
    Output("chart-social",    "figure"),
    Output("kpi-top",     "children"),
    Output("kpi-util",    "children"),
    Output("kpi-cost",    "children"),
    Output("kpi-co2",     "children"),
    Output("kpi-penalty", "children"),
    Input("scenario", "value"),
)
def update(scenario):
    w_env, w_econ, w_soc = SCENARIOS.get(scenario, SCENARIOS["balanced"])
    t = w_env + w_econ + w_soc
    scores     = score_vendors(w_env=w_env/t, w_econ=w_econ/t, w_soc=w_soc/t)
    top_vendor = scores.iloc[0]["name"]
    ranked     = scores["name"].tolist()
    base       = dict(margin=LB, font=FONT, **BG)

    # CHANGE [DASH-1]: build override → re-run simulation with scenario vendors
    vendor_override = _build_vendor_override(ranked)
    sim_df, sim_util, sim_cost, sim_penalty, _ = simulate_procurement(
        n_simulations=500,
        vendor_override=vendor_override,
    )

    # CO2 for assigned vendors (one dominant vendor per part in override)
    assigned_co2 = VENDORS[VENDORS["name"].isin(vendor_override.values())]["co2_emissions_total"].sum()

    str_util    = f"{sim_util}%"
    str_cost    = f"${sim_cost / 1e6:.2f}M"
    str_co2     = f"{assigned_co2 / 1e3:.1f}k kg"
    str_penalty = f"${sim_penalty / 1e3:.0f}K"

    # ── 1. Composite score bar ────────────────────────────────────────────────
    bar_cols = [VENDOR_COLORS[i % len(VENDOR_COLORS)] for i in range(len(scores))]
    bar_cols[0] = TEAL
    fig1 = go.Figure(go.Bar(
        x=scores["name"], y=scores["score_composite"].round(1),
        marker_color=bar_cols,
        text=scores["score_composite"].round(1), textposition="outside",
        hovertemplate="<b>%{x}</b><br>Composite: %{y:.1f}/100<extra></extra>",
    ))
    # CHANGE [DASH-3]: annotation on chart
    fig1.add_annotation(
        text="Relative ranking: 0 = worst in set, 100 = best in set",
        xref="paper", yref="paper", x=0, y=1.02, showarrow=False,
        font=dict(size=9, color="#888780"), align="left",
    )
    fig1.update_layout(**base,
        title=dict(text="Composite sustainability score (0–100, relative ranking)", font=dict(size=13), x=0),
        yaxis=dict(range=[0, 120], showgrid=True, gridcolor=GC),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 2. Radar — top 3 vendors ──────────────────────────────────────────────
    # CHANGE [DASH-4]: social axis label updated
    cats = ["Environmental<br>(KPI 1)", "Economic<br>(KPI 2+4)", "Social<br>(Labor·Safety·Community)"]
    fig2 = go.Figure()
    rcols = [TEAL, BLUE, AMBER]
    for i, row in scores.head(3).iterrows():
        vals = [row["score_env"], row["score_econ"], row["score_soc"]]
        fig2.add_trace(go.Scatterpolar(
            r=vals + vals[:1], theta=cats + [cats[0]],
            name=row["name"].split()[0],
            line=dict(color=rcols[i % 3]), fill="toself",
            fillcolor=rcols[i % 3], opacity=0.15,
        ))
    fig2.update_layout(**base,
        title=dict(text="Pillar scores — top 3 vendors", font=dict(size=13), x=0),
        polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False)),
        legend=dict(orientation="h", y=-0.1, font=dict(size=10)),
    )

    # ── 3. KPI 1: CO2 emissions ───────────────────────────────────────────────
    co2_sorted = VENDORS.sort_values("co2_emissions_total")
    fig3 = go.Figure(go.Bar(
        x=co2_sorted["name"],
        y=co2_sorted["co2_emissions_total"],
        marker_color=[TEAL if v == top_vendor else BLUE for v in co2_sorted["name"]],
        text=co2_sorted["co2_emissions_total"].apply(lambda v: f"{v / 1e3:.1f}k"),
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>CO₂: %{y:,.0f} kg<extra></extra>",
    ))
    fig3.update_layout(**base,
        title=dict(text="KPI 1 · CO₂ Emissions (kg) — absolute values", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="kg CO₂"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 4. KPI 2: Total cost stacked bar ──────────────────────────────────────
    cost_sorted = VENDORS.sort_values("total_cost_total", ascending=False)
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(name="Purchase", x=cost_sorted["name"], y=cost_sorted["purchase_cost_total"],
        marker_color=TEAL, hovertemplate="Purchase: $%{y:,.0f}<extra></extra>"))
    fig4.add_trace(go.Bar(name="Shipping", x=cost_sorted["name"], y=cost_sorted["shipping_cost_total"],
        marker_color=BLUE, hovertemplate="Shipping: $%{y:,.0f}<extra></extra>"))
    fig4.add_trace(go.Bar(name="In-Transit", x=cost_sorted["name"], y=cost_sorted["intransit_cost_total"],
        marker_color=AMBER, hovertemplate="In-Transit: $%{y:,.0f}<extra></extra>"))
    fig4.update_layout(**base,
        barmode="stack",
        title=dict(text="KPI 2 · Total Cost = Purchase + Shipping + In-Transit (absolute $)", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="USD ($)"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
        legend=dict(orientation="h", y=1.08, font=dict(size=10)),
    )

    # ── 5. KPI 3: Lead time with std error ────────────────────────────────────
    fig5 = go.Figure()
    for i, row in VENDORS.iterrows():
        fig5.add_trace(go.Bar(
            x=[row["name"].split()[0]], y=[row["lead_time_days"]],
            error_y=dict(type="data",
                array=[row["lead_time_std"] if pd.notna(row["lead_time_std"]) else 0],
                visible=True, color="#B4B2A9"),
            marker_color=VENDOR_COLORS[i % len(VENDOR_COLORS)],
            name=row["name"], showlegend=False,
            hovertemplate=f"<b>{row['name']}</b><br>Lead Time: {row['lead_time_days']:.1f}d ± {row['lead_time_std']:.1f}d<extra></extra>",
        ))
    fig5.update_layout(**base,
        title=dict(text="KPI 3 · Lead Time (days) · error bars = std dev", font=dict(size=13), x=0),
        yaxis=dict(title="Days", showgrid=True, gridcolor=GC),
        xaxis=dict(showgrid=False, tickfont=dict(size=10)),
        bargap=0.3,
    )

    # ── 6. KPI 4: MOQ Impact ──────────────────────────────────────────────────
    moq_sorted = VENDORS.sort_values("moq_impact_mean", ascending=False)
    moq_cols = [CORAL if v > moq_sorted["moq_impact_mean"].median() else GREEN
                for v in moq_sorted["moq_impact_mean"]]
    fig6 = go.Figure(go.Bar(
        x=moq_sorted["name"], y=moq_sorted["moq_impact_mean"].round(2),
        marker_color=moq_cols,
        text=moq_sorted["moq_impact_mean"].round(2), textposition="outside",
        hovertemplate="<b>%{x}</b><br>MOQ/Qty: %{y:.2f}  (>1 = forced over-order)<extra></extra>",
    ))
    fig6.update_layout(**base,
        title=dict(text="KPI 4 · MOQ Impact = MOQ ÷ Qty  ·  red = above median (worse)", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="Ratio"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 7. Stockout — CHANGE [DASH-5]: dynamic sim_df ─────────────────────────
    crit_col = {5: CORAL, 4: AMBER, 3: BLUE, 2: GRAY, 1: GREEN}
    scols = [crit_col.get(c, GRAY) for c in sim_df["criticality"]]
    fig7 = go.Figure(go.Bar(
        x=sim_df["part_name"], y=sim_df["stockout_risk_pct"],
        marker_color=scols,
        text=[f"{v}%" for v in sim_df["stockout_risk_pct"]], textposition="outside",
        customdata=sim_df[["vendor_name", "avg_penalty_cost_usd", "lead_time_days", "moq_impact"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>Stockout risk: %{y}%<br>"
            "Vendor: %{customdata[0]}<br>"
            "Penalty: $%{customdata[1]:,.0f}<br>"
            "Lead Time: %{customdata[2]} days<br>"
            "MOQ Impact: %{customdata[3]:.2f}<extra></extra>"
        ),
    ))
    fig7.update_layout(**base,
        title=dict(text="Stockout risk % by part (Monte Carlo) · red = critical/emergency", font=dict(size=13), x=0),
        yaxis=dict(range=[0, 15], showgrid=True, gridcolor=GC, title="Risk %"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 8. Social KPI breakdown — CHANGE [DASH-4]: replaces transport pie ─────
    sc = scores[["name", "social_labor_score", "social_safety_trir",
                 "social_community_score", "social_transparency"]].copy()
    mx, mn = sc["social_safety_trir"].max(), sc["social_safety_trir"].min()
    sc["safety_display"] = (mx - sc["social_safety_trir"]) / (mx - mn) * 100 if mx != mn else 50

    fig8 = go.Figure()
    fig8.add_trace(go.Bar(name="Labor Rights", x=sc["name"], y=sc["social_labor_score"],
        marker_color=TEAL, hovertemplate="<b>%{x}</b><br>Labor Rights: %{y}/100<extra></extra>"))
    fig8.add_trace(go.Bar(name="Safety (TRIR inverted)", x=sc["name"], y=sc["safety_display"].round(1),
        marker_color=BLUE, hovertemplate="<b>%{x}</b><br>Safety (inv. TRIR): %{y:.1f}/100<extra></extra>"))
    fig8.add_trace(go.Bar(name="Community/Diversity", x=sc["name"], y=sc["social_community_score"],
        marker_color=AMBER, hovertemplate="<b>%{x}</b><br>Community: %{y}/100<extra></extra>"))
    fig8.add_trace(go.Bar(name="Transparency", x=sc["name"], y=sc["social_transparency"],
        marker_color=GREEN, hovertemplate="<b>%{x}</b><br>Transparency: %{y}/100<extra></extra>"))
    fig8.update_layout(**base,
        barmode="group",
        title=dict(text="Social pillar — 4 KPIs per vendor (ranked by composite score)", font=dict(size=13), x=0),
        yaxis=dict(range=[0, 120], showgrid=True, gridcolor=GC, title="Score (0–100)"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
        legend=dict(orientation="h", y=1.1, font=dict(size=10)),
    )

    return (fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8,
            top_vendor, str_util, str_cost, str_co2, str_penalty)


if __name__ == "__main__":
    print("Starting NJ Transit Sustainability Dashboard v2...")
    print(f"Baseline warehouse utilization : {base_util}%")
    print(f"Baseline penalty exposure      : ${base_penalty:,.0f}")
    print(f"Baseline CO2 (vendor sourcing) : {base_co2:,.0f} kg")
    print("Open: http://127.0.0.1:8050")
    app.run(debug=True)
