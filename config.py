"""
Configuration: trade mappings, contractor mappings, and app settings.
Edit this file to update business rules.
"""

# ---------------------------------------------------------------------------
# Google Sheet settings (used when loading from Google Sheets instead of file)
# ---------------------------------------------------------------------------
GOOGLE_SHEET_ID = "1iJmrfFlFX9_FNlrZlMLi1ZofHQPZ1x7OMdTwTX-Q_78"

# ---------------------------------------------------------------------------
# In-scope contractors and gate-name mapping
# ---------------------------------------------------------------------------
CONTRACTOR_NAME_MAP = {
    "Axis(FOX)": "Axis",
    "Claymar": "Claymar",
    "Claymar-Nights": "Claymar",
    "Custofab": "Custofab",
    "Spartan Speciality": "Spartan",
    "PMI": "PMI",
    "PK Safety": "PK Safety",
}

# Default folder for daily gate files
DAILY_FILES_FOLDER = "~/Downloads/drive-download-20260406T193108Z-3-001"

# Lunch deduction (hours) applied to elapsed time
LUNCH_DEDUCTION_HOURS = 0.5

IN_SCOPE_CONTRACTORS = list(CONTRACTOR_NAME_MAP.values())

# ---------------------------------------------------------------------------
# Trade mapping rules
# Key: (contractor, gate_trade) -> {mapped_trade, zero_rate}
# Contractor-specific rules are checked first, then general normalizations.
# ---------------------------------------------------------------------------
CONTRACTOR_TRADE_MAPPINGS = {
    "Axis": {
        "Apprentice": {"mapped_trade": "Millwright", "zero_rate": False},
    },
    "Claymar": {
        "Tool Room":    {"mapped_trade": "Tool Room", "zero_rate": True},
        "QA/QC":        {"mapped_trade": "QA/QC Supervisor", "zero_rate": False},
        "Safety":       {"mapped_trade": "Safety Supervisor", "zero_rate": False},
        "Supervisor":   {"mapped_trade": "Superintendent", "zero_rate": False},
        "Firewatches":  {"mapped_trade": "Holewatch/Firewatch", "zero_rate": False},
        "Combo Welders": {"mapped_trade": "Welder", "zero_rate": False},
    },
    "Custofab": {
        "QA/QC":        {"mapped_trade": "QC Manager", "zero_rate": False},
        "Boilermaker":  {"mapped_trade": "Master Mechanic BM", "zero_rate": False},
        "Supervisor":   {"mapped_trade": "Project Manager", "zero_rate": False},
    },
    "PK Safety": {
        "Rescue Technician": {"mapped_trade": "Rescue Tech", "zero_rate": False},
        "Rescue Supervisor": {"mapped_trade": "Rescue Team Lead", "zero_rate": False},
        "Safety":            {"mapped_trade": "Rescue Tech", "zero_rate": False},
    },
    "PMI": {
        "Cleanup Laborers": {"mapped_trade": "Helper Laborer", "zero_rate": False},
        "Helper":           {"mapped_trade": "Helper Laborer", "zero_rate": False},
        "Ground Tech /":    {"mapped_trade": "Helper Laborer", "zero_rate": False},
        "Ground Tech":      {"mapped_trade": "Helper Laborer", "zero_rate": False},
        "Project Manager":  {"mapped_trade": "Project Manager", "zero_rate": True},
        "General Manager":  {"mapped_trade": "General Manager", "zero_rate": True},
        "Superintendent":   {"mapped_trade": "Superintendent", "zero_rate": False},
        "QA/QC":            {"mapped_trade": "QA/QC", "zero_rate": False},
        "Combo Welders":    {"mapped_trade": "Rig Welder", "zero_rate": False},
        "Welder":           {"mapped_trade": "Rig Welder", "zero_rate": False},
        "Fire Watcher":     {"mapped_trade": "Firewatch", "zero_rate": False},
        "Safety":           {"mapped_trade": "Firewatch", "zero_rate": False},
        "Foreman":          {"mapped_trade": "Working Foreman", "zero_rate": False},
        "Boilermaker":      {"mapped_trade": "Boiler Maker", "zero_rate": False},
        "Boilermakers":     {"mapped_trade": "Boiler Maker", "zero_rate": False},
        "Pipefitter":       {"mapped_trade": "Pipe Fitter", "zero_rate": False},
        "Pipefitters":      {"mapped_trade": "Pipe Fitter", "zero_rate": False},
    },
    "Spartan": {
        "Vac Truck Crew":   {"mapped_trade": "Technician", "zero_rate": False},
        "Hydroblast Crew":  {"mapped_trade": "Operator", "zero_rate": False},
        "Supervisor":       {"mapped_trade": "Project Manager", "zero_rate": False},
        "Foreman":          {"mapped_trade": "Technician", "zero_rate": False},
    },
}

