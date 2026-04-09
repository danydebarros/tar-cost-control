"""
Date-based estimate calculations.
Computes planned costs up to any given date from the daily estimate schedule.
"""

import pandas as pd
from config import DAILY_ESTIMATE_COSTS


def estimate_to_date(cutoff_date, contractor: str = None) -> dict:
    """Get cumulative estimated cost up to cutoff_date.

    Returns dict with labor, other, equipment, total for each contractor
    and a grand total.
    """
    cutoff = pd.Timestamp(cutoff_date).strftime("%Y-%m-%d")
    result = {}

    contractors = [contractor] if contractor else list(DAILY_ESTIMATE_COSTS.keys())

    for c in contractors:
        est = DAILY_ESTIMATE_COSTS.get(c, {})
        daily = est.get("daily", {})
        labor = other = equip = 0
        for dt, costs in daily.items():
            if dt <= cutoff:
                labor += costs["labor"]
                other += costs["other"]
                equip += costs["equipment"]

        result[c] = {
            "labor": round(labor, 2),
            "other": round(other, 2),
            "equipment": round(equip, 2),
            "total": round(labor + other + equip, 2),
            "total_budget_labor": est.get("total_labor", 0),
            "total_budget_other": est.get("total_other", 0),
            "total_budget_equipment": est.get("total_equipment", 0),
            "total_budget": est.get("total", 0),
        }

    return result


def estimate_summary_to_date(cutoff_date) -> dict:
    """Get aggregate estimate totals across all contractors up to cutoff_date."""
    by_contractor = estimate_to_date(cutoff_date)
    totals = {"labor": 0, "other": 0, "equipment": 0, "total": 0,
              "total_budget_labor": 0, "total_budget_other": 0,
              "total_budget_equipment": 0, "total_budget": 0}
    for c, v in by_contractor.items():
        for k in totals:
            totals[k] += v[k]
    return {"by_contractor": by_contractor, "totals": totals}


def estimate_daily_series(contractor: str = None) -> pd.DataFrame:
    """Get daily estimated cost as a time series for charting.

    Returns DataFrame with columns: date, contractor, labor, other, equipment, total,
    cum_labor, cum_other, cum_equipment, cum_total.
    """
    rows = []
    contractors = [contractor] if contractor else list(DAILY_ESTIMATE_COSTS.keys())

    for c in contractors:
        est = DAILY_ESTIMATE_COSTS.get(c, {})
        cum_labor = cum_other = cum_equip = 0
        for dt, costs in sorted(est.get("daily", {}).items()):
            cum_labor += costs["labor"]
            cum_other += costs["other"]
            cum_equip += costs["equipment"]
            rows.append({
                "date": pd.Timestamp(dt),
                "contractor": c,
                "est_labor": costs["labor"],
                "est_other": costs["other"],
                "est_equipment": costs["equipment"],
                "est_total": costs["total"],
                "cum_est_labor": cum_labor,
                "cum_est_other": cum_other,
                "cum_est_equipment": cum_equip,
                "cum_est_total": cum_labor + cum_other + cum_equip,
            })

    return pd.DataFrame(rows)
