"""Trade view: per-trade breakdown with daily hours, rates, costs, estimates."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from components import COLORS, CONTRACTOR_COLORS


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Trade View")

    # --- Summary table across all contractors ---
    trade_summary = comparison.groupby("mapped_trade").agg(
        contractors=("contractor", lambda x: ", ".join(sorted(x.unique()))),
        actual_nt=("actual_nt_hours", "sum"),
        actual_ot=("actual_ot_hours", "sum"),
        actual_total=("actual_total_hours", "sum"),
        actual_cost=("actual_total_cost", "sum"),
        est_hours=("est_hours", "sum"),
        est_cost=("est_cost", "sum"),
    ).reset_index()

    trade_summary["hours_var"] = trade_summary["est_hours"] - trade_summary["actual_total"]
    trade_summary["cost_var"] = trade_summary["est_cost"] - trade_summary["actual_cost"]
    trade_summary["ot_pct"] = np.where(
        trade_summary["actual_total"] > 0,
        trade_summary["actual_ot"] / trade_summary["actual_total"] * 100, 0
    )

    display = trade_summary[[
        "mapped_trade", "contractors", "actual_nt", "actual_ot",
        "actual_total", "actual_cost", "est_hours", "est_cost",
        "hours_var", "cost_var", "ot_pct",
    ]].copy()
    display.columns = [
        "Trade", "Contractors", "NT Hours", "OT Hours", "Total Hours",
        "Actual Cost", "Est Hours", "Est Cost", "Hours Var", "Cost Var", "OT %",
    ]
    display = display.sort_values("Actual Cost", ascending=False)

    st.dataframe(
        display.style.format({
            "NT Hours": "{:,.0f}",
            "OT Hours": "{:,.0f}",
            "Total Hours": "{:,.0f}",
            "Actual Cost": "${:,.0f}",
            "Est Hours": "{:,.0f}",
            "Est Cost": "${:,.0f}",
            "Hours Var": "{:+,.0f}",
            "Cost Var": "${:+,.0f}",
            "OT %": "{:.1f}%",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Hours Var", "Cost Var"],
        ),
        use_container_width=True, hide_index=True,
    )

    # --- Trade drill-down ---
    st.subheader("Trade Detail")

    selected_trade = st.selectbox(
        "Select trade", sorted(cost_df["mapped_trade"].unique()), key="trade_detail"
    )

    tdf = cost_df[cost_df["mapped_trade"] == selected_trade]
    tcomp = comparison[comparison["mapped_trade"] == selected_trade]

    # Contractor breakdown for this trade
    contractor_breakdown = tcomp[[
        "contractor", "actual_nt_hours", "actual_ot_hours",
        "actual_total_hours", "actual_total_cost",
        "est_hours", "est_cost", "hours_variance", "cost_variance",
    ]].copy()
    contractor_breakdown.columns = [
        "Contractor", "NT Hours", "OT Hours", "Total Hours", "Actual Cost",
        "Est Hours", "Est Cost", "Hours Var", "Cost Var",
    ]

    st.dataframe(
        contractor_breakdown.style.format({
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

    # Rate comparison
    st.markdown("**Rate Comparison**")
    rates = tdf.groupby("contractor").agg(
        nt_rate=("nt_rate", "first"),
        ot_rate=("ot_rate", "first"),
    ).reset_index()
    rates.columns = ["Contractor", "NT Rate", "OT Rate"]
    st.dataframe(
        rates.style.format({"NT Rate": "${:,.2f}", "OT Rate": "${:,.2f}"}),
        use_container_width=True, hide_index=True,
    )

    # Daily hours chart for trade
    col1, col2 = st.columns(2)

    with col1:
        daily_trade = tdf.groupby(["date", "contractor"]).agg(
            hours=("total_hours", "sum"),
        ).reset_index()
        fig = px.bar(daily_trade, x="date", y="hours", color="contractor",
                     color_discrete_sequence=CONTRACTOR_COLORS)
        fig.update_layout(barmode="stack", height=350,
                          title=f"{selected_trade} - Daily Hours by Contractor",
                          margin=dict(l=40, r=20, t=40, b=40),
                          plot_bgcolor="white",
                          legend=dict(orientation="h", y=-0.2))
        fig.update_xaxes(gridcolor="#E8EAED")
        fig.update_yaxes(gridcolor="#E8EAED")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        daily_ntot = tdf.groupby("date").agg(
            NT=("nt_hours", "sum"),
            OT=("ot_hours", "sum"),
        ).reset_index()
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=daily_ntot["date"], y=daily_ntot["NT"],
                              name="NT", marker_color=COLORS["nt"]))
        fig2.add_trace(go.Bar(x=daily_ntot["date"], y=daily_ntot["OT"],
                              name="OT", marker_color=COLORS["ot"]))
        fig2.update_layout(barmode="stack", height=350,
                           title=f"{selected_trade} - NT/OT Split",
                           margin=dict(l=40, r=20, t=40, b=40),
                           plot_bgcolor="white",
                           legend=dict(orientation="h", y=-0.2))
        fig2.update_xaxes(gridcolor="#E8EAED")
        fig2.update_yaxes(gridcolor="#E8EAED")
        st.plotly_chart(fig2, use_container_width=True)

    # Person-level detail
    with st.expander(f"Person-level detail for {selected_trade}"):
        person_detail = tdf.groupby(["name", "contractor"]).agg(
            days=("date", "nunique"),
            total=("total_hours", "sum"),
            nt=("nt_hours", "sum"),
            ot=("ot_hours", "sum"),
            cost=("total_cost", "sum"),
        ).reset_index().sort_values("total", ascending=False)
        person_detail.columns = ["Name", "Contractor", "Days", "Total Hours",
                                 "NT Hours", "OT Hours", "Total Cost"]
        st.dataframe(
            person_detail.style.format({
                "Total Hours": "{:,.1f}",
                "NT Hours": "{:,.1f}",
                "OT Hours": "{:,.1f}",
                "Total Cost": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )
