"""Forecast view: simplified, persistent, no lag.

Uses saved forecast as the baseline going forward.
New saves become the active forecast until someone updates it.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from forecast_store import save_forecast, load_forecast
from estimate import estimate_to_date
from components import metric_row, COLORS
from config import DAILY_ESTIMATE_COSTS
import plotly.graph_objects as go


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Forecast")

    # =====================================================================
    # Load saved forecast (persistent baseline)
    # =====================================================================
    if "forecast_loaded" not in st.session_state:
        saved = load_forecast()
        if saved and "plans" in saved:
            for key, val in saved["plans"].items():
                st.session_state[key] = val
            st.session_state["forecast_meta"] = {
                "saved_by": saved.get("saved_by", ""),
                "saved_at": saved.get("saved_at", ""),
                "note": saved.get("note", ""),
            }
        st.session_state["forecast_loaded"] = True

    meta = st.session_state.get("forecast_meta", {})
    if meta.get("saved_by"):
        st.caption(
            f"Active forecast by **{meta['saved_by']}** on {meta['saved_at']}"
            + (f" — _{meta['note']}_" if meta.get("note") else "")
        )

    # =====================================================================
    # Key dates
    # =====================================================================
    last_actual = cost_df["date"].max().date()
    forecast_start = last_actual + timedelta(days=1)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Last Actual", last_actual.strftime("%b %d, %Y"))
    with col2:
        forecast_days = st.number_input("Forecast days", 7, 60, 14, key="fc_days")
    with col3:
        forecast_end = forecast_start + timedelta(days=forecast_days - 1)
        st.metric("Forecast To", forecast_end.strftime("%b %d, %Y"))

    forecast_dates = pd.date_range(start=forecast_start, periods=forecast_days, freq="D")
    date_labels = [d.strftime("%a %m/%d") for d in forecast_dates]

    # =====================================================================
    # Contractor selector
    # =====================================================================
    contractors = sorted(cost_df["contractor"].unique())
    fc_contractor = st.selectbox("Contractor", contractors, key="fc_contractor")

    # Get trades and rates
    contractor_comp = comparison[comparison["contractor"] == fc_contractor].copy()
    trades = sorted(contractor_comp["mapped_trade"].unique())

    # Include trades from rate table that may not have actuals
    from data_loader import get_embedded_rate_table
    rate_table = get_embedded_rate_table()
    all_rate_trades = rate_table[rate_table["Contractor"] == fc_contractor]["Trade"].unique()
    trade_rates = {}
    for _, row in contractor_comp.iterrows():
        t = row["mapped_trade"]
        if row["actual_total_hours"] > 0:
            trade_rates[t] = round(row["actual_total_cost"] / row["actual_total_hours"], 2)
        elif row["est_hours"] > 0:
            trade_rates[t] = round(row["est_cost"] / row["est_hours"], 2)
    for t in all_rate_trades:
        if t not in trades:
            trades.append(t)
        if t not in trade_rates:
            r = rate_table[(rate_table["Contractor"] == fc_contractor) & (rate_table["Trade"] == t)]
            if len(r) > 0:
                trade_rates[t] = round(r["Rate"].values[0], 2)
    trades = sorted(set(trades))

    # =====================================================================
    # Build forecast grid — pre-fill from estimate, use saved if exists
    # =====================================================================
    plan_key = f"fc_{fc_contractor}_{forecast_days}"

    # Default from estimate planned hours
    from collections import defaultdict
    planned_rows = DAILY_ESTIMATE_COSTS.get(fc_contractor, {}).get("daily", {})

    if plan_key not in st.session_state:
        plan_data = {}
        for trade in trades:
            # Try to get per-trade hours from PLANNED_DAILY_HOURS
            from config import PLANNED_DAILY_HOURS
            planned_by_trade = defaultdict(list)
            for pr in PLANNED_DAILY_HOURS.get(fc_contractor, []):
                base = pr["trade"]
                for suffix in [" NT", " OT", " DT", " ST", " - Standard", " - Overtime",
                               " NT (Pre/Post)", " / ST"]:
                    if base.endswith(suffix):
                        base = base[:-len(suffix)]
                        break
                planned_by_trade[base].append(pr)

            matching = planned_by_trade.get(trade, [])
            daily_vals = []
            for fd in forecast_dates:
                dt_str = fd.strftime("%Y-%m-%d")
                hrs = sum(pr["daily"].get(dt_str, 0) * pr["qty"] for pr in matching)
                daily_vals.append(round(hrs, 1))
            plan_data[trade] = daily_vals
        st.session_state[plan_key] = plan_data

    # Ensure all trades present
    for trade in trades:
        if trade not in st.session_state[plan_key]:
            st.session_state[plan_key][trade] = [0.0] * len(forecast_dates)
        elif len(st.session_state[plan_key][trade]) != len(forecast_dates):
            st.session_state[plan_key][trade] = [0.0] * len(forecast_dates)

    # =====================================================================
    # Editable grid
    # =====================================================================
    st.subheader(f"{fc_contractor} — Daily Hours Forecast")
    st.caption("Values are total hours per trade per day. Edit to adjust.")

    plan_df = pd.DataFrame(st.session_state[plan_key], index=date_labels).T
    plan_df.index.name = "Trade"

    edited = st.data_editor(plan_df, use_container_width=True)

    # Persist edits
    if edited is not None:
        for trade in edited.index:
            vals = pd.to_numeric(edited.loc[trade], errors="coerce").fillna(0)
            st.session_state[plan_key][trade] = [float(v) for v in vals.values]

    # =====================================================================
    # Calculate results
    # =====================================================================
    if edited is not None:
        edited = edited.apply(pd.to_numeric, errors="coerce").fillna(0)

        rows = []
        for trade in edited.index:
            fc_hrs = float(edited.loc[trade].sum())
            rate = trade_rates.get(trade, 0)
            fc_cost = fc_hrs * rate

            comp_row = contractor_comp[contractor_comp["mapped_trade"] == trade]
            act_hrs = comp_row["actual_total_hours"].sum() if len(comp_row) > 0 else 0
            act_cost = comp_row["actual_total_cost"].sum() if len(comp_row) > 0 else 0

            # Date-based estimate for this trade
            est_hrs = comp_row["est_hours"].sum() if len(comp_row) > 0 else 0
            est_cost = comp_row["est_cost"].sum() if len(comp_row) > 0 else 0

            rows.append({
                "Trade": trade, "Rate": rate,
                "Actual Hrs": act_hrs, "Actual Cost": act_cost,
                "FC Hrs": fc_hrs, "FC Cost": fc_cost,
                "EAC Hrs": act_hrs + fc_hrs, "EAC Cost": act_cost + fc_cost,
                "Est Hrs": est_hrs, "Est Cost": est_cost,
                "Var Hrs": est_hrs - (act_hrs + fc_hrs),
                "Var Cost": est_cost - (act_cost + fc_cost),
            })

        result = pd.DataFrame(rows)
        tot = result.select_dtypes(include=[np.number]).sum()

        # KPIs
        metric_row([
            {"label": "Actual Cost", "value": tot["Actual Cost"], "prefix": "$"},
            {"label": "Forecast Cost", "value": tot["FC Cost"], "prefix": "$"},
            {"label": "EAC Cost", "value": tot["EAC Cost"], "prefix": "$"},
            {"label": "Variance", "value": tot["Est Cost"] - tot["EAC Cost"], "prefix": "$",
             "delta": "Under" if tot["Est Cost"] >= tot["EAC Cost"] else "OVER",
             "delta_color": "normal" if tot["Est Cost"] >= tot["EAC Cost"] else "inverse"},
        ])

        st.dataframe(
            result.style.format({
                "Rate": "${:,.2f}",
                "Actual Hrs": "{:,.0f}", "Actual Cost": "${:,.0f}",
                "FC Hrs": "{:,.0f}", "FC Cost": "${:,.0f}",
                "EAC Hrs": "{:,.0f}", "EAC Cost": "${:,.0f}",
                "Est Hrs": "{:,.0f}", "Est Cost": "${:,.0f}",
                "Var Hrs": "{:+,.0f}", "Var Cost": "${:+,.0f}",
            }).map(
                lambda v: "color: #C5221F; font-weight: bold" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Var Hrs", "Var Cost"],
            ),
            use_container_width=True, hide_index=True,
        )

    # =====================================================================
    # SAVE
    # =====================================================================
    st.divider()
    sc1, sc2, sc3 = st.columns([1, 2, 1])
    with sc1:
        save_name = st.text_input("Your name", key="fc_save_name")
    with sc2:
        save_note = st.text_input("Note", key="fc_save_note")
    with sc3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Save Forecast", type="primary", use_container_width=True, key="fc_save"):
            if not save_name:
                st.warning("Enter your name.")
            else:
                # Collect all contractor forecast plans
                all_plans = {k: v for k, v in st.session_state.items()
                             if k.startswith("fc_") and isinstance(v, dict)}
                # Also include equipment data
                for k in ["equip_actuals", "equip_forecast", "equip_rates"]:
                    if k in st.session_state:
                        all_plans[k] = st.session_state[k]

                success = save_forecast(
                    plans=all_plans, saved_by=save_name, note=save_note,
                )
                if success:
                    st.session_state["forecast_meta"] = {
                        "saved_by": save_name,
                        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "note": save_note,
                    }
                    st.success(f"Forecast saved. This is now the active baseline.")
