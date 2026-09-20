"""
Demand estimator.

Converts raw TrafficState into normalised demand signals that the
priority engine can act on.

The demand score for each vehicle type combines:
  • arrival rate  — immediate pressure
  • queue length  — accumulated unserved demand

demand = arrivals + QUEUE_WEIGHT * queue_length

Thresholds that trigger priority changes are configured in settings.yaml,
not hard-coded here, so they can be adjusted without changing code.
"""

from __future__ import annotations
from src.models import TrafficState, DemandEstimate

QUEUE_WEIGHT = 0.5  # weight applied to queue length in demand scoring


class DemandEstimator:
    """
    Estimates per-type demand from a single TrafficState snapshot.

    All thresholds read from config so that judges / reviewers can
    adjust them without modifying source code.
    """

    def __init__(self, config: dict) -> None:
        self.config     = config
        self.thresholds = config["demand"]["thresholds"]

    # ------------------------------------------------------------------
    # Core estimation
    # ------------------------------------------------------------------

    def estimate(self, state: TrafficState) -> DemandEstimate:
        """
        Produce a DemandEstimate from the current TrafficState.

        Demand = arrivals_this_step + QUEUE_WEIGHT × current_queue
        This rewards both fast response (arrivals) and accumulated pressure (queue).
        """
        a = state.arrivals
        q = state.queues

        car_demand        = a.get("car",        0.0) + QUEUE_WEIGHT * q.get("car",        0.0)
        bus_demand        = a.get("bus",        0.0) + QUEUE_WEIGHT * q.get("bus",        0.0)
        bicycle_demand    = a.get("bicycle",    0.0) + QUEUE_WEIGHT * q.get("bicycle",    0.0)
        pedestrian_demand = a.get("pedestrian", 0.0) + QUEUE_WEIGHT * q.get("pedestrian", 0.0)

        demands = {
            "car":        car_demand,
            "bus":        bus_demand,
            "bicycle":    bicycle_demand,
            "pedestrian": pedestrian_demand,
        }
        dominant = max(demands, key=lambda k: demands[k])

        return DemandEstimate(
            car_demand        = round(car_demand,        2),
            bus_demand        = round(bus_demand,        2),
            bicycle_demand    = round(bicycle_demand,    2),
            pedestrian_demand = round(pedestrian_demand, 2),
            emergency_flag    = state.emergency_detected,
            dominant_demand   = dominant,
        )

    # ------------------------------------------------------------------
    # Threshold checks (used by PriorityEngine)
    # ------------------------------------------------------------------

    def is_bus_priority_warranted(self, demand: DemandEstimate) -> bool:
        """Return True if bus demand score exceeds the configured threshold."""
        return demand.bus_demand >= self.thresholds["bus_priority"]

    def is_bicycle_priority_warranted(self, demand: DemandEstimate) -> bool:
        """Return True if bicycle demand score exceeds the configured threshold."""
        return demand.bicycle_demand >= self.thresholds["bicycle_priority"]

    def is_pedestrian_surge(self, demand: DemandEstimate) -> bool:
        """Return True if pedestrian demand score exceeds the configured threshold."""
        return demand.pedestrian_demand >= self.thresholds["pedestrian_priority"]
