"""
Data loading: daily gate files (folder of .xls/.xlsm), Google Sheet, or Excel upload.
Returns raw DataFrames for gate time data and rate table.
"""

import pandas as pd
import numpy as np
import requests
import os
import shutil
import tempfile
import re
import streamlit as st
from io import StringIO
from datetime import datetime, timedelta
from config import (
    GATE_COLUMNS, RATE_TABLE_HEADER_ROW, CONTRACTOR_NAME_MAP, IN_SCOPE_CONTRACTORS,
    EMBEDDED_RATE_TABLE, LUNCH_DEDUCTION_HOURS,
)


# ---------------------------------------------------------------------------
# Embedded rate table
# ---------------------------------------------------------------------------

def get_embedded_rate_table() -> pd.DataFrame:
    """Build rate table DataFrame from the embedded data in config.py."""
    df = pd.DataFrame(EMBEDDED_RATE_TABLE)
    for col in ["Rate", "Estimate Hours", "Estimate Cost"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Daily gate file reader (folder of .xls / .xlsm files from Titan system)
# ---------------------------------------------------------------------------

def load_daily_gate_files(folder_path: str) -> pd.DataFrame:
    """Read all daily gate files from a folder and consolidate into one DataFrame.

    Handles both .xls and .xlsm files from the Titan Safety T&A system.
    Files may have slightly different column layouts (day vs night shifts).
    """
    folder = os.path.expanduser(folder_path)
    if not os.path.isdir(folder):
        st.error(f"Folder not found: {folder}")
        return pd.DataFrame()

    files = [f for f in os.listdir(folder)
             if f.endswith((".xls", ".xlsm")) and not f.startswith("~")]
    if not files:
        st.error(f"No .xls/.xlsm files found in {folder}")
        return pd.DataFrame()

    all_records = []
    errors = []
    progress = st.progress(0, text="Reading daily files...")

    for i, fname in enumerate(sorted(files)):
        progress.progress((i + 1) / len(files), text=f"Reading {fname[:50]}...")
        path = os.path.join(folder, fname)

        try:
            records = _parse_single_gate_file(path, fname)
            all_records.extend(records)
        except Exception as e:
            errors.append(f"{fname}: {e}")

    progress.empty()

    if errors:
        with st.expander(f"{len(errors)} file(s) had errors"):
            for err in errors:
                st.caption(err)

    if not all_records:
        st.error("No records extracted from any file.")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    st.caption(f"Loaded {len(df):,} records from {len(files)} files")
    return df


def _parse_single_gate_file(path: str, fname: str) -> list:
    """Parse a single Titan Safety daily gate file."""
    # These .xls files are often actually xlsx format
    tmp = tempfile.mktemp(suffix=".xlsx")
    shutil.copy2(path, tmp)
    try:
        df = pd.read_excel(tmp, header=None, engine="openpyxl")
    finally:
        os.unlink(tmp)

    # Find the header row (contains 'Company')
    header_idx = None
    for i in range(min(10, len(df))):
        row_vals = [str(v).strip() for v in df.iloc[i].values]
        if "Company" in row_vals:
            header_idx = i
            break
    if header_idx is None:
        return []

    # Map column positions
    header = df.iloc[header_idx]
    col_map = {}
    for j, val in enumerate(header):
        s = str(val).strip()
        if s == "Company":
            col_map["company"] = j
        elif s == "Cardholder":
            col_map["name"] = j
        elif s == "Craft":
            col_map["craft"] = j
        elif s == "Card Number":
            col_map["badge"] = j
        elif s == "In Date/Time":
            col_map["in_dt"] = j
        elif s == "Out Date/Time":
            col_map["out_dt"] = j
        elif s == "Elapsed Time":
            col_map["elapsed"] = j

    if "company" not in col_map or "name" not in col_map:
        return []

    # Extract file date from filename
    file_date = _extract_date_from_filename(fname)
    is_night = "night" in fname.lower()

    records = []
    data = df.iloc[header_idx + 1:]

    for _, row in data.iterrows():
        company = row.iloc[col_map["company"]] if "company" in col_map else None
        if pd.isna(company) or "Total" in str(company):
            continue

        company = str(company).strip()
        name = str(row.iloc[col_map["name"]]).strip() if "name" in col_map else ""
        craft = str(row.iloc[col_map["craft"]]).strip() if "craft" in col_map else ""
        badge = row.iloc[col_map["badge"]] if "badge" in col_map else None

        if not name or name == "nan":
            continue

        # Parse in/out datetime
        in_dt = _parse_datetime(row.iloc[col_map["in_dt"]]) if "in_dt" in col_map else None
        out_dt = _parse_datetime(row.iloc[col_map["out_dt"]]) if "out_dt" in col_map else None

        # Parse elapsed time
        elapsed_str = str(row.iloc[col_map["elapsed"]]) if "elapsed" in col_map else ""
        elapsed_hours = _parse_elapsed(elapsed_str)

        # Calculate hours: use elapsed if valid, else compute from in/out
        if elapsed_hours and elapsed_hours > 0:
            onsite_hours = elapsed_hours
        elif in_dt and out_dt and out_dt > in_dt:
            onsite_hours = (out_dt - in_dt).total_seconds() / 3600
        else:
            onsite_hours = 0

        # Apply lunch deduction for shifts > 5 hours
        paid_hours = max(0, onsite_hours - LUNCH_DEDUCTION_HOURS) if onsite_hours > 5 else onsite_hours

        # Determine the date (from In datetime or filename)
        if in_dt:
            gate_date = in_dt.date()
        elif file_date:
            gate_date = file_date
        else:
            continue

        records.append({
            "Badge No": badge,
            "Name and Surname": name,
            "Contractor": company,
            "Trade": craft,
            "Date": pd.Timestamp(gate_date),
            "Onsite Hours": round(onsite_hours, 2),
            "Less: Lunch Deduction": round(paid_hours, 2),
            "shift": "Night" if is_night else "Day",
            "source_file": fname,
        })

    return records


def _extract_date_from_filename(fname: str):
    """Extract date from filenames like '- Titan Safety - T&A - Daily All - 2026-03-18 05-00-08.xlsm'"""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def _parse_datetime(val) -> datetime:
    """Parse datetime from various formats."""
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    if not s or s in ("nan", "*****", "NaN"):
        return None
    for fmt in ["%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_elapsed(val) -> float:
    """Parse elapsed time string like '11:47:40' or '09:59:17' to hours."""
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if not s or s in ("nan", "*****", "NaN", "00:00:00"):
        return 0
    match = re.match(r"(\d+):(\d+):(\d+)", s)
    if match:
        h, m, sec = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return h + m / 60 + sec / 3600
    return 0


# ---------------------------------------------------------------------------
# Google Sheet (public, anyone with link can view)
# ---------------------------------------------------------------------------

def load_gate_from_google_sheet(sheet_id: str, gid: str = "0") -> pd.DataFrame:
    """Load Gate Time Data from a public Google Sheet via CSV export."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError:
        st.error("Cannot access Google Sheet. Make sure sharing is set to 'Anyone with the link'.")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {e}")
        return pd.DataFrame()

    try:
        return pd.read_csv(StringIO(resp.text))
    except Exception as e:
        st.error(f"Failed to parse CSV: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Excel file upload (fallback)
# ---------------------------------------------------------------------------

def load_from_excel(file) -> dict:
    """Load gate time data and rate table from an uploaded Excel file."""
    xls = pd.ExcelFile(file)
    result = {}

    if "Gate Time Data" in xls.sheet_names:
        gate_df = pd.read_excel(xls, "Gate Time Data")
        expected_cols = {"Badge No", "Name and Surname", "Contractor", "Trade"}
        if not expected_cols.issubset(set(gate_df.columns)):
            gate_df = pd.read_excel(xls, "Gate Time Data", header=1)
        if not expected_cols.issubset(set(gate_df.columns)):
            st.error(f"Cannot find expected columns. Found: {list(gate_df.columns[:10])}")
            return {}

        cols = list(gate_df.columns)
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

        gate_cols = ["Badge No", "Name and Surname", "Contractor", "Trade",
                     "Date", "Time", "Date.1", "Time.1", "Onsite Hours",
                     "Less: Lunch Deduction"]
        keep = [c for c in gate_cols if c in gate_df.columns]
        gate_df = gate_df[keep].copy()
        result["gate_raw"] = gate_df
    else:
        st.error("Sheet 'Gate Time Data' not found.")
        return {}

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

    # Rename columns to standard names if they match GATE_COLUMNS
    col_map = {}
    for std_name, src_col in GATE_COLUMNS.items():
        if src_col in df.columns:
            col_map[src_col] = std_name
    df = df.rename(columns=col_map)

    # Drop rows missing critical fields
    required = [c for c in ["name", "contractor", "date_in"] if c in df.columns]
    if "date_in" not in df.columns and "Date" in df.columns:
        df = df.rename(columns={"Date": "date_in"})
        required = [c for c in ["name", "contractor", "date_in"] if c in df.columns]

    # Handle daily file format (columns already named correctly)
    if "Name and Surname" in df.columns and "name" not in df.columns:
        df = df.rename(columns={
            "Name and Surname": "name",
            "Contractor": "contractor",
            "Trade": "trade",
            "Badge No": "badge",
            "Date": "date_in",
            "Onsite Hours": "onsite_hours",
            "Less: Lunch Deduction": "paid_hours",
        })

    df = df.dropna(subset=["name", "contractor"])
    if "date_in" in df.columns:
        df = df.dropna(subset=["date_in"])

    # Filter to in-scope contractors only
    df = df[df["contractor"].isin(CONTRACTOR_NAME_MAP.keys())].copy()
    df["contractor"] = df["contractor"].map(CONTRACTOR_NAME_MAP)

    # Parse date
    if "date_in" in df.columns:
        df["date"] = pd.to_datetime(df["date_in"], errors="coerce")
    elif "date" not in df.columns:
        st.error("No date column found in data.")
        return pd.DataFrame()
    df = df.dropna(subset=["date"])

    # Hours
    if "paid_hours" in df.columns:
        df["paid_hours"] = pd.to_numeric(df["paid_hours"], errors="coerce").fillna(0)
    elif "onsite_hours" in df.columns:
        df["paid_hours"] = pd.to_numeric(df["onsite_hours"], errors="coerce").fillna(0)
    else:
        df["paid_hours"] = 0

    # Clean trade names
    if "trade" not in df.columns and "Trade" in df.columns:
        df["trade"] = df["Trade"]
    df["trade"] = df["trade"].astype(str).str.strip()

    # Person ID
    if "badge" in df.columns and df["badge"].notna().any():
        df["person_id"] = df["badge"].astype(str) + "|" + df["contractor"]
    else:
        df["person_id"] = df["name"].astype(str) + "|" + df["contractor"]

    # ISO week
    df["week_start"] = df["date"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(int)
    df["iso_year"] = df["date"].dt.isocalendar().year.astype(int)

    return df


# ---------------------------------------------------------------------------
# Rate table processing
# ---------------------------------------------------------------------------

def build_rate_lookup(rate_table: pd.DataFrame) -> pd.DataFrame:
    """Pivot rate table to (Contractor, Trade) with NT/OT/DT/ST rates."""
    rt = rate_table.copy()
    rt["Time Type"] = rt["Time Type"].astype(str).str.strip().str.upper()

    rate_pivot = rt.pivot_table(
        index=["Contractor", "Trade"], columns="Time Type",
        values="Rate", aggfunc="first",
    ).reset_index()
    rate_pivot.columns.name = None

    for col in ["NT", "OT", "DT", "ST"]:
        if col not in rate_pivot.columns:
            rate_pivot[col] = 0.0
    rate_pivot = rate_pivot.fillna(0)

    est_hours = rt.groupby(["Contractor", "Trade"])["Estimate Hours"].sum().reset_index()
    est_hours.columns = ["Contractor", "Trade", "est_hours"]
    est_cost = rt.groupby(["Contractor", "Trade"])["Estimate Cost"].sum().reset_index()
    est_cost.columns = ["Contractor", "Trade", "est_cost"]

    lookup = rate_pivot.merge(est_hours, on=["Contractor", "Trade"], how="left")
    lookup = lookup.merge(est_cost, on=["Contractor", "Trade"], how="left")
    lookup = lookup.fillna(0)
    lookup = lookup.rename(columns={
        "NT": "nt_rate", "OT": "ot_rate", "DT": "dt_rate", "ST": "st_rate"
    })

    keep_cols = ["Contractor", "Trade", "nt_rate", "ot_rate", "dt_rate", "st_rate",
                 "est_hours", "est_cost"]
    lookup = lookup[[c for c in keep_cols if c in lookup.columns]]
    return lookup
