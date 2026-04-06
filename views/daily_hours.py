"""Daily Hours view: hours per trade/day with charts and filters."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from components import COLORS, CONTRACTOR_COLORS


def render(cost_df: pd.DataFrame):
    st.header("Daily Hours")

    # --- Filters ---
    col1, col2, col3, col4 = st.columns(4)

    contractors = sorted(cost_df["contractor"].unique())
    with col1:
        sel_contractors = st.multiselect(
            "Contractor", contractors, default=contractors, key="dh_contractors"
        )

    trades = sorted(cost_df[cost_df["contractor"].isin(sel_contractors)]["mapped_trade"].unique())
    with col2:
        sel_trades = st.multiselect(
            "Trade", trades, default=trades, key="dh_trades"
        )

    date_range = cost_df["date"].agg(["min", "max"])
    with col3:
        start_date = st.date_input(
            "Start Date", value=date_range["min"].date(), key="dh_start"
        )
    with col4:
        end_date = st.date_input(
            "End Date", value=date_range["max"].date(), key="dh_end"
        )

    hour_type = st.radio(
        "Hour Type", ["Total", "NT / OT Split"], horizontal=True, key="dh_hour_type"
    )

    # Apply filters
    mask = (
        cost_df["contractor"].isin(sel_contractors)
        & cost_df["mapped_trade"].isin(sel_trades)
        & (cost_df["date"].dt.date >= start_date)
        & (cost_df["date"].dt.date <= end_date)
    )
    filtered = cost_df[mask].copy()

    if filtered.empty:
        st.warning("No data matches the selected filters.")
        return

    # --- Daily Hours Chart ---
    st.subheader("Daily Hours by Trade")

    if hour_type == "NT / OT Split":
        daily_agg = filtered.groupby("date").agg(
            NT=("nt_hours", "sum"),
            OT=("ot_hours", "sum"),
        ).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(x=daily_agg["date"], y=daily_agg["NT"],
                             name="NT", marker_color=COLORS["nt"]))
        fig.add_trace(go.Bar(x=daily_agg["date"], y=daily_agg["OT"],
                             name="OT", marker_color=COLORS["ot"]))
        fig.update_layout(barmode="stack", height=400,
                          margin=dict(l=40, r=20, t=30, b=40),
                          xaxis_title="Date", yaxis_title="Hours",
                          legend=dict(orientation="h", y=-0.15),
                          plot_bgcolor="white")
    else:
        daily_trade = filtered.groupby(["date", "mapped_trade"])["total_hours"].sum().reset_index()
        fig = px.bar(daily_trade, x="date", y="total_hours", color="mapped_trade",
                     color_discrete_sequence=CONTRACTOR_COLORS)
        fig.update_layout(barmode="stack", height=400,
                          margin=dict(l=40, r=20, t=30, b=40),
                          xaxis_title="Date", yaxis_title="Hours",
                          legend=dict(orientation="h", y=-0.15),
                          plot_bgcolor="white")

    fig.update_xaxes(gridcolor="#E8EAED")
    fig.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig, use_container_width=True)

    # --- Daily Hours Table ---
    st.subheader("Daily Hours Table")

    pivot_data = filtered.groupby(["date", "mapped_trade"]).agg(
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
        headcount=("person_id", "nunique"),
    ).reset_index()

    # Pivot for display
    if hour_type == "NT / OT Split":
        pivot_nt = pivot_data.pivot_table(
            index="mapped_trade", columns="date", values="nt", aggfunc="sum", fill_value=0
        )
        pivot_ot = pivot_data.pivot_table(
            index="mapped_trade", columns="date", values="ot", aggfunc="sum", fill_value=0
        )
        # Format date columns
        pivot_nt.columns = [d.strftime("%m/%d") for d in pivot_nt.columns]
        pivot_ot.columns = [d.strftime("%m/%d") for d in pivot_ot.columns]

        tab1, tab2 = st.tabs(["NT Hours", "OT Hours"])
        with tab1:
            pivot_nt["Total NT"] = pivot_nt.sum(axis=1)
            st.dataframe(pivot_nt.style.format("{:.1f}"), use_container_width=True)
        with tab2:
            pivot_ot["Total OT"] = pivot_ot.sum(axis=1)
            st.dataframe(pivot_ot.style.format("{:.1f}"), use_container_width=True)
    else:
        pivot_total = pivot_data.pivot_table(
            index="mapped_trade", columns="date", values="total", aggfunc="sum", fill_value=0
        )
        pivot_total.columns = [d.strftime("%m/%d") for d in pivot_total.columns]
        pivot_total["Total"] = pivot_total.sum(axis=1)
        st.dataframe(pivot_total.style.format("{:.1f}"), use_container_width=True)

    # --- Daily Cost Chart ---
    st.subheader("Daily Cost")

    daily_cost = filtered.groupby("date").agg(
        daily_cost=("total_cost", "sum"),
        daily_nt_cost=("nt_cost", "sum"),
        daily_ot_cost=("ot_cost", "sum"),
    ).reset_index().sort_values("date")

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=daily_cost["date"], y=daily_cost["daily_nt_cost"],
                          name="NT Cost", marker_color=COLORS["nt"]))
    fig2.add_trace(go.Bar(x=daily_cost["date"], y=daily_cost["daily_ot_cost"],
                          name="OT Cost", marker_color=COLORS["ot"]))
    fig2.update_layout(barmode="stack", height=350,
                       margin=dict(l=40, r=20, t=30, b=40),
                       xaxis_title="Date", yaxis_title="Cost ($)",
                       legend=dict(orientation="h", y=-0.15),
                       plot_bgcolor="white")
    fig2.update_xaxes(gridcolor="#E8EAED")
    fig2.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig2, use_container_width=True)

    # --- Daily Cost Table ---
    st.subheader("Daily Cost Table")
    cost_pivot = filtered.groupby(["date", "mapped_trade"])["total_cost"].sum().reset_index()
    cost_table = cost_pivot.pivot_table(
        index="mapped_trade", columns="date", values="total_cost", aggfunc="sum", fill_value=0
    )
    cost_table.columns = [d.strftime("%m/%d") for d in cost_table.columns]
    cost_table["Total"] = cost_table.sum(axis=1)
    st.dataframe(
        cost_table.style.format("${:,.0f}"),
        use_container_width=True,
    )

    # --- Headcount chart ---
    st.subheader("Daily Headcount")
    headcount = filtered.groupby("date")["person_id"].nunique().reset_index()
    headcount.columns = ["date", "headcount"]
    fig3 = go.Figure(go.Bar(
        x=headcount["date"], y=headcount["headcount"],
        marker_color=COLORS["primary"], opacity=0.7,
    ))
    fig3.update_layout(height=300,
                       margin=dict(l=40, r=20, t=30, b=40),
                       xaxis_title="Date", yaxis_title="People on Site",
                       plot_bgcolor="white")
    fig3.update_xaxes(gridcolor="#E8EAED")
    fig3.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig3, use_container_width=True)
