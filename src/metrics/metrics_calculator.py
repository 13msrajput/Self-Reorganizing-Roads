"""
Metrics calculator.

IMPORTANT: All metrics are computed from simulation state at runtime.
No values in this module are hard-coded. Results are labelled
"Simulated result — not a real-world measurement" throughout the dashboard.

Metrics computed
─────────────────
• travel_time[vehicle_type]  — minutes (free-flow + congestion term)
• queue_lengths[vehicle_type] — vehicles waiting
• throughput[vehicle_type]   — vehicles cleared per step
• total_throughput           — sum across all types
• bus_delay                  — minutes above free-flow for buses
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List, Optional

from src.models import (
    LaneFunction, MetricsSnapshot, ScenarioMetrics, TrafficState
)

# BPR-style congestion delay coefficient (dimensionless).
# travel_time = free_flow × (1 + BPR_ALPHA × (queue/capacity)^BPR_BETA)
BPR_ALPHA = 0.15
BPR_BETA  = 1.0   # linear for simplicity (full BPR uses 4.0)

VEHICLE_TYPES = ["car", "bus", "bicycle", "pedestrian", "emergency"]


class MetricsCalculator:
    """
    Records per-step metrics and computes aggregate summaries.

    Usage
    ─────
    calc = MetricsCalculator(config)
    for step in range(N):
        snap = calc.record(state, capacity, lane_config, system_state)
    summary = calc.get_summary("scenario_name")
    """

    def __init__(self, config: dict) -> None:
        self.config     = config
        self.free_flow  = config["simulation"]["road"]["free_flow_time"]
        self.snapshots: List[MetricsSnapshot] = []

    def reset(self) -> None:
        """Clear all recorded snapshots."""
        self.snapshots = []

    # ------------------------------------------------------------------
    # Per-step recording
    # ------------------------------------------------------------------

    def record(
        self,
        state:        TrafficState,
        capacity:     Dict[str, float],
        lane_config:  List[LaneFunction],
        system_state: str = "NORMAL",
    ) -> MetricsSnapshot:
        """
        Compute and store metrics for one simulation step.

        travel_time is calculated from the BPR function applied to
        the current queue/capacity ratio — NOT from a lookup table.
        """
        travel_times: Dict[str, float] = {}
        for vt in VEHICLE_TYPES:
            q   = state.queues.get(vt, 0.0)
            cap = max(capacity.get(vt, 0.0), 1e-6)
            ratio = q / cap
            tt = self.free_flow * (1.0 + BPR_ALPHA * (ratio ** BPR_BETA))
            travel_times[vt] = round(tt, 3)

        total_tp = sum(state.departures.values())
        bus_tt   = travel_times.get("bus", self.free_flow)
        bus_delay = max(0.0, round(bus_tt - self.free_flow, 3))

        snap = MetricsSnapshot(
            timestamp        = state.timestamp,
            travel_times     = travel_times,
            queue_lengths    = dict(state.queues),
            throughput       = dict(state.departures),
            total_throughput = round(total_tp, 2),
            bus_delay        = bus_delay,
            lane_config      = list(lane_config),
            system_state     = system_state,
        )
        self.snapshots.append(snap)
        return snap

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_summary(self, scenario_name: str = "") -> ScenarioMetrics:
        """Aggregate all recorded snapshots into a ScenarioMetrics summary."""
        if not self.snapshots:
            return ScenarioMetrics(scenario_name=scenario_name)

        avg_tt: Dict[str, float] = {}
        avg_q:  Dict[str, float] = {}

        for vt in VEHICLE_TYPES:
            tts    = [s.travel_times.get(vt, self.free_flow) for s in self.snapshots]
            queues = [s.queue_lengths.get(vt, 0.0)           for s in self.snapshots]
            avg_tt[vt] = round(float(np.mean(tts)),    3)
            avg_q[vt]  = round(float(np.mean(queues)), 2)

        avg_tp      = round(float(np.mean([s.total_throughput for s in self.snapshots])), 2)
        total_served = round(float(sum(s.total_throughput for s in self.snapshots)), 1)
        avg_bus_delay = round(float(np.mean([s.bus_delay for s in self.snapshots])),  3)

        return ScenarioMetrics(
            scenario_name        = scenario_name,
            avg_travel_times     = avg_tt,
            avg_queue_lengths    = avg_q,
            avg_throughput       = avg_tp,
            total_vehicles_served = total_served,
            avg_bus_delay        = avg_bus_delay,
            snapshots            = list(self.snapshots),
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(
        baseline:  ScenarioMetrics,
        optimised: ScenarioMetrics,
    ) -> Dict:
        """
        Produce a comparison dict with delta and % change for key metrics.

        A negative pct_change for travel time / queue / delay = improvement.
        A positive pct_change for throughput = improvement.

        These are simulation-derived comparisons, not real-world guarantees.
        """

        def _delta(base: float, opt: float, higher_is_better: bool = False) -> Dict:
            delta      = round(opt - base, 3)
            pct        = round(((opt - base) / (base + 1e-9)) * 100.0, 1)
            improved   = (pct > 0) if higher_is_better else (pct < 0)
            return {
                "baseline":  round(base, 3),
                "optimised": round(opt, 3),
                "delta":     delta,
                "pct_change": pct,
                "improved":  improved,
            }

        return {
            "bus_travel_time": _delta(
                baseline.avg_travel_times.get("bus", 2.0),
                optimised.avg_travel_times.get("bus", 2.0),
            ),
            "car_travel_time": _delta(
                baseline.avg_travel_times.get("car", 2.0),
                optimised.avg_travel_times.get("car", 2.0),
            ),
            "bus_queue": _delta(
                baseline.avg_queue_lengths.get("bus", 0.0),
                optimised.avg_queue_lengths.get("bus", 0.0),
            ),
            "pedestrian_queue": _delta(
                baseline.avg_queue_lengths.get("pedestrian", 0.0),
                optimised.avg_queue_lengths.get("pedestrian", 0.0),
            ),
            "throughput": _delta(
                baseline.avg_throughput,
                optimised.avg_throughput,
                higher_is_better=True,
            ),
            "bus_delay": _delta(
                baseline.avg_bus_delay,
                optimised.avg_bus_delay,
            ),
        }