# General normalizations applied after contractor-specific rules
GENERAL_TRADE_NORMALIZATIONS = {
    "Welder":        "Welder",
    "Combo Welders": "Welder",
    "Pipefitters":   "Pipefitter",
    "Pipefitter":    "Pipefitter",
    "Boilermakers":  "Boilermaker",
    "Boilermaker":   "Boilermaker",
    "Fire Watcher":  "Firewatch",
    "Firewatch":     "Firewatch",
    "Firewatches":   "Firewatch",
}

# ---------------------------------------------------------------------------
# NT / OT settings
# ---------------------------------------------------------------------------
NT_WEEKLY_THRESHOLD = 40  # First 40 hours per person per week = Normal Time
WEEK_START_DAY = "monday"  # ISO week (Monday start)

# ---------------------------------------------------------------------------
# Project dates
# ---------------------------------------------------------------------------
PROJECT_START = "2026-02-05"
PROJECT_END = "2026-05-04"

# ---------------------------------------------------------------------------
# Gate Time Data columns (as they appear in the Excel/Google Sheet)
# ---------------------------------------------------------------------------
GATE_COLUMNS = {
    "badge": "Badge No",
    "name": "Name and Surname",
    "contractor": "Contractor",
    "trade": "Trade",
    "date_in": "Date",
    "time_in": "Time",
    "date_out": "Date.1",
    "time_out": "Time.1",
    "onsite_hours": "Onsite Hours",
    "paid_hours": "Less: Lunch Deduction",
}

# ---------------------------------------------------------------------------
# Rate Table columns (row 0 is a sub-header, actual header is row 1)
# ---------------------------------------------------------------------------
RATE_TABLE_HEADER_ROW = 1  # 0-indexed: skip the title row
RATE_TABLE_COLUMNS = {
    "contractor": 0,
    "trade": 1,
    "time_type": 2,
    "rate": 3,
    "estimate_hours": 4,
    "estimate_cost": 5,
}

# ---------------------------------------------------------------------------
# Google Sheet for gate data (your own sheet, set to "Anyone with link")
# The user pastes Gate Time Data into this sheet daily.
# ---------------------------------------------------------------------------
GATE_DATA_SHEET_ID = ""  # Fill in after creating your own Google Sheet

