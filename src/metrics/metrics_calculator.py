"""
Metrics calculator.

IMPORTANT: All metrics are computed from simulation state at runtime.
No values in this module are hard-coded. Results are labelled
"Simulated result — not a real-world measurement" throughout the dashboard.

Throughput definitions
──────────────────────
vehicle_throughput  = car + bus + bicycle + emergency  (NOT pedestrian)
pedestrian_flow     = pedestrian departures
motor_throughput    = car + bus + emergency
road_user_flow      = all departures combined  (label explicitly — ≠ "vehicle throughput")

Pedestrians are never counted as vehicles in vehicle_throughput.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List

from src.models import LaneFunction, MetricsSnapshot, ScenarioMetrics, TrafficState

# BPR-style congestion delay coefficient (dimensionless).
# travel_time = free_flow × (1 + BPR_ALPHA × (queue/capacity)^BPR_BETA)
BPR_ALPHA = 0.15
BPR_BETA = 1.0  # linear for simplicity (full BPR uses 4.0)

ALL_TYPES = ["car", "bus", "bicycle", "pedestrian", "emergency"]
VEHICLE_TYPES = ["car", "bus", "bicycle", "emergency"]  # excludes pedestrians
MOTOR_TYPES = ["car", "bus", "emergency"]  # motorised only


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
        self.config = config
        self.free_flow = config["simulation"]["road"]["free_flow_time"]
        self.snapshots: List[MetricsSnapshot] = []

    def reset(self) -> None:
        """Clear all recorded snapshots."""
        self.snapshots = []

    # ------------------------------------------------------------------
    # Per-step recording
    # ------------------------------------------------------------------

    def record(
        self,
        state: TrafficState,
        capacity: Dict[str, float],
        lane_config: List[LaneFunction],
        system_state: str = "NORMAL",
    ) -> MetricsSnapshot:
        """
        Compute and store metrics for one simulation step.

        travel_time is calculated from the BPR function applied to
        the current queue/capacity ratio — NOT from a lookup table.
        """
        travel_times: Dict[str, float] = {}
        for vt in ALL_TYPES:
            q = state.queues.get(vt, 0.0)
            cap = max(capacity.get(vt, 0.0), 1e-6)
            ratio = q / cap
            tt = self.free_flow * (1.0 + BPR_ALPHA * (ratio**BPR_BETA))
            travel_times[vt] = round(tt, 3)

        deps = state.departures

        # ── Throughput breakdowns ────────────────────────────────────────
        road_user_flow = round(sum(deps.get(vt, 0.0) for vt in ALL_TYPES), 2)
        vehicle_throughput = round(sum(deps.get(vt, 0.0) for vt in VEHICLE_TYPES), 2)
        pedestrian_flow = round(deps.get("pedestrian", 0.0), 2)
        motor_throughput = round(sum(deps.get(vt, 0.0) for vt in MOTOR_TYPES), 2)

        bus_tt = travel_times.get("bus", self.free_flow)
        bus_delay = max(0.0, round(bus_tt - self.free_flow, 3))

        snap = MetricsSnapshot(
            timestamp=state.timestamp,
            travel_times=travel_times,
            queue_lengths=dict(state.queues),
            throughput=dict(deps),
            road_user_flow=road_user_flow,
            bus_delay=bus_delay,
            vehicle_throughput=vehicle_throughput,
            pedestrian_flow=pedestrian_flow,
            motor_throughput=motor_throughput,
            # Emergency-specific
            emergency_queue=round(state.queues.get("emergency", 0.0), 2),
            emergency_arrivals=round(state.arrivals.get("emergency", 0.0), 2),
            emergency_departures=round(deps.get("emergency", 0.0), 2),
            lane_config=list(lane_config),
            system_state=system_state,
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
        avg_q: Dict[str, float] = {}

        for vt in ALL_TYPES:
            tts = [s.travel_times.get(vt, self.free_flow) for s in self.snapshots]
            queues = [s.queue_lengths.get(vt, 0.0) for s in self.snapshots]
            avg_tt[vt] = round(float(np.mean(tts)), 3)
            avg_q[vt] = round(float(np.mean(queues)), 2)

        avg_ruf = round(float(np.mean([s.road_user_flow for s in self.snapshots])), 2)
        avg_vt = round(
            float(np.mean([s.vehicle_throughput for s in self.snapshots])), 2
        )
        avg_pf = round(float(np.mean([s.pedestrian_flow for s in self.snapshots])), 2)
        avg_mt = round(float(np.mean([s.motor_throughput for s in self.snapshots])), 2)
        total_srv = round(float(sum(s.vehicle_throughput for s in self.snapshots)), 1)
        avg_bd = round(float(np.mean([s.bus_delay for s in self.snapshots])), 3)

        # Emergency aggregates
        avg_eq = round(float(np.mean([s.emergency_queue for s in self.snapshots])), 2)
        max_eq = round(float(max(s.emergency_queue for s in self.snapshots)), 2)
        tot_ea = round(float(sum(s.emergency_arrivals for s in self.snapshots)), 1)
        tot_ed = round(float(sum(s.emergency_departures for s in self.snapshots)), 1)

        return ScenarioMetrics(
            scenario_name=scenario_name,
            avg_travel_times=avg_tt,
            avg_queue_lengths=avg_q,
            avg_road_user_flow=avg_ruf,
            avg_vehicle_throughput=avg_vt,
            avg_pedestrian_flow=avg_pf,
            avg_motor_throughput=avg_mt,
            total_vehicles_served=total_srv,
            avg_bus_delay=avg_bd,
            avg_emergency_queue=avg_eq,
            max_emergency_queue=max_eq,
            total_emergency_arrivals=tot_ea,
            total_emergency_departures=tot_ed,
            snapshots=list(self.snapshots),
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(
        baseline: ScenarioMetrics,
        optimised: ScenarioMetrics,
    ) -> Dict:
        """
        Produce a comparison dict with delta and % change for key metrics.

        A negative pct_change for travel time / queue / delay = improvement.
        A positive pct_change for throughput = improvement.

        These are simulation-derived comparisons, not real-world guarantees.
        Throughput comparison uses vehicle_throughput (not road_user_flow)
        so pedestrians are not counted as vehicles.
        """

        def _delta(base: float, opt: float, higher_is_better: bool = False) -> Dict:
            delta = round(opt - base, 3)
            pct = round(((opt - base) / (base + 1e-9)) * 100.0, 1)
            improved = (pct > 0) if higher_is_better else (pct < 0)
            return {
                "baseline": round(base, 3),
                "optimised": round(opt, 3),
                "delta": delta,
                "pct_change": pct,
                "improved": improved,
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
            # Uses vehicle_throughput — pedestrians excluded
            "vehicle_throughput": _delta(
                baseline.avg_vehicle_throughput,
                optimised.avg_vehicle_throughput,
                higher_is_better=True,
            ),
            "bus_delay": _delta(
                baseline.avg_bus_delay,
                optimised.avg_bus_delay,
            ),
            "emergency_queue": _delta(
                baseline.avg_emergency_queue,
                optimised.avg_emergency_queue,
            ),
        }
