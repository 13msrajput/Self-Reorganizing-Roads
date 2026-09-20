"""
Simplified macroscopic traffic simulation.

MODELLING ASSUMPTIONS
─────────────────────
• Each time step represents 1 simulated minute.
• Vehicle arrivals are sampled from a Poisson distribution with a fixed
  random seed — results are therefore fully reproducible.
• Queue dynamics: Q(t+1) = Q(t) + arrivals(t) − departures(t)
• Departure rate is bounded by effective lane capacity (see below).
• Signal green-ratio is fixed at 0.5 (simplified cycle model).
• Travel time: free_flow + congestion_delay term proportional to queue/capacity.
• This is NOT a calibrated real-world traffic model. It is sufficient to
  demonstrate the value of adaptive lane allocation in a proof-of-concept.
"""

from __future__ import annotations
import numpy as np
from typing import Dict, List

from src.models import LaneFunction, TrafficState

# ---------------------------------------------------------------------------
# Capacity matrix
# Fraction of BASE_CAPACITY[vehicle_type] that each lane function provides.
# Multiplied by GREEN_RATIO to get effective throughput per step.
# ---------------------------------------------------------------------------

LANE_CAPACITY_MATRIX: Dict[LaneFunction, Dict[str, float]] = {
    LaneFunction.GENERAL: {
        "car": 1.00,  # full car throughput
        "bus": 0.25,  # buses can use general but lower priority/spacing
        "bicycle": 0.00,  # bicycles use dedicated lanes only
        "pedestrian": 0.10,  # minor share at signal-controlled crossings
        "emergency": 0.50,  # emergency can push through, not ideal
    },
    LaneFunction.BUS_PRIORITY: {
        "car": 0.40,  # cars tolerated but yielded
        "bus": 1.00,  # full dedicated bus throughput
        "bicycle": 0.00,
        "pedestrian": 0.10,
        "emergency": 0.50,
    },
    LaneFunction.EMERGENCY: {
        "car": 0.00,  # cleared entirely
        "bus": 0.00,
        "bicycle": 0.00,
        "pedestrian": 0.00,
        "emergency": 1.00,  # dedicated corridor
    },
    LaneFunction.BICYCLE: {
        "car": 0.00,
        "bus": 0.00,
        "bicycle": 1.00,  # full dedicated throughput
        "pedestrian": 0.20,  # shared path (cyclists and pedestrians co-exist)
        "emergency": 0.00,
    },
    LaneFunction.PEDESTRIAN_BUFFER: {
        "car": 0.00,
        "bus": 0.00,
        "bicycle": 0.40,  # wide shared path
        "pedestrian": 1.00,  # full protected pedestrian throughput
        "emergency": 0.00,
    },
    LaneFunction.TRANSITION: {
        "car": 0.50,  # reduced capacity during reconfiguration
        "bus": 0.50,
        "bicycle": 0.50,
        "pedestrian": 0.50,
        "emergency": 0.50,
    },
    LaneFunction.CLOSED: {
        "car": 0.00,
        "bus": 0.00,
        "bicycle": 0.00,
        "pedestrian": 0.00,
        "emergency": 0.00,
    },
}

# Base throughput capacity per lane per minute (before green-ratio).
# Vehicles/min for a dedicated lane of that function.
BASE_CAPACITY: Dict[str, float] = {
    "car": 20.0,
    "bus": 8.0,
    "bicycle": 30.0,
    "pedestrian": 50.0,
    "emergency": 2.0,
}

VEHICLE_TYPES = ["car", "bus", "bicycle", "pedestrian", "emergency"]

# Signal green phase fraction (simplified: 50 % of cycle is green).
GREEN_RATIO = 0.5


