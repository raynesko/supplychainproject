"""
simulation.py
Monte Carlo procurement simulation using real NJTransit data.
Models lead time variability (KPI 3) over a 90-day FIFA 2026 service window.

KPIs used:
  KPI 2 – Total Cost drives avg_total_cost_usd (purchase + shipping + in-transit)
  KPI 3 – Lead Time (days) drives stockout risk via reorder-point logic
  KPI 4 – MOQ Impact informs order frequency and stockout exposure

CHANGES vs previous version:
  [1] daily_demand: was monthly_demand / 30, where monthly_demand = total_qty_sum / 3.
      That treats sum-of-all-order-quantities as if it were 3 months of consumption,
      yielding ~150-196 units/day — physically implausible for transit maintenance
      parts and 41× higher than MOQ coverage (MOQ only lasted ~1.5 days).
      Fix: derive daily demand from Quantity Needed / Lead Time (days) per order row,
      then average across rows for that product. This uses the data's own logic —
      each order's quantity is sized to cover its lead time — and gives ~17-36
      units/day with MOQ covering 9-17 days, which is realistic.

  [2] initial_inventory: was 1×MOQ. With corrected daily demand, 1×MOQ lasts 9-17
      days, so a 90-day simulation starting at 1×MOQ will immediately reorder and
      still run dry during the first lead time. Fix: start at 3×MOQ (~30-50 days of
      coverage), representing a realistic pre-event stock-up for FIFA 2026.

  [3] order_qty: was always 1×MOQ regardless of lead time. For parts where
      daily_demand × lead_time > MOQ (common here), ordering just 1×MOQ means
      the replenishment arrives but is consumed within 1-2 days, causing chronic
      near-stockout. Fix: order max(MOQ, ceil(daily_demand × (lead_time + reorder_days)))
      — standard reorder-point logic that ensures each order covers the full
      lead time gap plus the reorder buffer.

  [4] peak_warehouse_m3: was avg_total_units_ordered × vol × 0.3 (throughput proxy
      with arbitrary 0.3 dampener). Fix: track max concurrent inventory day-by-day
      within each simulation run and average that across simulations. This is what
      warehouse space planning actually requires.
"""

import numpy as np
import pandas as pd
from vendor_data import VENDORS, PARTS, WAREHOUSE

# Load raw data once for implied-demand calculation
_RAW = pd.read_excel("NJTransit_FIFA2026_Synthetic_Data.xlsx")


def _implied_daily_demand(product_name: str) -> float:
    """
    Estimate daily consumption rate from procurement data.
    Uses Quantity Needed / Lead Time (days) per order row, averaged across orders.
    This leverages the data's own sizing logic rather than treating order totals
    as monthly consumption figures.
    """
    rows = _RAW[_RAW["Product Name"] == product_name]
    if rows.empty:
        return 10.0
    return (rows["Quantity Needed"] / rows["Lead Time (days)"].replace(0, np.nan)).mean()


def simulate_procurement(
    n_simulations=500,
    horizon_days=90,
    reorder_point_days=7,
    initial_stock_multiplier=3,
    seed=42,
):
    rng = np.random.default_rng(seed)
    results = []

    for _, part in PARTS.iterrows():
        vendor = VENDORS[VENDORS["vendor_id"] == part["preferred_vendor"]].iloc[0]

        # [FIX 1]: use implied daily demand from qty/lead_time, not total_qty/3/30
        daily_demand = _implied_daily_demand(part["name"])
        moq          = max(1, int(vendor["moq"]))

        # KPI 3: Lead Time
        lead_mean = vendor["lead_time_days"]
        lead_std  = vendor["lead_time_std"] if pd.notna(vendor["lead_time_std"]) else 3.0

        # KPI 4: MOQ Impact
        moq_impact = vendor["moq_impact_mean"]

        # KPI 2: unit-level total cost
        unit_total_cost = vendor["total_cost_mean"] / max(1, vendor["qty_needed_total"] / len(PARTS))
        vol_per_unit    = part["unit_volume_m3"]
        penalty_per_day = vendor["penalty_cost_day"]

        stockout_days    = 0
        total_orders     = 0
        total_units      = 0
        total_penalty    = 0.0
        total_peak_units = 0.0  # [FIX 4]: accumulate concurrent peak per simulation

        for _ in range(n_simulations):
            # [FIX 2]: start with 3×MOQ — represents FIFA pre-event stock-up
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
                    # KPI 3: stochastic lead time
                    lead = max(1, int(rng.normal(lead_mean, lead_std)))
                    order_arriving_day = day + lead
                    # [FIX 3]: order enough to cover lead time + reorder buffer
                    order_qty    = max(moq, int(np.ceil(daily_demand * (lead + reorder_point_days))))
                    total_orders += 1
                    total_units  += order_qty

                if inventory == 0:
                    stockout_days += 1
                    sim_penalty   += penalty_per_day

                # [FIX 4]: track actual peak concurrent inventory
                sim_peak_units = max(sim_peak_units, float(inventory))

            total_penalty    += sim_penalty
            total_peak_units += sim_peak_units

        stockout_prob  = stockout_days / (n_simulations * horizon_days)
        avg_orders     = total_orders  / n_simulations
        avg_units      = total_units   / n_simulations
        avg_cost       = avg_units * unit_total_cost
        avg_penalty    = total_penalty / n_simulations
        # [FIX 4]: peak_warehouse = avg max concurrent units × volume per unit
        avg_peak_units = total_peak_units / n_simulations
        peak_wh        = avg_peak_units * vol_per_unit

        results.append({
            "part_id":                part["part_id"],
            "part_name":              part["name"],
            "vendor":                 vendor["vendor_id"],
            "vendor_name":            vendor["name"],
            "criticality":            part["criticality"],
            # KPI 1
            "co2_emissions_total":    round(part["co2_emissions_total"], 1),
            # KPI 2
            "avg_total_cost_usd":     round(avg_cost, 0),
            # KPI 3
            "lead_time_days":         round(lead_mean, 1),
            # KPI 4
            "moq_impact":             round(moq_impact, 2),
            # Simulation outputs
            "stockout_risk_pct":      round(stockout_prob * 100, 2),
            "avg_orders_per_horizon": round(avg_orders, 1),
            "avg_penalty_cost_usd":   round(avg_penalty, 0),
            # [FIX 4]: actual concurrent peak, not throughput-based proxy
            "peak_warehouse_m3":      round(peak_wh, 1),
            # expose implied daily demand for debugging/display
            "daily_demand":           round(daily_demand, 1),
        })

    summary = pd.DataFrame(results)

    available_m3  = (
        WAREHOUSE["total_capacity_m3"]
        - WAREHOUSE["current_used_m3"]
        - WAREHOUSE["fifa_reserved_m3"]
    )
    total_peak_m3 = summary["peak_warehouse_m3"].sum()

    # Utilization = actual concurrent peak / available space — now varies with vendor mix
    wh_utilization = round((total_peak_m3 / available_m3) * 100, 1)

    # Overflow penalty: $150/m3 for emergency 3rd-party storage
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
