"""
Self-Reorganizing Roads — Streamlit Dashboard
═════════════════════════════════════════════
Proof-of-concept prototype for Fund My Crazy 2026 hackathon.

Run from the project root:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is on the path when run via `streamlit run app/...`
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src.config.settings import load_config
from src.models import LaneFunction, ScenarioMetrics
from src.orchestrator import run_scenario_pair
from src.visualization.road_visualizer import (
    create_road_figure,
    create_metric_chart,
    create_comparison_bar,
    LANE_COLORS,
    STATE_COLORS,
)

# ── Page setup ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Self-Reorganizing Roads",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
    .main-title   { font-size:2.0rem; font-weight:700; color:#EAEAEA; }
    .sub-title    { font-size:1.0rem; color:#9E9E9E; margin-top:-0.5rem; }
    .state-badge  { display:inline-block; padding:6px 18px; border-radius:20px;
                    font-size:0.9rem; font-weight:700; letter-spacing:1px; }
    .section-head { font-size:1.0rem; font-weight:600; color:#BCBCBC;
                    text-transform:uppercase; letter-spacing:1px;
                    border-bottom:1px solid #333; padding-bottom:4px; margin-bottom:8px; }
    .decision-box { background:#1A1A2E; border-left:4px solid #3A7BCC;
                    border-radius:6px; padding:14px 18px; margin:8px 0; }
    .metric-val   { font-size:1.5rem; font-weight:700; color:#EAEAEA; }
    .metric-lbl   { font-size:0.75rem; color:#888; text-transform:uppercase; }
    .disclaimer   { font-size:0.75rem; color:#666; font-style:italic; }
    .lane-chip    { display:inline-block; border-radius:4px; padding:3px 10px;
                    font-size:0.75rem; font-weight:700; margin:2px; color:white; }
    div[data-testid="stMetricDelta"] > div { font-size: 0.8rem !important; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# ── Config & caching ─────────────────────────────────────────────────────────


@st.cache_resource
def _config() -> dict:
    return load_config()


@st.cache_data(show_spinner="Running simulation…")
def _run(scenario: str, seed: int, steps: int) -> tuple:
    """Cached scenario pair — computed once per session per scenario key."""
    config = load_config()
    return run_scenario_pair(scenario, config)


# ── Session state defaults ────────────────────────────────────────────────────

if "scenario" not in st.session_state:
    st.session_state.scenario = "normal"


# ── Header ───────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="main-title">🚦 Self-Reorganizing Roads</div>'
    '<div class="sub-title">Adaptive allocation of urban road space using real-time traffic demand</div>',
    unsafe_allow_html=True,
)
st.markdown("---")


# ── Scenario selector ─────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Select Scenario</div>', unsafe_allow_html=True)
s_col1, s_col2, s_col3, s_col4 = st.columns(4)

SCENARIO_META = {
    "normal": ("🚗 Normal Traffic", "#3A7BCC", "Baseline — no special conditions"),
    "high_bus": (
        "🚌 High Bus Demand",
        "#E8A020",
        "Bus frequency increases; triggers BUS PRIORITY",
    ),
    "emergency": (
        "🚨 Emergency Vehicle",
        "#D62728",
        "Ambulance detected; triggers EMERGENCY CORRIDOR",
    ),
    "pedestrian_surge": (
        "🚶 Pedestrian Surge",
        "#8E44AD",
        "Pedestrian demand spikes; triggers PEDESTRIAN BUFFER",
    ),
}

for col, (key, (label, color, desc)) in zip(
    [s_col1, s_col2, s_col3, s_col4], SCENARIO_META.items()
):
    with col:
        active = st.session_state.scenario == key
        border = f"3px solid {color}" if active else "1px solid #333"
        st.markdown(
            f"<div style='border:{border};border-radius:8px;padding:8px;text-align:center;"
            f"background:#111;cursor:pointer;'>"
            f"<b style='color:{color};font-size:0.95rem;'>{label}</b><br>"
            f"<span style='color:#888;font-size:0.75rem;'>{desc}</span></div>",
            unsafe_allow_html=True,
        )
        if st.button(
            f"Run {label.split()[0]}", key=f"btn_{key}", use_container_width=True
        ):
            st.session_state.scenario = key
            st.rerun()

st.markdown("")


# ── Load results ─────────────────────────────────────────────────────────────

config = _config()
seed = config["simulation"]["random_seed"]
steps = config["simulation"]["time_steps"]
scenario = st.session_state.scenario

step_history, baseline_metrics, reorg_metrics, comparison = _run(scenario, seed, steps)

# Find the best display step:
# prefer the LAST step in a priority-active state so the demo road visualisation
# always shows the lane change rather than a brief reversion to NORMAL at the end.
_PRIORITY_STATES = {
    "EMERGENCY_ACTIVE",
    "BUS_PRIORITY_ACTIVE",
    "PEDESTRIAN_BUFFER_ACTIVE",
}


def _display_step(history):
    for s in reversed(history):
        if s["system_state"] in _PRIORITY_STATES:
            return s
    return history[-1]


display_step = _display_step(step_history)
final_step = step_history[-1]  # kept for raw metrics display
final_cfg = display_step["config"]
final_state = display_step["system_state"]
last_alloc = display_step["allocation"]
last_demand = display_step["demand"]
last_prio = display_step["priority"]
final_snap = display_step["snap"]

state_color = STATE_COLORS.get(final_state, "#888")
scenario_label = SCENARIO_META[scenario][0]


# ── Main tabs ────────────────────────────────────────────────────────────────

tab_dash, tab_metrics, tab_guide = st.tabs(
    ["📊 Dashboard", "📈 Metrics & Analysis", "📖 System Guide"]
)


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

with tab_dash:
    left, right = st.columns([3, 2], gap="medium")

    # ── Left: Road visualisation + traffic state ──────────────────────────
    with left:
        st.markdown(
            '<div class="section-head">Road Configuration</div>', unsafe_allow_html=True
        )

        road_fig = create_road_figure(
            lane_config=final_cfg,
            traffic_state=final_step["state"],
            system_state=final_state,
            title=f"Simulation End — Step {steps}",
        )
        st.plotly_chart(road_fig, use_container_width=True)

        # Lane config table
        st.markdown(
            '<div class="section-head">Lane Assignment</div>', unsafe_allow_html=True
        )
        lane_cols = st.columns(len(final_cfg))
        for ci, (lc, func) in enumerate(zip(lane_cols, final_cfg)):
            color = LANE_COLORS.get(
                LaneFunction(func) if isinstance(func, str) else func, "#555"
            )
            lbl = func.value if hasattr(func, "value") else str(func)
            lc.markdown(
                f"<div style='text-align:center;'>"
                f"<div style='font-size:0.75rem;color:#888;'>Lane {ci+1}</div>"
                f"<div class='lane-chip' style='background:{color};'>{lbl}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Traffic state metrics
        st.markdown("")
        st.markdown(
            '<div class="section-head">Traffic State (final step)</div>',
            unsafe_allow_html=True,
        )
        q = final_step["state"].queues
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("🚗 Cars queued", f"{q.get('car', 0):.0f}")
        m2.metric("🚌 Buses queued", f"{q.get('bus', 0):.0f}")
        m3.metric("🚲 Bikes queued", f"{q.get('bicycle', 0):.0f}")
        m4.metric("🚶 Peds queued", f"{q.get('pedestrian', 0):.0f}")
        m5.metric(
            "🚨 Emergency", "YES" if final_step["state"].emergency_detected else "NO"
        )

        st.markdown(
            '<p class="disclaimer">⚠ Simulated result — not a real-world measurement.</p>',
            unsafe_allow_html=True,
        )

    # ── Right: System state + decision engine ────────────────────────────
    with right:
        # System state badge
        st.markdown(
            '<div class="section-head">System State</div>', unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='text-align:center;margin:10px 0 18px 0;'>"
            f"<span class='state-badge' style='background:{state_color};color:white;'>"
            f"{final_state.replace('_', ' ')}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        # Decision engine
        st.markdown(
            '<div class="section-head">Decision Engine</div>', unsafe_allow_html=True
        )
        if last_prio:
            lvl_colors = {
                "SAFETY": "#D62728",
                "EMERGENCY": "#D62728",
                "PEDESTRIAN_CYCLIST": "#8E44AD",
                "PUBLIC_TRANSPORT": "#E8A020",
                "GENERAL_TRAFFIC": "#3A7BCC",
            }
            lc = lvl_colors.get(last_prio.priority_level, "#555")
            st.markdown(
                f"<div class='decision-box' style='border-left-color:{lc};'>"
                f"<div style='color:{lc};font-size:0.75rem;font-weight:700;letter-spacing:1px;'>"
                f"PRIORITY LEVEL: {last_prio.priority_level}</div>"
                f"<div style='font-size:1.0rem;font-weight:700;color:#EAEAEA;margin:6px 0;'>"
                f"{last_prio.action.replace('_', ' ')}</div>"
                f"<div style='font-size:0.82rem;color:#AAA;line-height:1.5;'>"
                f"{last_prio.reason}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Demand indicators
        st.markdown(
            '<div class="section-head" style="margin-top:10px;">Demand Signals</div>',
            unsafe_allow_html=True,
        )
        if last_demand:
            thresholds = config["demand"]["thresholds"]
            demand_rows = [
                ("🚗 Car demand", last_demand.car_demand, None),
                ("🚌 Bus demand", last_demand.bus_demand, thresholds["bus_priority"]),
                (
                    "🚲 Bicycle demand",
                    last_demand.bicycle_demand,
                    thresholds["bicycle_priority"],
                ),
                (
                    "🚶 Pedestrian demand",
                    last_demand.pedestrian_demand,
                    thresholds["pedestrian_priority"],
                ),
            ]
            for label, val, thresh in demand_rows:
                pct = min(1.0, val / (thresh if thresh else max(val, 1)))
                color = "#D62728" if (thresh and val >= thresh) else "#3A7BCC"
                st.markdown(
                    f"<div style='margin-bottom:6px;'>"
                    f"<div style='display:flex;justify-content:space-between;'>"
                    f"<span style='font-size:0.8rem;color:#CCC;'>{label}</span>"
                    f"<span style='font-size:0.8rem;color:{color};font-weight:700;'>{val:.1f}"
                    + (f" / {thresh:.1f}" if thresh else "")
                    + f"</span></div>"
                    f"<div style='background:#222;border-radius:3px;height:6px;margin-top:2px;'>"
                    f"<div style='width:{pct*100:.0f}%;background:{color};height:6px;border-radius:3px;'></div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

        # Reconfiguration path
        if last_alloc and last_alloc.decision not in ("NO_CHANGE", "MAINTAIN_NORMAL"):
            st.markdown("")
            st.markdown(
                '<div class="section-head">Reconfiguration Path</div>',
                unsafe_allow_html=True,
            )

            def _config_str(cfg):
                return " → ".join(
                    f.value if hasattr(f, "value") else str(f) for f in cfg
                )

            st.markdown(
                f"<div style='font-size:0.78rem;color:#888;margin-bottom:4px;'>BEFORE</div>"
                f"<div style='font-size:0.8rem;color:#EEE;font-family:monospace;background:#111;padding:6px 10px;border-radius:4px;'>"
                f"{_config_str(last_alloc.previous_config)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:center;color:#E67E22;font-size:1.2rem;'>⬇</div>"
                f"<div style='font-size:0.78rem;color:#888;margin-bottom:4px;'>TRANSITION</div>"
                f"<div style='font-size:0.8rem;color:#E67E22;font-family:monospace;background:#111;padding:6px 10px;border-radius:4px;'>"
                f"{_config_str(last_alloc.transition_config)}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:center;color:#2ECC71;font-size:1.2rem;'>⬇</div>"
                f"<div style='font-size:0.78rem;color:#888;margin-bottom:4px;'>AFTER</div>"
                f"<div style='font-size:0.8rem;color:#2ECC71;font-family:monospace;background:#111;padding:6px 10px;border-radius:4px;'>"
                f"{_config_str(last_alloc.new_config)}</div>",
                unsafe_allow_html=True,
            )
            if last_alloc.expected_effect:
                st.markdown(
                    f"<div style='font-size:0.78rem;color:#888;margin-top:8px;'>"
                    f"Expected effect: {last_alloc.expected_effect}</div>",
                    unsafe_allow_html=True,
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — METRICS & ANALYSIS
# ════════════════════════════════════════════════════════════════════════════

with tab_metrics:
    b_snaps = baseline_metrics.snapshots
    r_snaps = reorg_metrics.snapshots

    st.markdown(
        f'<div class="section-head">Performance Comparison — {scenario_label} (Simulated)</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "⚠ All values are simulation outputs. They are NOT real-world measurements or predictions."
    )

    # Summary numbers
    c1, c2, c3, c4 = st.columns(4)
    b_bus_tt = baseline_metrics.avg_travel_times.get("bus", 2.0)
    r_bus_tt = reorg_metrics.avg_travel_times.get("bus", 2.0)
    b_bus_q = baseline_metrics.avg_queue_lengths.get("bus", 0.0)
    r_bus_q = reorg_metrics.avg_queue_lengths.get("bus", 0.0)

    c1.metric(
        "Avg bus travel time",
        f"{r_bus_tt:.2f} min",
        delta=f"{r_bus_tt - b_bus_tt:+.2f} vs baseline",
        delta_color="inverse",
    )
    c2.metric(
        "Avg bus queue",
        f"{r_bus_q:.1f} veh",
        delta=f"{r_bus_q - b_bus_q:+.1f} vs baseline",
        delta_color="inverse",
    )
    b_tp = baseline_metrics.avg_throughput
    r_tp = reorg_metrics.avg_throughput
    c3.metric(
        "Avg throughput / step",
        f"{r_tp:.1f} veh",
        delta=f"{r_tp - b_tp:+.1f} vs baseline",
    )
    b_car = baseline_metrics.avg_travel_times.get("car", 2.0)
    r_car = reorg_metrics.avg_travel_times.get("car", 2.0)
    c4.metric(
        "Avg car travel time",
        f"{r_car:.2f} min",
        delta=f"{r_car - b_car:+.2f} vs baseline",
        delta_color="inverse",
    )

    st.markdown("---")

    # Charts
    ch1, ch2 = st.columns(2)
    with ch1:
        fig_bq = create_metric_chart(
            b_snaps,
            r_snaps,
            lambda s: s.queue_lengths.get("bus", 0.0),
            "Bus Queue Length Over Time",
            "Buses waiting",
        )
        st.plotly_chart(fig_bq, use_container_width=True)

    with ch2:
        fig_bt = create_metric_chart(
            b_snaps,
            r_snaps,
            lambda s: s.travel_times.get("bus", 2.0),
            "Bus Travel Time Over Time",
            "Minutes",
        )
        st.plotly_chart(fig_bt, use_container_width=True)

    ch3, ch4 = st.columns(2)
    with ch3:
        fig_tp = create_metric_chart(
            b_snaps,
            r_snaps,
            lambda s: s.total_throughput,
            "Total Throughput Over Time",
            "Vehicles/step",
        )
        st.plotly_chart(fig_tp, use_container_width=True)

    with ch4:
        fig_pq = create_metric_chart(
            b_snaps,
            r_snaps,
            lambda s: s.queue_lengths.get("pedestrian", 0.0),
            "Pedestrian Queue Over Time",
            "Pedestrians waiting",
        )
        st.plotly_chart(fig_pq, use_container_width=True)

    # % change bar chart
    st.markdown("---")
    bar_fig = create_comparison_bar(comparison)
    st.plotly_chart(bar_fig, use_container_width=True)

    # Detailed comparison table
    st.markdown(
        '<div class="section-head">Detailed Comparison Table</div>',
        unsafe_allow_html=True,
    )
    metric_names = {
        "bus_travel_time": "Bus travel time (min)",
        "car_travel_time": "Car travel time (min)",
        "bus_queue": "Bus queue (vehicles)",
        "bus_delay": "Bus delay (min)",
        "throughput": "Throughput (veh/step)",
        "pedestrian_queue": "Pedestrian queue",
    }
    rows = []
    for key, label in metric_names.items():
        if key not in comparison:
            continue
        d = comparison[key]
        improved = d["improved"]
        direction = (
            "✅ Improved"
            if improved
            else ("➖ Unchanged" if abs(d["pct_change"]) < 0.5 else "⚠️ Trade-off")
        )
        rows.append(
            {
                "Metric": label,
                "Baseline": f"{d['baseline']:.2f}",
                "Self-Reorganising": f"{d['optimised']:.2f}",
                "Change": f"{d['delta']:+.3f}",
                "% Change": f"{d['pct_change']:+.1f}%",
                "Result": direction,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Simulation log
    with st.expander("📋 Simulation step log (first 10 steps)"):
        log_rows = []
        for entry in step_history[:10]:
            sn = entry["snap"]
            log_rows.append(
                {
                    "Step": entry["step"],
                    "System state": entry["system_state"],
                    "Config": " | ".join(
                        (f.value if hasattr(f, "value") else str(f))
                        for f in entry["config"]
                    ),
                    "Bus queue": f"{sn.queue_lengths.get('bus', 0):.1f}",
                    "Car queue": f"{sn.queue_lengths.get('car', 0):.1f}",
                    "Throughput": f"{sn.total_throughput:.1f}",
                }
            )
        st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
        st.caption("⚠ Simulated results only.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — SYSTEM GUIDE
# ════════════════════════════════════════════════════════════════════════════

with tab_guide:
    left_g, right_g = st.columns([2, 1])

    with left_g:
        st.markdown("""
