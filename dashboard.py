"""
NJ Transit Sustainability Dashboard — FIFA 2026
KPI-driven: CO2 Emissions, Total Cost, Lead Time, MOQ Impact.

Run:
  pip install dash plotly pandas numpy openpyxl
  python dashboard.py
  Open http://127.0.0.1:8050
"""

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from vendor_data import VENDORS, PARTS, WAREHOUSE
from scorecard import score_vendors
from simulation import simulate_procurement

# ── pre-run simulation once at startup ────────────────────────────────────────
sim_df, base_util, base_cost, base_penalty, base_co2 = simulate_procurement(n_simulations=500)

# Pre-compute sim penalty per vendor — passed into scorecard so it uses real
# Monte Carlo penalty instead of the raw penalty_cost_day column
vendor_penalty = (
    sim_df.groupby("vendor")["avg_penalty_cost_usd"]
    .sum()
    .reset_index()
    .rename(columns={"vendor": "vendor_id", "avg_penalty_cost_usd": "sim_penalty"})
)

# ── app ────────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, title="NJ Transit — Sustainability Dashboard")

TEAL   = "#1D9E75"; BLUE   = "#378ADD"; AMBER = "#EF9F27"
CORAL  = "#D85A30"; GRAY   = "#888780"; GREEN = "#639922"
PURPLE = "#7F77DD"; PINK   = "#D4537E"
VENDOR_COLORS = [TEAL, BLUE, AMBER, CORAL, GRAY, GREEN, PURPLE, PINK, "#BA7517", "#5DCAA5"]

card   = {"background":"white","border":"0.5px solid #D3D1C7","borderRadius":"12px",
          "padding":"1rem 1.25rem","marginBottom":"12px"}
metric = {"background":"#F1EFE8","borderRadius":"8px","padding":"0.65rem 1rem","textAlign":"center"}
slabel = {"marginBottom":"5px","fontSize":"12px","color":"#5F5E5A"}

SCENARIOS = {
    "balanced": (0.33, 0.33, 0.34),
    "green":    (0.70, 0.15, 0.15),
    "fast":     (0.20, 0.60, 0.20),
    "cheap":    (0.15, 0.70, 0.15),
}

KPI_NOTE = html.Div(
    style={"background":"#E8F4FD","borderRadius":"8px","padding":"0.5rem 0.85rem",
           "marginBottom":"12px","fontSize":"11px","color":"#2C5F8A","lineHeight":"1.6"},
    children=[
        html.Strong("KPI Formulas — "),
        "① CO₂ = CO₂/kg × Weight × Qty  ",
        html.Span("·", style={"margin":"0 4px"}),
        "② Total Cost = (Price × Qty) + (Ship/kg × Weight × Qty) + In-Transit  ",
        html.Span("·", style={"margin":"0 4px"}),
        "③ Lead Time (days)  ",
        html.Span("·", style={"margin":"0 4px"}),
        "④ MOQ Impact = MOQ ÷ Qty  ",
        html.Span("·", style={"margin":"0 4px"}),
        html.Strong("Monte Carlo: "),
        "500 simulations · 90-day FIFA window · reorder point = 30 days · penalty from actual stockout days",
    ]
)

available_m3 = (
    WAREHOUSE["total_capacity_m3"]
    - WAREHOUSE["current_used_m3"]
    - WAREHOUSE["fifa_reserved_m3"]
)

