"""
Data loading: public Google Sheet (CSV export), Excel upload, or embedded rates.
Returns raw DataFrames for gate time data and rate table.
"""

import pandas as pd
import numpy as np
import requests
import streamlit as st
from io import StringIO
from config import (
    GATE_COLUMNS, RATE_TABLE_HEADER_ROW, CONTRACTOR_NAME_MAP, IN_SCOPE_CONTRACTORS,
    EMBEDDED_RATE_TABLE,
)


# ---------------------------------------------------------------------------
# Embedded rate table (from config — rates don't change daily)
# ---------------------------------------------------------------------------

def get_embedded_rate_table() -> pd.DataFrame:
    """Build rate table DataFrame from the embedded data in config.py."""
    df = pd.DataFrame(EMBEDDED_RATE_TABLE)
    for col in ["Rate", "Estimate Hours", "Estimate Cost"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Google Sheet (public, anyone with link can view)
# ---------------------------------------------------------------------------

def load_gate_from_google_sheet(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    """Load Gate Time Data from a public Google Sheet via CSV export.

    The sheet must be set to 'Anyone with the link can view'.
    gid is the sheet tab ID (0 = first tab).
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 401 or resp.status_code == 403:
            st.error(
                "Cannot access Google Sheet. Make sure sharing is set to "
                "'Anyone with the link' as Viewer."
            )
        else:
            st.error(f"Failed to fetch Google Sheet: {e}")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"Network error fetching Google Sheet: {e}")
        return pd.DataFrame()

    try:
        df = pd.read_csv(StringIO(resp.text))
    except Exception as e:
        st.error(f"Failed to parse Google Sheet CSV: {e}")
        return pd.DataFrame()

    if df.empty:
        st.warning("Google Sheet returned empty data.")

    return df


# ---------------------------------------------------------------------------
# Excel file upload (fallback)
# ---------------------------------------------------------------------------

def load_from_excel(file) -> dict:
    """Load gate time data and rate table from an uploaded Excel file.

    Handles both the original processed file (header on row 0) and the
    full client file (header on row 1 with a junk row 0).
    """
    xls = pd.ExcelFile(file)
    result = {}

    # --- Gate Time Data ---
    if "Gate Time Data" in xls.sheet_names:
        # Try reading with default header (row 0)
        gate_df = pd.read_excel(xls, "Gate Time Data")

        # Detect if row 0 is junk and the real header is row 1
        # Check if expected columns exist
        expected_cols = {"Badge No", "Name and Surname", "Contractor", "Trade"}
        if not expected_cols.issubset(set(gate_df.columns)):
            # Try with header=1 (skip junk row 0)
            gate_df = pd.read_excel(xls, "Gate Time Data", header=1)

        if not expected_cols.issubset(set(gate_df.columns)):
            st.error(
                "Cannot find expected columns in Gate Time Data. "
                f"Found: {list(gate_df.columns[:10])}"
            )
            return {}

        # Only keep the first 10 columns (A-J: gate data), drop extra columns
        gate_cols = ["Badge No", "Name and Surname", "Contractor", "Trade",
                     "Date", "Time", "Date.1", "Time.1", "Onsite Hours",
                     "Less: Lunch Deduction"]
        # Handle duplicate 'Date' and 'Time' column names
        cols = list(gate_df.columns)
        # Rename duplicates: second Date -> Date.1, second Time -> Time.1
        seen = {}
        new_cols = []
        for c in cols:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}.{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        gate_df.columns = new_cols

        # Keep only the gate columns that exist
        keep = [c for c in gate_cols if c in gate_df.columns]
        gate_df = gate_df[keep].copy()

        result["gate_raw"] = gate_df
    else:
        st.error("Sheet 'Gate Time Data' not found in the uploaded file.")
        return {}

    # --- Rate Table (use embedded if not in file) ---
    if "Rate_Table" in xls.sheet_names:
        rate_df = pd.read_excel(xls, "Rate_Table", header=None)
        rate_df = rate_df.iloc[RATE_TABLE_HEADER_ROW:].reset_index(drop=True)
        rate_df.columns = ["Contractor", "Trade", "Time Type", "Rate",
                           "Estimate Hours", "Estimate Cost"]
        rate_df = rate_df.dropna(subset=["Contractor"])
        for col in ["Rate", "Estimate Hours", "Estimate Cost"]:
            rate_df[col] = pd.to_numeric(rate_df[col], errors="coerce").fillna(0)
        result["rate_table"] = rate_df
    else:
        # Use embedded rate table
        result["rate_table"] = get_embedded_rate_table()

    result["sheet_names"] = xls.sheet_names
    result["source"] = "excel"
    return result


# ---------------------------------------------------------------------------
# Gate data cleaning (works for all sources)
# ---------------------------------------------------------------------------

def clean_gate_data(gate_df: pd.DataFrame) -> pd.DataFrame:
    """Clean raw gate data: filter to in-scope contractors, map names, parse dates."""
    df = gate_df.copy()

    # Rename columns to standard names
    col_map = {}
    for std_name, src_col in GATE_COLUMNS.items():
        if src_col in df.columns:
            col_map[src_col] = std_name
    df = df.rename(columns=col_map)

    # Drop rows missing critical fields
    df = df.dropna(subset=["name", "contractor", "date_in"])

    # Filter to in-scope contractors only
    df = df[df["contractor"].isin(CONTRACTOR_NAME_MAP.keys())].copy()

    # Map contractor names to standard
    df["contractor"] = df["contractor"].map(CONTRACTOR_NAME_MAP)

    # Parse date
    df["date"] = pd.to_datetime(df["date_in"], errors="coerce")
    df = df.dropna(subset=["date"])

    # Use paid_hours (Less: Lunch Deduction) as the hours worked
    if "paid_hours" in df.columns:
        df["paid_hours"] = pd.to_numeric(df["paid_hours"], errors="coerce").fillna(0)
    elif "onsite_hours" in df.columns:
        df["paid_hours"] = pd.to_numeric(df["onsite_hours"], errors="coerce").fillna(0)
    else:
        st.warning("No hours column found.")
        df["paid_hours"] = 0

    # Clean trade names (strip whitespace)
    df["trade"] = df["trade"].astype(str).str.strip()

    # Create person ID (badge if available, else name+contractor)
    if "badge" in df.columns and df["badge"].notna().any():
        df["person_id"] = df["badge"].astype(str) + "|" + df["contractor"]
    else:
        df["person_id"] = df["name"].astype(str) + "|" + df["contractor"]

    # ISO week
    df["week_start"] = df["date"].dt.to_period("W-SAT").apply(
        lambda p: p.start_time
    )
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(int)
    df["iso_year"] = df["date"].dt.isocalendar().year.astype(int)

    return df


# ---------------------------------------------------------------------------
# Rate table processing
# ---------------------------------------------------------------------------

def build_rate_lookup(rate_table: pd.DataFrame) -> pd.DataFrame:
    """Pivot rate table so each row is (Contractor, Trade) with NT/OT/DT/ST rates
    and estimate hours/cost."""
    rt = rate_table.copy()
    rt["Time Type"] = rt["Time Type"].astype(str).str.strip().str.upper()

    # Pivot rates
    rate_pivot = rt.pivot_table(
        index=["Contractor", "Trade"],
        columns="Time Type",
        values="Rate",
        aggfunc="first",
    ).reset_index()
    rate_pivot.columns.name = None

    # Ensure standard rate columns exist
    for col in ["NT", "OT", "DT", "ST"]:
        if col not in rate_pivot.columns:
            rate_pivot[col] = 0.0
    rate_pivot = rate_pivot.fillna(0)

    # Pivot estimate hours and costs (sum across time types)
    est_hours = rt.groupby(["Contractor", "Trade"])["Estimate Hours"].sum().reset_index()
    est_hours.columns = ["Contractor", "Trade", "est_hours"]
    est_cost = rt.groupby(["Contractor", "Trade"])["Estimate Cost"].sum().reset_index()
    est_cost.columns = ["Contractor", "Trade", "est_cost"]

    lookup = rate_pivot.merge(est_hours, on=["Contractor", "Trade"], how="left")
    lookup = lookup.merge(est_cost, on=["Contractor", "Trade"], how="left")
    lookup = lookup.fillna(0)

    # Rename rate columns
    lookup = lookup.rename(columns={
        "NT": "nt_rate", "OT": "ot_rate", "DT": "dt_rate", "ST": "st_rate"
    })

    # Drop any non-standard columns that leaked through pivot
    keep_cols = ["Contractor", "Trade", "nt_rate", "ot_rate", "dt_rate", "st_rate",
                 "est_hours", "est_cost"]
    lookup = lookup[[c for c in keep_cols if c in lookup.columns]]

    return lookup
