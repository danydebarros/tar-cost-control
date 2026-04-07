"""
TAR Cost Control - Nederland ASU3 Turnaround 2026
Main application entry point.

Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime

from data_loader import (
    load_from_excel, load_daily_gate_files, load_gate_from_google_sheet,
    get_embedded_rate_table, clean_gate_data, build_rate_lookup,
)
from drive_loader import download_drive_files, extract_folder_id
from processing import run_pipeline
from forecast import calculate_forecast
from config import DAILY_FILES_FOLDER
from views import (
    executive_summary,
    daily_hours,
    contractor_view,
    trade_view,
    forecast_view,
    allocation_gaps,
    timesheet_view,
    hours_drilldown,
)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TAR Cost Control",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    [data-testid="stMetricValue"] { font-size: 1.4rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; color: #5F6368; }
    .app-header {
        background: linear-gradient(135deg, #1A2B4A 0%, #2D4A7A 100%);
        color: white; padding: 0.8rem 1.5rem; border-radius: 8px; margin-bottom: 1rem;
    }
    .app-header h1 { margin: 0; font-size: 1.5rem; font-weight: 600; }
    .app-header p { margin: 0; font-size: 0.85rem; opacity: 0.8; }
    [data-testid="stSidebar"] { background-color: #F8F9FA; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .status-ok { color: #0D904F; font-weight: 600; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="app-header">
    <h1>TAR Cost Control</h1>
    <p>Nederland ASU3 Turnaround 2026 &mdash; Labor Cost Tracking & Forecasting</p>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Data Source")

    # Check for default folders/files
    default_folder = os.path.expanduser(DAILY_FILES_FOLDER)
    has_daily_folder = os.path.isdir(default_folder)

    default_file = None
    for fname in [
        "TAR2026 - Nederland TAR Costing Tracking (1).xlsx",
        "TAR2026 - Nederland TAR Costing Tracking.xlsx",
        "Nederland_TAR_Cost_Tracker_Updated.xlsx",
    ]:
        p = os.path.expanduser(f"~/Downloads/{fname}")
        if os.path.exists(p):
            default_file = p
            break
    has_default_file = default_file is not None

    source_options = ["Google Drive Folder"]
    if has_daily_folder:
        source_options.append("Local Folder")

    data_source = st.radio("Load data from:", source_options, key="data_source")

    # Google Drive folder
    drive_folder_url = None
    if data_source == "Google Drive Folder":
        drive_folder_url = st.text_input(
            "Drive Folder URL",
            value="https://drive.google.com/drive/u/0/folders/10hFTxkKROBsuaBxqP5rZo9j6Y_FPAPpC",
            help="Paste the Google Drive folder URL (must be shared as 'Anyone with the link')",
            key="drive_folder_url",
        )

    # Local folder path input
    folder_path = None
    if data_source == "Local Folder":
        folder_path = st.text_input(
            "Folder path",
            value=default_folder if has_daily_folder else "",
            help="Path to folder containing daily .xls/.xlsm gate files",
            key="gate_folder",
        )

    # Refresh
    if st.button("Refresh Data", type="primary", use_container_width=True):
        st.cache_data.clear()
        # Bump refresh counter to bust any remaining caches
        st.session_state["refresh_counter"] = st.session_state.get("refresh_counter", 0) + 1
        for key in list(st.session_state.keys()):
            if key in ("forecast_df", "forecast_loaded"):
                del st.session_state[key]
        st.rerun()

    st.divider()
    st.markdown("### Navigation")
    page = st.radio(
        "View",
        ["Executive Summary", "Hours Drill-Down", "Daily Hours",
         "Contractor View", "Trade View", "Timesheets / Invoices",
         "Forecast", "Data Audit"],
        key="nav_page",
    )

    if "last_refresh" in st.session_state:
        st.caption(f"Last refresh: {st.session_state['last_refresh']}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def load_and_process_daily_folder(folder: str):
    """Load from folder of daily gate files + embedded rates."""
    gate_raw = load_daily_gate_files(folder)
    if gate_raw.empty:
        return None
    rate_table = get_embedded_rate_table()
    gate_clean = clean_gate_data(gate_raw)
    rate_lookup = build_rate_lookup(rate_table)
    result = run_pipeline(gate_clean, rate_lookup)
    result["rate_lookup"] = rate_lookup
    result["gate_clean"] = gate_clean
    result["gate_raw"] = gate_raw
    return result


@st.cache_data(show_spinner=False, ttl=300)
def load_and_process_drive_folder(folder_id: str, _refresh_key: str = ""):
    """Download files from Google Drive folder, then process.
    _refresh_key is used to bust the cache on Refresh."""
    local_dir = download_drive_files(folder_id)
    return load_and_process_daily_folder(local_dir)


@st.cache_data(show_spinner="Loading from Google Sheet...", ttl=300)
def load_and_process_gsheet(sheet_id: str, gid: str):
    gate_raw = load_gate_from_google_sheet(sheet_id, gid)
    if gate_raw.empty:
        return None
    rate_table = get_embedded_rate_table()
    gate_clean = clean_gate_data(gate_raw)
    rate_lookup = build_rate_lookup(rate_table)
    result = run_pipeline(gate_clean, rate_lookup)
    result["rate_lookup"] = rate_lookup
    result["gate_clean"] = gate_clean
    result["gate_raw"] = gate_raw
    return result


@st.cache_data(show_spinner="Loading from file...")
def load_and_process_file(file_path_or_bytes, source_type: str):
    raw = load_from_excel(file_path_or_bytes)
    if not raw:
        return None
    gate_clean = clean_gate_data(raw["gate_raw"])
    rate_lookup = build_rate_lookup(raw["rate_table"])
    result = run_pipeline(gate_clean, rate_lookup)
    result["rate_lookup"] = rate_lookup
    result["gate_clean"] = gate_clean
    result["gate_raw"] = raw["gate_raw"]
    return result


# Route to the right loader
processed = None

if data_source == "Google Drive Folder":
    if not drive_folder_url:
        st.info("Paste the Google Drive folder URL in the sidebar.")
        st.stop()
    folder_id = extract_folder_id(drive_folder_url)
    refresh_key = str(st.session_state.get("refresh_counter", 0))
    processed = load_and_process_drive_folder(folder_id, _refresh_key=refresh_key)

elif data_source == "Local Folder":
    if not folder_path:
        st.info("Enter the path to the folder containing daily gate files.")
        st.stop()
    processed = load_and_process_daily_folder(folder_path)

elif data_source == "Local Folder" and has_daily_folder:
    if not folder_path:
        st.info("Enter the path to the folder containing daily gate files.")
        st.stop()
    processed = load_and_process_daily_folder(folder_path)

if processed is None:
    st.error("Failed to load data. Check the data source and try again.")
    st.stop()

st.session_state["last_refresh"] = datetime.now().strftime("%H:%M:%S")

cost_df = processed["cost_df"]
comparison = processed["comparison"]
unmapped = processed["unmapped"]
gate_raw = processed.get("gate_raw")
gate_clean = processed.get("gate_clean")

# Default forecast
if "forecast_df" not in st.session_state:
    st.session_state["forecast_df"] = calculate_forecast(
        comparison, cost_df, method="current_performance"
    )
forecast_df = st.session_state.get("forecast_df", None)

# Sidebar summary
st.sidebar.divider()
st.sidebar.markdown("### Data Summary")
st.sidebar.caption(f"{len(cost_df):,} records")
st.sidebar.caption(f"{cost_df['person_id'].nunique()} people")
st.sidebar.caption(f"{cost_df['total_hours'].sum():,.0f} total hours")
st.sidebar.caption(f"${cost_df['total_cost'].sum():,.0f} total cost")
st.sidebar.caption(
    f"{cost_df['date'].min().strftime('%b %d')} — {cost_df['date'].max().strftime('%b %d')}"
)

# ---------------------------------------------------------------------------
# Route to view
# ---------------------------------------------------------------------------
if page == "Executive Summary":
    executive_summary.render(cost_df, comparison, forecast_df)
elif page == "Hours Drill-Down":
    hours_drilldown.render(cost_df, comparison)
elif page == "Daily Hours":
    daily_hours.render(cost_df)
elif page == "Contractor View":
    contractor_view.render(cost_df, comparison)
elif page == "Trade View":
    trade_view.render(cost_df, comparison)
elif page == "Timesheets / Invoices":
    timesheet_view.render(cost_df, comparison)
elif page == "Forecast":
    forecast_view.render(cost_df, comparison)
elif page == "Data Audit":
    allocation_gaps.render(cost_df, unmapped, gate_raw, gate_clean)
