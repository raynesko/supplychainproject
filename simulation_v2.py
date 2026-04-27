"""
simulation.py  (v2 — Dynamic Vendor Assignment)
Monte Carlo procurement simulation using real NJTransit data.
Models lead time variability (KPI 3) over a 90-day FIFA 2026 service window.

KPIs used:
  KPI 2 – Total Cost drives avg_total_cost_usd (purchase + shipping + in-transit)
  KPI 3 – Lead Time (days) drives stockout risk via reorder-point logic
  KPI 4 – MOQ Impact informs order frequency and stockout exposure

CHANGES FROM v1:
─────────────────────────────────────────────────────────────────────────────
  [SIM-1] vendor_override parameter added to simulate_procurement().
          When provided (a dict of {part_name: vendor_name}), the simulation
          uses those vendor assignments instead of the frozen preferred_vendor
          from the PARTS table. This is the core fix for the utilization
          lock-in bug: dashboard.py now computes scenario-specific vendor
          assignments from the scorecard ranking and passes them here, so
          warehouse utilization, cost, CO2, and penalty all respond to
          pillar weight changes.

  [SIM-2] _get_vendor_for_part() helper added. Given a scored ranking of
          vendors and a part name, it finds the highest-ranked vendor that
          actually has rows in the raw data for that part — preventing
          mismatches where a top-ranked vendor doesn't supply a given part.

  [SIM-3] _RAW now loaded from the enriched Excel file
          (NJTransit_FIFA2026_WithSocialPillar.xlsx) so the file reference
          is consistent across all modules.
"""

import numpy as np
import pandas as pd
from vendor_data_v2 import VENDORS, PARTS, WAREHOUSE

# CHANGE [SIM-3]: load from enriched file (consistent with vendor_data_v2)
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
_RAW = pd.read_excel(os.path.join(_DIR, "NJTransit_FIFA2026_WithSocialPillar.xlsx"), sheet_name="Sourcing Data")
_RAW["total_cost"] = (
    (_RAW["Purchase Price ($)"] * _RAW["Quantity Needed"])
    + (_RAW["Shipping Cost per KG ($)"] * _RAW["Unit Weight (kg)"] * _RAW["Quantity Needed"])
    + _RAW["In-Transit Costs ($)"]
)

# Pre-build: which vendors supply each part (vendor name → set of part names)
_PART_VENDOR_MAP: dict[str, list[str]] = (
    _RAW[_RAW["Location Type"] == "Vendor"]
    .groupby("Product Name")["Location Name"]
    .apply(list)
    .to_dict()
)


def _implied_daily_demand(product_name: str) -> float:
    """Estimate daily consumption rate from procurement data."""
    rows = _RAW[_RAW["Product Name"] == product_name]
    if rows.empty:
        return 10.0
    return (rows["Quantity Needed"] / rows["Lead Time (days)"].replace(0, np.nan)).mean()


# CHANGE [SIM-2]: new helper — picks highest-ranked vendor that supplies the part
def get_best_vendor_for_part(part_name: str, ranked_vendor_names: list[str]) -> pd.Series:
    """
    Walk the scorecard ranking top-to-bottom and return the first vendor
    row that actually supplies `part_name` in the raw data.
    Falls back to the default preferred_vendor if none match.
    """
    eligible = set(_PART_VENDOR_MAP.get(part_name, []))
    for vname in ranked_vendor_names:
        if vname in eligible:
            row = VENDORS[VENDORS["name"] == vname]
            if not row.empty:
                return row.iloc[0]
    # Fallback: return preferred_vendor from PARTS table
    part_row = PARTS[PARTS["name"] == part_name].iloc[0]
    return VENDORS[VENDORS["vendor_id"] == part_row["preferred_vendor"]].iloc[0]


