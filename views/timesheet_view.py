"""Timesheet / Invoice Reconciliation view.

Per contractor, per day, per person breakdown for comparing
against contractor invoices and timesheets.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from components import COLORS


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Timesheet / Invoice Reconciliation")

    # --- Filters ---
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        contractor = st.selectbox(
            "Contractor",
            sorted(cost_df["contractor"].unique()),
            key="ts_contractor",
        )

    cdf = cost_df[cost_df["contractor"] == contractor].copy()
    dates = sorted(cdf["date"].dt.date.unique())

    with col2:
        view_mode = st.radio(
            "View", ["Single Day", "Date Range", "Weekly Summary"],
            horizontal=True, key="ts_mode",
        )

    with col3:
        if view_mode == "Single Day":
            selected_date = st.select_slider(
                "Date", options=dates,
                value=dates[-1] if dates else None,
                format_func=lambda d: d.strftime("%a %b %d"),
                key="ts_date",
            )
            date_mask = cdf["date"].dt.date == selected_date
        elif view_mode == "Date Range":
            c1, c2 = st.columns(2)
            with c1:
                start = st.date_input("From", value=dates[0] if dates else None, key="ts_start")
            with c2:
                end = st.date_input("To", value=dates[-1] if dates else None, key="ts_end")
            date_mask = (cdf["date"].dt.date >= start) & (cdf["date"].dt.date <= end)
        else:  # Weekly
            weeks = sorted(cdf[["iso_year", "iso_week", "week_start"]].drop_duplicates()
                           .itertuples(index=False), key=lambda x: (x[0], x[1]))
            week_labels = {
                (w.iso_year, w.iso_week): f"Week {w.iso_week} ({w.week_start.strftime('%b %d')})"
                for w in weeks
            }
            selected_week = st.selectbox(
                "Week",
                list(week_labels.keys()),
                format_func=lambda k: week_labels[k],
                index=len(week_labels) - 1 if week_labels else 0,
                key="ts_week",
            )
            date_mask = (
                (cdf["iso_year"] == selected_week[0])
                & (cdf["iso_week"] == selected_week[1])
            )

    filtered = cdf[date_mask].copy()

    if filtered.empty:
        st.warning("No records for this selection.")
        return

    # --- Summary banner ---
    total_hrs = filtered["total_hours"].sum()
    total_nt = filtered["nt_hours"].sum()
    total_ot = filtered["ot_hours"].sum()
    has_dt = "dt_hours" in filtered.columns
    total_dt = filtered["dt_hours"].sum() if has_dt else 0
    total_cost = filtered["total_cost"].sum()
    headcount = filtered["person_id"].nunique()
    days = filtered["date"].dt.date.nunique()

    if has_dt:
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    else:
        m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Headcount", f"{headcount}")
    m2.metric("Days", f"{days}")
    m3.metric("Total Hours", f"{total_hrs:,.1f}")
    m4.metric("NT Hours", f"{total_nt:,.1f}")
    m5.metric("OT Hours", f"{total_ot:,.1f}")
    if has_dt:
        m6.metric("DT Hours", f"{total_dt:,.1f}")
        m7.metric("Total Cost", f"${total_cost:,.0f}")
    else:
        m6.metric("Total Cost", f"${total_cost:,.0f}")

    st.divider()

    # --- Person x Day matrix (hours) ---
    st.subheader(f"{contractor} — Hours by Person by Day")

    person_day = filtered.groupby(["name", "date"]).agg(
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
        trade=("mapped_trade", "first"),
    ).reset_index()

    # Pivot: person rows, date columns
    hours_pivot = person_day.pivot_table(
        index="name", columns="date", values="total",
        aggfunc="sum", fill_value=0,
    )
    hours_pivot.columns = [d.strftime("%a %m/%d") for d in hours_pivot.columns]
    hours_pivot["Total"] = hours_pivot.sum(axis=1)

    # Add trade column
    trade_map = person_day.groupby("name")["trade"].first()
    hours_pivot.insert(0, "Trade", hours_pivot.index.map(trade_map))
    hours_pivot = hours_pivot.sort_values(["Trade", "Total"], ascending=[True, False])

    # Add totals row
    totals_row = hours_pivot.select_dtypes(include=[np.number]).sum()
    totals_row["Trade"] = "TOTAL"
    totals_df = pd.DataFrame([totals_row], index=["TOTAL"])
    hours_display = pd.concat([hours_pivot, totals_df])

    st.dataframe(
        hours_display.style.format(
            {c: "{:.1f}" for c in hours_display.columns if c != "Trade"},
            na_rep="",
        ),
        use_container_width=True,
        height=min(800, 56 + 35 * len(hours_display)),
    )

    # --- NT / OT split per person ---
    st.subheader(f"{contractor} — NT / OT Split by Person")

    ntot_agg = dict(
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
    )
    if "dt_hours" in filtered.columns:
        ntot_agg["dt"] = ("dt_hours", "sum")
    ntot_agg.update(dict(
        nt_cost=("nt_cost", "sum"),
        ot_cost=("ot_cost", "sum"),
    ))
    if "dt_cost" in filtered.columns:
        ntot_agg["dt_cost"] = ("dt_cost", "sum")
    ntot_agg.update(dict(
        total_cost=("total_cost", "sum"),
        days=("date", "nunique"),
    ))
    ntot_summary = filtered.groupby(["name", "mapped_trade"]).agg(
        **ntot_agg
    ).reset_index().sort_values("total", ascending=False)

    ntot_summary["ot_pct"] = np.where(
        ntot_summary["total"] > 0,
        ntot_summary["ot"] / ntot_summary["total"] * 100, 0
    )

    ntot_display = ntot_summary.copy()
    col_names = ["Name", "Trade", "Total Hrs", "NT Hrs", "OT Hrs"]
    if "dt" in ntot_summary.columns:
        col_names.append("DT Hrs")
    col_names.extend(["NT Cost", "OT Cost"])
    if "dt_cost" in ntot_summary.columns:
        col_names.append("DT Cost")
    col_names.extend(["Total Cost", "Days", "OT %"])
    ntot_display.columns = col_names

    # Add totals
    num_totals = ntot_display.select_dtypes(include=[np.number]).sum()
    total_row = pd.DataFrame([{
        "Name": "TOTAL", "Trade": "",
        **{c: num_totals[c] for c in num_totals.index},
    }])
    if num_totals["Total Hrs"] > 0:
        total_row["OT %"] = num_totals["OT Hrs"] / num_totals["Total Hrs"] * 100
    ntot_display = pd.concat([ntot_display, total_row], ignore_index=True)

    fmt = {
        "Total Hrs": "{:,.1f}",
        "NT Hrs": "{:,.1f}",
        "OT Hrs": "{:,.1f}",
        "NT Cost": "${:,.2f}",
        "OT Cost": "${:,.2f}",
        "Total Cost": "${:,.2f}",
        "Days": "{:.0f}",
        "OT %": "{:.1f}%",
    }
    if "DT Hrs" in ntot_display.columns:
        fmt["DT Hrs"] = "{:,.1f}"
    if "DT Cost" in ntot_display.columns:
        fmt["DT Cost"] = "${:,.2f}"

    st.dataframe(
        ntot_display.style.format(fmt).map(
            lambda v: "font-weight: bold" if isinstance(v, str) and v == "TOTAL" else "",
            subset=["Name"],
        ),
        use_container_width=True, hide_index=True,
        height=min(800, 56 + 35 * len(ntot_display)),
    )

    # --- Cost breakdown per person per day ---
    st.subheader(f"{contractor} — Daily Cost by Person")

    cost_pivot = filtered.groupby(["name", "date"])["total_cost"].sum().reset_index()
    cost_table = cost_pivot.pivot_table(
        index="name", columns="date", values="total_cost",
        aggfunc="sum", fill_value=0,
    )
    cost_table.columns = [d.strftime("%a %m/%d") for d in cost_table.columns]
    cost_table["Total"] = cost_table.sum(axis=1)
    cost_table.insert(0, "Trade", cost_table.index.map(trade_map))
    cost_table = cost_table.sort_values(["Trade", "Total"], ascending=[True, False])

    # Totals
    cost_totals = cost_table.select_dtypes(include=[np.number]).sum()
    cost_totals["Trade"] = "TOTAL"
    cost_totals_df = pd.DataFrame([cost_totals], index=["TOTAL"])
    cost_display = pd.concat([cost_table, cost_totals_df])

    st.dataframe(
        cost_display.style.format(
            {c: "${:,.2f}" for c in cost_display.columns if c != "Trade"},
            na_rep="",
        ),
        use_container_width=True,
        height=min(800, 56 + 35 * len(cost_display)),
    )

    # --- Trade summary for the period ---
    st.subheader(f"{contractor} — Trade Summary")

    trade_agg = dict(
        headcount=("person_id", "nunique"),
        days=("date", "nunique"),
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
    )
    if "dt_hours" in filtered.columns:
        trade_agg["dt"] = ("dt_hours", "sum")
    trade_agg.update(dict(
        nt_rate=("nt_rate", "first"),
        ot_rate=("ot_rate", "first"),
        nt_cost=("nt_cost", "sum"),
        ot_cost=("ot_cost", "sum"),
    ))
    if "dt_cost" in filtered.columns:
        trade_agg["dt_cost"] = ("dt_cost", "sum")
    trade_agg["total_cost"] = ("total_cost", "sum")

    trade_summary = filtered.groupby("mapped_trade").agg(
        **trade_agg
    ).reset_index().sort_values("total_cost", ascending=False)

    ts_cols = ["Trade", "People", "Days", "Total Hrs", "NT Hrs", "OT Hrs"]
    if "dt" in trade_summary.columns:
        ts_cols.append("DT Hrs")
    ts_cols.extend(["NT Rate", "OT Rate", "NT Cost", "OT Cost"])
    if "dt_cost" in trade_summary.columns:
        ts_cols.append("DT Cost")
    ts_cols.append("Total Cost")
    trade_summary.columns = ts_cols

    ts_fmt = {
        "Total Hrs": "{:,.1f}",
        "NT Hrs": "{:,.1f}",
        "OT Hrs": "{:,.1f}",
        "NT Rate": "${:,.2f}",
        "OT Rate": "${:,.2f}",
        "NT Cost": "${:,.2f}",
        "OT Cost": "${:,.2f}",
        "Total Cost": "${:,.2f}",
    }
    if "DT Hrs" in trade_summary.columns:
        ts_fmt["DT Hrs"] = "{:,.1f}"
    if "DT Cost" in trade_summary.columns:
        ts_fmt["DT Cost"] = "${:,.2f}"

    st.dataframe(
        trade_summary.style.format(ts_fmt),
        use_container_width=True, hide_index=True,
    )

    # --- Downloadable detail ---
    st.subheader("Export Detail")

    export_cols = [
        "date", "name", "trade", "mapped_trade", "paid_hours",
        "nt_hours", "ot_hours",
    ]
    export_col_names = [
        "Date", "Name", "Gate Trade", "Mapped Trade", "Paid Hours",
        "NT Hours", "OT Hours",
    ]
    if "dt_hours" in filtered.columns:
        export_cols.append("dt_hours")
        export_col_names.append("DT Hours")
    export_cols.extend(["nt_rate", "ot_rate", "nt_cost", "ot_cost"])
    export_col_names.extend(["NT Rate", "OT Rate", "NT Cost", "OT Cost"])
    if "dt_cost" in filtered.columns:
        export_cols.append("dt_cost")
        export_col_names.append("DT Cost")
    export_cols.append("total_cost")
    export_col_names.append("Total Cost")

    export = filtered[export_cols].copy()
    export["date"] = export["date"].dt.strftime("%Y-%m-%d")
    export.columns = export_col_names
    export = export.sort_values(["Date", "Mapped Trade", "Name"])

    csv = export.to_csv(index=False)
    st.download_button(
        f"Download {contractor} detail as CSV",
        csv,
        file_name=f"{contractor}_timesheet_detail.csv",
        mime="text/csv",
        use_container_width=True,
    )
