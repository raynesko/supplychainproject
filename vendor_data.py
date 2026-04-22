"""
vendor_data.py
All data loaded directly from NJTransit_FIFA2026_Synthetic_Data.xlsx.

KPI Formulas applied at the row level before aggregation:
  1. CO2 Emissions  = CO2 per KG × Unit Weight (kg) × Quantity Needed
  2. Total Cost     = (Purchase Price × Quantity Needed)
                    + (Shipping Cost per KG × Unit Weight × Quantity Needed)
                    + In-Transit Costs
  3. Lead Time      = Lead Time (days)   [direct column, KPI 3]
  4. MOQ Impact     = MOQ ÷ Quantity Needed

CHANGES vs previous version:
  [1] is_domestic: now derived from vendor NAME pattern rather than transport_mode.
      The synthetic dataset mixes German city names into all vendor rows (even
      "NJ Local Auto Sourcing" has ~11% Berlin/Frankfurt rows), making City/Country
      unreliable as a signal. Vendor names clearly separate NJ Transit infrastructure
      (Kearny Yard, Newark Depot, Hoboken Terminal, etc.) from "Global EuroParts",
      the only vendor whose name signals non-US/international sourcing.
      This is the correct social-pillar domestic-sourcing signal.

  [2] WAREHOUSE: total_capacity_m3 now sized on PEAK CONCURRENT inventory
      (MOQ + safety-stock buffer per part) rather than 1.2× total throughput.
      Total throughput is NOT a warehouse capacity metric — it's the sum of every
      unit that passes through over 90 days (~202,000 m3), which is ~41× what's
      ever sitting in the warehouse at one time. The old formula hardwired
      utilization to ~42.9% for any vendor selection because:
          peak ≈ 0.30 × 90-day demand
          available ≈ 0.70 × total throughput
          util = 0.30/0.70 = 42.9% — a constant, not a real signal.
      New formula: capacity = 3× peak concurrent → baseline util ≈ 62%,
      and it moves up/down meaningfully as MOQ and lead time change per vendor.
"""

import pandas as pd
import numpy as np

# ── Domestic vendor set (by name — see rationale above) ──────────────────────
# All NJ Transit facility names are domestic US operations.
# "Global EuroParts" is the sole international/non-domestic vendor in this dataset.
_NON_DOMESTIC = {"Global EuroParts"}

_RAW = pd.read_excel("NJTransit_FIFA2026_Synthetic_Data.xlsx")
_RAW["Order Date"]    = pd.to_datetime(_RAW["Order Date"])
_RAW["Required Date"] = pd.to_datetime(_RAW["Required Date"])
_RAW["days_available"] = (_RAW["Required Date"] - _RAW["Order Date"]).dt.days
_RAW["on_time"] = (_RAW["days_available"] >= _RAW["Lead Time (days)"]).astype(float)

# ── KPI 1: CO2 Emissions ─────────────────────────────────────────────────────
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
    co2_emissions_total = ("co2_emissions",            "sum"),
    co2_emissions_mean  = ("co2_emissions",            "mean"),
    # KPI 2
    total_cost_total    = ("total_cost",               "sum"),
    total_cost_mean     = ("total_cost",               "mean"),
    purchase_cost_total = ("purchase_cost",            "sum"),
    shipping_cost_total = ("shipping_cost",            "sum"),
    intransit_cost_total= ("In-Transit Costs ($)",     "sum"),
    # KPI 3
    lead_time_days      = ("Lead Time (days)",         "mean"),
    lead_time_std       = ("Lead Time (days)",         "std"),
    # KPI 4
    moq_impact_mean     = ("moq_impact",               "mean"),
    # Supporting cols
    unit_price          = ("Purchase Price ($)",       "mean"),
    moq                 = ("MOQ (Units)",              "mean"),
    co2_per_kg          = ("CO2 Emissions per KG",     "mean"),
    shipping_cost_per_kg= ("Shipping Cost per KG ($)", "mean"),
    carrying_cost       = ("Carrying Cost ($/unit/month)", "mean"),
    on_time_rate        = ("on_time",                  "mean"),
    unit_volume_m3      = ("Unit Volume (m3)",         "mean"),
    unit_weight_kg      = ("Unit Weight (kg)",         "mean"),
    penalty_cost_day    = ("Penalty Cost ($/day)",     "mean"),
    competitive_flag    = ("Competitive Offer Flag",   lambda x: (x == "Yes").mean()),
    transport_mode      = ("Transportation Mode",      lambda x: x.mode()[0]),
    processing_hours    = ("Processing Time (hours)",  "mean"),
    transit_speed_days  = ("Transportation Speed (days)", "mean"),
    qty_needed_total    = ("Quantity Needed",          "sum"),
).round(2).reset_index()

_AGG["vendor_id"] = ["V" + str(i + 1) for i in range(len(_AGG))]
_AGG["co2_per_unit"] = (_AGG["co2_per_kg"] * _AGG["unit_weight_kg"]).round(2)

# [FIX 1] is_domestic: True for all vendors EXCEPT those in _NON_DOMESTIC set.
_AGG["is_domestic"] = ~_AGG["Location Name"].isin(_NON_DOMESTIC)

co2_med = _AGG["co2_per_kg"].median()
otr_med = _AGG["on_time_rate"].median()
_AGG["has_iso14001"]  = (_AGG["co2_per_kg"] <= co2_med) & (_AGG["on_time_rate"] >= otr_med)
_AGG["diversity_cert"] = _AGG["competitive_flag"] >= _AGG["competitive_flag"].median()

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
# [FIX 2] Size on peak CONCURRENT inventory, not total throughput.
# Peak concurrent per part = MOQ (order just received) + safety stock (reorder buffer).
# reorder_point_days = 14 days, matching simulation.py.
# AFTER
_REORDER_DAYS = 30   # matches simulation reorder_point_days fix
_peak_concurrent_m3 = 0.0
for _, _part in PARTS.iterrows():
    _vendor       = VENDORS[VENDORS["vendor_id"] == _part["preferred_vendor"]].iloc[0]
    _moq          = max(1, int(_vendor["moq"]))
    # Use implied daily demand (qty/lead_time) — consistent with simulation.py
    _part_rows    = _RAW[_RAW["Product Name"] == _part["name"]]
    _daily_demand = (_part_rows["Quantity Needed"] / _part_rows["Lead Time (days)"].replace(0, np.nan)).mean()
    _safety_stock = _daily_demand * _REORDER_DAYS
    _peak_concurrent_m3 += (_moq + _safety_stock) * _part["unit_volume_m3"]

# Capacity = 3× peak concurrent (realistic headroom for a transit maintenance facility).
# current_used = 1× peak (baseline stock already in warehouse).
# fifa_reserved = 0.4× peak (FIFA ops buffer — ~13% of total capacity).
# Available = 3.0 - 1.0 - 0.4 = 1.6× peak → baseline utilization ≈ 62%.
# This moves meaningfully when vendor MOQs or part volumes change.
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
    print("\n=== VENDORS ===")
    print(VENDORS[[
        "vendor_id", "name", "is_domestic",
        "co2_emissions_total", "total_cost_total",
        "lead_time_days", "moq_impact_mean", "on_time_rate", "transport_mode"
    ]].to_string(index=False))
    print("\n=== PARTS ===")
    print(PARTS.to_string(index=False))
    print("\n=== WAREHOUSE ===", WAREHOUSE)