class TrafficSimulator:
    """
    Macroscopic queue-based traffic simulator.

    Usage
    ─────
    sim = TrafficSimulator(config, seed=42)
    sim.reset("high_bus")
    for step in range(30):
        state = sim.step(current_lane_config)
        cap   = sim.compute_effective_capacity(current_lane_config)
    """

    def __init__(self, config: dict, seed: int = 42) -> None:
        self.config = config
        self.seed = seed
        self.rng: np.random.Generator = np.random.default_rng(seed)
        self.queues: Dict[str, float] = {vt: 0.0 for vt in VEHICLE_TYPES}
        self.timestamp = 0
        self.scenario = "normal"
        self.arrival_rates: Dict[str, float] = {}
        self._load_scenario("normal")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, scenario: str = "normal") -> None:
        """Reset simulator state for a fresh scenario run."""
        self.rng = np.random.default_rng(self.seed)
        self.queues = {vt: 0.0 for vt in VEHICLE_TYPES}
        self.timestamp = 0
        self.scenario = scenario
        self._load_scenario(scenario)

    def step(self, lane_config: List[LaneFunction]) -> TrafficState:
        """
        Advance simulation by one time step with the given lane configuration.

        Returns the TrafficState snapshot for this step.
        """
        self.timestamp += 1

        # --- Sample arrivals (Poisson) ---
        arrivals: Dict[str, float] = {}
        for vt in VEHICLE_TYPES:
            rate = max(0.0, self.arrival_rates.get(vt, 0.0))
            arrivals[vt] = float(self.rng.poisson(rate))

        emergency_detected = arrivals.get("emergency", 0.0) > 0.0

        # --- Compute effective capacities ---
        capacity = self.compute_effective_capacity(lane_config)

        # --- Update queues ---
        departures: Dict[str, float] = {}
        new_queues: Dict[str, float] = {}
        for vt in VEHICLE_TYPES:
            available = self.queues[vt] + arrivals[vt]
            cap = capacity.get(vt, 0.0)
            dep = min(available, cap)
            departures[vt] = dep
            new_queues[vt] = max(0.0, available - dep)

        self.queues = new_queues

        # Occupancy: rough normalised indicator (not a physical density)
        total_cap = sum(capacity.values()) + 1e-6
        occupancy = min(1.0, sum(new_queues.values()) / (total_cap * 2.0))

        return TrafficState(
            timestamp=self.timestamp,
            arrivals=arrivals,
            queues=dict(new_queues),
            departures=departures,
            occupancy=round(occupancy, 3),
            emergency_detected=emergency_detected,
        )

    def compute_effective_capacity(
        self, lane_config: List[LaneFunction]
    ) -> Dict[str, float]:
        """
        Compute effective departure capacity (vehicles/minute) per vehicle type
        for the given lane configuration.

        effective_cap[vt] = Σ_lanes  BASE_CAPACITY[vt] * multiplier[func][vt] * GREEN_RATIO
        """
        capacity: Dict[str, float] = {vt: 0.0 for vt in VEHICLE_TYPES}
        for lane_func in lane_config:
            mult_row = LANE_CAPACITY_MATRIX.get(lane_func, {})
            for vt in VEHICLE_TYPES:
                mult = mult_row.get(vt, 0.0)
                capacity[vt] += BASE_CAPACITY[vt] * mult * GREEN_RATIO
        return capacity

    def compute_travel_time(
        self, vehicle_type: str, capacity: Dict[str, float]
    ) -> float:
        """
        Approximate travel time for a vehicle type (minutes).

        travel_time = free_flow_time × (1 + DELAY_FACTOR × queue/capacity)

        This is a simplified BPR-style function, NOT a calibrated model.
        """
        free_flow = self.config["simulation"]["road"]["free_flow_time"]
        queue = self.queues.get(vehicle_type, 0.0)
        cap = max(capacity.get(vehicle_type, 0.0), 1e-6)
        congestion = queue / cap
        return round(free_flow * (1.0 + 0.15 * congestion), 3)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_scenario(self, scenario: str) -> None:
        rates = self.config["simulation"]["arrival_rates"]
        self.arrival_rates = rates.get(scenario, rates["normal"])
