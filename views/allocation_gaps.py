"""Data Audit & Allocation Gaps view.

Full reconciliation: confirms all manhours and trades are accounted for,
flags anything dropped or uncosted.
"""

import streamlit as st
import pandas as pd
import numpy as np
from components import metric_row, COLORS


def render(cost_df: pd.DataFrame, unmapped: pd.DataFrame,
           gate_raw: pd.DataFrame = None, gate_clean: pd.DataFrame = None):
    st.header("Data Audit & Allocation Gaps")

    # =====================================================================
    # SECTION 1: Pipeline Reconciliation
    # =====================================================================
    st.subheader("1. Pipeline Reconciliation")
    st.caption(
        "Confirms that every gate record is accounted for through the processing pipeline. "
        "No hours should be lost between raw gate data and final costed output."
    )

    raw_rows = len(gate_raw) if gate_raw is not None else 0
    clean_rows = len(gate_clean) if gate_clean is not None else 0
    costed_rows = len(cost_df)
    dropped_filter = raw_rows - clean_rows  # Dropped because not in-scope contractor
    dropped_processing = clean_rows - costed_rows

    raw_hours = 0
    if gate_raw is not None and "Less: Lunch Deduction" in gate_raw.columns:
        raw_hours = pd.to_numeric(gate_raw["Less: Lunch Deduction"], errors="coerce").sum()
    elif gate_raw is not None and "Onsite Hours" in gate_raw.columns:
        raw_hours = pd.to_numeric(gate_raw["Onsite Hours"], errors="coerce").sum()

    clean_hours = gate_clean["paid_hours"].sum() if gate_clean is not None else 0
    costed_hours = cost_df["total_hours"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Raw Gate Records", f"{raw_rows:,}")
    col2.metric("In-Scope (6 Contractors)", f"{clean_rows:,}",
                delta=f"{dropped_filter:,} other contractors filtered out")
    col3.metric("Costed Records", f"{costed_rows:,}",
                delta=f"{dropped_processing:,} dropped in processing" if dropped_processing else "All accounted for")
    col4.metric("Costed Hours", f"{costed_hours:,.1f}")

    # Check: do clean hours = costed hours?
    hours_diff = abs(clean_hours - costed_hours)
    if hours_diff < 0.1:
        st.success(
            f"All {costed_hours:,.1f} hours from in-scope contractors are fully accounted for. "
            f"No hours lost in processing."
        )
    else:
        st.warning(
            f"Hours mismatch: {clean_hours:,.1f} cleaned vs {costed_hours:,.1f} costed. "
            f"Difference: {hours_diff:,.1f} hours. Check processing pipeline."
        )

    # Show what was filtered out (other contractors)
    if gate_raw is not None and dropped_filter > 0:
        with st.expander(f"View {dropped_filter:,} records filtered out (other contractors)"):
            from config import CONTRACTOR_NAME_MAP
            if "Contractor" in gate_raw.columns:
                other = gate_raw[~gate_raw["Contractor"].isin(CONTRACTOR_NAME_MAP.keys())]
            else:
                other = pd.DataFrame()

            if len(other) > 0:
                other_summary = other.groupby("Contractor").agg(
                    records=("Contractor", "count"),
                    hours=("Less: Lunch Deduction", lambda x: pd.to_numeric(x, errors="coerce").sum()),
                ).reset_index().sort_values("hours", ascending=False)
                other_summary.columns = ["Contractor", "Records", "Total Hours"]
                st.dataframe(
                    other_summary.style.format({"Total Hours": "{:,.1f}"}),
                    use_container_width=True, hide_index=True,
                )
                st.caption(
                    "These contractors are not in scope (Axis, Claymar, Custofab, PK Safety, PMI, Spartan). "
                    "Their hours are excluded from all calculations."
                )

    # =====================================================================
    # SECTION 2: Trade Mapping Audit
    # =====================================================================
    st.divider()
    st.subheader("2. Trade Mapping Audit")
    st.caption(
        "Every gate trade must map to an estimate trade to be costed. "
        "This table shows how every trade was mapped and whether it has a matching rate."
    )

    mapping_audit = cost_df.groupby(
        ["contractor", "trade", "mapped_trade", "mapping_source", "zero_rate", "has_rate"]
    ).agg(
        total_hours=("total_hours", "sum"),
        headcount=("person_id", "nunique"),
        records=("person_id", "count"),
        total_cost=("total_cost", "sum"),
    ).reset_index().sort_values(["contractor", "trade"])

    # Status column
    def get_status(row):
        if row["zero_rate"]:
            return "No Charge (hours tracked, $0 rate)"
        elif row["has_rate"]:
            return "Costed"
        else:
            return "UNCOSTED — No matching rate"

    mapping_audit["Status"] = mapping_audit.apply(get_status, axis=1)

    display = mapping_audit[[
        "contractor", "trade", "mapped_trade", "mapping_source",
        "Status", "headcount", "records", "total_hours", "total_cost",
    ]].copy()
    display.columns = [
        "Contractor", "Gate Trade", "Mapped To", "Rule",
        "Status", "People", "Records", "Hours", "Cost",
    ]

    # Color code
    def highlight_status(row):
        if "UNCOSTED" in str(row["Status"]):
            return ["background-color: #FFEBEE"] * len(row)
        elif "No Charge" in str(row["Status"]):
            return ["background-color: #FFF8E1"] * len(row)
        return [""] * len(row)

    st.dataframe(
        display.style.format({
            "Hours": "{:,.1f}",
            "Cost": "${:,.0f}",
        }).apply(highlight_status, axis=1),
        use_container_width=True, hide_index=True,
        height=min(800, 56 + 35 * len(display)),
    )

    # Summary counts
    costed = mapping_audit[mapping_audit["has_rate"] & ~mapping_audit["zero_rate"]]
    zero_rate = mapping_audit[mapping_audit["zero_rate"]]
    uncosted = mapping_audit[~mapping_audit["has_rate"] & ~mapping_audit["zero_rate"]]

    col1, col2, col3 = st.columns(3)
    col1.metric("Costed Trades",
                f"{len(costed)} ({costed['total_hours'].sum():,.0f} hrs)")
    col2.metric("No-Charge Trades",
                f"{len(zero_rate)} ({zero_rate['total_hours'].sum():,.0f} hrs)")
    col3.metric("Uncosted Trades",
                f"{len(uncosted)} ({uncosted['total_hours'].sum():,.0f} hrs)",
                delta="Action needed" if len(uncosted) > 0 else None,
                delta_color="inverse" if len(uncosted) > 0 else "normal")

    if len(uncosted) == 0:
        st.success("All trades are either costed or intentionally zero-rated. No gaps.")
    else:
        st.error(
            f"{len(uncosted)} trade(s) with {uncosted['total_hours'].sum():,.0f} hours "
            f"have no matching rate. These hours are tracked but NOT included in cost totals."
        )

    # =====================================================================
    # SECTION 3: Rate Coverage Check
    # =====================================================================
    st.divider()
    st.subheader("3. Rate Coverage Check")
    st.caption(
        "Verifies that every contractor/trade combination from actuals "
        "has a matching entry in the rate table."
    )

    rate_check = cost_df.groupby(["contractor", "mapped_trade"]).agg(
        hours=("total_hours", "sum"),
        nt_rate=("nt_rate", "first"),
        ot_rate=("ot_rate", "first"),
        st_rate=("st_rate", "first"),
        zero_rate=("zero_rate", "first"),
        has_rate=("has_rate", "first"),
        cost=("total_cost", "sum"),
    ).reset_index()

    rate_check["Rate Status"] = rate_check.apply(
        lambda r: "Zero Rate" if r["zero_rate"]
        else "OK" if r["has_rate"]
        else "MISSING", axis=1
    )

    rate_display = rate_check[[
        "contractor", "mapped_trade", "hours", "nt_rate", "ot_rate",
        "st_rate", "Rate Status", "cost",
    ]].copy()
    rate_display.columns = [
        "Contractor", "Trade", "Hours", "NT Rate", "OT Rate",
        "ST Rate", "Status", "Cost",
    ]

    st.dataframe(
        rate_display.style.format({
            "Hours": "{:,.1f}",
            "NT Rate": "${:,.2f}",
            "OT Rate": "${:,.2f}",
            "ST Rate": "${:,.2f}",
            "Cost": "${:,.0f}",
        }).map(
            lambda v: "color: #C5221F; font-weight: bold" if v == "MISSING" else "",
            subset=["Status"],
        ),
        use_container_width=True, hide_index=True,
    )

    # =====================================================================
    # SECTION 4: Hours Cross-Check by Contractor
    # =====================================================================
    st.divider()
    st.subheader("4. Hours Cross-Check by Contractor")
    st.caption("Compare total hours from gate data against costed hours per contractor.")

    cross_check = cost_df.groupby("contractor").agg(
        gate_hours=("paid_hours", "sum"),
        costed_hours=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
        cost=("total_cost", "sum"),
        people=("person_id", "nunique"),
        records=("person_id", "count"),
    ).reset_index()

    cross_check["nt_ot_check"] = cross_check["nt"] + cross_check["ot"]
    cross_check["hours_match"] = abs(cross_check["gate_hours"] - cross_check["nt_ot_check"]) < 0.1

    cc_display = cross_check[[
        "contractor", "records", "people", "gate_hours",
        "nt", "ot", "nt_ot_check", "hours_match", "cost",
    ]].copy()
    cc_display.columns = [
        "Contractor", "Records", "People", "Gate Hours",
        "NT", "OT", "NT+OT", "Match", "Total Cost",
    ]

    # Totals
    tot = cc_display.select_dtypes(include=[np.number]).sum()
    tot_row = pd.DataFrame([{
        "Contractor": "TOTAL",
        "Records": int(tot["Records"]),
        "People": int(tot["People"]),
        "Gate Hours": tot["Gate Hours"],
        "NT": tot["NT"],
        "OT": tot["OT"],
        "NT+OT": tot["NT+OT"],
        "Match": abs(tot["Gate Hours"] - tot["NT+OT"]) < 0.1,
        "Total Cost": tot["Total Cost"],
    }])
    cc_display = pd.concat([cc_display, tot_row], ignore_index=True)

    st.dataframe(
        cc_display.style.format({
            "Gate Hours": "{:,.1f}",
            "NT": "{:,.1f}",
            "OT": "{:,.1f}",
            "NT+OT": "{:,.1f}",
            "Total Cost": "${:,.0f}",
        }).map(
            lambda v: "color: #0D904F" if v is True else ("color: #C5221F; font-weight: bold" if v is False else ""),
            subset=["Match"],
        ),
        use_container_width=True, hide_index=True,
    )

    all_match = cross_check["hours_match"].all()
    if all_match:
        st.success("All contractors: Gate Hours = NT + OT. No hours lost in the NT/OT split.")
    else:
        mismatches = cross_check[~cross_check["hours_match"]]
        st.error(f"Hours mismatch for: {', '.join(mismatches['contractor'].tolist())}")

    # =====================================================================
    # SECTION 5: NT/OT Integrity Check
    # =====================================================================
    st.divider()
    st.subheader("5. NT/OT Integrity Check")
    st.caption(
        "Verifies the 40-hour rule: no person should have more than 40 NT hours in any week."
    )

    weekly = cost_df.groupby(["person_id", "iso_year", "iso_week"]).agg(
        name=("name", "first"),
        contractor=("contractor", "first"),
        total=("total_hours", "sum"),
        nt=("nt_hours", "sum"),
        ot=("ot_hours", "sum"),
    ).reset_index()

    violations = weekly[weekly["nt"] > 40.01]  # small tolerance

    col1, col2, col3 = st.columns(3)
    col1.metric("Person-Weeks Checked", f"{len(weekly):,}")
    col2.metric("Violations (NT > 40)", f"{len(violations)}")
    col3.metric("Max NT in a Week", f"{weekly['nt'].max():.1f}")

    if len(violations) == 0:
        st.success("NT/OT rule verified: no person exceeds 40 NT hours in any week.")
    else:
        st.error(f"{len(violations)} violations found:")
        st.dataframe(violations[["name", "contractor", "iso_week", "total", "nt", "ot"]]
                     .sort_values("nt", ascending=False),
                     use_container_width=True, hide_index=True)
