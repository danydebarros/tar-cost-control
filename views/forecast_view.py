"""Forecast view: interactive EAC with manual overrides and adjustable parameters."""

import streamlit as st
import pandas as pd
import numpy as np
from forecast import calculate_forecast, get_daily_burn_rate
from components import metric_row, eac_chart, COLORS
import plotly.graph_objects as go


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Forecast")

    # --- Forecast parameters ---
    st.subheader("Forecast Parameters")

    col1, col2, col3 = st.columns(3)

    with col1:
        method = st.selectbox(
            "Forecast Method",
            ["current_performance", "manual", "hybrid"],
            format_func=lambda x: {
                "current_performance": "Current Performance",
                "manual": "Manual Remaining",
                "hybrid": "Hybrid (Performance + Manual Overrides)",
            }[x],
            key="fc_method",
        )

    with col2:
        productivity = st.slider(
            "Productivity Factor",
            min_value=0.5, max_value=2.0, value=1.0, step=0.05,
            help="< 1.0 = worse than plan, > 1.0 = better than plan",
            key="fc_productivity",
        )

    with col3:
        burn_rate = st.slider(
            "Burn Rate Factor",
            min_value=0.5, max_value=2.0, value=1.0, step=0.05,
            help="Multiplier on remaining hours (1.0 = no adjustment)",
            key="fc_burn_rate",
        )

    # --- Manual overrides (editable table) ---
    if method in ("manual", "hybrid"):
        st.subheader("Manual Overrides")
        st.caption("Edit remaining hours or cost for specific contractor/trade combinations.")

        override_data = comparison[["contractor", "mapped_trade", "est_hours",
                                     "actual_total_hours", "est_cost",
                                     "actual_total_cost"]].copy()
        override_data["remaining_hours"] = (
            override_data["est_hours"] - override_data["actual_total_hours"]
        ).clip(lower=0)
        override_data["remaining_cost"] = (
            override_data["est_cost"] - override_data["actual_total_cost"]
        ).clip(lower=0)

        # Only show rows with actual activity or positive estimate
        override_data = override_data[
            (override_data["actual_total_hours"] > 0) | (override_data["est_hours"] > 0)
        ].copy()

        display_cols = {
            "contractor": "Contractor",
            "mapped_trade": "Trade",
            "est_hours": "Est Hours",
            "actual_total_hours": "Actual Hours",
            "remaining_hours": "Remaining Hours",
            "remaining_cost": "Remaining Cost",
        }
        edit_df = override_data[list(display_cols.keys())].copy()
        edit_df.columns = list(display_cols.values())

        edited = st.data_editor(
            edit_df,
            disabled=["Contractor", "Trade", "Est Hours", "Actual Hours"],
            num_rows="fixed",
            use_container_width=True,
            key="fc_overrides",
        )

        # Build overrides dict from edited data
        manual_overrides = {}
        if edited is not None:
            for _, row in edited.iterrows():
                orig = override_data[
                    (override_data["contractor"] == row["Contractor"])
                    & (override_data["mapped_trade"] == row["Trade"])
                ]
                if len(orig) > 0:
                    orig_remaining = orig["remaining_hours"].values[0]
                    orig_cost = orig["remaining_cost"].values[0]
                    if (row["Remaining Hours"] != orig_remaining or
                            row["Remaining Cost"] != orig_cost):
                        manual_overrides[(row["Contractor"], row["Trade"])] = {
                            "remaining_hours": row["Remaining Hours"],
                            "remaining_cost": row["Remaining Cost"],
                        }
    else:
        manual_overrides = {}

    # --- Run forecast ---
    forecast_df = calculate_forecast(
        comparison=comparison,
        cost_df=cost_df,
        method=method,
        productivity_factor=productivity,
        burn_rate_factor=burn_rate,
        manual_overrides=manual_overrides,
    )

    # Store in session state for other views
    st.session_state["forecast_df"] = forecast_df

    # --- Forecast KPIs ---
    st.subheader("Forecast Summary")

    total_eac_cost = forecast_df["eac_cost"].sum()
    total_est_cost = forecast_df["est_cost"].sum()
    total_actual = forecast_df["actual_total_cost"].sum()
    forecast_var = total_est_cost - total_eac_cost

    total_eac_hrs = forecast_df["eac_hours"].sum()
    total_est_hrs = forecast_df["est_hours"].sum()
    total_act_hrs = forecast_df["actual_total_hours"].sum()

    total_forecast_ot = forecast_df["forecast_ot_hours"].sum()
    total_forecast_total = total_eac_hrs
    forecast_ot_pct = (total_forecast_ot / total_forecast_total * 100
                       if total_forecast_total > 0 else 0)

    metric_row([
        {"label": "Estimate", "value": total_est_cost, "prefix": "$"},
        {"label": "Actual to Date", "value": total_actual, "prefix": "$"},
        {"label": "EAC (Cost)", "value": total_eac_cost, "prefix": "$"},
        {"label": "Forecast Variance", "value": forecast_var, "prefix": "$",
         "delta": "Under" if forecast_var >= 0 else "OVER",
         "delta_color": "normal" if forecast_var >= 0 else "inverse"},
        {"label": "Forecast OT %", "value": forecast_ot_pct, "prefix": "%"},
    ])

    # --- EAC chart ---
    st.subheader("EAC by Contractor")
    fig = eac_chart(forecast_df, "contractor")
    st.plotly_chart(fig, use_container_width=True)

    # --- EAC by trade ---
    st.subheader("EAC by Trade")
    fig2 = eac_chart(forecast_df, "mapped_trade")
    st.plotly_chart(fig2, use_container_width=True)

    # --- Detailed forecast table ---
    st.subheader("Forecast Detail")

    fc_display = forecast_df[[
        "contractor", "mapped_trade",
        "est_hours", "actual_total_hours", "eac_hours", "forecast_hours_variance",
        "est_cost", "actual_total_cost", "eac_cost", "forecast_cost_variance",
        "pct_hours_complete", "current_ot_ratio",
    ]].copy()
    fc_display.columns = [
        "Contractor", "Trade",
        "Est Hours", "Actual Hours", "EAC Hours", "Hours Var",
        "Est Cost", "Actual Cost", "EAC Cost", "Cost Var",
        "% Complete", "OT Ratio",
    ]
    fc_display = fc_display.sort_values("EAC Cost", ascending=False)

    st.dataframe(
        fc_display.style.format({
            "Est Hours": "{:,.0f}",
            "Actual Hours": "{:,.0f}",
            "EAC Hours": "{:,.0f}",
            "Hours Var": "{:+,.0f}",
            "Est Cost": "${:,.0f}",
            "Actual Cost": "${:,.0f}",
            "EAC Cost": "${:,.0f}",
            "Cost Var": "${:+,.0f}",
            "% Complete": "{:.0f}%",
            "OT Ratio": "{:.1%}",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Hours Var", "Cost Var"],
        ),
        use_container_width=True, hide_index=True,
    )

    # --- Burn rate trend ---
    st.subheader("Burn Rate Trend")

    col1, _ = st.columns([1, 3])
    with col1:
        trailing = st.number_input("Trailing days", min_value=3, max_value=30,
                                   value=7, key="fc_trailing")

    daily = get_daily_burn_rate(cost_df, trailing_days=trailing)

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(
        x=daily["date"], y=daily["daily_cost"], name="Daily Cost",
        marker_color=COLORS["primary"], opacity=0.3,
    ))
    fig3.add_trace(go.Scatter(
        x=daily["date"], y=daily["rolling_avg_cost"],
        name=f"{trailing}-day Avg", mode="lines",
        line=dict(color=COLORS["danger"], width=2),
    ))
    fig3.update_layout(
        height=350,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Date", yaxis_title="Daily Cost ($)",
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
    )
    fig3.update_xaxes(gridcolor="#E8EAED")
    fig3.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig3, use_container_width=True)

    # --- S-Curve ---
    st.subheader("S-Curve: Cumulative Actual vs Estimate")

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(
        x=daily["date"], y=daily["cum_cost"],
        mode="lines", name="Actual (Cumulative)",
        line=dict(color=COLORS["actual"], width=3),
    ))
    # Add estimate line (flat total)
    fig4.add_hline(
        y=total_est_cost,
        line_dash="dash",
        line_color=COLORS["estimate"],
        annotation_text=f"Estimate: ${total_est_cost:,.0f}",
    )
    fig4.add_hline(
        y=total_eac_cost,
        line_dash="dot",
        line_color=COLORS["forecast"],
        annotation_text=f"EAC: ${total_eac_cost:,.0f}",
    )
    fig4.update_layout(
        height=400,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Date", yaxis_title="Cumulative Cost ($)",
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
    )
    fig4.update_xaxes(gridcolor="#E8EAED")
    fig4.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig4, use_container_width=True)