# ---------------------------------------------------------------------------
# Embedded Rate Table (from contractor estimates — does not change daily)
# Edit this list if rates or estimates are updated.
# ---------------------------------------------------------------------------
EMBEDDED_RATE_TABLE = [
    {"Contractor": "Axis", "Trade": "Foreman", "Time Type": "DT", "Rate": 186.49, "Estimate Hours": 72, "Estimate Cost": 13427.28},
    {"Contractor": "Axis", "Trade": "Foreman", "Time Type": "NT", "Rate": 106.89, "Estimate Hours": 324, "Estimate Cost": 34632.36},
    {"Contractor": "Axis", "Trade": "Foreman", "Time Type": "OT", "Rate": 146.69, "Estimate Hours": 192, "Estimate Cost": 28164.48},
    {"Contractor": "Axis", "Trade": "Millwright", "Time Type": "DT", "Rate": 143.33, "Estimate Hours": 600, "Estimate Cost": 85998.0},
    {"Contractor": "Axis", "Trade": "Millwright", "Time Type": "NT", "Rate": 83.86, "Estimate Hours": 2170, "Estimate Cost": 181976.2},
    {"Contractor": "Axis", "Trade": "Millwright", "Time Type": "OT", "Rate": 113.6, "Estimate Hours": 1600, "Estimate Cost": 181760.0},
    {"Contractor": "Claymar", "Trade": "Foreman", "Time Type": "NT", "Rate": 74.4, "Estimate Hours": 448, "Estimate Cost": 33331.2},
    {"Contractor": "Claymar", "Trade": "Foreman", "Time Type": "OT", "Rate": 91.56, "Estimate Hours": 264, "Estimate Cost": 24171.84},
    {"Contractor": "Claymar", "Trade": "Holewatch/Firewatch", "Time Type": "NT", "Rate": 44.64, "Estimate Hours": 924, "Estimate Cost": 41247.36},
    {"Contractor": "Claymar", "Trade": "Holewatch/Firewatch", "Time Type": "OT", "Rate": 54.94, "Estimate Hours": 924, "Estimate Cost": 50764.56},
    {"Contractor": "Claymar", "Trade": "Pipefitter", "Time Type": "NT", "Rate": 69.44, "Estimate Hours": 1772, "Estimate Cost": 123047.68},
    {"Contractor": "Claymar", "Trade": "Pipefitter", "Time Type": "OT", "Rate": 85.46, "Estimate Hours": 1584, "Estimate Cost": 135368.64},
    {"Contractor": "Claymar", "Trade": "QA/QC Supervisor", "Time Type": "NT", "Rate": 82.67, "Estimate Hours": 212, "Estimate Cost": 17526.04},
    {"Contractor": "Claymar", "Trade": "QA/QC Supervisor", "Time Type": "OT", "Rate": 101.74, "Estimate Hours": 132, "Estimate Cost": 13429.68},
    {"Contractor": "Claymar", "Trade": "Safety Supervisor", "Time Type": "NT", "Rate": 82.67, "Estimate Hours": 132, "Estimate Cost": 10912.44},
    {"Contractor": "Claymar", "Trade": "Safety Supervisor", "Time Type": "OT", "Rate": 101.74, "Estimate Hours": 132, "Estimate Cost": 13429.68},
    {"Contractor": "Claymar", "Trade": "Superintendent", "Time Type": "NT", "Rate": 99.2, "Estimate Hours": 224, "Estimate Cost": 22220.8},
    {"Contractor": "Claymar", "Trade": "Superintendent", "Time Type": "OT", "Rate": 122.09, "Estimate Hours": 132, "Estimate Cost": 16115.88},
    {"Contractor": "Claymar", "Trade": "Tool Room", "Time Type": "NT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "Claymar", "Trade": "Tool Room", "Time Type": "OT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "Claymar", "Trade": "Welder", "Time Type": "NT", "Rate": 72.75, "Estimate Hours": 952, "Estimate Cost": 69258.0},
    {"Contractor": "Claymar", "Trade": "Welder", "Time Type": "OT", "Rate": 89.53, "Estimate Hours": 792, "Estimate Cost": 70907.76},
    {"Contractor": "Custofab", "Trade": "Foreman", "Time Type": "NT", "Rate": 75.5155, "Estimate Hours": 200, "Estimate Cost": 15103.1},
    {"Contractor": "Custofab", "Trade": "Foreman", "Time Type": "OT", "Rate": 97.72175, "Estimate Hours": 176, "Estimate Cost": 17199.028},
    {"Contractor": "Custofab", "Trade": "Master Mechanic BM", "Time Type": "NT", "Rate": 63.592, "Estimate Hours": 480, "Estimate Cost": 30524.16},
    {"Contractor": "Custofab", "Trade": "Master Mechanic BM", "Time Type": "OT", "Rate": 82.292, "Estimate Hours": 528, "Estimate Cost": 43450.176},
    {"Contractor": "Custofab", "Trade": "Office Manager (Offsite)", "Time Type": "NT", "Rate": 60.4124, "Estimate Hours": 33, "Estimate Cost": 1993.6092},
    {"Contractor": "Custofab", "Trade": "Office Manager (Offsite)", "Time Type": "OT", "Rate": 78.1774, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "Custofab", "Trade": "Project Manager", "Time Type": "NT", "Rate": 103.337, "Estimate Hours": 120, "Estimate Cost": 12400.44},
    {"Contractor": "Custofab", "Trade": "Project Manager", "Time Type": "OT", "Rate": 133.7245, "Estimate Hours": 88, "Estimate Cost": 11767.756},
    {"Contractor": "Custofab", "Trade": "QC Manager", "Time Type": "NT", "Rate": 89.0288, "Estimate Hours": 120, "Estimate Cost": 10683.456},
    {"Contractor": "Custofab", "Trade": "QC Manager", "Time Type": "OT", "Rate": 115.2088, "Estimate Hours": 88, "Estimate Cost": 10138.3744},
    {"Contractor": "PK Safety", "Trade": "Rescue Team Lead", "Time Type": "NT", "Rate": 57, "Estimate Hours": 156, "Estimate Cost": 8892.0},
    {"Contractor": "PK Safety", "Trade": "Rescue Team Lead", "Time Type": "OT", "Rate": 79.8, "Estimate Hours": 52, "Estimate Cost": 4149.6},
    {"Contractor": "PK Safety", "Trade": "Rescue Tech", "Time Type": "NT", "Rate": 47, "Estimate Hours": 812, "Estimate Cost": 38164.0},
    {"Contractor": "PK Safety", "Trade": "Rescue Tech", "Time Type": "OT", "Rate": 65.8, "Estimate Hours": 364, "Estimate Cost": 23951.2},
    {"Contractor": "PMI", "Trade": "Boiler Maker", "Time Type": "NT", "Rate": 54.3, "Estimate Hours": 1504, "Estimate Cost": 81667.2},
    {"Contractor": "PMI", "Trade": "Boiler Maker", "Time Type": "OT", "Rate": 74.3, "Estimate Hours": 1296, "Estimate Cost": 96292.8},
    {"Contractor": "PMI", "Trade": "Boiler Maker / Bus Driver", "Time Type": "NT", "Rate": 54.3, "Estimate Hours": 364, "Estimate Cost": 19765.2},
    {"Contractor": "PMI", "Trade": "Boiler Maker / Bus Driver", "Time Type": "OT", "Rate": 74.3, "Estimate Hours": 396, "Estimate Cost": 29422.8},
    {"Contractor": "PMI", "Trade": "Firewatch", "Time Type": "NT", "Rate": 35.15, "Estimate Hours": 336, "Estimate Cost": 11810.4},
    {"Contractor": "PMI", "Trade": "Firewatch", "Time Type": "OT", "Rate": 48.1, "Estimate Hours": 352, "Estimate Cost": 16931.2},
    {"Contractor": "PMI", "Trade": "General Manager", "Time Type": "NT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "PMI", "Trade": "General Manager", "Time Type": "OT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "PMI", "Trade": "Helper Laborer", "Time Type": "NT", "Rate": 35.15, "Estimate Hours": 376, "Estimate Cost": 13216.4},
    {"Contractor": "PMI", "Trade": "Helper Laborer", "Time Type": "OT", "Rate": 48.1, "Estimate Hours": 396, "Estimate Cost": 19047.6},
    {"Contractor": "PMI", "Trade": "Pipe Fitter", "Time Type": "NT", "Rate": 57.5, "Estimate Hours": 336, "Estimate Cost": 19320.0},
    {"Contractor": "PMI", "Trade": "Pipe Fitter", "Time Type": "OT", "Rate": 78.7, "Estimate Hours": 352, "Estimate Cost": 27702.4},
    {"Contractor": "PMI", "Trade": "Project Manager", "Time Type": "NT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "PMI", "Trade": "Project Manager", "Time Type": "OT", "Rate": 0, "Estimate Hours": 0, "Estimate Cost": 0},
    {"Contractor": "PMI", "Trade": "QA/QC", "Time Type": "NT", "Rate": 79.9, "Estimate Hours": 268, "Estimate Cost": 21413.2},
    {"Contractor": "PMI", "Trade": "QA/QC", "Time Type": "OT", "Rate": 109.35, "Estimate Hours": 144, "Estimate Cost": 15746.4},
    {"Contractor": "PMI", "Trade": "Rig Welder", "Time Type": "NT", "Rate": 87.85, "Estimate Hours": 376, "Estimate Cost": 33031.6},
    {"Contractor": "PMI", "Trade": "Rig Welder", "Time Type": "OT", "Rate": 120.25, "Estimate Hours": 352, "Estimate Cost": 42328.0},
    {"Contractor": "PMI", "Trade": "Superintendent", "Time Type": "NT", "Rate": 79.9, "Estimate Hours": 272, "Estimate Cost": 21732.8},
    {"Contractor": "PMI", "Trade": "Superintendent", "Time Type": "OT", "Rate": 109.35, "Estimate Hours": 144, "Estimate Cost": 15746.4},
    {"Contractor": "PMI", "Trade": "Working Foreman", "Time Type": "NT", "Rate": 63.9, "Estimate Hours": 716, "Estimate Cost": 45752.4},
    {"Contractor": "PMI", "Trade": "Working Foreman", "Time Type": "OT", "Rate": 87.45, "Estimate Hours": 432, "Estimate Cost": 37778.4},
    {"Contractor": "Spartan", "Trade": "Operator", "Time Type": "ST", "Rate": 38, "Estimate Hours": 336, "Estimate Cost": 12768.0},
    {"Contractor": "Spartan", "Trade": "Project Manager", "Time Type": "ST", "Rate": 42, "Estimate Hours": 240, "Estimate Cost": 10080.0},
    {"Contractor": "Spartan", "Trade": "Technician", "Time Type": "ST", "Rate": 35, "Estimate Hours": 528, "Estimate Cost": 18480.0},
]
