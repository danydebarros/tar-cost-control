"""
Reusable UI components: charts, metric cards, styled tables.
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
COLORS = {
    "primary": "#1A73E8",
    "secondary": "#5F6368",
    "success": "#0D904F",
    "warning": "#E37400",
    "danger": "#C5221F",
    "light_bg": "#F8F9FA",
    "nt": "#1A73E8",
    "ot": "#E37400",
    "estimate": "#5F6368",
    "actual": "#1A73E8",
    "forecast": "#0D904F",
    "variance_pos": "#0D904F",
    "variance_neg": "#C5221F",
}

CONTRACTOR_COLORS = px.colors.qualitative.Set2


# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------

def metric_row(metrics: list[dict]):
    """Render a row of metric cards.
    Each dict: {label, value, delta (optional), delta_color (optional), prefix (optional)}
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            delta = m.get("delta")
            delta_color = m.get("delta_color", "normal")
            prefix = m.get("prefix", "")
            value = m["value"]
            if isinstance(value, (int, float)):
                if prefix == "$":
                    value = f"${value:,.0f}"
                elif prefix == "%":
                    value = f"{value:.1f}%"
                else:
                    value = f"{value:,.0f}"
            st.metric(
                label=m["label"],
                value=value,
                delta=delta,
                delta_color=delta_color,
            )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def daily_hours_chart(daily_df: pd.DataFrame, color_by: str = "contractor",
                      show_nt_ot: bool = False, height: int = 400) -> go.Figure:
    """Stacked bar chart of daily hours."""
    if show_nt_ot:
        nt_agg = daily_df.groupby("date")["nt_hours"].sum().reset_index()
        ot_agg = daily_df.groupby("date")["ot_hours"].sum().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=nt_agg["date"], y=nt_agg["nt_hours"],
            name="NT", marker_color=COLORS["nt"],
        ))
        fig.add_trace(go.Bar(
            x=ot_agg["date"], y=ot_agg["ot_hours"],
            name="OT", marker_color=COLORS["ot"],
        ))
        fig.update_layout(barmode="stack")
    else:
        agg = daily_df.groupby(["date", color_by])["total_hours"].sum().reset_index()
        fig = px.bar(
            agg, x="date", y="total_hours", color=color_by,
            color_discrete_sequence=CONTRACTOR_COLORS,
        )
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Date",
        yaxis_title="Hours",
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#E8EAED")
    fig.update_yaxes(gridcolor="#E8EAED")
    return fig


