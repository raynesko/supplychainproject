"""
vendor_data.py  (v2 — Social Pillar Refactor)
All data loaded directly from NJTransit_FIFA2026_WithSocialPillar.xlsx.

KPI Formulas applied at the row level before aggregation:
  1. CO2 Emissions  = CO2 per KG × Unit Weight (kg) × Quantity Needed
  2. Total Cost     = (Purchase Price × Quantity Needed)
                    + (Shipping Cost per KG × Unit Weight × Quantity Needed)
                    + In-Transit Costs
  3. Lead Time      = Lead Time (days)   [direct column, KPI 3]
  4. MOQ Impact     = MOQ ÷ Quantity Needed

SOCIAL PILLAR — CHANGES FROM v1:
─────────────────────────────────────────────────────────────────────────────
  [SOC-1] Replaced binary is_domestic / has_iso14001 / diversity_cert flags
          with four continuous social KPI columns sourced from the enriched
          Excel file (NJTransit_FIFA2026_WithSocialPillar.xlsx):

          • social_labor_score     — Labor rights compliance (0-100, higher=better)
            Per vendor mean of Social_LaborRights_Score (1-100)

          • social_safety_trir     — Total Recordable Incident Rate (lower=better)
            Per vendor mean of Social_Safety_TRIR (Lower=Better)

          • social_community_score — Community impact & diversity (0-100, higher=better)
            Per vendor mean of Social_CommunityDiversity_Score (1-100)

          • social_transparency    — Supply chain transparency (0-100, higher=better)
            Per vendor mean of Social_Transparency_Index (1-100)

  [SOC-2] is_domestic retained as a binary domestic-sourcing flag (True/False).
          Still derived from vendor name: all except "Global EuroParts" = True.
          Used as a supplemental signal in the scorecard but no longer the
          *primary* anchor of the social pillar — that role now belongs to
          social_labor_score and social_safety_trir.

  [SOC-3] has_iso14001 and diversity_cert REMOVED. These were proxies computed
          from CO2/kg and competitive_flag — not genuine social measures. The
          enriched social columns are far more semantically correct.

WAREHOUSE CHANGES (unchanged from v1):
  [WH-1] Capacity sized on 3× peak concurrent inventory (not total throughput).
  [WH-2] Reorder point days = 30, matching simulation.py.
"""

import pandas as pd
import numpy as np

# ── Domestic vendor set (by name) ─────────────────────────────────────────────
_NON_DOMESTIC = {"Global EuroParts"}

# ── Load enriched data (includes social KPI columns) ──────────────────────────
# CHANGE [SOC-1]: load from enriched file instead of bare original
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
_RAW = pd.read_excel(os.path.join(_DIR, "NJTransit_FIFA2026_WithSocialPillar.xlsx"), sheet_name="Sourcing Data")
_RAW["Order Date"]    = pd.to_datetime(_RAW["Order Date"])
_RAW["Required Date"] = pd.to_datetime(_RAW["Required Date"])
_RAW["days_available"] = (_RAW["Required Date"] - _RAW["Order Date"]).dt.days
_RAW["on_time"] = (_RAW["days_available"] >= _RAW["Lead Time (days)"]).astype(float)

# ── KPI 1: CO2 Emissions ──────────────────────────────────────────────────────
_RAW["co2_emissions"] = (
    _RAW["CO2 Emissions per KG"]
    * _RAW["Unit Weight (kg)"]
    * _RAW["Quantity Needed"]
)

# ── KPI 2: Total Cost ─────────────────────────────────────────────────────────
_RAW["purchase_cost"] = _RAW["Purchase Price ($)"] * _RAW["Quantity Needed"]
_RAW["shipping_cost"] = (
    _RAW["Shipping Cost per KG ($)"]
    * _RAW["Unit Weight (kg)"]
    * _RAW["Quantity Needed"]
)
_RAW["total_cost"] = (
    _RAW["purchase_cost"]
    + _RAW["shipping_cost"]
    + _RAW["In-Transit Costs ($)"]
)

