"""
Road visualisation helpers.

Creates Plotly figures used in the Streamlit dashboard:
  • create_road_figure   — top-down lane diagram
  • create_metric_chart  — baseline vs reorganized time-series comparison
  • create_comparison_bar — bar chart of metric deltas
"""

from __future__ import annotations
from typing import Callable, List, Optional

import plotly.graph_objects as go

from src.models import LaneFunction, MetricsSnapshot, TrafficState

# ── Visual design constants ──────────────────────────────────────────────────

LANE_COLORS = {
    LaneFunction.GENERAL: "#3A7BCC",
    LaneFunction.BUS_PRIORITY: "#E8A020",
    LaneFunction.EMERGENCY: "#D62728",
    LaneFunction.BICYCLE: "#2CA02C",
    LaneFunction.PEDESTRIAN_BUFFER: "#8E44AD",
    LaneFunction.TRANSITION: "#7F8C8D",
    LaneFunction.CLOSED: "#2C3E50",
}

LANE_LABELS = {
    LaneFunction.GENERAL: "GENERAL TRAFFIC",
    LaneFunction.BUS_PRIORITY: "BUS PRIORITY",
    LaneFunction.EMERGENCY: "EMERGENCY CORRIDOR",
    LaneFunction.BICYCLE: "BICYCLE LANE",
    LaneFunction.PEDESTRIAN_BUFFER: "PEDESTRIAN BUFFER",
    LaneFunction.TRANSITION: "⚠ TRANSITION / CLEARING",
    LaneFunction.CLOSED: "CLOSED",
}

LANE_ICONS = {
    LaneFunction.GENERAL: "🚗",
    LaneFunction.BUS_PRIORITY: "🚌",
    LaneFunction.EMERGENCY: "🚨",
    LaneFunction.BICYCLE: "🚲",
    LaneFunction.PEDESTRIAN_BUFFER: "🚶",
    LaneFunction.TRANSITION: "⚠️",
    LaneFunction.CLOSED: "🚫",
}

STATE_COLORS = {
    "NORMAL": "#27AE60",
    "TRANSITIONING": "#E67E22",
    "BUS_PRIORITY_ACTIVE": "#E8A020",
    "EMERGENCY_ACTIVE": "#D62728",
    "PEDESTRIAN_BUFFER_ACTIVE": "#8E44AD",
    "FALLBACK_SAFE": "#D62728",
}

BG_DARK = "#0D0D0D"
BG_ROAD = "#1A1A2E"
BG_PAPER = "#0D0D0D"
TEXT_COL = "#EAEAEA"


# ── Road diagram ─────────────────────────────────────────────────────────────


def create_road_figure(
    lane_config: List[LaneFunction],
    traffic_state: Optional[TrafficState] = None,
    system_state: str = "NORMAL",
    title: str = "Current Road Configuration",
) -> go.Figure:
    """
    Top-down schematic of the road with colour-coded lane functions.

    Each lane is rendered as a horizontal band; lanes are numbered 1..N
    from top to bottom.  The current function is labelled in the band.
    """
    n_lanes = len(lane_config)
    lane_h = 1.2  # height per lane in data units
    road_w = 12.0  # road length in data units

    fig = go.Figure()

    # Road asphalt background
    fig.add_shape(
        type="rect",
        x0=0,
        y0=0,
        x1=road_w,
        y1=n_lanes * lane_h,
        fillcolor=BG_ROAD,
        line=dict(color="#333", width=1),
        layer="below",
    )

    for i, func in enumerate(lane_config):
        y0 = i * lane_h
        y1 = (i + 1) * lane_h
        ymid = (y0 + y1) / 2
        color = LANE_COLORS.get(func, "#555")
        label = LANE_LABELS.get(func, func.value)
        icon = LANE_ICONS.get(func, "")

        # Lane band
        fig.add_shape(
            type="rect",
            x0=0.15,
            y0=y0 + 0.06,
            x1=road_w - 0.15,
            y1=y1 - 0.06,
            fillcolor=color,
            opacity=0.88,
            line=dict(color="white", width=1.0),
        )

        # Lane number badge
        fig.add_annotation(
            x=0.55,
            y=ymid,
            text=f"<b>L{i+1}</b>",
            showarrow=False,
            font=dict(color="white", size=12, family="monospace"),
        )

        # Function label
        fig.add_annotation(
            x=road_w / 2,
            y=ymid,
            text=f"<b>{icon}  {label}</b>",
            showarrow=False,
            font=dict(color="white", size=13),
        )

        # Queue indicator (right side)
        if traffic_state is not None:
            q_map = {
                LaneFunction.GENERAL: "car",
                LaneFunction.BUS_PRIORITY: "bus",
                LaneFunction.EMERGENCY: "emergency",
                LaneFunction.BICYCLE: "bicycle",
                LaneFunction.PEDESTRIAN_BUFFER: "pedestrian",
            }
            vt = q_map.get(func)
            qty = traffic_state.queues.get(vt, 0.0) if vt else 0.0
            if qty > 0:
                fig.add_annotation(
                    x=road_w - 0.7,
                    y=ymid,
                    text=f"Q:{qty:.0f}",
                    showarrow=False,
                    font=dict(color="white", size=10, family="monospace"),
                )

    # Dashed lane dividers
    for i in range(1, n_lanes):
        y = i * lane_h
        for x in range(1, int(road_w), 2):
            fig.add_shape(
                type="line",
                x0=x,
                y0=y,
                x1=x + 0.9,
                y1=y,
                line=dict(color="rgba(255,255,255,0.3)", width=1, dash="dash"),
            )

    # Direction arrows
    arrow_y = n_lanes * lane_h / 2
    for ax in [2.5, 5.5, 8.5]:
        fig.add_annotation(
            x=ax,
            y=arrow_y,
            ax=ax - 0.8,
            ay=arrow_y,
            text="",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.4,
            arrowwidth=2,
            arrowcolor="rgba(255,255,255,0.25)",
        )

    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=15, color=TEXT_COL),
        ),
        plot_bgcolor=BG_DARK,
        paper_bgcolor=BG_PAPER,
        font=dict(color=TEXT_COL),
        height=max(180, n_lanes * 80 + 80),
        margin=dict(l=10, r=10, t=45, b=10),
        xaxis=dict(visible=False, range=[-0.3, road_w + 0.3]),
        yaxis=dict(visible=False, range=[-0.2, n_lanes * lane_h + 0.2]),
        showlegend=False,
    )
    return fig


