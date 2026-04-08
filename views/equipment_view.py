"""Equipment / Other Costs: per-contractor manual input for equipment, per diem, etc."""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from forecast_store import save_forecast, load_forecast
from components import metric_row

# Default items available for all contractors (rate is set per contractor)
EQUIPMENT_ITEMS = [
    "Crane - 600 Ton",
    "Crane - 175 Ton",
    "Crane - 125 Ton",
    "Crane - 30 Ton",
    "Crane - 15 Ton",
    "Per Diem - IFL",
    "Per Diem - DFL",
    "Mobilization Cost",
    "Truck Hourly",
    "Gas Monitor",
    "Other",
]

# Default rates per contractor (user can override in the app)
DEFAULT_RATES = {
    "Sterling": {
        "Crane - 600 Ton": 550, "Crane - 175 Ton": 265, "Crane - 125 Ton": 220,
        "Crane - 30 Ton": 140, "Crane - 15 Ton": 125,
    },
}


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Equipment / Other Costs")

    contractors = sorted(cost_df["contractor"].unique())
    last_actual = cost_df["date"].max().date()
    project_start = cost_df["date"].min().date()

    # Auto-load saved data
    if "equip_loaded" not in st.session_state:
        saved = load_forecast()
        if saved and "plans" in saved:
            plans = saved["plans"]
            if "equip_actuals" in plans:
                st.session_state["equip_actuals"] = plans["equip_actuals"]
            if "equip_forecast" in plans:
                st.session_state["equip_forecast"] = plans["equip_forecast"]
            if "equip_rates" in plans:
                st.session_state["equip_rates"] = plans["equip_rates"]
        st.session_state["equip_loaded"] = True

    # Select contractor
    contractor = st.selectbox("Contractor", contractors, key="equip_contractor")

    # =====================================================================
    # RATES setup for this contractor
    # =====================================================================
    with st.expander("Set Rates for this Contractor", expanded=False):
        if "equip_rates" not in st.session_state:
            st.session_state["equip_rates"] = {}
        if contractor not in st.session_state["equip_rates"]:
            st.session_state["equip_rates"][contractor] = (
                DEFAULT_RATES.get(contractor, {}).copy()
            )

        rate_data = []
        for item in EQUIPMENT_ITEMS:
            current = st.session_state["equip_rates"][contractor].get(item, 0)
            rate_data.append({"Item": item, "Rate ($/unit)": current})

        rate_df = pd.DataFrame(rate_data)
        edited_rates = st.data_editor(
            rate_df, disabled=["Item"], use_container_width=True,
            key=f"equip_rate_edit_{contractor}",
        )

        if edited_rates is not None:
            for _, row in edited_rates.iterrows():
                val = pd.to_numeric(row["Rate ($/unit)"], errors="coerce")
                st.session_state["equip_rates"][contractor][row["Item"]] = (
                    float(val) if pd.notna(val) else 0
                )

    # =====================================================================
    # TABS: Actuals | Forecast | Summary
    # =====================================================================
    tab_actual, tab_forecast, tab_summary = st.tabs(["Actuals", "Forecast", "Summary"])

    rates = st.session_state.get("equip_rates", {}).get(contractor, {})
    # Only show items that have a rate > 0 for this contractor
    active_items = [item for item in EQUIPMENT_ITEMS if rates.get(item, 0) > 0]

    if not active_items:
        st.info("Set rates for at least one item above to start tracking.")
        return

    # --- ACTUALS ---
    with tab_actual:
        st.subheader(f"{contractor} — Equipment Actuals")
        st.caption("Enter actual hours/units per day.")

        actual_dates = pd.date_range(start=project_start, end=last_actual, freq="D")
        actual_labels = [d.strftime("%a %m/%d") for d in actual_dates]

        if "equip_actuals" not in st.session_state:
            st.session_state["equip_actuals"] = {}
        if contractor not in st.session_state["equip_actuals"]:
            st.session_state["equip_actuals"][contractor] = {}

        c_actuals = st.session_state["equip_actuals"][contractor]
        for item in active_items:
            if item not in c_actuals:
                c_actuals[item] = [0.0] * len(actual_dates)
            elif len(c_actuals[item]) < len(actual_dates):
                c_actuals[item] += [0.0] * (len(actual_dates) - len(c_actuals[item]))
            elif len(c_actuals[item]) > len(actual_dates):
                c_actuals[item] = c_actuals[item][:len(actual_dates)]

        act_df = pd.DataFrame(
            {item: c_actuals[item] for item in active_items},
            index=actual_labels,
        ).T
        act_df.index.name = "Item"

        edited_act = st.data_editor(act_df, use_container_width=True)

        if edited_act is not None:
            for item in edited_act.index:
                vals = pd.to_numeric(edited_act.loc[item], errors="coerce").fillna(0)
                c_actuals[item] = [float(v) for v in vals.values]

        # Actuals summary
        act_summary = []
        for item in active_items:
            hrs = sum(c_actuals.get(item, []))
            rate = rates.get(item, 0)
            act_summary.append({
                "Item": item, "Rate": rate, "Total Units": hrs, "Total Cost": hrs * rate,
            })
        act_result = pd.DataFrame(act_summary)
        st.metric("Actual Equipment Cost", f"${act_result['Total Cost'].sum():,.0f}")
        st.dataframe(
            act_result.style.format({
                "Rate": "${:,.0f}", "Total Units": "{:,.1f}", "Total Cost": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    # --- FORECAST ---
    with tab_forecast:
        st.subheader(f"{contractor} — Equipment Forecast")

        forecast_start = last_actual + timedelta(days=1)
        fc_days = st.number_input("Forecast days", 7, 60, 14, key="equip_fc_days")
        forecast_dates = pd.date_range(start=forecast_start, periods=fc_days, freq="D")
        fc_labels = [d.strftime("%a %m/%d") for d in forecast_dates]

        if "equip_forecast" not in st.session_state:
            st.session_state["equip_forecast"] = {}
        if contractor not in st.session_state["equip_forecast"]:
            st.session_state["equip_forecast"][contractor] = {}

        c_forecast = st.session_state["equip_forecast"][contractor]
        for item in active_items:
            if item not in c_forecast:
                c_forecast[item] = [0.0] * len(forecast_dates)
            elif len(c_forecast[item]) != len(forecast_dates):
                c_forecast[item] = [0.0] * len(forecast_dates)

        fc_df = pd.DataFrame(
            {item: c_forecast[item] for item in active_items},
            index=fc_labels,
        ).T
        fc_df.index.name = "Item"

        edited_fc = st.data_editor(fc_df, use_container_width=True)

        if edited_fc is not None:
            for item in edited_fc.index:
                vals = pd.to_numeric(edited_fc.loc[item], errors="coerce").fillna(0)
                c_forecast[item] = [float(v) for v in vals.values]

        fc_summary = []
        for item in active_items:
            hrs = sum(c_forecast.get(item, []))
            rate = rates.get(item, 0)
            fc_summary.append({
                "Item": item, "Rate": rate, "Forecast Units": hrs, "Forecast Cost": hrs * rate,
            })
        fc_result = pd.DataFrame(fc_summary)
        st.metric("Forecast Equipment Cost", f"${fc_result['Forecast Cost'].sum():,.0f}")
        st.dataframe(
            fc_result.style.format({
                "Rate": "${:,.0f}", "Forecast Units": "{:,.1f}", "Forecast Cost": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    # --- SUMMARY (EAC) ---
    with tab_summary:
        st.subheader(f"{contractor} — Equipment EAC")

        summary_rows = []
        for item in active_items:
            rate = rates.get(item, 0)
            act_hrs = sum(st.session_state.get("equip_actuals", {}).get(contractor, {}).get(item, []))
            fc_hrs = sum(st.session_state.get("equip_forecast", {}).get(contractor, {}).get(item, []))
            summary_rows.append({
                "Item": item, "Rate": rate,
                "Actual": act_hrs, "Actual Cost": act_hrs * rate,
                "Forecast": fc_hrs, "Forecast Cost": fc_hrs * rate,
                "EAC": act_hrs + fc_hrs, "EAC Cost": (act_hrs + fc_hrs) * rate,
            })

        summary_df = pd.DataFrame(summary_rows)
        total = summary_df.select_dtypes(include=[np.number]).sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Actual", f"${total['Actual Cost']:,.0f}")
        m2.metric("Forecast", f"${total['Forecast Cost']:,.0f}")
        m3.metric("EAC", f"${total['EAC Cost']:,.0f}")

        st.dataframe(
            summary_df.style.format({
                "Rate": "${:,.0f}",
                "Actual": "{:,.1f}", "Actual Cost": "${:,.0f}",
                "Forecast": "{:,.1f}", "Forecast Cost": "${:,.0f}",
                "EAC": "{:,.1f}", "EAC Cost": "${:,.0f}",
            }),
            use_container_width=True, hide_index=True,
        )

    # --- All contractors summary ---
    st.divider()
    st.subheader("All Contractors — Equipment/Other Totals")

    all_summary = []
    for c in contractors:
        c_rates = st.session_state.get("equip_rates", {}).get(c, {})
        c_act = st.session_state.get("equip_actuals", {}).get(c, {})
        c_fc = st.session_state.get("equip_forecast", {}).get(c, {})
        act_total = sum(sum(hrs) * c_rates.get(item, 0) for item, hrs in c_act.items())
        fc_total = sum(sum(hrs) * c_rates.get(item, 0) for item, hrs in c_fc.items())
        all_summary.append({
            "Contractor": c, "Actual Cost": act_total,
            "Forecast Cost": fc_total, "EAC Cost": act_total + fc_total,
        })

    all_df = pd.DataFrame(all_summary)
    st.dataframe(
        all_df.style.format({
            "Actual Cost": "${:,.0f}", "Forecast Cost": "${:,.0f}", "EAC Cost": "${:,.0f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # --- SAVE ---
    st.divider()
    sc1, sc2, sc3 = st.columns([1, 2, 1])
    with sc1:
        save_name = st.text_input("Your name", key="equip_save_name")
    with sc2:
        save_note = st.text_input("Note", key="equip_save_note")
    with sc3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Save Equipment Data", type="primary", use_container_width=True, key="equip_save"):
            if not save_name:
                st.warning("Enter your name.")
            else:
                all_plans = {k: v for k, v in st.session_state.items()
                             if k.startswith("daily_plan_v2_")}
                all_plans["equip_actuals"] = st.session_state.get("equip_actuals", {})
                all_plans["equip_forecast"] = st.session_state.get("equip_forecast", {})
                all_plans["equip_rates"] = st.session_state.get("equip_rates", {})

                success = save_forecast(
                    plans=all_plans, saved_by=save_name, note=save_note,
                )
                if success:
                    st.success(f"Equipment data saved by {save_name}")
