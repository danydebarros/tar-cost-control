"""Forecast view: interactive EAC with daily planning, manual overrides, and adjustable parameters."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from forecast import calculate_forecast, get_daily_burn_rate
from components import metric_row, eac_chart, COLORS
from config import PROJECT_END
import plotly.graph_objects as go


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Forecast")

    # =====================================================================
    # SECTION 1: Daily Forecast Planner
    # =====================================================================
    st.subheader("Daily Forecast Planner")
    st.caption(
        "Adjust headcount per trade per day starting from today. "
        "Pre-filled with yesterday's actual headcount. Forecast window: 14 days."
    )

    # Key dates
    last_actual = cost_df["date"].max().date()
    forecast_start = last_actual + timedelta(days=1)  # day after last actual

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Last Actual", last_actual.strftime("%b %d"))
    with col_b:
        st.metric("Forecast From", forecast_start.strftime("%b %d"))
    with col_c:
        forecast_days = st.number_input(
            "Forecast days", min_value=7, max_value=60, value=14, key="fc_days"
        )
    with col_d:
        forecast_end = forecast_start + timedelta(days=forecast_days - 1)
        st.metric("Forecast To", forecast_end.strftime("%b %d"))

    # Contractor selector
    fc_contractor = st.selectbox(
        "Contractor", sorted(cost_df["contractor"].unique()), key="fc_plan_contractor"
    )

    # Get trades and rates for this contractor
    contractor_comp = comparison[comparison["contractor"] == fc_contractor].copy()
    trades = sorted(contractor_comp["mapped_trade"].unique())

    trade_rates = {}
    for _, row in contractor_comp.iterrows():
        t = row["mapped_trade"]
        if row["actual_total_hours"] > 0:
            blended = row["actual_total_cost"] / row["actual_total_hours"]
        elif row["est_hours"] > 0:
            blended = row["est_cost"] / row["est_hours"]
        else:
            blended = 0
        trade_rates[t] = round(blended, 2)

    # Get yesterday's actual headcount per trade (to use as default)
    yesterday = last_actual  # use last actual date as "yesterday"
    yesterday_data = cost_df[
        (cost_df["contractor"] == fc_contractor) & (cost_df["date"].dt.date == yesterday)
    ]
    yesterday_hc = yesterday_data.groupby("mapped_trade")["person_id"].nunique().to_dict()

    # Generate forecast dates
    forecast_dates = pd.date_range(start=forecast_start, periods=forecast_days, freq="D")

    # Settings
    col1, col2 = st.columns(2)
    with col1:
        hours_per_day = st.number_input(
            "Hours per person per day", min_value=4.0, max_value=16.0,
            value=10.0, step=0.5, key="fc_hrs_per_day",
        )
    with col2:
        nt_ot_split = st.slider(
            "Expected NT/OT split (% NT)",
            min_value=50, max_value=100, value=75, step=5,
            help="What % of hours will be NT vs OT",
            key="fc_nt_pct",
        )

    # Build or load the daily plan
    plan_key = f"daily_plan_v2_{fc_contractor}_{forecast_days}"
    if plan_key not in st.session_state:
        # Pre-fill with yesterday's headcount for every day
        plan_data = {}
        for trade in trades:
            default_hc = yesterday_hc.get(trade, 0)
            plan_data[trade] = [default_hc] * len(forecast_dates)
        st.session_state[plan_key] = plan_data

    # Ensure all trades present
    for trade in trades:
        if trade not in st.session_state[plan_key]:
            default_hc = yesterday_hc.get(trade, 0)
            st.session_state[plan_key][trade] = [default_hc] * len(forecast_dates)
        elif len(st.session_state[plan_key][trade]) != len(forecast_dates):
            default_hc = yesterday_hc.get(trade, 0)
            st.session_state[plan_key][trade] = [default_hc] * len(forecast_dates)

    # Build editable DataFrame
    plan_df = pd.DataFrame(
        st.session_state[plan_key],
        index=forecast_dates,
    ).T
    plan_df.columns = [d.strftime("%a %m/%d") for d in forecast_dates]
    plan_df.index.name = "Trade"

    st.caption(
        f"Pre-filled with {yesterday.strftime('%b %d')} actual headcount. "
        f"Edit any cell to adjust. Set to 0 to remove a trade from a day."
    )

    edited_plan = st.data_editor(
        plan_df,
        use_container_width=True,
        key=f"fc_plan_editor_v2_{fc_contractor}_{forecast_days}",
    )

    # Save back
    if edited_plan is not None:
        st.session_state[plan_key] = {
            trade: list(edited_plan.loc[trade].values)
            for trade in edited_plan.index
        }

    # Calculate forecast
    if edited_plan is not None:
        plan_summary = []
        for trade in edited_plan.index:
            hc_days = edited_plan.loc[trade].sum()
            forecast_hrs = hc_days * hours_per_day
            nt_pct = nt_ot_split / 100
            fc_nt = forecast_hrs * nt_pct
            fc_ot = forecast_hrs * (1 - nt_pct)
            rate = trade_rates.get(trade, 0)
            fc_cost = forecast_hrs * rate

            comp_row = contractor_comp[contractor_comp["mapped_trade"] == trade]
            act_hrs = comp_row["actual_total_hours"].sum() if len(comp_row) > 0 else 0
            act_cost = comp_row["actual_total_cost"].sum() if len(comp_row) > 0 else 0
            est_hrs = comp_row["est_hours"].sum() if len(comp_row) > 0 else 0
            est_cost = comp_row["est_cost"].sum() if len(comp_row) > 0 else 0

            plan_summary.append({
                "Trade": trade,
                "Yesterday HC": yesterday_hc.get(trade, 0),
                "HC Days": hc_days,
                "Forecast Hrs": forecast_hrs,
                "FC NT": fc_nt,
                "FC OT": fc_ot,
                "Blended Rate": rate,
                "Forecast Cost": fc_cost,
                "Actual Hrs": act_hrs,
                "Actual Cost": act_cost,
                "EAC Hrs": act_hrs + forecast_hrs,
                "EAC Cost": act_cost + fc_cost,
                "Est Hrs": est_hrs,
                "Est Cost": est_cost,
                "Var Hrs": est_hrs - (act_hrs + forecast_hrs),
                "Var Cost": est_cost - (act_cost + fc_cost),
            })

        plan_result = pd.DataFrame(plan_summary)

        st.markdown(f"**{fc_contractor} — Forecast from Daily Plan**")

        tot = plan_result.select_dtypes(include=[np.number]).sum()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Forecast Hours", f"{tot['Forecast Hrs']:,.0f}")
        m2.metric("Forecast Cost", f"${tot['Forecast Cost']:,.0f}")
        m3.metric("EAC Cost", f"${tot['EAC Cost']:,.0f}")
        var = tot["Est Cost"] - tot["EAC Cost"]
        m4.metric("Variance to Est", f"${var:+,.0f}",
                  delta="Under" if var >= 0 else "OVER",
                  delta_color="normal" if var >= 0 else "inverse")

        st.dataframe(
            plan_result.style.format({
                "Yesterday HC": "{:,.0f}",
                "HC Days": "{:,.0f}",
                "Forecast Hrs": "{:,.0f}",
                "FC NT": "{:,.0f}",
                "FC OT": "{:,.0f}",
                "Blended Rate": "${:,.2f}",
                "Forecast Cost": "${:,.0f}",
                "Actual Hrs": "{:,.0f}",
                "Actual Cost": "${:,.0f}",
                "EAC Hrs": "{:,.0f}",
                "EAC Cost": "${:,.0f}",
                "Est Hrs": "{:,.0f}",
                "Est Cost": "${:,.0f}",
                "Var Hrs": "{:+,.0f}",
                "Var Cost": "${:+,.0f}",
            }).map(
                lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Var Hrs", "Var Cost"],
            ),
            use_container_width=True, hide_index=True,
        )

    # =====================================================================
    # SECTION 2: Overall Forecast (all contractors)
    # =====================================================================
    st.divider()
    st.subheader("Overall Forecast")

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
            help="Multiplier on remaining hours",
            key="fc_burn_rate",
        )

    # Manual overrides
    if method in ("manual", "hybrid"):
        st.markdown("**Manual Overrides** — edit Remaining Hours or Cost below:")

        override_data = comparison[["contractor", "mapped_trade", "est_hours",
                                     "actual_total_hours", "est_cost",
                                     "actual_total_cost"]].copy()
        override_data["remaining_hours"] = (
            override_data["est_hours"] - override_data["actual_total_hours"]
        ).clip(lower=0)
        override_data["remaining_cost"] = (
            override_data["est_cost"] - override_data["actual_total_cost"]
        ).clip(lower=0)
        override_data = override_data[
            (override_data["actual_total_hours"] > 0) | (override_data["est_hours"] > 0)
        ].copy()

        edit_df = override_data[["contractor", "mapped_trade", "est_hours",
                                  "actual_total_hours", "remaining_hours",
                                  "remaining_cost"]].copy()
        edit_df.columns = ["Contractor", "Trade", "Est Hours", "Actual Hours",
                           "Remaining Hours", "Remaining Cost"]

        edited = st.data_editor(
            edit_df,
            disabled=["Contractor", "Trade", "Est Hours", "Actual Hours"],
            num_rows="fixed", use_container_width=True, key="fc_overrides",
        )

        manual_overrides = {}
        if edited is not None:
            for _, row in edited.iterrows():
                orig = override_data[
                    (override_data["contractor"] == row["Contractor"])
                    & (override_data["mapped_trade"] == row["Trade"])
                ]
                if len(orig) > 0:
                    if (row["Remaining Hours"] != orig["remaining_hours"].values[0] or
                            row["Remaining Cost"] != orig["remaining_cost"].values[0]):
                        manual_overrides[(row["Contractor"], row["Trade"])] = {
                            "remaining_hours": row["Remaining Hours"],
                            "remaining_cost": row["Remaining Cost"],
                        }
    else:
        manual_overrides = {}

    # Run forecast
    forecast_df = calculate_forecast(
        comparison=comparison, cost_df=cost_df,
        method=method, productivity_factor=productivity,
        burn_rate_factor=burn_rate, manual_overrides=manual_overrides,
    )
    st.session_state["forecast_df"] = forecast_df

    # KPIs
    total_eac_cost = forecast_df["eac_cost"].sum()
    total_est_cost = forecast_df["est_cost"].sum()
    total_actual = forecast_df["actual_total_cost"].sum()
    forecast_var = total_est_cost - total_eac_cost
    total_eac_hrs = forecast_df["eac_hours"].sum()
    total_forecast_ot = forecast_df["forecast_ot_hours"].sum()
    forecast_ot_pct = (total_forecast_ot / total_eac_hrs * 100
                       if total_eac_hrs > 0 else 0)

    metric_row([
        {"label": "Estimate", "value": total_est_cost, "prefix": "$"},
        {"label": "Actual to Date", "value": total_actual, "prefix": "$"},
        {"label": "EAC (Cost)", "value": total_eac_cost, "prefix": "$"},
        {"label": "Forecast Variance", "value": forecast_var, "prefix": "$",
         "delta": "Under" if forecast_var >= 0 else "OVER",
         "delta_color": "normal" if forecast_var >= 0 else "inverse"},
        {"label": "Forecast OT %", "value": forecast_ot_pct, "prefix": "%"},
    ])

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**EAC by Contractor**")
        st.plotly_chart(eac_chart(forecast_df, "contractor"), use_container_width=True)
    with col2:
        st.markdown("**EAC by Trade**")
        st.plotly_chart(eac_chart(forecast_df, "mapped_trade"), use_container_width=True)

    # Detail table
    st.markdown("**Forecast Detail**")
    fc_display = forecast_df[[
        "contractor", "mapped_trade",
        "est_hours", "actual_total_hours", "eac_hours", "forecast_hours_variance",
        "est_cost", "actual_total_cost", "eac_cost", "forecast_cost_variance",
        "pct_hours_complete", "current_ot_ratio",
    ]].copy()
    fc_display.columns = [
        "Contractor", "Trade", "Est Hours", "Actual Hours", "EAC Hours", "Hours Var",
        "Est Cost", "Actual Cost", "EAC Cost", "Cost Var", "% Complete", "OT Ratio",
    ]
    fc_display = fc_display.sort_values("EAC Cost", ascending=False)

    st.dataframe(
        fc_display.style.format({
            "Est Hours": "{:,.0f}", "Actual Hours": "{:,.0f}",
            "EAC Hours": "{:,.0f}", "Hours Var": "{:+,.0f}",
            "Est Cost": "${:,.0f}", "Actual Cost": "${:,.0f}",
            "EAC Cost": "${:,.0f}", "Cost Var": "${:+,.0f}",
            "% Complete": "{:.0f}%", "OT Ratio": "{:.1%}",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
            subset=["Hours Var", "Cost Var"],
        ),
        use_container_width=True, hide_index=True,
    )

    # Burn rate & S-curve
    st.markdown("**Burn Rate Trend**")
    col1, _ = st.columns([1, 3])
    with col1:
        trailing = st.number_input("Trailing days", min_value=3, max_value=30,
                                   value=7, key="fc_trailing")
    daily = get_daily_burn_rate(cost_df, trailing_days=trailing)

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=daily["date"], y=daily["daily_cost"], name="Daily Cost",
                          marker_color=COLORS["primary"], opacity=0.3))
    fig3.add_trace(go.Scatter(x=daily["date"], y=daily["rolling_avg_cost"],
                              name=f"{trailing}-day Avg", mode="lines",
                              line=dict(color=COLORS["danger"], width=2)))
    fig3.update_layout(height=350, margin=dict(l=40, r=20, t=30, b=40),
                       xaxis_title="Date", yaxis_title="Daily Cost ($)",
                       legend=dict(orientation="h", y=-0.15), plot_bgcolor="white")
    fig3.update_xaxes(gridcolor="#E8EAED")
    fig3.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("**S-Curve: Cumulative Actual vs Estimate**")
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=daily["date"], y=daily["cum_cost"],
                              mode="lines", name="Actual",
                              line=dict(color=COLORS["actual"], width=3)))
    fig4.add_hline(y=total_est_cost, line_dash="dash", line_color=COLORS["estimate"],
                   annotation_text=f"Estimate: ${total_est_cost:,.0f}")
    fig4.add_hline(y=total_eac_cost, line_dash="dot", line_color=COLORS["forecast"],
                   annotation_text=f"EAC: ${total_eac_cost:,.0f}")
    fig4.update_layout(height=400, margin=dict(l=40, r=20, t=30, b=40),
                       xaxis_title="Date", yaxis_title="Cumulative Cost ($)",
                       legend=dict(orientation="h", y=-0.15), plot_bgcolor="white")
    fig4.update_xaxes(gridcolor="#E8EAED")
    fig4.update_yaxes(gridcolor="#E8EAED")
    st.plotly_chart(fig4, use_container_width=True)