# ── Metric time-series chart ─────────────────────────────────────────────────


def create_metric_chart(
    baseline_snaps: List[MetricsSnapshot],
    reorg_snaps: List[MetricsSnapshot],
    metric_fn: Callable[[MetricsSnapshot], float],
    title: str,
    y_label: str,
) -> go.Figure:
    """
    Line chart comparing a metric over time for baseline vs reorganized run.

    metric_fn is a callable that extracts the desired value from a snapshot,
    e.g.  lambda s: s.queue_lengths.get("bus", 0.0)
    """
    fig = go.Figure()

    if baseline_snaps:
        x = [s.timestamp for s in baseline_snaps]
        y = [metric_fn(s) for s in baseline_snaps]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                name="Baseline (fixed config)",
                line=dict(color="#E67E22", width=2, dash="dash"),
                mode="lines",
            )
        )

    if reorg_snaps:
        x2 = [s.timestamp for s in reorg_snaps]
        y2 = [metric_fn(s) for s in reorg_snaps]
        fig.add_trace(
            go.Scatter(
                x=x2,
                y=y2,
                name="Self-Reorganizing",
                line=dict(color="#3A7BCC", width=2.5),
                mode="lines",
            )
        )

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=13, color=TEXT_COL)),
        plot_bgcolor="#111122",
        paper_bgcolor=BG_PAPER,
        font=dict(color=TEXT_COL),
        xaxis=dict(title="Sim step (min)", color=TEXT_COL, gridcolor="#333"),
        yaxis=dict(title=y_label, color=TEXT_COL, gridcolor="#333"),
        legend=dict(font=dict(color=TEXT_COL, size=11)),
        height=260,
        margin=dict(l=50, r=20, t=40, b=50),
        annotations=[
            dict(
                x=0.5,
                y=-0.22,
                xref="paper",
                yref="paper",
                text="⚠ Simulated result — not a real-world measurement",
                showarrow=False,
                font=dict(size=9, color="#888"),
            )
        ],
    )
    return fig


# ── Comparison bar chart ─────────────────────────────────────────────────────


def create_comparison_bar(comparison: dict) -> go.Figure:
    """
    Horizontal bar chart showing % change for each key metric.

    Green bars = improvement (for travel time / delay / queue: negative = better).
    Red   bars = degradation.
    """
    metric_labels = {
        "bus_travel_time": "Bus travel time",
        "car_travel_time": "Car travel time",
        "bus_queue": "Bus queue length",
        "bus_delay": "Bus delay",
        "throughput": "Total throughput",
        "pedestrian_queue": "Pedestrian queue",
    }

    labels, values, colors = [], [], []
    for key, label in metric_labels.items():
        if key not in comparison:
            continue
        pct = comparison[key]["pct_change"]
        improved = comparison[key]["improved"]
        labels.append(label)
        values.append(pct)
        colors.append("#2ECC71" if improved else "#E74C3C")

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.1f}%" for v in values],
            textposition="outside",
            textfont=dict(color=TEXT_COL, size=11),
        )
    )

    fig.update_layout(
        title=dict(
            text="<b>% Change vs Baseline (Simulated)</b>",
            font=dict(size=13, color=TEXT_COL),
        ),
        plot_bgcolor="#111122",
        paper_bgcolor=BG_PAPER,
        font=dict(color=TEXT_COL),
        xaxis=dict(
            title="% change",
            color=TEXT_COL,
            gridcolor="#333",
            zeroline=True,
            zerolinecolor="#555",
            zerolinewidth=1,
        ),
        yaxis=dict(color=TEXT_COL, automargin=True),
        height=280,
        margin=dict(l=140, r=60, t=45, b=40),
        annotations=[
            dict(
                x=0.5,
                y=-0.18,
                xref="paper",
                yref="paper",
                text="⚠ Simulated result — not a real-world measurement",
                showarrow=False,
                font=dict(size=9, color="#888"),
            )
        ],
    )
    return fig
