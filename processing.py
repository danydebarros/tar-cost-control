"""
Core processing: trade mapping, NT/OT calculation (per person per week),
cost engine, and estimate comparison.
"""

import pandas as pd
import numpy as np
from config import (
    CONTRACTOR_TRADE_MAPPINGS,
    GENERAL_TRADE_NORMALIZATIONS,
    NT_WEEKLY_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Trade mapping
# ---------------------------------------------------------------------------

def apply_trade_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Apply contractor-specific trade mapping rules, then general normalizations.
    Adds columns: mapped_trade, zero_rate, mapping_source, is_mapped.
    """
    df = df.copy()
    df["mapped_trade"] = None
    df["zero_rate"] = False
    df["mapping_source"] = "unmapped"

    for idx, row in df.iterrows():
        contractor = row["contractor"]
        trade = row["trade"]

        # 1. Check contractor-specific mapping
        if contractor in CONTRACTOR_TRADE_MAPPINGS:
            cmap = CONTRACTOR_TRADE_MAPPINGS[contractor]
            if trade in cmap:
                df.at[idx, "mapped_trade"] = cmap[trade]["mapped_trade"]
                df.at[idx, "zero_rate"] = cmap[trade].get("zero_rate", False)
                df.at[idx, "mapping_source"] = "contractor_specific"
                continue
            # Case-insensitive match
            for key, val in cmap.items():
                if key.lower() == trade.lower():
                    df.at[idx, "mapped_trade"] = val["mapped_trade"]
                    df.at[idx, "zero_rate"] = val.get("zero_rate", False)
                    df.at[idx, "mapping_source"] = "contractor_specific"
                    break
            if df.at[idx, "mapping_source"] == "contractor_specific":
                continue

        # 2. Check general normalizations
        if trade in GENERAL_TRADE_NORMALIZATIONS:
            df.at[idx, "mapped_trade"] = GENERAL_TRADE_NORMALIZATIONS[trade]
            df.at[idx, "mapping_source"] = "general"
            continue
        for key, val in GENERAL_TRADE_NORMALIZATIONS.items():
            if key.lower() == trade.lower():
                df.at[idx, "mapped_trade"] = val
                df.at[idx, "mapping_source"] = "general"
                break
        if df.at[idx, "mapping_source"] == "general":
            continue

        # 3. No mapping found - use original trade name
        df.at[idx, "mapped_trade"] = trade
        df.at[idx, "mapping_source"] = "passthrough"

    df["is_mapped"] = df["mapping_source"] != "unmapped"
    return df


# ---------------------------------------------------------------------------
# NT / OT calculation - PER PERSON, PER WEEK
# ---------------------------------------------------------------------------

def calculate_nt_ot(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate NT and OT hours per person per week.

    Rule: First 40 hours per person per week = NT. Above 40 = OT.
    This is calculated at the individual level, walking through each day
    in chronological order within the week.
    """
    df = df.copy()
    df = df.sort_values(["person_id", "iso_year", "iso_week", "date"]).reset_index(drop=True)

    nt_col = np.zeros(len(df))
    ot_col = np.zeros(len(df))

    # Group by person + week, iterate in sorted order
    for _, group in df.groupby(["person_id", "iso_year", "iso_week"]):
        cumulative = 0.0
        for idx in group.index:
            day_hours = df.at[idx, "paid_hours"]
            if day_hours <= 0:
                continue

            remaining_nt = max(0, NT_WEEKLY_THRESHOLD - cumulative)
            nt = min(day_hours, remaining_nt)
            ot = day_hours - nt

            nt_col[idx] = round(nt, 2)
            ot_col[idx] = round(ot, 2)
            cumulative += day_hours

    df["nt_hours"] = nt_col
    df["ot_hours"] = ot_col
    df["total_hours"] = df["paid_hours"]

    return df


# ---------------------------------------------------------------------------
# Cost engine
# ---------------------------------------------------------------------------

def calculate_costs(df: pd.DataFrame, rate_lookup: pd.DataFrame) -> pd.DataFrame:
    """Join hours with rates and compute actual costs.

    For zero_rate trades, rates are forced to 0.
    For Spartan (ST rate only), all hours use the ST rate regardless of NT/OT.
    """
    df = df.copy()

    # Merge with rate lookup on (contractor, mapped_trade)
    merged = df.merge(
        rate_lookup,
        left_on=["contractor", "mapped_trade"],
        right_on=["Contractor", "Trade"],
        how="left",
        suffixes=("", "_rate"),
    )

    # Drop duplicate key columns from rate table
    merged = merged.drop(columns=["Contractor", "Trade"], errors="ignore")

    # Fill missing rates with 0
    for col in ["nt_rate", "ot_rate", "dt_rate", "st_rate"]:
        if col not in merged.columns:
            merged[col] = 0.0
        merged[col] = merged[col].fillna(0)

    # Apply zero_rate flag
    merged.loc[merged["zero_rate"] == True, ["nt_rate", "ot_rate", "dt_rate", "st_rate"]] = 0

    # For Spartan and Sterling (ST rate only), use st_rate for all hours
    st_contractors = merged["contractor"].isin(["Spartan", "Sterling"])
    merged.loc[st_contractors & (merged["nt_rate"] == 0) & (merged["st_rate"] > 0), "nt_rate"] = \
        merged.loc[st_contractors & (merged["nt_rate"] == 0) & (merged["st_rate"] > 0), "st_rate"]
    merged.loc[st_contractors & (merged["ot_rate"] == 0) & (merged["st_rate"] > 0), "ot_rate"] = \
        merged.loc[st_contractors & (merged["ot_rate"] == 0) & (merged["st_rate"] > 0), "st_rate"]

    # Axis Sunday rule: all hours on Sunday use DT (double time) rate
    merged["dt_hours"] = 0.0
    axis_sunday = (merged["contractor"] == "Axis") & (merged["date"].dt.dayofweek == 6)
    if axis_sunday.any():
        # Move all hours to DT on Sundays for Axis
        merged.loc[axis_sunday, "dt_hours"] = merged.loc[axis_sunday, "total_hours"]
        merged.loc[axis_sunday, "nt_hours"] = 0
        merged.loc[axis_sunday, "ot_hours"] = 0

    # Calculate costs
    merged["nt_cost"] = merged["nt_hours"] * merged["nt_rate"]
    merged["ot_cost"] = merged["ot_hours"] * merged["ot_rate"]
    merged["dt_cost"] = merged["dt_hours"] * merged["dt_rate"]
    merged["total_cost"] = merged["nt_cost"] + merged["ot_cost"] + merged["dt_cost"]

    # Flag rows with no rate found (potential allocation gaps)
    merged["has_rate"] = (merged["nt_rate"] > 0) | (merged["ot_rate"] > 0) | (merged["st_rate"] > 0) | merged["zero_rate"]

    return merged


# ---------------------------------------------------------------------------
# Build estimate comparison
# ---------------------------------------------------------------------------

def build_estimate_comparison(cost_df: pd.DataFrame, rate_lookup: pd.DataFrame) -> pd.DataFrame:
    """Build actual vs estimate comparison by contractor and mapped trade."""
    # Actuals: aggregate from cost_df
    actuals = cost_df.groupby(["contractor", "mapped_trade"]).agg(
        actual_nt_hours=("nt_hours", "sum"),
        actual_ot_hours=("ot_hours", "sum"),
        actual_dt_hours=("dt_hours", "sum"),
        actual_total_hours=("total_hours", "sum"),
        actual_nt_cost=("nt_cost", "sum"),
        actual_ot_cost=("ot_cost", "sum"),
        actual_dt_cost=("dt_cost", "sum"),
        actual_total_cost=("total_cost", "sum"),
        headcount=("person_id", "nunique"),
        days_worked=("date", "nunique"),
    ).reset_index()

    # Estimates: from rate lookup
    estimates = rate_lookup[["Contractor", "Trade", "est_hours", "est_cost"]].copy()
    estimates.columns = ["contractor", "mapped_trade", "est_hours", "est_cost"]

    # Merge
    comp = actuals.merge(estimates, on=["contractor", "mapped_trade"], how="outer")
    comp = comp.fillna(0)

    # Variances
    comp["hours_variance"] = comp["est_hours"] - comp["actual_total_hours"]
    comp["cost_variance"] = comp["est_cost"] - comp["actual_total_cost"]
    comp["hours_variance_pct"] = np.where(
        comp["est_hours"] > 0,
        (comp["hours_variance"] / comp["est_hours"]) * 100,
        0,
    )
    comp["cost_variance_pct"] = np.where(
        comp["est_cost"] > 0,
        (comp["cost_variance"] / comp["est_cost"]) * 100,
        0,
    )

    # OT %
    comp["ot_pct"] = np.where(
        comp["actual_total_hours"] > 0,
        (comp["actual_ot_hours"] / comp["actual_total_hours"]) * 100,
        0,
    )

    return comp


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(gate_df: pd.DataFrame, rate_lookup: pd.DataFrame) -> dict:
    """Run the full processing pipeline. Returns dict of DataFrames."""
    # 1. Trade mapping
    mapped_df = apply_trade_mapping(gate_df)

    # 2. NT/OT calculation
    hours_df = calculate_nt_ot(mapped_df)

    # 3. Cost calculation
    cost_df = calculate_costs(hours_df, rate_lookup)

    # 4. Estimate comparison
    comparison = build_estimate_comparison(cost_df, rate_lookup)

    # 5. Allocation gaps
    unmapped = cost_df[~cost_df["has_rate"]].copy()
    unmapped_summary = (
        unmapped.groupby(["contractor", "trade", "mapped_trade", "mapping_source"])
        .agg(
            total_hours=("total_hours", "sum"),
            headcount=("person_id", "nunique"),
            records=("person_id", "count"),
        )
        .reset_index()
        .sort_values("total_hours", ascending=False)
    )

    return {
        "cost_df": cost_df,
        "comparison": comparison,
        "unmapped": unmapped_summary,
        "mapped_df": mapped_df,
    }