## How Self-Reorganizing Roads Works

### 🔍 What makes this different from adaptive traffic signals?

| Traditional adaptive signal | Self-Reorganizing Roads |
|---|---|
| Changes **signal timing** | Changes **lane function** |
| Same lanes, different green phases | Different lanes serve different purposes |
| Buses wait in the same lane, just slightly less | Bus gets a **dedicated priority lane** |
| No structural reorganisation | Road space is dynamically reallocated |

---

### Pipeline

```
Traffic State → Demand Estimation → Priority Engine → Lane Allocation → Simulation → Metrics
```

**1. Traffic sensing** (simulated)
Cameras and inductive loops measure arrivals, queue lengths, and vehicle types.
An emergency transponder signal triggers immediate detection.

**2. Demand estimation**
Each vehicle type gets a demand score: `arrivals + 0.5 × queue_length`.
Higher scores = more pressure to serve that type.

**3. Priority engine — 5-level hierarchy**
```
Level 1: SAFETY           — enforce hard constraints, fall back if violated
Level 2: EMERGENCY        — create corridor for emergency vehicles
Level 3: PEDESTRIAN/CYCLIST — protect vulnerable road users during surges
Level 4: PUBLIC TRANSPORT  — bus-priority lane when bus demand is high
Level 5: GENERAL TRAFFIC  — maintain default if no condition is met
```
Each level is checked in order. First match wins. All decisions are logged with a reason.

