"""
Self-Reorganizing Roads — Streamlit Dashboard
═════════════════════════════════════════════
Rule-based adaptive road-space allocation prototype.
Fund My Crazy 2026 hackathon proof-of-concept.

Run from the project root:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from src.config.settings import load_config
from src.models import LaneFunction
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


# ── Session state ────────────────────────────────────────────────────────────

if "scenario" not in st.session_state:
    st.session_state.scenario = "normal"


# ── Header ───────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="main-title">🚦 Self-Reorganizing Roads</div>'
    '<div class="sub-title">'
    'Rule-based adaptive allocation of urban road space using real-time traffic demand'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown("---")


# ── Scenario selector ─────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Run Scenario</div>', unsafe_allow_html=True)
s_col1, s_col2, s_col3, s_col4 = st.columns(4)

SCENARIO_META = {
    "normal":           ("🚗 Normal Traffic",   "#3A7BCC", "Baseline — no special conditions"),
    "high_bus":         ("🚌 High Bus Demand",  "#E8A020", "Bus frequency increases → BUS PRIORITY"),
    "emergency":        ("🚨 Emergency Vehicle","#D62728", "Ambulance detected → EMERGENCY CORRIDOR"),
    "pedestrian_surge": ("🚶 Pedestrian Surge", "#8E44AD", "Pedestrian demand spikes → PEDESTRIAN BUFFER"),
}

for col, (key, (label, color, desc)) in zip(
    [s_col1, s_col2, s_col3, s_col4], SCENARIO_META.items()
):
    with col:
        active = st.session_state.scenario == key
        border = f"3px solid {color}" if active else "1px solid #333"
        st.markdown(
            f"<div style='border:{border};border-radius:8px;padding:8px;"
            f"text-align:center;background:#111;'>"
            f"<b style='color:{color};font-size:0.95rem;'>{label}</b><br>"
            f"<span style='color:#888;font-size:0.75rem;'>{desc}</span></div>",
            unsafe_allow_html=True,
        )
        if st.button(f"Run {label.split()[0]}", key=f"btn_{key}", use_container_width=True):
            st.session_state.scenario = key
            st.rerun()

st.markdown("")


# ── Load results ─────────────────────────────────────────────────────────────

config   = _config()
seed     = config["simulation"]["random_seed"]
steps    = config["simulation"]["time_steps"]
scenario = st.session_state.scenario

step_history, baseline_metrics, reorg_metrics, comparison = _run(scenario, seed, steps)

# ── Select representative step — SINGLE SOURCE OF TRUTH ──────────────────────
# Every panel on the dashboard (road config, queues, emergency status, demand,
# decision, allocation path) refers to this ONE step.  There is no split between
# a "display step" for the road view and a "final step" for queue counts.
#
# Selection rule: use the last step in a priority-active state so the visual
# shows the active lane change.  Falls back to the final step for the Normal
# scenario where no priority mode is ever activated.

_PRIORITY_STATES = {"EMERGENCY_ACTIVE", "BUS_PRIORITY_ACTIVE", "PEDESTRIAN_BUFFER_ACTIVE"}

def _selected_step(history: list) -> dict:
    for s in reversed(history):
        if s["system_state"] in _PRIORITY_STATES:
            return s
    return history[-1]

sel         = _selected_step(step_history)
sel_cfg     = sel["config"]
sel_state   = sel["system_state"]
sel_alloc   = sel["allocation"]
sel_demand  = sel["demand"]
sel_prio    = sel["priority"]
sel_snap    = sel["snap"]
sel_traffic = sel["state"]          # TrafficState for this step

state_color    = STATE_COLORS.get(sel_state, "#888")
scenario_label = SCENARIO_META[scenario][0]

# Emergency status — distinguish detection event from corridor activation.
# These can differ: clearance timer keeps the corridor active even when no
# new emergency vehicle arrived in the selected step.
emerg_detected  = sel_traffic.emergency_detected        # new arrival this step
emerg_corridor  = sel_state == "EMERGENCY_ACTIVE"       # system in emergency mode


# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_dash, tab_metrics, tab_guide = st.tabs(
    ["📊 Dashboard", "📈 Metrics & Analysis", "📖 System Guide"]
)


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

with tab_dash:
    left, right = st.columns([3, 2], gap="medium")

    # ── Left ─────────────────────────────────────────────────────────────
    with left:
        # Road visualisation — title shows the selected step number
        st.markdown('<div class="section-head">Road Configuration</div>',
                    unsafe_allow_html=True)
        road_fig = create_road_figure(
            lane_config   = sel_cfg,
            traffic_state = sel_traffic,
            system_state  = sel_state,
            title         = f"Active Configuration — Step {sel['step']}",
        )
        st.plotly_chart(road_fig, use_container_width=True)

        # Lane chips — same step as road visualisation
        st.markdown('<div class="section-head">Lane Assignment</div>',
                    unsafe_allow_html=True)
        lane_cols = st.columns(len(sel_cfg))
        for ci, (lc, func) in enumerate(zip(lane_cols, sel_cfg)):
            f    = LaneFunction(func) if isinstance(func, str) else func
            col  = LANE_COLORS.get(f, "#555")
            lbl  = f.value
            lc.markdown(
                f"<div style='text-align:center;'>"
                f"<div style='font-size:0.75rem;color:#888;'>Lane {ci+1}</div>"
                f"<div class='lane-chip' style='background:{col};'>{lbl}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Traffic state — same step as road visualisation
        st.markdown("")
        st.markdown(
            f'<div class="section-head">Traffic State — Step {sel["step"]}</div>',
            unsafe_allow_html=True,
        )
        q = sel_traffic.queues
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🚗 Cars queued",  f"{q.get('car', 0):.0f}")
        m2.metric("🚌 Buses queued", f"{q.get('bus', 0):.0f}")
        m3.metric("🚲 Bikes queued", f"{q.get('bicycle', 0):.0f}")
        m4.metric("🚶 Peds queued",  f"{q.get('pedestrian', 0):.0f}")

        # Emergency status — two distinct indicators, never contradictory
        st.markdown("")
        st.markdown('<div class="section-head">Emergency Status</div>',
                    unsafe_allow_html=True)
        ec1, ec2 = st.columns(2)
        ec1.metric(
            "🚨 New detection (this step)",
            "YES" if emerg_detected else "NO",
            help="A new emergency vehicle arrived in this simulation step.",
        )
        ec2.metric(
            "🚧 Emergency corridor",
            "ACTIVE" if emerg_corridor else "INACTIVE",
            help=(
                "The system is holding an emergency corridor. "
                "Remains active for the configured clearance window "
                "after the last detection."
            ),
        )

        st.markdown(
            '<p class="disclaimer">'
            '⚠ Simulated result — not a real-world measurement.'
            '</p>',
            unsafe_allow_html=True,
        )

    # ── Right ────────────────────────────────────────────────────────────
    with right:
        # System state badge
        st.markdown('<div class="section-head">System State</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align:center;margin:10px 0 18px 0;'>"
            f"<span class='state-badge' style='background:{state_color};color:white;'>"
            f"{sel_state.replace('_', ' ')}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        # Decision engine
        st.markdown('<div class="section-head">Decision Engine</div>',
                    unsafe_allow_html=True)
        if sel_prio:
            lvl_colors = {
                "SAFETY":            "#D62728",
                "EMERGENCY":         "#D62728",
                "PEDESTRIAN_CYCLIST":"#8E44AD",
                "PUBLIC_TRANSPORT":  "#E8A020",
                "GENERAL_TRAFFIC":   "#3A7BCC",
            }
            lc = lvl_colors.get(sel_prio.priority_level, "#555")
            st.markdown(
                f"<div class='decision-box' style='border-left-color:{lc};'>"
                f"<div style='color:{lc};font-size:0.75rem;font-weight:700;"
                f"letter-spacing:1px;'>PRIORITY LEVEL: {sel_prio.priority_level}</div>"
                f"<div style='font-size:1.0rem;font-weight:700;color:#EAEAEA;margin:6px 0;'>"
                f"{sel_prio.action.replace('_', ' ')}</div>"
                f"<div style='font-size:0.82rem;color:#AAA;line-height:1.5;'>"
                f"{sel_prio.reason}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Demand signals
        st.markdown(
            '<div class="section-head" style="margin-top:10px;">Demand Signals</div>',
            unsafe_allow_html=True,
        )
        if sel_demand:
            thresholds = config["demand"]["thresholds"]
            demand_rows = [
                ("🚗 Car demand",        sel_demand.car_demand,        None),
                ("🚌 Bus demand",        sel_demand.bus_demand,        thresholds["bus_priority"]),
                ("🚲 Bicycle demand",    sel_demand.bicycle_demand,    thresholds["bicycle_priority"]),
                ("🚶 Pedestrian demand", sel_demand.pedestrian_demand, thresholds["pedestrian_priority"]),
            ]
            for dlabel, val, thresh in demand_rows:
                safe_denom = thresh if thresh else max(val, 1)
                pct   = min(1.0, val / safe_denom)
                color = "#D62728" if (thresh and val >= thresh) else "#3A7BCC"
                st.markdown(
                    f"<div style='margin-bottom:6px;'>"
                    f"<div style='display:flex;justify-content:space-between;'>"
                    f"<span style='font-size:0.8rem;color:#CCC;'>{dlabel}</span>"
                    f"<span style='font-size:0.8rem;color:{color};font-weight:700;'>"
                    f"{val:.1f}"
                    + (f" / {thresh:.1f}" if thresh else "")
                    + "</span></div>"
                    f"<div style='background:#222;border-radius:3px;height:6px;margin-top:2px;'>"
                    f"<div style='width:{pct*100:.0f}%;background:{color};"
                    f"height:6px;border-radius:3px;'></div></div></div>",
                    unsafe_allow_html=True,
                )

        # Reconfiguration path
        if sel_alloc and sel_alloc.decision not in ("NO_CHANGE", "MAINTAIN_NORMAL"):
            st.markdown("")
            st.markdown('<div class="section-head">Reconfiguration Path</div>',
                        unsafe_allow_html=True)

            def _cfg_str(cfg):
                return " → ".join(
                    f.value if hasattr(f, "value") else str(f) for f in cfg
                )

            for phase, cfg, color in [
                ("BEFORE",     sel_alloc.previous_config,   "#EEE"),
                ("TRANSITION", sel_alloc.transition_config, "#E67E22"),
                ("AFTER",      sel_alloc.new_config,        "#2ECC71"),
            ]:
                st.markdown(
                    f"<div style='font-size:0.78rem;color:#888;margin-bottom:2px;'>"
                    f"{phase}</div>"
                    f"<div style='font-size:0.8rem;color:{color};font-family:monospace;"
                    f"background:#111;padding:6px 10px;border-radius:4px;"
                    f"margin-bottom:6px;'>{_cfg_str(cfg)}</div>",
                    unsafe_allow_html=True,
                )
            if sel_alloc.expected_effect:
                st.markdown(
                    f"<div style='font-size:0.78rem;color:#888;'>"
                    f"Expected effect: {sel_alloc.expected_effect}</div>",
                    unsafe_allow_html=True,
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — METRICS & ANALYSIS
# ════════════════════════════════════════════════════════════════════════════

with tab_metrics:
    b_snaps = baseline_metrics.snapshots
    r_snaps = reorg_metrics.snapshots

    st.markdown(
        f'<div class="section-head">'
        f'Performance Comparison — {scenario_label} (Simulated)</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "⚠ All values are simulation outputs. "
        "They are NOT real-world measurements or predictions."
    )

    # Summary metrics row
    c1, c2, c3, c4 = st.columns(4)
    b_bus_tt = baseline_metrics.avg_travel_times.get("bus", 2.0)
    r_bus_tt = reorg_metrics.avg_travel_times.get("bus", 2.0)
    b_bus_q  = baseline_metrics.avg_queue_lengths.get("bus", 0.0)
    r_bus_q  = reorg_metrics.avg_queue_lengths.get("bus", 0.0)

    c1.metric(
        "Avg bus travel time",
        f"{r_bus_tt:.2f} min",
        delta=f"{r_bus_tt - b_bus_tt:+.2f} vs baseline",
        delta_color="inverse",
    )
    c2.metric(
        "Avg bus queue",
        f"{r_bus_q:.1f} buses",
        delta=f"{r_bus_q - b_bus_q:+.1f} vs baseline",
        delta_color="inverse",
    )
    # Vehicle throughput — pedestrians excluded
    b_vt = baseline_metrics.avg_vehicle_throughput
    r_vt = reorg_metrics.avg_vehicle_throughput
    c3.metric(
        "Avg vehicle throughput / step",
        f"{r_vt:.1f} vehicles",
        delta=f"{r_vt - b_vt:+.1f} vs baseline",
        help="car + bus + bicycle + emergency. Pedestrians counted separately.",
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
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.queue_lengths.get("bus", 0.0),
                "Bus Queue Length Over Time",
                "Buses waiting",
            ),
            use_container_width=True,
        )
    with ch2:
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.travel_times.get("bus", 2.0),
                "Bus Travel Time Over Time",
                "Minutes",
            ),
            use_container_width=True,
        )

    ch3, ch4 = st.columns(2)
    with ch3:
        # Vehicle throughput chart — label explicitly excludes pedestrians
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.vehicle_throughput,
                "Vehicle Throughput Over Time (excl. pedestrians)",
                "Vehicles / step",
            ),
            use_container_width=True,
        )
    with ch4:
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.queue_lengths.get("pedestrian", 0.0),
                "Pedestrian Queue Over Time",
                "Pedestrians waiting",
            ),
            use_container_width=True,
        )

    # Pedestrian flow chart (separate — not mixed with vehicles)
    st.markdown("")
    col_pf, col_eq = st.columns(2)
    with col_pf:
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.pedestrian_flow,
                "Pedestrian Flow Over Time",
                "Pedestrians / step",
            ),
            use_container_width=True,
        )
    with col_eq:
        st.plotly_chart(
            create_metric_chart(
                b_snaps, r_snaps,
                lambda s: s.emergency_queue,
                "Emergency Vehicle Queue Over Time",
                "Emergency vehicles waiting",
            ),
            use_container_width=True,
        )

    # % change bar
    st.markdown("---")
    bar_cmp = {k: v for k, v in comparison.items() if k != "throughput"}
    if "vehicle_throughput" in comparison:
        bar_cmp["vehicle_throughput"] = comparison["vehicle_throughput"]
    st.plotly_chart(create_comparison_bar(bar_cmp), use_container_width=True)

    # Detailed comparison table
    st.markdown(
        '<div class="section-head">Detailed Comparison Table</div>',
        unsafe_allow_html=True,
    )
    metric_names = {
        "bus_travel_time":    "Bus travel time (min)",
        "car_travel_time":    "Car travel time (min)",
        "bus_queue":          "Bus queue (buses)",
        "bus_delay":          "Bus delay above free-flow (min)",
        "vehicle_throughput": "Vehicle throughput / step (cars+buses+bikes)",
        "pedestrian_queue":   "Pedestrian queue",
        "emergency_queue":    "Emergency vehicle queue",
    }
    rows = []
    for key, label in metric_names.items():
        if key not in comparison:
            continue
        d = comparison[key]
        improved  = d["improved"]
        direction = (
            "✅ Improved"   if improved else
            "➖ Unchanged"  if abs(d["pct_change"]) < 0.5 else
            "⚠️ Trade-off"
        )
        rows.append({
            "Metric":            label,
            "Baseline":          f"{d['baseline']:.2f}",
            "Self-Reorganising": f"{d['optimised']:.2f}",
            "Change":            f"{d['delta']:+.3f}",
            "% Change":          f"{d['pct_change']:+.1f}%",
            "Result":            direction,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("⚠ Simulated results only.")

    # Emergency-specific metrics panel
    st.markdown("---")
    st.markdown(
        '<div class="section-head">Emergency Metrics (Simulated)</div>',
        unsafe_allow_html=True,
    )
    em1, em2, em3, em4 = st.columns(4)
    em1.metric(
        "Avg emergency queue",
        f"{reorg_metrics.avg_emergency_queue:.2f}",
        delta=f"{reorg_metrics.avg_emergency_queue - baseline_metrics.avg_emergency_queue:+.2f} vs baseline",
        delta_color="inverse",
        help="Average number of emergency vehicles waiting, over all steps.",
    )
    em2.metric(
        "Max emergency queue",
        f"{reorg_metrics.max_emergency_queue:.0f}",
        help="Peak emergency vehicle queue observed during the scenario.",
    )
    em3.metric(
        "Total emergency arrivals",
        f"{reorg_metrics.total_emergency_arrivals:.0f}",
        help="Total emergency vehicle arrivals over all simulation steps.",
    )
    em4.metric(
        "Total emergency departures",
        f"{reorg_metrics.total_emergency_departures:.0f}",
        help="Total emergency vehicle departures (cleared) over all simulation steps.",
    )
    st.caption("⚠ Simulated results — not real-world measurements.")

    # Step log
    with st.expander("📋 Simulation step log (first 10 steps)"):
        log_rows = []
        for entry in step_history[:10]:
            sn = entry["snap"]
            log_rows.append({
                "Step":               entry["step"],
                "System state":       entry["system_state"],
                "Config":             " | ".join(
                    (f.value if hasattr(f, "value") else str(f))
                    for f in entry["config"]
                ),
                "Bus queue":          f"{sn.queue_lengths.get('bus', 0):.1f}",
                "Car queue":          f"{sn.queue_lengths.get('car', 0):.1f}",
                "Vehicle throughput": f"{sn.vehicle_throughput:.1f}",
                "Ped flow":           f"{sn.pedestrian_flow:.1f}",
            })
        st.dataframe(
            pd.DataFrame(log_rows), use_container_width=True, hide_index=True
        )
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

### Decision pipeline

```
Traffic State
    ↓
Demand Estimation          arrivals + 0.5 × queue
    ↓
Priority Engine            5-level rule-based hierarchy
    ↓
Safety Constraint Check    hard rules — never overridden
    ↓
Lane Allocator             validates + generates TRANSITION state
    ↓
Simulation Update          queue model + BPR travel time
    ↓
Metrics                    all values from simulation state
```

**1. Traffic sensing** (simulated)
Cameras and inductive loops measure arrivals, queue lengths, and vehicle types.
An emergency transponder signal triggers immediate detection.

**2. Demand estimation**
Each type gets a score: `arrivals + 0.5 × queue_length`.
Higher score = more pressure to serve that type.

**3. Priority engine — 5-level rule-based hierarchy**
```
Level 1: SAFETY            — hard constraints; fall back if violated
Level 2: EMERGENCY         — corridor for emergency vehicles
Level 3: PEDESTRIAN/CYCLIST— protect vulnerable road users during surges
Level 4: PUBLIC TRANSPORT  — bus-priority lane when bus demand is high
Level 5: GENERAL TRAFFIC   — maintain default if no condition is met
```
Each level checked in order. First match wins. Every decision logged with a reason.

> This is a **rule-based adaptive control system**, not a machine-learning
> or AI prediction model. All logic is inspectable in `src/priority/priority_engine.py`.

**4. Safety constraint engine**
Before any reallocation is committed, the safety manager checks:
- At least 1 general-traffic lane must always remain
- EMERGENCY and PEDESTRIAN_BUFFER cannot coexist
- Only one EMERGENCY corridor permitted at a time
- Emergency safely overrides lower-priority modes (BUS_PRIORITY, PEDESTRIAN_BUFFER)

If any check fails → safe fallback: `[GENERAL, GENERAL, GENERAL, BICYCLE]`

**5. Lane allocator + transition state**
Lanes do not instantly change function. A `TRANSITION` state is held for
a configurable duration (default: 2 steps) — representing real-world clearing,
signage update, and traffic rerouting time. During transition, lane capacity
is reduced to 50 %.

**6. Throughput accounting**
- **Vehicle throughput**: car + bus + bicycle + emergency (NOT pedestrians)
- **Pedestrian flow**: pedestrian departures, reported separately
- **Road-user flow**: all types combined; always labelled explicitly

---

### Key modelling assumptions

- Each simulation step = 1 simulated minute
- Vehicle arrivals = Poisson process (deterministic, seed = 42)
- Signal green ratio fixed at 50 %
- Travel time = BPR function of queue/capacity ratio
- Physical road width and signal infrastructure not modelled
- Single road segment; no network effects
        """)

    with right_g:
        st.markdown("### Scenario Quick Reference")
        for key, (label, color, desc) in SCENARIO_META.items():
            cfg_list = {
                "normal":           ["GENERAL", "GENERAL", "GENERAL", "BICYCLE"],
                "high_bus":         ["GENERAL", "BUS_PRIORITY", "GENERAL", "BICYCLE"],
                "emergency":        ["EMERGENCY", "GENERAL", "GENERAL", "BICYCLE"],
                "pedestrian_surge": ["GENERAL", "GENERAL", "PEDESTRIAN_BUFFER", "BICYCLE"],
            }
            target = " | ".join(cfg_list.get(key, []))
            st.markdown(
                f"<div style='border:1px solid {color};border-radius:6px;"
                f"padding:10px;margin-bottom:10px;'>"
                f"<b style='color:{color};'>{label}</b><br>"
                f"<span style='font-size:0.8rem;color:#999;'>{desc}</span><br>"
                f"<span style='font-size:0.75rem;color:#666;font-family:monospace;'>"
                f"Target: {target}</span></div>",
                unsafe_allow_html=True,
            )

        st.markdown("### Thresholds (from settings.yaml)")
        thresholds = config["demand"]["thresholds"]
        st.json({
            "bus_priority":        f"{thresholds['bus_priority']} demand score",
            "bicycle_priority":    f"{thresholds['bicycle_priority']} demand score",
            "pedestrian_priority": f"{thresholds['pedestrian_priority']} demand score",
        })

        st.markdown("### Limitations")
        st.warning(
            "This is a simplified proof-of-concept simulation.\n\n"
            "• Not a calibrated real-world traffic model\n"
            "• Rule-based logic only — no ML or AI prediction\n"
            "• Single road segment; no network effects\n"
            "• No weather, incidents, or special events\n"
            "• Pedestrian/cyclist capacity is approximate\n"
            "• Physical transition costs are simplified\n\n"
            "All metrics shown are **simulated results** — "
            "not real-world measurements or predictions."
        )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🚦 Self-Reorganizing Roads")
    st.markdown(f"**Active scenario:** {scenario_label}")
    st.markdown(
        f"<span class='state-badge' "
        f"style='background:{state_color};color:white;font-size:0.8rem;'>"
        f"{sel_state.replace('_', ' ')}</span>",
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
        "1. **Run Normal** — observe baseline GENERAL configuration\n"
        "2. **Run High Bus Demand** — observe BUS PRIORITY lane activation\n"
        "3. **Run Emergency** — observe EMERGENCY CORRIDOR creation\n"
        "4. **Run Pedestrian Surge** — observe PEDESTRIAN BUFFER allocation\n"
        "5. **Metrics tab** — compare each scenario against its own baseline\n\n"
        "_Each scenario is an independent simulation run. "
        "They do not share state._"
    )
    st.markdown("---")
    st.caption("Fund My Crazy 2026 — hackathon proof-of-concept")
    st.caption("⚠ All results are simulated, not real-world.")