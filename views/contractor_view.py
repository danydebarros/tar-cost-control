"""Contractor view: per-contractor breakdown with drill-down to trades."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from components import COLORS, CONTRACTOR_COLORS, comparison_bar_chart


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Contractor View")

    # --- Summary table ---
    # Get DT hours if available
    has_dt = "actual_dt_hours" in comparison.columns

    agg_dict = {
        "est_hours": ("est_hours", "sum"),
        "actual_nt": ("actual_nt_hours", "sum"),
        "actual_ot": ("actual_ot_hours", "sum"),
        "actual_total": ("actual_total_hours", "sum"),
        "est_cost": ("est_cost", "sum"),
        "actual_cost": ("actual_total_cost", "sum"),
        "headcount": ("headcount", "sum"),
    }
    if has_dt:
        agg_dict["actual_dt"] = ("actual_dt_hours", "sum")
        agg_dict["actual_dt_cost"] = ("actual_dt_cost", "sum")

    contractor_summary = comparison.groupby("contractor").agg(**agg_dict).reset_index()

    contractor_summary["hours_variance"] = contractor_summary["est_hours"] - contractor_summary["actual_total"]
    contractor_summary["cost_variance"] = contractor_summary["est_cost"] - contractor_summary["actual_cost"]
    contractor_summary["ot_pct"] = np.where(
        contractor_summary["actual_total"] > 0,
        contractor_summary["actual_ot"] / contractor_summary["actual_total"] * 100, 0
    )
    contractor_summary["cost_var_pct"] = np.where(
        contractor_summary["est_cost"] > 0,
        contractor_summary["cost_variance"] / contractor_summary["est_cost"] * 100, 0
    )

    # Equipment/Other costs from session state
    equip_costs = {}
    equip_actuals = st.session_state.get("equip_actuals", {})
    equip_rates = st.session_state.get("equip_rates", {})
    for contractor in contractor_summary["contractor"]:
        c_equip = equip_actuals.get(contractor, {})
        c_rates = equip_rates.get(contractor, {})
        total = 0
        for item, hours_list in c_equip.items():
            rate = c_rates.get(item, 0)
            total += sum(hours_list) * rate
        equip_costs[contractor] = total
    contractor_summary["equip_cost"] = contractor_summary["contractor"].map(equip_costs).fillna(0)
    contractor_summary["total_with_equip"] = contractor_summary["actual_cost"] + contractor_summary["equip_cost"]

    display_cols = {
        "contractor": "Contractor",
        "est_hours": "Est Hours",
        "actual_nt": "NT Hours",
        "actual_ot": "OT Hours",
    }
    if has_dt:
        display_cols["actual_dt"] = "DT Hours"
    display_cols.update({
        "actual_total": "Total Hours",
        "est_cost": "Est Cost",
        "actual_cost": "Labor Cost",
        "equip_cost": "Equip/Other",
        "total_with_equip": "Total Cost",
        "cost_variance": "Cost Variance",
        "cost_var_pct": "Var %",
        "ot_pct": "OT %",
    })

    display = contractor_summary[list(display_cols.keys())].copy()
    display.columns = list(display_cols.values())

    # Add totals row
    totals = display.select_dtypes(include=[np.number]).sum()
    totals_row = pd.DataFrame([["TOTAL"] + totals.tolist()], columns=display.columns)
    # Recalculate percentages for total
    total_hours = totals_row["Total Hours"].values[0]
    total_est = totals_row["Est Cost"].values[0]
    if total_hours > 0:
        totals_row["OT %"] = totals_row["OT Hours"] / total_hours * 100
    if total_est > 0:
        totals_row["Var %"] = totals_row["Cost Variance"] / total_est * 100
    display = pd.concat([display, totals_row], ignore_index=True)

    fmt = {
            "Est Hours": "{:,.0f}",
            "NT Hours": "{:,.0f}",
            "OT Hours": "{:,.0f}",
            "Total Hours": "{:,.0f}",
            "Est Cost": "${:,.0f}",
            "Labor Cost": "${:,.0f}",
            "Equip/Other": "${:,.0f}",
            "Total Cost": "${:,.0f}",
    }
    if "DT Hours" in display.columns:
        fmt["DT Hours"] = "{:,.0f}"

    st.dataframe(
        display.style.format({**fmt,
            "Cost Variance": "${:+,.0f}",
            "Var %": "{:+.1f}%",
            "OT %": "{:.1f}%",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Cost Variance", "Var %"],
        ),
        use_container_width=True, hide_index=True, height=min(400, 56 + 35 * len(display)),
    )

    # --- Actual vs Estimate chart ---
    st.subheader("Actual vs Estimate")
    tab_cost, tab_hours = st.tabs(["Cost", "Hours"])
    with tab_cost:
        fig = comparison_bar_chart(comparison, "contractor", "cost")
        st.plotly_chart(fig, use_container_width=True)
    with tab_hours:
        fig = comparison_bar_chart(comparison, "contractor", "hours")
        st.plotly_chart(fig, use_container_width=True)

    # --- Drill-down per contractor ---
    st.subheader("Contractor Drill-Down")

    selected = st.selectbox(
        "Select contractor", sorted(cost_df["contractor"].unique()),
        key="contractor_drilldown"
    )

    cdf = cost_df[cost_df["contractor"] == selected]
    ccomp = comparison[comparison["contractor"] == selected]

    # Trade breakdown table
    trade_summary = ccomp[[
        "mapped_trade", "actual_nt_hours", "actual_ot_hours",
        "actual_total_hours", "actual_total_cost",
        "est_hours", "est_cost", "hours_variance", "cost_variance",
    ]].copy()
    trade_summary.columns = [
        "Trade", "NT Hours", "OT Hours", "Total Hours", "Actual Cost",
        "Est Hours", "Est Cost", "Hours Var", "Cost Var",
    ]
    trade_summary = trade_summary.sort_values("Actual Cost", ascending=False)

    st.dataframe(
        trade_summary.style.format({
            "NT Hours": "{:,.1f}",
            "OT Hours": "{:,.1f}",
            "Total Hours": "{:,.1f}",
            "Actual Cost": "${:,.0f}",
            "Est Hours": "{:,.0f}",
            "Est Cost": "${:,.0f}",
            "Hours Var": "{:+,.0f}",
            "Cost Var": "${:+,.0f}",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Hours Var", "Cost Var"],
        ),
        use_container_width=True, hide_index=True,
    )

    # Daily hours trend for selected contractor
    daily_c = cdf.groupby("date").agg(
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
        headcount=("person_id", "nunique"),
    ).reset_index().sort_values("date")

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_c["date"], y=daily_c["nt"], name="NT",
                             marker_color=COLORS["nt"]))
        fig.add_trace(go.Bar(x=daily_c["date"], y=daily_c["ot"], name="OT",
                             marker_color=COLORS["ot"]))
        fig.update_layout(barmode="stack", height=300, title=f"{selected} Daily Hours",
                          margin=dict(l=40, r=20, t=40, b=40),
                          plot_bgcolor="white", legend=dict(orientation="h", y=-0.2))
        fig.update_xaxes(gridcolor="#E8EAED")
        fig.update_yaxes(gridcolor="#E8EAED")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = go.Figure(go.Scatter(
            x=daily_c["date"], y=daily_c["headcount"],
            mode="lines+markers", marker_color=COLORS["primary"],
        ))
        fig2.update_layout(height=300, title=f"{selected} Daily Headcount",
                           margin=dict(l=40, r=20, t=40, b=40),
                           plot_bgcolor="white")
        fig2.update_xaxes(gridcolor="#E8EAED")
        fig2.update_yaxes(gridcolor="#E8EAED")
        st.plotly_chart(fig2, use_container_width=True)