# ── KPI 4: MOQ Impact ─────────────────────────────────────────────────────────
_RAW["moq_impact"] = _RAW["MOQ (Units)"] / _RAW["Quantity Needed"].replace(0, np.nan)

# ── Vendor-level aggregation ──────────────────────────────────────────────────
_VENDOR_ROWS = _RAW[_RAW["Location Type"] == "Vendor"].copy()

_AGG = _VENDOR_ROWS.groupby("Location Name").agg(
    # KPI 1
    co2_emissions_total  = ("co2_emissions",            "sum"),
    co2_emissions_mean   = ("co2_emissions",            "mean"),
    # KPI 2
    total_cost_total     = ("total_cost",               "sum"),
    total_cost_mean      = ("total_cost",               "mean"),
    purchase_cost_total  = ("purchase_cost",            "sum"),
    shipping_cost_total  = ("shipping_cost",            "sum"),
    intransit_cost_total = ("In-Transit Costs ($)",     "sum"),
    # KPI 3
    lead_time_days       = ("Lead Time (days)",         "mean"),
    lead_time_std        = ("Lead Time (days)",         "std"),
    # KPI 4
    moq_impact_mean      = ("moq_impact",               "mean"),
    # Supporting cols
    unit_price           = ("Purchase Price ($)",       "mean"),
    moq                  = ("MOQ (Units)",              "mean"),
    co2_per_kg           = ("CO2 Emissions per KG",     "mean"),
    shipping_cost_per_kg = ("Shipping Cost per KG ($)", "mean"),
    carrying_cost        = ("Carrying Cost ($/unit/month)", "mean"),
    on_time_rate         = ("on_time",                  "mean"),
    unit_volume_m3       = ("Unit Volume (m3)",         "mean"),
    unit_weight_kg       = ("Unit Weight (kg)",         "mean"),
    penalty_cost_day     = ("Penalty Cost ($/day)",     "mean"),
    competitive_flag     = ("Competitive Offer Flag",   lambda x: (x == "Yes").mean()),
    transport_mode       = ("Transportation Mode",      lambda x: x.mode()[0]),
    processing_hours     = ("Processing Time (hours)",  "mean"),
    transit_speed_days   = ("Transportation Speed (days)", "mean"),
    qty_needed_total     = ("Quantity Needed",          "sum"),
    # CHANGE [SOC-1]: aggregate the four real social KPI columns
    social_labor_score   = ("Social_LaborRights_Score (1-100)",         "mean"),
    social_safety_trir   = ("Social_Safety_TRIR (Lower=Better)",        "mean"),
    social_community_score = ("Social_CommunityDiversity_Score (1-100)", "mean"),
    social_transparency  = ("Social_Transparency_Index (1-100)",        "mean"),
).round(2).reset_index()

_AGG["vendor_id"]   = ["V" + str(i + 1) for i in range(len(_AGG))]
_AGG["co2_per_unit"] = (_AGG["co2_per_kg"] * _AGG["unit_weight_kg"]).round(2)

# CHANGE [SOC-2]: is_domestic retained as binary domestic-sourcing flag
_AGG["is_domestic"] = ~_AGG["Location Name"].isin(_NON_DOMESTIC)

# CHANGE [SOC-3]: has_iso14001 and diversity_cert REMOVED — replaced by real social KPIs above

VENDORS = _AGG.rename(columns={"Location Name": "name"})

# ── Part demand ───────────────────────────────────────────────────────────────
_PARTS_AGG = _VENDOR_ROWS.groupby("Product Name").agg(
    monthly_demand      = ("Quantity Needed",    lambda x: int(x.sum() / 3)),
    co2_emissions_total = ("co2_emissions",      "sum"),
    total_cost_total    = ("total_cost",         "sum"),
    lead_time_mean      = ("Lead Time (days)",   "mean"),
    moq_impact_mean     = ("moq_impact",         "mean"),
    criticality_raw     = ("Product Group",      lambda x: x.mode()[0]),
    unit_volume_m3      = ("Unit Volume (m3)",   "mean"),
    unit_weight_kg      = ("Unit Weight (kg)",   "mean"),
).reset_index()

