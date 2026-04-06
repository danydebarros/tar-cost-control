"""Executive Summary view: KPIs, top overruns, OT%, forecast position."""

import streamlit as st
import pandas as pd
import numpy as np
from components import (
    metric_row, comparison_bar_chart, ot_percentage_chart,
    daily_cost_chart, COLORS,
)


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame, forecast_df: pd.DataFrame):
    st.header("Executive Summary")

    # --- Top-level KPIs ---
    total_est_hours = comparison["est_hours"].sum()
    total_act_hours = comparison["actual_total_hours"].sum()
    total_est_cost = comparison["est_cost"].sum()
    total_act_cost = comparison["actual_total_cost"].sum()
    total_ot_hours = comparison["actual_ot_hours"].sum()
    ot_pct = (total_ot_hours / total_act_hours * 100) if total_act_hours > 0 else 0
    hours_var = total_est_hours - total_act_hours
    cost_var = total_est_cost - total_act_cost

    # Forecast totals
    if forecast_df is not None and len(forecast_df) > 0:
        forecast_eac = forecast_df["eac_cost"].sum()
        forecast_var = total_est_cost - forecast_eac
    else:
        forecast_eac = total_act_cost
        forecast_var = cost_var

    metric_row([
        {"label": "Estimated Hours", "value": total_est_hours},
        {"label": "Actual Hours", "value": total_act_hours,
         "delta": f"{hours_var:+,.0f} remaining"},
        {"label": "Estimated Cost", "value": total_est_cost, "prefix": "$"},
        {"label": "Actual Cost", "value": total_act_cost, "prefix": "$",
         "delta": f"${cost_var:+,.0f} under" if cost_var >= 0 else f"${cost_var:+,.0f} OVER"},
        {"label": "OT %", "value": ot_pct, "prefix": "%"},
    ])

    st.divider()

    metric_row([
        {"label": "Forecast EAC", "value": forecast_eac, "prefix": "$"},
        {"label": "Forecast Variance", "value": forecast_var, "prefix": "$",
         "delta": "Under budget" if forecast_var >= 0 else "OVER BUDGET",
         "delta_color": "normal" if forecast_var >= 0 else "inverse"},
        {"label": "Hours Burned %",
         "value": (total_act_hours / total_est_hours * 100) if total_est_hours > 0 else 0,
         "prefix": "%"},
        {"label": "Cost Burned %",
         "value": (total_act_cost / total_est_cost * 100) if total_est_cost > 0 else 0,
         "prefix": "%"},
    ])

    st.divider()

    # --- Charts row ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Actual vs Estimate by Contractor")
        fig = comparison_bar_chart(comparison, "contractor", "cost")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("OT % by Contractor")
        fig = ot_percentage_chart(comparison, "contractor")
        st.plotly_chart(fig, use_container_width=True)

    # --- Cumulative cost trend ---
    st.subheader("Daily Cost Trend")
    fig = daily_cost_chart(cost_df)
    st.plotly_chart(fig, use_container_width=True)

    # --- Top overruns ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top Contractor Overruns (Cost)")
        overruns = comparison.groupby("contractor").agg(
            actual=("actual_total_cost", "sum"),
            estimate=("est_cost", "sum"),
        ).reset_index()
        overruns["variance"] = overruns["estimate"] - overruns["actual"]
        overruns["variance_pct"] = np.where(
            overruns["estimate"] > 0,
            overruns["variance"] / overruns["estimate"] * 100, 0
        )
        overruns = overruns.sort_values("variance").head(5)

        display = overruns[["contractor", "estimate", "actual", "variance", "variance_pct"]].copy()
        display.columns = ["Contractor", "Estimate", "Actual", "Variance ($)", "Variance %"]
        st.dataframe(
            display.style.format({
                "Estimate": "${:,.0f}",
                "Actual": "${:,.0f}",
                "Variance ($)": "${:+,.0f}",
                "Variance %": "{:+.1f}%",
            }).map(
                lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Variance ($)", "Variance %"],
            ),
            use_container_width=True, hide_index=True,
        )

    with col2:
        st.subheader("Top Trade Overruns (Cost)")
        trade_overruns = comparison.groupby("mapped_trade").agg(
            actual=("actual_total_cost", "sum"),
            estimate=("est_cost", "sum"),
        ).reset_index()
        trade_overruns["variance"] = trade_overruns["estimate"] - trade_overruns["actual"]
        trade_overruns["variance_pct"] = np.where(
            trade_overruns["estimate"] > 0,
            trade_overruns["variance"] / trade_overruns["estimate"] * 100, 0
        )
        trade_overruns = trade_overruns.sort_values("variance").head(5)

        display = trade_overruns[["mapped_trade", "estimate", "actual", "variance", "variance_pct"]].copy()
        display.columns = ["Trade", "Estimate", "Actual", "Variance ($)", "Variance %"]
        st.dataframe(
            display.style.format({
                "Estimate": "${:,.0f}",
                "Actual": "${:,.0f}",
                "Variance ($)": "${:+,.0f}",
                "Variance %": "{:+.1f}%",
            }).map(
                lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Variance ($)", "Variance %"],
            ),
            use_container_width=True, hide_index=True,
        )