app.layout = html.Div(
    style={"fontFamily":"system-ui,sans-serif","maxWidth":"1140px","margin":"0 auto","padding":"1.5rem"},
    children=[
        # ── header ────────────────────────────────────────────────────────────
        html.Div(style={"borderBottom":f"2px solid {TEAL}","paddingBottom":"0.75rem","marginBottom":"1rem"},
                 children=[
            html.Div(style={"display":"flex","justifyContent":"space-between",
                            "alignItems":"center","flexWrap":"wrap","gap":"8px"}, children=[
                html.H1("NJ Transit — Vendor Sustainability Dashboard",
                        style={"fontSize":"18px","fontWeight":"500","margin":0}),
                html.Div(style={"display":"flex","gap":"6px"}, children=[
                    html.Span("FIFA 2026", style={"background":"#E1F5EE","color":"#0F6E56",
                              "fontSize":"11px","fontWeight":"500","padding":"3px 10px","borderRadius":"20px"}),
                    html.Span("10 vendors · 8 parts", style={"background":"#F1EFE8","color":"#5F5E5A",
                              "fontSize":"11px","padding":"3px 10px","borderRadius":"20px"}),
                ]),
            ]),
            html.P("Select a scenario to reweight sustainability pillars — all KPI charts update live.",
                   style={"fontSize":"13px","color":"#888780","margin":"4px 0 0"}),
        ]),

        KPI_NOTE,

        # ── controls + KPIs ───────────────────────────────────────────────────
        html.Div(style={"display":"grid","gridTemplateColumns":"0.9fr 1fr",
                        "gap":"12px","marginBottom":"12px"}, children=[

            # Scenario card
            html.Div(style=card, children=[
                html.P("Scenario preset", style={**slabel,"fontWeight":"500","fontSize":"13px"}),
                dcc.RadioItems(id="scenario",
                    options=[
                        {"label":"  Balanced (33 / 33 / 34)",       "value":"balanced"},
                        {"label":"  Lowest carbon — KPI 1 (70/15/15)","value":"green"},
                        {"label":"  Fastest lead time — KPI 3 (20/60/20)","value":"fast"},
                        {"label":"  Lowest cost — KPI 2 (15/70/15)", "value":"cheap"},
                    ],
                    value="balanced",
                    labelStyle={"display":"block","marginBottom":"12px","fontSize":"13px","cursor":"pointer"},
                ),
                html.Div(style={"marginTop":"12px","fontSize":"11px","color":"#888780","lineHeight":"1.7"},
                         children=[
                    html.Strong("Pillars: "),
                    "Env = CO₂ (70%) + On-time (30%)  ·  ",
                    "Econ = Cost (45%) + MOQ (20%) + Carrying (20%) + Penalty (15%)  ·  ",
                    "Social = Domestic (50%) + ISO proxy (30%) + Diversity (20%)",
                ]),
            ]),

            # KPI metric tiles
            html.Div(style={"display":"flex","flexDirection":"column","gap":"8px"}, children=[
                html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"8px"}, children=[
                    html.Div(style=metric, children=[
                        html.P("Warehouse utilization", style={"fontSize":"11px","color":"#5F5E5A","margin":0}),
                        html.P(id="kpi-util", style={"fontSize":"24px","fontWeight":"500","margin":0}),
                        html.P(f"of {WAREHOUSE['total_capacity_m3']:,} m³ total",
                               style={"fontSize":"10px","color":"#888780","margin":0}),
                    ]),
                    html.Div(style=metric, children=[
                        html.P("KPI 2 · Procurement cost", style={"fontSize":"11px","color":"#5F5E5A","margin":0}),
                        html.P(id="kpi-cost", style={"fontSize":"24px","fontWeight":"500","margin":0}),
                        html.P("90-day horizon", style={"fontSize":"10px","color":"#888780","margin":0}),
                    ]),
                ]),
                html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"8px"}, children=[
                    html.Div(style=metric, children=[
                        html.P("KPI 1 · CO₂ emissions", style={"fontSize":"11px","color":"#5F5E5A","margin":0}),
                        html.P(id="kpi-co2", style={"fontSize":"24px","fontWeight":"500","margin":0,"color":GREEN}),
                        html.P("vendor sourcing only", style={"fontSize":"10px","color":"#888780","margin":0}),
                    ]),
                    html.Div(style=metric, children=[
                        html.P("Penalty exposure (Monte Carlo)", style={"fontSize":"11px","color":"#5F5E5A","margin":0}),
                        html.P(id="kpi-penalty", style={"fontSize":"24px","fontWeight":"500","margin":0,"color":CORAL}),
                        html.P("stockout-driven", style={"fontSize":"10px","color":"#888780","margin":0}),
                    ]),
                ]),
                html.Div(style={**metric,"background":"#E1F5EE"}, children=[
                    html.P("Top-ranked vendor (composite score)", style={"fontSize":"11px","color":"#5F5E5A","margin":0}),
                    html.P(id="kpi-top", style={"fontSize":"14px","fontWeight":"500","margin":0,"color":TEAL}),
                ]),
            ]),
        ]),

        # ── row 1: composite + radar ───────────────────────────────────────────
        html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}, children=[
            html.Div(style=card,children=[dcc.Graph(id="chart-composite",style={"height":"300px"})]),
            html.Div(style=card,children=[dcc.Graph(id="chart-radar",    style={"height":"300px"})]),
        ]),

        # ── row 2: KPI 1 CO2 + KPI 2 Total Cost ───────────────────────────────
        html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}, children=[
            html.Div(style=card,children=[dcc.Graph(id="chart-co2",  style={"height":"280px"})]),
            html.Div(style=card,children=[dcc.Graph(id="chart-cost", style={"height":"280px"})]),
        ]),

        # ── row 3: KPI 3 Lead Time + KPI 4 MOQ Impact ─────────────────────────
        html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}, children=[
            html.Div(style=card,children=[dcc.Graph(id="chart-leadtime", style={"height":"260px"})]),
            html.Div(style=card,children=[dcc.Graph(id="chart-moq",      style={"height":"260px"})]),
        ]),

        # ── row 4: stockout risk + transport mix ───────────────────────────────
        html.Div(style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px"}, children=[
            html.Div(style=card,children=[dcc.Graph(id="chart-stockout",  style={"height":"260px"})]),
            html.Div(style=card,children=[dcc.Graph(id="chart-transport", style={"height":"260px"})]),
        ]),
    ]
)

