"""Allocation Gaps view: unmapped trades and missing rates for review."""

import streamlit as st
import pandas as pd
import numpy as np
from components import metric_row


def render(cost_df: pd.DataFrame, unmapped: pd.DataFrame):
    st.header("Allocation Gaps")

    # --- Unmapped trades (no rate found) ---
    no_rate = cost_df[~cost_df["has_rate"]].copy()

    if len(no_rate) == 0 and len(unmapped) == 0:
        st.success("No allocation gaps found. All gate trades are mapped and have rates.")
        return

    # Summary metrics
    total_hours = cost_df["total_hours"].sum()
    unmapped_hours = no_rate["total_hours"].sum()
    unmapped_pct = (unmapped_hours / total_hours * 100) if total_hours > 0 else 0
    unmapped_people = no_rate["person_id"].nunique()

    metric_row([
        {"label": "Unmapped Hours", "value": unmapped_hours},
        {"label": "% of Total Hours", "value": unmapped_pct, "prefix": "%"},
        {"label": "Affected People", "value": unmapped_people},
        {"label": "Records Affected", "value": len(no_rate)},
    ])

    st.divider()

    # --- Detail: trades with no rate ---
    st.subheader("Trades Without Matching Rate")
    st.caption(
        "These gate trades could not be matched to a rate in the Rate Table. "
        "Hours are tracked but cost cannot be calculated."
    )

    if len(no_rate) > 0:
        gap_summary = no_rate.groupby(["contractor", "trade", "mapped_trade", "mapping_source"]).agg(
            total_hours=("total_hours", "sum"),
            headcount=("person_id", "nunique"),
            records=("person_id", "count"),
            first_date=("date", "min"),
            last_date=("date", "max"),
        ).reset_index().sort_values("total_hours", ascending=False)

        gap_summary.columns = [
            "Contractor", "Gate Trade", "Mapped To", "Mapping Source",
            "Total Hours", "Headcount", "Records", "First Date", "Last Date",
        ]

        st.dataframe(
            gap_summary.style.format({
                "Total Hours": "{:,.1f}",
                "First Date": lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x),
                "Last Date": lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x),
            }),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("All mapped trades have matching rates.")

    # --- Trade mapping audit ---
    st.subheader("Trade Mapping Audit")
    st.caption("Full list of how gate trades were mapped for all records.")

    mapping_audit = cost_df.groupby(
        ["contractor", "trade", "mapped_trade", "mapping_source", "zero_rate"]
    ).agg(
        total_hours=("total_hours", "sum"),
        headcount=("person_id", "nunique"),
        has_rate=("has_rate", "first"),
    ).reset_index().sort_values(["contractor", "trade"])

    mapping_audit.columns = [
        "Contractor", "Gate Trade", "Mapped Trade", "Source", "Zero Rate",
        "Total Hours", "Headcount", "Has Rate",
    ]

    def highlight_gaps(row):
        if not row["Has Rate"] and not row["Zero Rate"]:
            return ["background-color: #FFF3E0"] * len(row)
        return [""] * len(row)

    st.dataframe(
        mapping_audit.style.format({
            "Total Hours": "{:,.1f}",
        }).apply(highlight_gaps, axis=1),
        use_container_width=True, hide_index=True,
    )
