"""Contractor view: per-contractor breakdown with drill-down to trades."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from components import COLORS, CONTRACTOR_COLORS, comparison_bar_chart
from estimate import estimate_to_date


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Contractor View")

    has_dt = "actual_dt_hours" in comparison.columns
    last_actual = cost_df["date"].max().date()

    # Date-based estimate cutoff
    col_d, _ = st.columns([1, 3])
    with col_d:
        cutoff = st.date_input("Estimate as at", value=last_actual, key="cv_cutoff")

    est_by_contractor = estimate_to_date(cutoff)

    # --- Summary table ---
    agg_dict = {
        "actual_nt": ("actual_nt_hours", "sum"),
        "actual_ot": ("actual_ot_hours", "sum"),
        "actual_total": ("actual_total_hours", "sum"),
        "actual_cost": ("actual_total_cost", "sum"),
        "headcount": ("headcount", "sum"),
    }
    if has_dt:
        agg_dict["actual_dt"] = ("actual_dt_hours", "sum")

    contractor_summary = comparison.groupby("contractor").agg(**agg_dict).reset_index()

    # Add date-based estimates
    contractor_summary["est_labor"] = contractor_summary["contractor"].map(
        lambda c: est_by_contractor.get(c, {}).get("labor", 0))
    contractor_summary["est_other"] = contractor_summary["contractor"].map(
        lambda c: est_by_contractor.get(c, {}).get("other", 0))
    contractor_summary["est_equip"] = contractor_summary["contractor"].map(
        lambda c: est_by_contractor.get(c, {}).get("equipment", 0))
    contractor_summary["est_total"] = (
        contractor_summary["est_labor"] + contractor_summary["est_other"] + contractor_summary["est_equip"]
    )
    contractor_summary["budget"] = contractor_summary["contractor"].map(
        lambda c: est_by_contractor.get(c, {}).get("total_budget", 0))

    # Equipment/Other actuals from session state
    equip_actuals = st.session_state.get("equip_actuals", {})
    equip_rates = st.session_state.get("equip_rates", {})
    def _equip_cost(c):
        c_act = equip_actuals.get(c, {})
        c_rates = equip_rates.get(c, {})
        return sum(sum(hrs) * c_rates.get(item, 0) for item, hrs in c_act.items())
    contractor_summary["equip_actual"] = contractor_summary["contractor"].map(_equip_cost)
    contractor_summary["total_actual"] = contractor_summary["actual_cost"] + contractor_summary["equip_actual"]

    # Variances
    contractor_summary["labor_var"] = contractor_summary["est_labor"] - contractor_summary["actual_cost"]
    contractor_summary["total_var"] = contractor_summary["est_total"] - contractor_summary["total_actual"]
    contractor_summary["var_pct"] = np.where(
        contractor_summary["est_total"] > 0,
        contractor_summary["total_var"] / contractor_summary["est_total"] * 100, 0
    )
    contractor_summary["ot_pct"] = np.where(
        contractor_summary["actual_total"] > 0,
        contractor_summary["actual_ot"] / contractor_summary["actual_total"] * 100, 0
    )

    # Build display
    cols = ["contractor", "actual_nt", "actual_ot"]
    names = ["Contractor", "NT Hours", "OT Hours"]
    if has_dt:
        cols.append("actual_dt")
        names.append("DT Hours")
    cols += ["actual_total", "actual_cost", "equip_actual",
             "est_labor", "est_other", "est_equip", "est_total",
             "budget", "labor_var", "total_var", "var_pct", "ot_pct"]
    names += ["Total Hours", "Labor Cost", "Equip/Other Actual",
              "Est Labor", "Est Other", "Est Equip/Other", "Est Total (to date)",
              "Budget (Total)", "Labor Var", "Total Var", "Var %", "OT %"]

    display = contractor_summary[cols].copy()
    display.columns = names

    # Totals row
    totals = display.select_dtypes(include=[np.number]).sum()
    tot_row = pd.DataFrame([["TOTAL"] + totals.tolist()], columns=display.columns)
    if totals["Total Hours"] > 0:
        tot_row["OT %"] = totals["OT Hours"] / totals["Total Hours"] * 100
    if totals["Est Total (to date)"] > 0:
        tot_row["Var %"] = totals["Total Var"] / totals["Est Total (to date)"] * 100
    display = pd.concat([display, tot_row], ignore_index=True)

    fmt = {
        "NT Hours": "{:,.0f}", "OT Hours": "{:,.0f}", "Total Hours": "{:,.0f}",
        "Labor Cost": "${:,.0f}", "Equip/Other Actual": "${:,.0f}",
        "Est Labor": "${:,.0f}", "Est Other": "${:,.0f}", "Est Equip/Other": "${:,.0f}",
        "Est Total (to date)": "${:,.0f}", "Budget (Total)": "${:,.0f}",
        "Labor Var": "${:+,.0f}", "Total Var": "${:+,.0f}",
        "Var %": "{:+.1f}%", "OT %": "{:.1f}%",
    }
    if "DT Hours" in display.columns:
        fmt["DT Hours"] = "{:,.0f}"

    st.dataframe(
        display.style.format(fmt).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Labor Var", "Total Var", "Var %"],
        ),
        use_container_width=True, hide_index=True,
        height=min(450, 56 + 35 * len(display)),
    )

    # --- Actual vs Estimate chart ---
    st.subheader("Actual vs Estimate (to date)")
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
    trade_cols = ["mapped_trade", "actual_nt_hours", "actual_ot_hours"]
    trade_names = ["Trade", "NT Hours", "OT Hours"]
    if has_dt and "actual_dt_hours" in ccomp.columns:
        trade_cols.append("actual_dt_hours")
        trade_names.append("DT Hours")
    trade_cols += ["actual_total_hours", "actual_total_cost",
                   "est_hours", "est_cost", "hours_variance", "cost_variance"]
    trade_names += ["Total Hours", "Actual Cost", "Est Hours", "Est Cost", "Hours Var", "Cost Var"]

    trade_summary = ccomp[trade_cols].copy()
    trade_summary.columns = trade_names
    trade_summary = trade_summary.sort_values("Actual Cost", ascending=False)

    trade_fmt = {
        "NT Hours": "{:,.1f}", "OT Hours": "{:,.1f}", "Total Hours": "{:,.1f}",
        "Actual Cost": "${:,.0f}", "Est Hours": "{:,.0f}", "Est Cost": "${:,.0f}",
        "Hours Var": "{:+,.0f}", "Cost Var": "${:+,.0f}",
    }
    if "DT Hours" in trade_summary.columns:
        trade_fmt["DT Hours"] = "{:,.1f}"

    st.dataframe(
        trade_summary.style.format(trade_fmt).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Hours Var", "Cost Var"],
        ),
        use_container_width=True, hide_index=True,
    )

    # Daily hours trend
    agg_dict_daily = {
        "nt": ("nt_hours", "sum"),
        "ot": ("ot_hours", "sum"),
        "headcount": ("person_id", "nunique"),
    }
    if "dt_hours" in cdf.columns:
        agg_dict_daily["dt"] = ("dt_hours", "sum")
    daily_c = cdf.groupby("date").agg(**agg_dict_daily).reset_index().sort_values("date")

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_c["date"], y=daily_c["nt"], name="NT",
                             marker_color=COLORS["nt"]))
        fig.add_trace(go.Bar(x=daily_c["date"], y=daily_c["ot"], name="OT",
                             marker_color=COLORS["ot"]))
        if "dt" in daily_c.columns and daily_c["dt"].sum() > 0:
            fig.add_trace(go.Bar(x=daily_c["date"], y=daily_c["dt"], name="DT",
                                 marker_color="#9C27B0"))
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
