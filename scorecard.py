"""
scorecard.py
Weighted multi-criteria sustainability scorecard using real NJTransit data.
Scores each vendor 0-100 on Environmental, Economic, and Social pillars.

KPIs powering each pillar:
  Environmental  → KPI 1 (CO2 Emissions), on-time rate, transit speed
  Economic       → KPI 2 (Total Cost), KPI 4 (MOQ Impact), carrying cost, penalty cost
  Social         → domestic sourcing (US vs. non-US), ISO proxy, diversity cert

CHANGES vs previous version:
  [1] Social pillar: w_domestic now uses is_domestic (US company = True) as the
      PRIMARY social signal (weight 0.50), replacing the old has_iso14001 anchor.
      Rationale: the brief explicitly asks for social scoring based on whether the
      vendor is a domestic (American) company. is_domestic is sourced from vendor
      name patterns — all NJ Transit facility vendors = True, Global EuroParts = False.
  [2] has_iso14001 retained as a secondary signal (weight 0.30) — it's an
      environmental-proxy (low CO2/kg + good on-time rate) that the social pillar
      can reasonably reward.
  [3] diversity_cert retained as tertiary signal (weight 0.20).
"""

import pandas as pd
import numpy as np
from vendor_data import VENDORS
from simulation import simulate_procurement


def normalize(series, invert=False):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 100
    return (100 - norm) if invert else norm


# AFTER
def score_vendors(
    w_env=0.33, w_econ=0.33, w_soc=0.34,
    # Environmental sub-weights
    w_carbon=0.70, w_ontime=0.30,
    # Economic sub-weights
    w_totalcost=0.45, w_moq_impact=0.20, w_carrying=0.20, w_penalty=0.15,
    # Social sub-weights
    w_domestic=0.50, w_iso=0.30, w_diversity=0.20,
    # Simulation penalty — passed in from dashboard to avoid re-running Monte Carlo
    sim_penalty_by_vendor=None,
):
    df = VENDORS.copy()

    # ── Environmental pillar ──────────────────────────────────────────────────
    # KPI 1: CO2 Emissions = CO2/kg × weight × qty  (lower → invert)
    carbon_score  = normalize(df["co2_emissions_total"], invert=True)
    ontime_score  = normalize(df["on_time_rate"])
    
    df["score_env"] = (
        w_carbon        * carbon_score +
        w_ontime        * ontime_score 
        
    )

    # ── Economic pillar ───────────────────────────────────────────────────────
    # KPI 2: Total Cost  (lower → invert)
    total_cost_score = normalize(df["total_cost_total"],  invert=True)
    # KPI 4: MOQ Impact = MOQ / Qty  (lower ratio = more flexible → invert)
    moq_score        = normalize(df["moq_impact_mean"],   invert=True)
    carrying_score   = normalize(df["carrying_cost"],     invert=True)
    # AFTER
    if sim_penalty_by_vendor is not None:
        df = df.merge(sim_penalty_by_vendor, on="vendor_id", how="left")
        df["sim_penalty"] = df["sim_penalty"].fillna(0)
        penalty_score = normalize(df["sim_penalty"], invert=True)
    else:
        penalty_score = normalize(df["penalty_cost_day"], invert=True)
    df["score_econ"] = (
        w_totalcost  * total_cost_score +
        w_moq_impact * moq_score +
        w_carrying   * carrying_score +
        w_penalty    * penalty_score
    )

    # ── Social pillar ─────────────────────────────────────────────────────────
    # [FIX 1] Primary: domestic sourcing (US company = 100, non-US = 0)
    domestic_score  = df["is_domestic"].astype(float) * 100
    iso_score       = df["has_iso14001"].astype(float) * 100
    diversity_score = df["diversity_cert"].astype(float) * 100
    df["score_soc"] = (
        w_domestic  * domestic_score +
        w_iso       * iso_score +
        w_diversity * diversity_score
    )

    # ── Composite ─────────────────────────────────────────────────────────────
    total = (w_env or 0.01) + (w_econ or 0.01) + (w_soc or 0.01)
    df["score_composite"] = (
        (w_env  / total) * df["score_env"] +
        (w_econ / total) * df["score_econ"] +
        (w_soc  / total) * df["score_soc"]
    )

    cols = [
        "vendor_id", "name",
        "score_env", "score_econ", "score_soc", "score_composite",
        # expose KPI values for tooltip / drill-down
        "co2_emissions_total", "total_cost_total",
        "lead_time_days", "moq_impact_mean",
        # social signals — useful for drill-down display
        "is_domestic", "has_iso14001", "diversity_cert",
    ]
    return df[cols].sort_values("score_composite", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    results = score_vendors()
    print(results[[
        "name", "is_domestic", "score_env", "score_econ",
        "score_soc", "score_composite"
    ]].to_string(index=False))