LB   = dict(l=10,r=10,t=35,b=10)
BG   = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
FONT = dict(family="system-ui,sans-serif", size=12)
GC   = "#F1EFE8"


@app.callback(
    Output("chart-composite","figure"),
    Output("chart-radar","figure"),
    Output("chart-co2","figure"),
    Output("chart-cost","figure"),
    Output("chart-leadtime","figure"),
    Output("chart-moq","figure"),
    Output("chart-stockout","figure"),
    Output("chart-transport","figure"),
    Output("kpi-top","children"),
    Output("kpi-util","children"),
    Output("kpi-cost","children"),
    Output("kpi-co2","children"),
    Output("kpi-penalty","children"),
    Input("scenario","value"),
)
def update(scenario):
    w_env, w_econ, w_soc = SCENARIOS.get(scenario, SCENARIOS["balanced"])
    t       = w_env + w_econ + w_soc
    w_env_n = w_env / t
    w_econ_n= w_econ / t
    w_soc_n = w_soc / t

    # Score vendors — pass real Monte Carlo penalty so economic pillar is grounded
    scores     = score_vendors(w_env=w_env_n, w_econ=w_econ_n, w_soc=w_soc_n,
                               sim_penalty_by_vendor=vendor_penalty)
    top_vendor = scores.iloc[0]["name"]
    base       = dict(margin=LB, font=FONT, **BG)

    # ── KPI metric values ─────────────────────────────────────────────────────
    # Warehouse util: from Monte Carlo simulation (fixed, vendor assignments don't
    # change with pillar weights — stated as Monte Carlo baseline)
    str_util    = f"{base_util}%"

    # Cost & CO2: weighted blend across vendors by composite score
    total_score   = scores["score_composite"].sum()
    alloc_weights = scores["score_composite"].values / (total_score if total_score > 0 else 1)
    v_data        = VENDORS.set_index("name").loc[scores["name"]]
    new_cost      = (v_data["total_cost_total"] * alloc_weights).sum()
    new_co2       = (v_data["co2_emissions_total"] * alloc_weights).sum()
    str_cost      = f"${new_cost/1e6:.2f}M"
    str_co2       = f"{new_co2/1e3:.1f}k kg"

    # Penalty: real Monte Carlo total (fixed baseline — doesn't change with weights)
    str_penalty   = f"${base_penalty/1e3:.0f}K"

    # ── 1. Composite score bar ────────────────────────────────────────────────
    bar_cols = [VENDOR_COLORS[i % len(VENDOR_COLORS)] for i in range(len(scores))]
    bar_cols[0] = TEAL
    fig1 = go.Figure(go.Bar(
        x=scores["name"], y=scores["score_composite"].round(1),
        marker_color=bar_cols,
        text=scores["score_composite"].round(1), textposition="outside",
        hovertemplate="<b>%{x}</b><br>Composite: %{y:.1f}/100<extra></extra>",
    ))
    fig1.update_layout(**base,
        title=dict(text="Composite sustainability score (0–100)", font=dict(size=13), x=0),
        yaxis=dict(range=[0,115], showgrid=True, gridcolor=GC),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 2. Radar — top 3 vendors ──────────────────────────────────────────────
    cats = ["Environmental<br>(KPI 1)", "Economic<br>(KPI 2+4)", "Social<br>(domestic)"]
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
        polar=dict(radialaxis=dict(range=[0,100], showticklabels=False)),
        legend=dict(orientation="h", y=-0.1, font=dict(size=10)),
    )

    # ── 3. KPI 1: CO2 emissions ───────────────────────────────────────────────
    co2_sorted = VENDORS.sort_values("co2_emissions_total")
    fig3 = go.Figure(go.Bar(
        x=co2_sorted["name"],
        y=co2_sorted["co2_emissions_total"],
        marker_color=[TEAL if v == top_vendor else BLUE for v in co2_sorted["name"]],
        text=co2_sorted["co2_emissions_total"].apply(lambda v: f"{v/1e3:.1f}k"),
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>CO₂: %{y:,.0f} kg<extra></extra>",
    ))
    fig3.update_layout(**base,
        title=dict(text="KPI 1 · CO₂ Emissions (kg) — vendor sourcing rows only", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="kg CO₂"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 4. KPI 2: Total cost stacked bar ──────────────────────────────────────
    cost_sorted = VENDORS.sort_values("total_cost_total", ascending=False)
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(
        name="Purchase", x=cost_sorted["name"], y=cost_sorted["purchase_cost_total"],
        marker_color=TEAL, hovertemplate="Purchase: $%{y:,.0f}<extra></extra>",
    ))
    fig4.add_trace(go.Bar(
        name="Shipping", x=cost_sorted["name"], y=cost_sorted["shipping_cost_total"],
        marker_color=BLUE, hovertemplate="Shipping: $%{y:,.0f}<extra></extra>",
    ))
    fig4.add_trace(go.Bar(
        name="In-Transit", x=cost_sorted["name"], y=cost_sorted["intransit_cost_total"],
        marker_color=AMBER, hovertemplate="In-Transit: $%{y:,.0f}<extra></extra>",
    ))
    fig4.update_layout(**base,
        barmode="stack",
        title=dict(text="KPI 2 · Total Cost = Purchase + Shipping + In-Transit", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="USD ($)"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
        legend=dict(orientation="h", y=1.08, font=dict(size=10)),
    )

    # ── 5. KPI 3: Lead time with std error ────────────────────────────────────
    fig5 = go.Figure()
    for i, row in VENDORS.iterrows():
        fig5.add_trace(go.Bar(
            x=[row["name"].split()[0]],
            y=[row["lead_time_days"]],
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
    moq_cols   = [CORAL if v > moq_sorted["moq_impact_mean"].median() else GREEN
                  for v in moq_sorted["moq_impact_mean"]]
    fig6 = go.Figure(go.Bar(
        x=moq_sorted["name"],
        y=moq_sorted["moq_impact_mean"].round(2),
        marker_color=moq_cols,
        text=moq_sorted["moq_impact_mean"].round(2), textposition="outside",
        hovertemplate="<b>%{x}</b><br>MOQ/Qty: %{y:.2f}  (>1 = forced over-order)<extra></extra>",
    ))
    fig6.update_layout(**base,
        title=dict(text="KPI 4 · MOQ Impact = MOQ ÷ Qty  ·  red = above median (worse)", font=dict(size=13), x=0),
        yaxis=dict(showgrid=True, gridcolor=GC, title="Ratio"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 7. Stockout risk (Monte Carlo) ────────────────────────────────────────
    crit_col = {5: CORAL, 4: AMBER, 3: BLUE, 2: GRAY, 1: GREEN}
    scols = [crit_col.get(c, GRAY) for c in sim_df["criticality"]]
    fig7 = go.Figure(go.Bar(
        x=sim_df["part_name"], y=sim_df["stockout_risk_pct"],
        marker_color=scols,
        text=[f"{v}%" for v in sim_df["stockout_risk_pct"]], textposition="outside",
        customdata=sim_df[["vendor_name","avg_penalty_cost_usd","lead_time_days","moq_impact"]].values,
        hovertemplate=(
            "<b>%{x}</b><br>Stockout risk: %{y}%<br>"
            "Vendor: %{customdata[0]}<br>"
            "Penalty exposure: $%{customdata[1]:,.0f}<br>"
            "KPI 3 Lead Time: %{customdata[2]} days<br>"
            "KPI 4 MOQ Impact: %{customdata[3]:.2f}<extra></extra>"
        ),
    ))
    fig7.update_layout(**base,
        title=dict(text="Stockout risk % by part (Monte Carlo) · red = critical/emergency", font=dict(size=13), x=0),
        yaxis=dict(range=[0,15], showgrid=True, gridcolor=GC, title="Risk %"),
        xaxis=dict(showgrid=False, tickangle=-25, tickfont=dict(size=10)),
    )

    # ── 8. Transport mode mix ──────────────────────────────────────────────────
    mode_counts = VENDORS["transport_mode"].value_counts()
    mode_colors = {"Road": TEAL, "Rail": BLUE, "Sea": AMBER, "Air": CORAL}
    fig8 = go.Figure(go.Pie(
        labels=mode_counts.index,
        values=mode_counts.values,
        marker_colors=[mode_colors.get(m, GRAY) for m in mode_counts.index],
        hole=0.45, textfont=dict(size=12),
    ))
    fig8.update_layout(**base,
        title=dict(text="Vendor transportation mode mix (dominant mode per vendor)", font=dict(size=13), x=0),
        legend=dict(orientation="v", font=dict(size=11)),
    )

    return (fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8,
            top_vendor, str_util, str_cost, str_co2, str_penalty)


if __name__ == "__main__":
    print("Starting NJ Transit Sustainability Dashboard...")
    print(f"Warehouse utilization (Monte Carlo baseline): {base_util}%")
    print(f"Total penalty exposure (Monte Carlo):         ${base_penalty:,.0f}")
    print(f"Total CO2 (vendor sourcing):                  {base_co2:,.0f} kg")
    print("Open: http://127.0.0.1:8050")
    app.run(debug=True)
