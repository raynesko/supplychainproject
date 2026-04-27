"""
scorecard.py  (v2 — Social Pillar Refactor)
Weighted multi-criteria sustainability scorecard using real NJTransit data.
Scores each vendor 0-100 on Environmental, Economic, and Social pillars.

KPIs powering each pillar:
  Environmental  → KPI 1 (CO2 Emissions), on-time rate
  Economic       → KPI 2 (Total Cost), KPI 4 (MOQ Impact), carrying cost, penalty cost
  Social         → labor rights, safety (TRIR inverted), community/diversity,
                   transparency, domestic sourcing bonus

CHANGES FROM v1 (Social Pillar Refactor):
─────────────────────────────────────────────────────────────────────────────
  [SOC-1] REPLACED the three binary social signals (is_domestic / has_iso14001 /
          diversity_cert) with four continuous, semantically correct social KPIs
          sourced from the enriched dataset:

          Sub-weight  KPI column (from VENDORS)      Direction
          0.30        social_labor_score              higher = better (already 0-100)
          0.30        social_safety_trir              lower = better → inverted via normalize()
          0.25        social_community_score          higher = better (already 0-100)
          0.15        social_transparency             higher = better (already 0-100)

  [SOC-2] is_domestic retained as an ADDITIVE BONUS (+5 pts, capped at 100) on
          top of the four-KPI social score. Rationale: the brief asks for social
          scoring that considers whether the vendor is a domestic (American)
          company, but domestic origin should supplement — not dominate — genuine
          labor/safety/community measures.

  [SOC-3] has_iso14001 and diversity_cert parameters REMOVED from the function
          signature (they were CO2 and competitive_flag proxies, not real social
          signals). Any callers that passed those kwargs will need to remove them.

  [SOC-4] score_vendors() signature sub-weight defaults updated:
          w_labor=0.30, w_safety=0.30, w_community=0.25, w_transparency=0.15
          Total = 1.0 (no change to outer pillar weights).
"""

import pandas as pd
import numpy as np
from vendor_data_v2 import VENDORS
from simulation_v2 import simulate_procurement


def normalize(series, invert=False):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    norm = (series - mn) / (mx - mn) * 100
    return (100 - norm) if invert else norm


def score_vendors(
    w_env=0.33, w_econ=0.33, w_soc=0.34,
    # Environmental sub-weights
    w_carbon=0.70, w_ontime=0.30,
    # Economic sub-weights
    w_totalcost=0.45, w_moq_impact=0.20, w_carrying=0.20, w_penalty=0.15,
    # CHANGE [SOC-1 / SOC-4]: social sub-weights now map to four real KPIs
    w_labor=0.30,         # Social_LaborRights_Score (higher = better)
    w_safety=0.30,        # Social_Safety_TRIR (lower = better → inverted)
    w_community=0.25,     # Social_CommunityDiversity_Score (higher = better)
    w_transparency=0.15,  # Social_Transparency_Index (higher = better)
    # Simulation penalty — passed in from dashboard to avoid re-running Monte Carlo
    sim_penalty_by_vendor=None,
):
    df = VENDORS.copy()

    # ── Environmental pillar ──────────────────────────────────────────────────
    carbon_score = normalize(df["co2_emissions_total"], invert=True)
    ontime_score = normalize(df["on_time_rate"])
    df["score_env"] = w_carbon * carbon_score + w_ontime * ontime_score

    # ── Economic pillar ───────────────────────────────────────────────────────
    total_cost_score = normalize(df["total_cost_total"],  invert=True)
    moq_score        = normalize(df["moq_impact_mean"],   invert=True)
    carrying_score   = normalize(df["carrying_cost"],     invert=True)

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
    # CHANGE [SOC-1]: four continuous social KPIs replace three binary proxies
    labor_score       = normalize(df["social_labor_score"])               # higher = better
    safety_score      = normalize(df["social_safety_trir"], invert=True)  # lower TRIR = better → invert
    community_score   = normalize(df["social_community_score"])           # higher = better
    transparency_score = normalize(df["social_transparency"])             # higher = better

    raw_social = (
        w_labor        * labor_score +
        w_safety       * safety_score +
        w_community    * community_score +
        w_transparency * transparency_score
    )

    # CHANGE [SOC-2]: domestic bonus — +5 pts for US-based vendors, capped at 100
    domestic_bonus = df["is_domestic"].astype(float) * 5
    df["score_soc"] = (raw_social + domestic_bonus).clip(upper=100)

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
        # KPI values for tooltip / drill-down
        "co2_emissions_total", "total_cost_total",
        "lead_time_days", "moq_impact_mean",
        # CHANGE [SOC-3]: expose the four real social KPIs instead of binary flags
        "is_domestic",
        "social_labor_score", "social_safety_trir",
        "social_community_score", "social_transparency",
    ]
    return df[cols].sort_values("score_composite", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    results = score_vendors()
    print(results[[
        "name", "is_domestic",
        "social_labor_score", "social_safety_trir",
        "social_community_score", "social_transparency",
        "score_env", "score_econ", "score_soc", "score_composite"
    ]].to_string(index=False))