def simulate_procurement(
    n_simulations=500,
    horizon_days=90,
    reorder_point_days=30,
    initial_stock_multiplier=3,
    seed=42,
    # CHANGE [SIM-1]: new parameter — dict of {part_name: vendor_name} or None
    vendor_override: dict | None = None,
):
    """
    Run Monte Carlo procurement simulation.

    Parameters
    ----------
    vendor_override : dict | None
        If provided, maps each part name to a vendor name string.
        These assignments override the frozen preferred_vendor from PARTS.
        Pass the output of dashboard.py's _build_vendor_override() to make
        utilization respond to scorecard scenario changes.
    """
    rng = np.random.default_rng(seed)
    results = []

    for _, part in PARTS.iterrows():
        # CHANGE [SIM-1]: use override if provided, else fall back to preferred_vendor
        if vendor_override and part["name"] in vendor_override:
            v_name  = vendor_override[part["name"]]
            v_row   = VENDORS[VENDORS["name"] == v_name]
            vendor  = v_row.iloc[0] if not v_row.empty else VENDORS[VENDORS["vendor_id"] == part["preferred_vendor"]].iloc[0]
        else:
            vendor  = VENDORS[VENDORS["vendor_id"] == part["preferred_vendor"]].iloc[0]

        daily_demand = _implied_daily_demand(part["name"])
        moq          = max(1, int(vendor["moq"]))
        lead_mean    = vendor["lead_time_days"]
        lead_std     = vendor["lead_time_std"] if pd.notna(vendor["lead_time_std"]) else 3.0
        moq_impact   = vendor["moq_impact_mean"]

        _part_vendor_rows = _RAW[
            (_RAW["Product Name"] == part["name"]) &
            (_RAW["Location Name"] == vendor["name"])
        ]
        if not _part_vendor_rows.empty:
            unit_total_cost = (
                _part_vendor_rows["total_cost"].sum() /
                max(1, _part_vendor_rows["Quantity Needed"].sum())
            )
        else:
            unit_total_cost = vendor["total_cost_mean"] / max(1, vendor["qty_needed_total"] / len(PARTS))

        vol_per_unit    = part["unit_volume_m3"]
        penalty_per_day = vendor["penalty_cost_day"]

        stockout_days    = 0
        total_orders     = 0
        total_units      = 0
        total_penalty    = 0.0
        total_peak_units = 0.0

        for _ in range(n_simulations):
            inventory          = moq * initial_stock_multiplier
            order_arriving_day = None
            order_qty          = 0
            sim_penalty        = 0.0
            sim_peak_units     = float(inventory)

            for day in range(horizon_days):
                consumed  = rng.poisson(daily_demand)
                inventory = max(0, inventory - consumed)

                if order_arriving_day is not None and day >= order_arriving_day:
                    inventory += order_qty
                    order_arriving_day = None

                if inventory < daily_demand * reorder_point_days and order_arriving_day is None:
                    lead               = max(1, int(rng.normal(lead_mean, lead_std)))
                    order_arriving_day = day + lead
                    order_qty          = max(moq, int(np.ceil(daily_demand * (lead + reorder_point_days))))
                    total_orders      += 1
                    total_units       += order_qty

                if inventory == 0:
                    stockout_days += 1
                    sim_penalty   += penalty_per_day

                sim_peak_units = max(sim_peak_units, float(inventory))

            total_penalty    += sim_penalty
            total_peak_units += sim_peak_units

        stockout_prob  = stockout_days / (n_simulations * horizon_days)
        avg_orders     = total_orders  / n_simulations
        avg_units      = total_units   / n_simulations
        avg_cost       = avg_units * unit_total_cost
        avg_penalty    = total_penalty / n_simulations
        avg_peak_units = total_peak_units / n_simulations
        peak_wh        = avg_peak_units * vol_per_unit

        results.append({
            "part_id":                part["part_id"],
            "part_name":              part["name"],
            "vendor":                 vendor["vendor_id"],
            "vendor_name":            vendor["name"],
            "criticality":            part["criticality"],
            "co2_emissions_total":    round(part["co2_emissions_total"], 1),
            "avg_total_cost_usd":     round(avg_cost, 0),
            "lead_time_days":         round(lead_mean, 1),
            "moq_impact":             round(moq_impact, 2),
            "stockout_risk_pct":      round(stockout_prob * 100, 2),
            "avg_orders_per_horizon": round(avg_orders, 1),
            "avg_penalty_cost_usd":   round(avg_penalty, 0),
            "peak_warehouse_m3":      round(peak_wh, 1),
            "daily_demand":           round(daily_demand, 1),
        })

    summary = pd.DataFrame(results)

    available_m3  = (
        WAREHOUSE["total_capacity_m3"]
        - WAREHOUSE["current_used_m3"]
        - WAREHOUSE["fifa_reserved_m3"]
    )
    total_peak_m3 = summary["peak_warehouse_m3"].sum()
    wh_utilization = round((total_peak_m3 / available_m3) * 100, 1)

    overflow_m3           = max(0, total_peak_m3 - available_m3)
    overflow_penalty_cost = overflow_m3 * 150

    total_cost    = summary["avg_total_cost_usd"].sum() + overflow_penalty_cost
    total_penalty = summary["avg_penalty_cost_usd"].sum() + overflow_penalty_cost
    total_co2     = summary["co2_emissions_total"].sum()

    return summary, wh_utilization, total_cost, total_penalty, total_co2


if __name__ == "__main__":
    df, util, cost, penalty, co2 = simulate_procurement()
    print(f"Warehouse utilization : {util}%")
    print(f"Total procurement cost (KPI 2): ${cost:,.0f}")
    print(f"Total penalty exposure        : ${penalty:,.0f}")
    print(f"Total CO2 emissions (KPI 1)   : {co2:,.0f} kg")
    print()
    print(df[[
        "part_name", "vendor", "daily_demand",
        "co2_emissions_total", "avg_total_cost_usd",
        "lead_time_days", "moq_impact",
        "stockout_risk_pct", "peak_warehouse_m3", "avg_penalty_cost_usd"
    ]].to_string(index=False))
