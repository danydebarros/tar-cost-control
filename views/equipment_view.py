"""Equipment Tracker: manual input for crane hours (actuals + forecast) with online save."""

import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from forecast_store import save_forecast, load_forecast
from components import metric_row, COLORS

CRANE_RATES = {
    "Crane - 600 Ton": 550.0,
    "Crane - 175 Ton": 265.0,
    "Crane - 125 Ton": 220.0,
    "Crane - 30 Ton": 140.0,
    "Crane - 15 Ton": 125.0,
}


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Equipment Tracker — Sterling Cranes")

    cranes = list(CRANE_RATES.keys())
    rates = CRANE_RATES

    # Date range
    last_actual = cost_df["date"].max().date()
    project_start = cost_df["date"].min().date()

    # Auto-load saved equipment data
    if "equip_loaded" not in st.session_state:
        saved = load_forecast()
        if saved and "equipment_actuals" in saved.get("plans", {}):
            st.session_state["equip_actuals"] = saved["plans"]["equipment_actuals"]
        if saved and "equipment_forecast" in saved.get("plans", {}):
            st.session_state["equip_forecast"] = saved["plans"]["equipment_forecast"]
        st.session_state["equip_loaded"] = True

    # =====================================================================
    # TAB 1: Actuals (historical)
    # =====================================================================
    tab_actual, tab_forecast, tab_summary = st.tabs(["Actuals", "Forecast", "Summary"])

    with tab_actual:
        st.subheader("Crane Hours — Actuals")
        st.caption(
            "Enter actual crane hours per day. "
            "Values are hours the crane was on site/in use."
        )

        # Build date range for actuals
        actual_dates = pd.date_range(start=project_start, end=last_actual, freq="D")
        actual_labels = [d.strftime("%a %m/%d") for d in actual_dates]

        # Initialize or load
        if "equip_actuals" not in st.session_state:
            st.session_state["equip_actuals"] = {
                crane: [0.0] * len(actual_dates) for crane in cranes
            }

        # Ensure correct length
        for crane in cranes:
            if crane not in st.session_state["equip_actuals"]:
                st.session_state["equip_actuals"][crane] = [0.0] * len(actual_dates)
            elif len(st.session_state["equip_actuals"][crane]) != len(actual_dates):
                old = st.session_state["equip_actuals"][crane]
                if len(old) < len(actual_dates):
                    st.session_state["equip_actuals"][crane] = old + [0.0] * (len(actual_dates) - len(old))
                else:
                    st.session_state["equip_actuals"][crane] = old[:len(actual_dates)]

        actual_df = pd.DataFrame(
            st.session_state["equip_actuals"],
            index=actual_labels,
        ).T
        actual_df.index.name = "Crane"

        edited_actuals = st.data_editor(actual_df, use_container_width=True)

        if edited_actuals is not None:
            for crane in edited_actuals.index:
                vals = pd.to_numeric(edited_actuals.loc[crane], errors="coerce").fillna(0)
                st.session_state["equip_actuals"][crane] = [float(v) for v in vals.values]

        # Actuals summary
        if edited_actuals is not None:
            act_totals = edited_actuals.apply(pd.to_numeric, errors="coerce").fillna(0)
            act_summary = []
            for crane in cranes:
                hrs = float(act_totals.loc[crane].sum())
                act_summary.append({
                    "Crane": crane,
                    "Rate/hr": rates[crane],
                    "Total Hours": hrs,
                    "Total Cost": hrs * rates[crane],
                })
            act_result = pd.DataFrame(act_summary)
            tot_cost = act_result["Total Cost"].sum()
            tot_hrs = act_result["Total Hours"].sum()

            st.metric("Total Equipment Cost (Actuals)", f"${tot_cost:,.0f}")
            st.dataframe(
                act_result.style.format({
                    "Rate/hr": "${:,.0f}",
                    "Total Hours": "{:,.1f}",
                    "Total Cost": "${:,.0f}",
                }),
                use_container_width=True, hide_index=True,
            )

    # =====================================================================
    # TAB 2: Forecast
    # =====================================================================
    with tab_forecast:
        st.subheader("Crane Hours — Forecast")
        st.caption("Enter planned crane hours per day going forward.")

        forecast_start = last_actual + timedelta(days=1)
        fc_days = st.number_input("Forecast days", 7, 60, 14, key="equip_fc_days")
        forecast_dates = pd.date_range(start=forecast_start, periods=fc_days, freq="D")
        fc_labels = [d.strftime("%a %m/%d") for d in forecast_dates]

        if "equip_forecast" not in st.session_state:
            st.session_state["equip_forecast"] = {
                crane: [0.0] * len(forecast_dates) for crane in cranes
            }

        for crane in cranes:
            if crane not in st.session_state["equip_forecast"]:
                st.session_state["equip_forecast"][crane] = [0.0] * len(forecast_dates)
            elif len(st.session_state["equip_forecast"][crane]) != len(forecast_dates):
                st.session_state["equip_forecast"][crane] = [0.0] * len(forecast_dates)

        fc_df = pd.DataFrame(
            st.session_state["equip_forecast"],
            index=fc_labels,
        ).T
        fc_df.index.name = "Crane"

        edited_fc = st.data_editor(fc_df, use_container_width=True)

        if edited_fc is not None:
            for crane in edited_fc.index:
                vals = pd.to_numeric(edited_fc.loc[crane], errors="coerce").fillna(0)
                st.session_state["equip_forecast"][crane] = [float(v) for v in vals.values]

        # Forecast summary
        if edited_fc is not None:
            fc_totals = edited_fc.apply(pd.to_numeric, errors="coerce").fillna(0)
            fc_summary = []
            for crane in cranes:
                hrs = float(fc_totals.loc[crane].sum())
                fc_summary.append({
                    "Crane": crane,
                    "Rate/hr": rates[crane],
                    "Forecast Hours": hrs,
                    "Forecast Cost": hrs * rates[crane],
                })
            fc_result = pd.DataFrame(fc_summary)
            st.metric("Total Equipment Cost (Forecast)", f"${fc_result['Forecast Cost'].sum():,.0f}")
            st.dataframe(
                fc_result.style.format({
                    "Rate/hr": "${:,.0f}",
                    "Forecast Hours": "{:,.1f}",
                    "Forecast Cost": "${:,.0f}",
                }),
                use_container_width=True, hide_index=True,
            )

    # =====================================================================
    # TAB 3: Summary (Actuals + Forecast = EAC)
    # =====================================================================
    with tab_summary:
        st.subheader("Equipment EAC Summary")

        summary_rows = []
        for crane in cranes:
            act_hrs = sum(st.session_state.get("equip_actuals", {}).get(crane, []))
            fc_hrs = sum(st.session_state.get("equip_forecast", {}).get(crane, []))
            rate = rates[crane]
            summary_rows.append({
                "Crane": crane,
                "Rate/hr": rate,
                "Actual Hrs": act_hrs,
                "Actual Cost": act_hrs * rate,
                "Forecast Hrs": fc_hrs,
                "Forecast Cost": fc_hrs * rate,
                "EAC Hrs": act_hrs + fc_hrs,
                "EAC Cost": (act_hrs + fc_hrs) * rate,
            })

        summary_df = pd.DataFrame(summary_rows)
        total = summary_df.select_dtypes(include=[np.number]).sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Actual Equipment Cost", f"${total['Actual Cost']:,.0f}")
        m2.metric("Forecast Equipment Cost", f"${total['Forecast Cost']:,.0f}")
        m3.metric("EAC Equipment Cost", f"${total['EAC Cost']:,.0f}")

        st.dataframe(
            summary_df.style.format({
                "Rate/hr": "${:,.0f}",
                "Actual Hrs": "{:,.1f}",
                "Actual Cost": "${:,.0f}",
                "Forecast Hrs": "{:,.1f}",
                "Forecast Cost": "${:,.0f}",
                "EAC Hrs": "{:,.1f}",
                "EAC Cost": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    # =====================================================================
    # SAVE (equipment data saves with the forecast)
    # =====================================================================
    st.divider()
    sc1, sc2, sc3 = st.columns([1, 2, 1])
    with sc1:
        save_name = st.text_input("Your name", key="equip_save_name")
    with sc2:
        save_note = st.text_input("Note", key="equip_save_note", placeholder="e.g. Updated crane actuals")
    with sc3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Save Equipment Data", type="primary", use_container_width=True, key="equip_save"):
            if not save_name:
                st.warning("Enter your name.")
            else:
                # Merge equipment data into the forecast save
                all_plans = {k: v for k, v in st.session_state.items()
                             if k.startswith("daily_plan_v2_")}
                all_plans["equipment_actuals"] = st.session_state.get("equip_actuals", {})
                all_plans["equipment_forecast"] = st.session_state.get("equip_forecast", {})

                success = save_forecast(
                    plans=all_plans, saved_by=save_name, note=save_note,
                    params={"hours_per_day": 0, "nt_pct": 0, "forecast_days": 0},
                )
                if success:
                    st.success(f"Equipment data saved by {save_name}")