**4. Safety constraint engine**
Before any reallocation is committed, the safety manager checks:
- At least 1 general-traffic lane must always be available
- EMERGENCY and PEDESTRIAN_BUFFER cannot coexist (conflict at transition zones)
- Only one EMERGENCY corridor permitted at a time
- No adjacent lane pair may be incompatible

If the proposed configuration fails any check → safe fallback is used instead.

**5. Lane allocator + transition state**
Lanes do not instantly change function. A `TRANSITION` state is held for
a configurable duration (default: 2 steps). During transition, lanes operate
at 50 % capacity — representing real-world clearing, signage update, and
traffic rerouting time.

**6. Safe fallback**
If the adaptive system cannot determine a safe configuration (sensor failure,
conflicting demands, constraint violation), it falls back to the pre-configured
safe default: `[GENERAL, GENERAL, GENERAL, BICYCLE]`.

---

### Key modelling assumptions

- Each simulation step = 1 minute
- Vehicle arrivals = Poisson process (deterministic with seed = 42)
- Signal green ratio fixed at 50 %
- Travel time = BPR function of queue/capacity ratio
- Physical road width and signal infrastructure not modelled
- Single road segment; no network effects
        """)

    with right_g:
        st.markdown("### Scenario Quick Reference")
        for key, (label, color, desc) in SCENARIO_META.items():
            cfg_key = key
            cfg_list = {
                "normal": ["GENERAL", "GENERAL", "GENERAL", "BICYCLE"],
                "high_bus": ["GENERAL", "BUS_PRIORITY", "GENERAL", "BICYCLE"],
                "emergency": ["EMERGENCY", "GENERAL", "GENERAL", "BICYCLE"],
                "pedestrian_surge": [
                    "GENERAL",
                    "GENERAL",
                    "PEDESTRIAN_BUFFER",
                    "BICYCLE",
                ],
            }
            target = " | ".join(cfg_list.get(cfg_key, []))
            st.markdown(
                f"<div style='border:1px solid {color};border-radius:6px;padding:10px;margin-bottom:10px;'>"
                f"<b style='color:{color};'>{label}</b><br>"
                f"<span style='font-size:0.8rem;color:#999;'>{desc}</span><br>"
                f"<span style='font-size:0.75rem;color:#666;font-family:monospace;'>"
                f"Target: {target}</span></div>",
                unsafe_allow_html=True,
            )

        st.markdown("### Thresholds (from settings.yaml)")
        thresholds = config["demand"]["thresholds"]
        st.json(
            {
                "bus_priority": f"{thresholds['bus_priority']} demand score",
                "bicycle_priority": f"{thresholds['bicycle_priority']} demand score",
                "pedestrian_priority": f"{thresholds['pedestrian_priority']} demand score",
            }
        )

        st.markdown("### Limitations")
        st.warning(
            "This is a simplified proof-of-concept simulation.\n\n"
            "• Not a calibrated real-world traffic model\n"
            "• Single road segment only\n"
            "• No weather, accidents, or special events\n"
            "• No vehicle routing or network effects\n"
            "• Pedestrian/cyclist capacity is approximate\n"
            "• Physical lane transition costs are simplified\n\n"
            "All metrics shown are **simulated results** — "
            "not real-world measurements or predictions."
        )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🚦 Self-Reorganizing Roads")
    st.markdown(f"**Active scenario:** {scenario_label}")
    st.markdown(
        f"<span class='state-badge' style='background:{state_color};color:white;font-size:0.8rem;'>"
        f"{final_state.replace('_',' ')}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown(f"**Simulation steps:** {steps}")
    st.markdown(f"**Random seed:** {seed}")
    st.markdown(f"**Lanes:** {config['simulation']['road']['num_lanes']}")
    st.markdown(
        f"**Transition duration:** {config['lanes']['transition_duration']} steps"
    )
    st.markdown("---")
    st.markdown("**Demo sequence:**")
    st.markdown(
        "1. Start on **Normal**\n"
        "2. Switch to **High Bus Demand**\n"
        "3. Observe BUS PRIORITY activation\n"
        "4. Switch to **Emergency Vehicle**\n"
        "5. Observe EMERGENCY CORRIDOR\n"
        "6. Compare metrics on the Metrics tab"
    )
    st.markdown("---")
    st.caption("Fund My Crazy 2026 — hackathon proof-of-concept")
    st.caption("⚠ All results are simulated, not real-world.")