def daily_cost_chart(daily_df: pd.DataFrame, height: int = 400) -> go.Figure:
    """Line chart of cumulative daily cost."""
    daily_agg = daily_df.groupby("date").agg(
        daily_cost=("total_cost", "sum")
    ).reset_index().sort_values("date")
    daily_agg["cum_cost"] = daily_agg["daily_cost"].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_agg["date"], y=daily_agg["cum_cost"],
        mode="lines+markers", name="Cumulative Cost",
        line=dict(color=COLORS["actual"], width=2),
        marker=dict(size=4),
    ))
    fig.add_trace(go.Bar(
        x=daily_agg["date"], y=daily_agg["daily_cost"],
        name="Daily Cost", marker_color=COLORS["primary"], opacity=0.3,
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis_title="Date",
        yaxis_title="Cost ($)",
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#E8EAED")
    fig.update_yaxes(gridcolor="#E8EAED")
    return fig


def comparison_bar_chart(comp_df: pd.DataFrame, group_by: str = "contractor",
                         metric: str = "cost", height: int = 400) -> go.Figure:
    """Side-by-side bar chart comparing actual vs estimate."""
    if metric == "cost":
        actual_col, est_col = "actual_total_cost", "est_cost"
        y_label = "Cost ($)"
    else:
        actual_col, est_col = "actual_total_hours", "est_hours"
        y_label = "Hours"

    agg = comp_df.groupby(group_by).agg(
        actual=(actual_col, "sum"),
        estimate=(est_col, "sum"),
    ).reset_index().sort_values("actual", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=agg[group_by], x=agg["estimate"], name="Estimate",
        orientation="h", marker_color=COLORS["estimate"], opacity=0.6,
    ))
    fig.add_trace(go.Bar(
        y=agg[group_by], x=agg["actual"], name="Actual",
        orientation="h", marker_color=COLORS["actual"],
    ))
    fig.update_layout(
        barmode="group",
        height=max(height, len(agg) * 35 + 100),
        margin=dict(l=120, r=20, t=30, b=40),
        xaxis_title=y_label,
        legend=dict(orientation="h", y=-0.1),
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#E8EAED")
    fig.update_yaxes(gridcolor="#E8EAED")
    return fig


def ot_percentage_chart(comp_df: pd.DataFrame, group_by: str = "contractor",
                        height: int = 350) -> go.Figure:
    """Horizontal bar chart of OT% by group."""
    agg = comp_df.groupby(group_by).agg(
        total_ot=("actual_ot_hours", "sum"),
        total_hours=("actual_total_hours", "sum"),
    ).reset_index()
    agg["ot_pct"] = np.where(agg["total_hours"] > 0,
                              agg["total_ot"] / agg["total_hours"] * 100, 0)
    agg = agg.sort_values("ot_pct", ascending=True)

    colors = [COLORS["danger"] if p > 30 else COLORS["warning"] if p > 20
              else COLORS["success"] for p in agg["ot_pct"]]

    fig = go.Figure(go.Bar(
        y=agg[group_by], x=agg["ot_pct"],
        orientation="h", marker_color=colors,
        text=[f"{p:.1f}%" for p in agg["ot_pct"]],
        textposition="outside",
    ))
    fig.update_layout(
        height=max(height, len(agg) * 35 + 80),
        margin=dict(l=120, r=40, t=30, b=40),
        xaxis_title="OT %",
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#E8EAED")
    return fig


def eac_chart(forecast_df: pd.DataFrame, group_by: str = "contractor",
              height: int = 400) -> go.Figure:
    """Stacked bar chart showing actual + forecast remaining vs estimate."""
    agg = forecast_df.groupby(group_by).agg(
        actual=("actual_total_cost", "sum"),
        forecast_remaining=("forecast_remaining_cost", "sum"),
        estimate=("est_cost", "sum"),
    ).reset_index().sort_values("actual", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=agg[group_by], x=agg["actual"], name="Actual Cost",
        orientation="h", marker_color=COLORS["actual"],
    ))
    fig.add_trace(go.Bar(
        y=agg[group_by], x=agg["forecast_remaining"], name="Forecast Remaining",
        orientation="h", marker_color=COLORS["forecast"], opacity=0.6,
    ))
    # Add estimate markers
    fig.add_trace(go.Scatter(
        y=agg[group_by], x=agg["estimate"],
        mode="markers", name="Estimate",
        marker=dict(symbol="diamond", size=10, color=COLORS["danger"]),
    ))
    fig.update_layout(
        barmode="stack",
        height=max(height, len(agg) * 40 + 100),
        margin=dict(l=120, r=20, t=30, b=40),
        xaxis_title="Cost ($)",
        legend=dict(orientation="h", y=-0.1),
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#E8EAED")
    return fig


# ---------------------------------------------------------------------------
# Styled table
# ---------------------------------------------------------------------------

def format_currency(val):
    """Format number as currency."""
    if pd.isna(val) or val == 0:
        return "$0"
    return f"${val:,.0f}"


def format_hours(val):
    """Format number as hours."""
    if pd.isna(val):
        return "0"
    return f"{val:,.1f}"


def format_pct(val):
    """Format as percentage."""
    if pd.isna(val):
        return "0%"
    return f"{val:.1f}%"


def styled_comparison_table(df: pd.DataFrame, cost_cols: list = None,
                            hours_cols: list = None, pct_cols: list = None):
    """Display a styled DataFrame with conditional formatting."""
    display_df = df.copy()

    # Format columns
    format_dict = {}
    for col in (cost_cols or []):
        if col in display_df.columns:
            format_dict[col] = "${:,.0f}"
    for col in (hours_cols or []):
        if col in display_df.columns:
            format_dict[col] = "{:,.1f}"
    for col in (pct_cols or []):
        if col in display_df.columns:
            format_dict[col] = "{:.1f}%"

    def color_variance(val):
        if isinstance(val, (int, float)):
            if val < 0:
                return "color: #C5221F; font-weight: bold"
            elif val > 0:
                return "color: #0D904F"
        return ""

    variance_cols = [c for c in display_df.columns if "variance" in c.lower()]
    styler = display_df.style.format(format_dict)
    for vc in variance_cols:
        if vc in display_df.columns:
            styler = styler.map(color_variance, subset=[vc])

    st.dataframe(styler, use_container_width=True, hide_index=True)