_PARTS_AGG["criticality"] = _PARTS_AGG["criticality_raw"].map(
    {"Critical/Emergency": 5, "Routine Maintenance": 3}
)
_PARTS_AGG["part_id"] = ["P" + str(i + 1).zfill(2) for i in range(len(_PARTS_AGG))]


def _preferred_vendor(product_name):
    """Preferred vendor = balances Total Cost with Space Constraints (MOQ Volume)."""
    sub = _VENDOR_ROWS[_VENDOR_ROWS["Product Name"] == product_name].copy()
    if sub.empty:
        return VENDORS.iloc[0]["vendor_id"]
    sub["_unit_total_cost"] = sub["total_cost"] / sub["Quantity Needed"].replace(0, np.nan)
    sub["_moq_volume_m3"]   = sub["MOQ (Units)"] * sub["Unit Volume (m3)"]
    space_penalty_weight    = 50
    sub["_selection_score"] = sub["_unit_total_cost"] + (sub["_moq_volume_m3"] * space_penalty_weight)
    best = sub.groupby("Location Name")["_selection_score"].mean().idxmin()
    row  = VENDORS[VENDORS["name"] == best]
    return row.iloc[0]["vendor_id"] if not row.empty else VENDORS.iloc[0]["vendor_id"]


_PARTS_AGG["preferred_vendor"] = _PARTS_AGG["Product Name"].apply(_preferred_vendor)

PARTS = _PARTS_AGG.rename(columns={"Product Name": "name"})[
    ["part_id", "name", "monthly_demand", "criticality",
     "unit_volume_m3", "unit_weight_kg", "preferred_vendor",
     "co2_emissions_total", "total_cost_total", "lead_time_mean", "moq_impact_mean"]
]

# ── Warehouse ─────────────────────────────────────────────────────────────────
_REORDER_DAYS = 30
_peak_concurrent_m3 = 0.0
for _, _part in PARTS.iterrows():
    _vendor       = VENDORS[VENDORS["vendor_id"] == _part["preferred_vendor"]].iloc[0]
    _moq          = max(1, int(_vendor["moq"]))
    _part_rows    = _RAW[_RAW["Product Name"] == _part["name"]]
    _daily_demand = (_part_rows["Quantity Needed"] / _part_rows["Lead Time (days)"].replace(0, np.nan)).mean()
    _safety_stock = _daily_demand * _REORDER_DAYS
    _peak_concurrent_m3 += (_moq + _safety_stock) * _part["unit_volume_m3"]

WAREHOUSE = {
    "total_capacity_m3": round(_peak_concurrent_m3 * 3.0),
    "current_used_m3":   round(_peak_concurrent_m3 * 1.0),
    "fifa_reserved_m3":  round(_peak_concurrent_m3 * 0.4),
}


if __name__ == "__main__":
    available = (
        WAREHOUSE["total_capacity_m3"]
        - WAREHOUSE["current_used_m3"]
        - WAREHOUSE["fifa_reserved_m3"]
    )
    print(f"Peak concurrent inventory : {_peak_concurrent_m3:.1f} m3")
    print(f"Warehouse capacity        : {WAREHOUSE['total_capacity_m3']} m3")
    print(f"Currently used            : {WAREHOUSE['current_used_m3']} m3")
    print(f"FIFA reserved             : {WAREHOUSE['fifa_reserved_m3']} m3")
    print(f"Available                 : {available} m3")
    print(f"Baseline utilization      : {_peak_concurrent_m3 / available * 100:.1f}%")
    print("\n=== VENDORS (Social KPIs) ===")
    print(VENDORS[[
        "vendor_id", "name", "is_domestic",
        "social_labor_score", "social_safety_trir",
        "social_community_score", "social_transparency",
    ]].to_string(index=False))
    print("\n=== WAREHOUSE ===", WAREHOUSE)
