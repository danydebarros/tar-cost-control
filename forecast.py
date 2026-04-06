"""
Forecast engine: EAC calculations with multiple methods and manual overrides.
"""

import pandas as pd
import numpy as np


def calculate_forecast(
    comparison: pd.DataFrame,
    cost_df: pd.DataFrame,
    method: str = "current_performance",
    productivity_factor: float = 1.0,
    burn_rate_factor: float = 1.0,
    manual_overrides: dict = None,
    project_end: str = "2026-05-04",
) -> pd.DataFrame:
    """Calculate Estimate at Completion (EAC) using selected method.

    Methods:
    - current_performance: EAC = Actual + (Est Remaining / Productivity Factor)
    - manual: Use manual remaining hours/cost overrides
    - hybrid: Use manual where provided, current performance otherwise

    Returns DataFrame with forecast columns added to comparison data.
    """
    fc = comparison.copy()
    manual_overrides = manual_overrides or {}

    # Remaining estimate hours
    fc["est_remaining_hours"] = (fc["est_hours"] - fc["actual_total_hours"]).clip(lower=0)
    fc["est_remaining_cost"] = (fc["est_cost"] - fc["actual_total_cost"]).clip(lower=0)

    # Percent complete
    fc["pct_hours_complete"] = np.where(
        fc["est_hours"] > 0,
        (fc["actual_total_hours"] / fc["est_hours"]).clip(upper=1.0) * 100,
        0,
    )
    fc["pct_cost_complete"] = np.where(
        fc["est_cost"] > 0,
        (fc["actual_total_cost"] / fc["est_cost"]).clip(upper=1.0) * 100,
        0,
    )

    if method == "current_performance":
        # Forecast remaining = est remaining / productivity factor * burn rate
        fc["forecast_remaining_hours"] = (
            fc["est_remaining_hours"] / productivity_factor * burn_rate_factor
        )
        # EAC cost: use blended actual rate for remaining hours
        fc["blended_rate"] = np.where(
            fc["actual_total_hours"] > 0,
            fc["actual_total_cost"] / fc["actual_total_hours"],
            0,
        )
        fc["forecast_remaining_cost"] = fc["forecast_remaining_hours"] * fc["blended_rate"]

    elif method == "manual":
        fc["forecast_remaining_hours"] = fc["est_remaining_hours"]
        fc["forecast_remaining_cost"] = fc["est_remaining_cost"]

        # Apply manual overrides
        for key, override in manual_overrides.items():
            contractor, trade = key
            mask = (fc["contractor"] == contractor) & (fc["mapped_trade"] == trade)
            if mask.any():
                if "remaining_hours" in override:
                    fc.loc[mask, "forecast_remaining_hours"] = override["remaining_hours"]
                    # Re-calc cost with blended rate
                    blended = fc.loc[mask, "actual_total_cost"].values[0] / max(
                        fc.loc[mask, "actual_total_hours"].values[0], 1
                    )
                    fc.loc[mask, "forecast_remaining_cost"] = (
                        override["remaining_hours"] * blended
                    )
                if "remaining_cost" in override:
                    fc.loc[mask, "forecast_remaining_cost"] = override["remaining_cost"]

    elif method == "hybrid":
        # Start with current performance, then apply manual overrides
        fc["forecast_remaining_hours"] = (
            fc["est_remaining_hours"] / productivity_factor * burn_rate_factor
        )
        fc["blended_rate"] = np.where(
            fc["actual_total_hours"] > 0,
            fc["actual_total_cost"] / fc["actual_total_hours"],
            0,
        )
        fc["forecast_remaining_cost"] = fc["forecast_remaining_hours"] * fc["blended_rate"]

        for key, override in (manual_overrides or {}).items():
            contractor, trade = key
            mask = (fc["contractor"] == contractor) & (fc["mapped_trade"] == trade)
            if mask.any():
                if "remaining_hours" in override:
                    fc.loc[mask, "forecast_remaining_hours"] = override["remaining_hours"]
                    blended = fc.loc[mask, "blended_rate"].values[0]
                    fc.loc[mask, "forecast_remaining_cost"] = (
                        override["remaining_hours"] * blended
                    )
                if "remaining_cost" in override:
                    fc.loc[mask, "forecast_remaining_cost"] = override["remaining_cost"]

    # EAC
    fc["eac_hours"] = fc["actual_total_hours"] + fc["forecast_remaining_hours"]
    fc["eac_cost"] = fc["actual_total_cost"] + fc["forecast_remaining_cost"]

    # Forecast variance to estimate
    fc["forecast_hours_variance"] = fc["est_hours"] - fc["eac_hours"]
    fc["forecast_cost_variance"] = fc["est_cost"] - fc["eac_cost"]

    # OT exposure (forecast OT based on current OT ratio)
    fc["current_ot_ratio"] = np.where(
        fc["actual_total_hours"] > 0,
        fc["actual_ot_hours"] / fc["actual_total_hours"],
        0,
    )
    fc["forecast_ot_hours"] = fc["actual_ot_hours"] + (
        fc["forecast_remaining_hours"] * fc["current_ot_ratio"]
    )

    return fc


def get_daily_burn_rate(cost_df: pd.DataFrame, trailing_days: int = 7) -> pd.DataFrame:
    """Calculate rolling daily burn rate for trend analysis."""
    daily = cost_df.groupby("date").agg(
        daily_hours=("total_hours", "sum"),
        daily_cost=("total_cost", "sum"),
        daily_nt=("nt_hours", "sum"),
        daily_ot=("ot_hours", "sum"),
        headcount=("person_id", "nunique"),
    ).reset_index().sort_values("date")

    daily["cum_hours"] = daily["daily_hours"].cumsum()
    daily["cum_cost"] = daily["daily_cost"].cumsum()
    daily["rolling_avg_hours"] = daily["daily_hours"].rolling(
        trailing_days, min_periods=1
    ).mean()
    daily["rolling_avg_cost"] = daily["daily_cost"].rolling(
        trailing_days, min_periods=1
    ).mean()

    return daily
