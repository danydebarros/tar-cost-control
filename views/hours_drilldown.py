"""Hours Drill-Down view: Week > Contractor > Trade > Person hierarchy."""

import streamlit as st
import pandas as pd
import numpy as np
from components import COLORS


def render(cost_df: pd.DataFrame, comparison: pd.DataFrame):
    st.header("Hours Drill-Down")
    st.caption("Expand levels: Week > Contractor > Trade > Person")

    # --- Weekly summary (top level) ---
    wk_agg = dict(
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
    )
    has_dt = "dt_hours" in cost_df.columns
    if has_dt:
        wk_agg["dt"] = ("dt_hours", "sum")
    wk_agg.update(dict(
        cost=("total_cost", "sum"),
        headcount=("person_id", "nunique"),
        days=("date", "nunique"),
    ))
    weekly = cost_df.groupby(["iso_year", "iso_week", "week_start"]).agg(
        **wk_agg
    ).reset_index().sort_values("week_start")

    weekly["label"] = weekly.apply(
        lambda r: f"Week {int(r['iso_week'])} ({r['week_start'].strftime('%b %d')})", axis=1
    )
    weekly["ot_pct"] = np.where(weekly["total"] > 0, weekly["ot"] / weekly["total"] * 100, 0)

    # Weekly summary table
    wk_cols = ["label", "days", "headcount", "total", "nt", "ot"]
    wk_col_names = ["Week", "Days", "People", "Total Hrs", "NT", "OT"]
    if has_dt:
        wk_cols.append("dt")
        wk_col_names.append("DT")
    wk_cols.extend(["ot_pct", "cost"])
    wk_col_names.extend(["OT %", "Cost"])
    wk_display = weekly[wk_cols].copy()
    wk_display.columns = wk_col_names

    totals = wk_display.select_dtypes(include=[np.number]).sum()
    tot_dict = {
        "Week": "TOTAL", "Days": int(totals["Days"]), "People": "",
        "Total Hrs": totals["Total Hrs"], "NT": totals["NT"], "OT": totals["OT"],
        "OT %": totals["OT"] / totals["Total Hrs"] * 100 if totals["Total Hrs"] > 0 else 0,
        "Cost": totals["Cost"],
    }
    if has_dt:
        tot_dict["DT"] = totals["DT"]
    tot_row = pd.DataFrame([tot_dict])
    wk_display = pd.concat([wk_display, tot_row], ignore_index=True)

    wk_fmt = {
        "Total Hrs": "{:,.0f}", "NT": "{:,.0f}", "OT": "{:,.0f}",
        "OT %": "{:.1f}%", "Cost": "${:,.0f}",
    }
    if has_dt:
        wk_fmt["DT"] = "{:,.0f}"
    st.dataframe(
        wk_display.style.format(wk_fmt),
        use_container_width=True, hide_index=True,
    )

    # --- Drill-down: select week ---
    st.divider()
    week_options = list(zip(weekly["iso_year"], weekly["iso_week"], weekly["label"]))
    selected_week = st.selectbox(
        "Select week to drill into",
        week_options,
        format_func=lambda x: x[2],
        index=len(week_options) - 1 if week_options else 0,
        key="dd_week",
    )

    if not selected_week:
        return

    yr, wk, wk_label = selected_week
    wk_data = cost_df[(cost_df["iso_year"] == yr) & (cost_df["iso_week"] == wk)]

    st.subheader(f"{wk_label}")

    # --- Contractor level ---
    c_agg = dict(
        total=("total_hours", "sum"), nt=("nt_hours", "sum"), ot=("ot_hours", "sum"),
    )
    if has_dt:
        c_agg["dt"] = ("dt_hours", "sum")
    c_agg.update(dict(cost=("total_cost", "sum"), headcount=("person_id", "nunique")))
    by_contractor = wk_data.groupby("contractor").agg(
        **c_agg
    ).reset_index().sort_values("total", ascending=False)
    by_contractor["ot_pct"] = np.where(
        by_contractor["total"] > 0, by_contractor["ot"] / by_contractor["total"] * 100, 0
    )

    for _, crow in by_contractor.iterrows():
        contractor = crow["contractor"]
        c_data = wk_data[wk_data["contractor"] == contractor]

        with st.expander(
            f"**{contractor}** — {crow['total']:,.0f} hrs "
            f"({crow['headcount']} people, OT {crow['ot_pct']:.0f}%) — "
            f"${crow['cost']:,.0f}"
        ):
            # --- Trade level ---
            t_agg = dict(
                total=("total_hours", "sum"), nt=("nt_hours", "sum"), ot=("ot_hours", "sum"),
            )
            if has_dt:
                t_agg["dt"] = ("dt_hours", "sum")
            t_agg.update(dict(
                cost=("total_cost", "sum"), headcount=("person_id", "nunique"),
                has_rate=("has_rate", "first"),
                zero_rate=("zero_rate", "first"),
            ))
            by_trade = c_data.groupby("mapped_trade").agg(
                **t_agg
            ).reset_index().sort_values("total", ascending=False)

            for _, trow in by_trade.iterrows():
                trade = trow["mapped_trade"]
                t_data = c_data[c_data["mapped_trade"] == trade]

                rate_flag = ""
                if trow["zero_rate"]:
                    rate_flag = " (no charge)"
                elif not trow["has_rate"]:
                    rate_flag = " **UNCOSTED**"

                st.markdown(
                    f"**{trade}**{rate_flag} — "
                    f"{trow['total']:,.1f} hrs ({trow['headcount']} people) — "
                    f"${trow['cost']:,.0f}"
                )

                # --- Person level ---
                p_agg = dict(
                    days=("date", "nunique"),
                    total=("total_hours", "sum"),
                    nt=("nt_hours", "sum"),
                    ot=("ot_hours", "sum"),
                )
                if has_dt:
                    p_agg["dt"] = ("dt_hours", "sum")
                p_agg["cost"] = ("total_cost", "sum")
                by_person = t_data.groupby("name").agg(
                    **p_agg
                ).reset_index().sort_values("total", ascending=False)

                p_col_names = ["Name", "Days", "Total", "NT", "OT"]
                if has_dt:
                    p_col_names.append("DT")
                p_col_names.append("Cost")
                by_person.columns = p_col_names

                p_fmt = {
                    "Total": "{:,.1f}", "NT": "{:,.1f}", "OT": "{:,.1f}",
                    "Cost": "${:,.2f}",
                }
                if has_dt:
                    p_fmt["DT"] = "{:,.1f}"
                st.dataframe(
                    by_person.style.format(p_fmt),
                    use_container_width=True, hide_index=True,
                    height=min(400, 56 + 35 * len(by_person)),
                )

    # --- Unmapped trades for reallocation ---
    st.divider()
    st.subheader("Trades Needing Reallocation")
    st.caption(
        "These trades from the gate data could not be matched to an estimate trade. "
        "Update the trade mapping in config.py or tell me how to remap them."
    )

    uncosted = cost_df[~cost_df["has_rate"] & ~cost_df["zero_rate"]].copy()
    if len(uncosted) == 0:
        # Also show passthrough trades that may need review
        passthrough = cost_df[cost_df["mapping_source"] == "passthrough"].copy()
        if len(passthrough) > 0:
            pt_summary = passthrough.groupby(["contractor", "trade", "mapped_trade"]).agg(
                hours=("total_hours", "sum"),
                people=("person_id", "nunique"),
                has_rate=("has_rate", "first"),
            ).reset_index().sort_values(["contractor", "hours"], ascending=[True, False])
            pt_summary.columns = ["Contractor", "Gate Trade", "Mapped To", "Hours", "People", "Has Rate"]

            costed_pt = pt_summary[pt_summary["Has Rate"]]
            uncosted_pt = pt_summary[~pt_summary["Has Rate"]]

            if len(uncosted_pt) > 0:
                st.warning(f"{len(uncosted_pt)} passthrough trade(s) with no matching rate:")
                st.dataframe(uncosted_pt.style.format({"Hours": "{:,.1f}"}),
                             use_container_width=True, hide_index=True)
            else:
                st.success("All trades are mapped and costed. No reallocation needed.")

            if len(costed_pt) > 0:
                with st.expander("Passthrough trades (matched by name, no explicit rule)"):
                    st.dataframe(costed_pt.style.format({"Hours": "{:,.1f}"}),
                                 use_container_width=True, hide_index=True)
        else:
            st.success("All trades are mapped and costed. No reallocation needed.")
    else:
        gap_summary = uncosted.groupby(["contractor", "trade", "mapped_trade"]).agg(
            hours=("total_hours", "sum"),
            people=("person_id", "nunique"),
        ).reset_index().sort_values("hours", ascending=False)
        gap_summary.columns = ["Contractor", "Gate Trade", "Mapped To", "Hours", "People"]
        st.dataframe(
            gap_summary.style.format({"Hours": "{:,.1f}"}),
            use_container_width=True, hide_index=True,
        )
        st.info(
            "Tell me how to remap these trades and I'll update the config. "
            "For example: 'Map Claymar Safety to Safety Supervisor'"
        )
