"""Executive Summary view: KPIs with date-based estimate comparison."""

import streamlit as st
import pandas as pd
import numpy as np
from components import metric_row, comparison_bar_chart, ot_percentage_chart, daily_cost_chart, COLORS
from estimate import estimate_to_date, estimate_summary_to_date, estimate_daily_series
import plotly.graph_objects as go


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame, forecast_df: pd.DataFrame):
    st.header("Executive Summary")

    # Date selector
    last_actual = cost_df["date"].max().date()
    col_date, _ = st.columns([1, 3])
    with col_date:
        cutoff = st.date_input("Estimate cutoff date", value=last_actual, key="exec_cutoff")

    # Get date-based estimates
    est = estimate_summary_to_date(cutoff)
    totals = est["totals"]
    by_contractor = est["by_contractor"]

    # Actuals
    actual_mask = cost_df["date"].dt.date <= cutoff
    filtered = cost_df[actual_mask]
    total_act_hours = filtered["total_hours"].sum()
    total_act_labor = filtered["total_cost"].sum()
    total_ot = filtered["ot_hours"].sum() if "ot_hours" in filtered.columns else 0
    ot_pct = (total_ot / total_act_hours * 100) if total_act_hours > 0 else 0

    # Estimate to date
    est_labor_td = totals["labor"]
    est_other_td = totals["other"]
    est_equip_td = totals["equipment"]
    est_total_td = totals["total"]

    # Full budget
    budget_total = totals["total_budget"]
    budget_labor = totals["total_budget_labor"]

    # Variances (labor only for hours comparison)
    labor_var = est_labor_td - total_act_labor

    # --- KPIs ---
    metric_row([
        {"label": "Budget (Total)", "value": budget_total, "prefix": "$"},
        {"label": f"Estimate to {cutoff.strftime('%b %d')}", "value": est_total_td, "prefix": "$"},
        {"label": "Actual Labor Cost", "value": total_act_labor, "prefix": "$"},
        {"label": "Labor Variance", "value": labor_var, "prefix": "$",
         "delta": "Under" if labor_var >= 0 else "OVER",
         "delta_color": "normal" if labor_var >= 0 else "inverse"},
        {"label": "OT %", "value": ot_pct, "prefix": "%"},
    ])

    st.divider()

    # Breakdown
    metric_row([
        {"label": "Est Labor (to date)", "value": est_labor_td, "prefix": "$"},
        {"label": "Est Other (to date)", "value": est_other_td, "prefix": "$"},
        {"label": "Est Equipment (to date)", "value": est_equip_td, "prefix": "$"},
        {"label": "% Budget Burned", "value": (est_total_td / budget_total * 100) if budget_total > 0 else 0, "prefix": "%"},
    ])

    st.divider()

    # --- Contractor comparison ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Actual vs Estimate by Contractor (Labor)")
        # Build contractor comparison with date-based estimates
        contractor_data = []
        for c in sorted(by_contractor.keys()):
            c_mask = (cost_df["contractor"] == c) & actual_mask
            c_actual = cost_df[c_mask]["total_cost"].sum()
            contractor_data.append({
                "Contractor": c,
                "Est Labor": by_contractor[c]["labor"],
                "Actual Labor": c_actual,
                "Variance": by_contractor[c]["labor"] - c_actual,
                "Est Other": by_contractor[c]["other"],
                "Est Equip": by_contractor[c]["equipment"],
                "Est Total": by_contractor[c]["total"],
            })
        cdf = pd.DataFrame(contractor_data)

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=cdf["Contractor"], x=cdf["Est Labor"], name="Estimate (Labor)",
            orientation="h", marker_color=COLORS["estimate"], opacity=0.6,
        ))
        fig.add_trace(go.Bar(
            y=cdf["Contractor"], x=cdf["Actual Labor"], name="Actual (Labor)",
            orientation="h", marker_color=COLORS["actual"],
        ))
        fig.update_layout(barmode="group", height=350,
                          margin=dict(l=100, r=20, t=30, b=40),
                          legend=dict(orientation="h", y=-0.15),
                          plot_bgcolor="white")
        fig.update_xaxes(gridcolor="#E8EAED")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("OT % by Contractor")
        fig = ot_percentage_chart(comparison, "contractor")
        st.plotly_chart(fig, use_container_width=True)

    # --- S-Curve ---
    st.subheader("Cumulative Cost: Actual vs Estimate")

    # Actual daily cumulative
    daily_actual = filtered.groupby("date")["total_cost"].sum().reset_index().sort_values("date")
    daily_actual["cum_actual"] = daily_actual["total_cost"].cumsum()

    # Estimate daily cumulative (all contractors combined)
    est_series = estimate_daily_series()
    est_daily = est_series.groupby("date").agg(
        est_total=("est_total", "sum"),
    ).reset_index().sort_values("date")
    est_daily["cum_est"] = est_daily["est_total"].cumsum()

    fig_s = go.Figure()
    fig_s.add_trace(go.Scatter(
        x=daily_actual["date"], y=daily_actual["cum_actual"],
        mode="lines", name="Actual (Labor)",
        line=dict(color=COLORS["actual"], width=3),
    ))
    fig_s.add_trace(go.Scatter(
        x=est_daily["date"], y=est_daily["cum_est"],
        mode="lines", name="Estimate (Total)",
        line=dict(color=COLORS["estimate"], width=2, dash="dash"),
    ))
    fig_s.add_hline(y=budget_total, line_dash="dot", line_color=COLORS["danger"],
                    annotation_text=f"Total Budget: ${budget_total:,.0f}")
    fig_s.update_layout(height=400, margin=dict(l=40, r=20, t=30, b=40),
                        xaxis_title="Date", yaxis_title="Cumulative Cost ($)",
                        legend=dict(orientation="h", y=-0.15), plot_bgcolor="white")
    fig_s.update_xaxes(gridcolor="#E8EAED")
    fig_s.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig_s, use_container_width=True)

    # --- Contractor table ---
    st.subheader("Contractor Summary")

    cdf["Budget"] = [by_contractor[c]["total_budget"] for c in cdf["Contractor"]]
    display = cdf[["Contractor", "Budget", "Est Total", "Est Labor", "Actual Labor",
                    "Variance", "Est Other", "Est Equip"]].copy()

    st.dataframe(
        display.style.format({
            "Budget": "${:,.0f}", "Est Total": "${:,.0f}",
            "Est Labor": "${:,.0f}", "Actual Labor": "${:,.0f}",
            "Variance": "${:+,.0f}", "Est Other": "${:,.0f}", "Est Equip": "${:,.0f}",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Variance"],
        ),
        use_container_width=True, hide_index=True,
    )
