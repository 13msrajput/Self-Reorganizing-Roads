"""
Core domain models for Self-Reorganizing Roads.

All dataclasses here represent simulation state or decisions.
Nothing in this file is hard-coded to a specific outcome;
values are produced by the simulation pipeline at runtime.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Enumerations ────────────────────────────────────────────────────────────


class LaneFunction(str, Enum):
    """zz
    Functions that a physical lane can be assigned to.

    The physical lane does NOT move — only its assigned function changes.
    TRANSITION is a safety state during reconfiguration: reduced capacity,
    no vehicles committed to the new function yet.
    """

    GENERAL = "GENERAL"
    BUS_PRIORITY = "BUS_PRIORITY"
    EMERGENCY = "EMERGENCY"
    BICYCLE = "BICYCLE"
    PEDESTRIAN_BUFFER = "PEDESTRIAN_BUFFER"
    TRANSITION = "TRANSITION"
    CLOSED = "CLOSED"


class ScenarioType(str, Enum):
    """Available demonstration scenarios."""

    NORMAL = "normal"
    HIGH_BUS = "high_bus"
    EMERGENCY = "emergency"
    PEDESTRIAN_SURGE = "pedestrian_surge"


# ── Simulation state ─────────────────────────────────────────────────────────


@dataclass
class TrafficState:
    """
    Snapshot of simulated traffic conditions at one time step.

    All values are outputs of the traffic simulator.
    Label as "Simulated result — not a real-world measurement."
    """

    timestamp: int
    arrivals: Dict[str, float]  # vehicles arriving this step, by type
    queues: Dict[str, float]  # vehicles waiting, by type
    departures: Dict[str, float]  # vehicles cleared this step, by type
    occupancy: float  # overall lane occupancy 0.0–1.0
    emergency_detected: bool = False

    def total_queued(self) -> float:
        return sum(self.queues.values())


# ── Demand estimation ────────────────────────────────────────────────────────


@dataclass
class DemandEstimate:
    """
    Processed demand signals derived from TrafficState.

    Combines arrival rate and queue pressure into per-type demand scores.
    Scores are not physical units; they are relative demand indicators.
    """

    car_demand: float
    bus_demand: float
    bicycle_demand: float
    pedestrian_demand: float
    emergency_flag: bool
    dominant_demand: str  # vehicle type with highest demand score

    def to_dict(self) -> Dict:
        return {
            "car": round(self.car_demand, 2),
            "bus": round(self.bus_demand, 2),
            "bicycle": round(self.bicycle_demand, 2),
            "pedestrian": round(self.pedestrian_demand, 2),
            "emergency": self.emergency_flag,
            "dominant": self.dominant_demand,
        }


# ── Safety ───────────────────────────────────────────────────────────────────


@dataclass
class SafetyAssessment:
    """Result of a safety-constraint check on a proposed lane configuration."""

    is_safe: bool
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ── Priority decision ─────────────────────────────────────────────────────────


@dataclass
class PriorityDecision:
    """
    Output of the priority engine — what action the system should take.

    The target_config is a proposal only; the lane allocator validates it
    against safety constraints before committing.
    """

    action: str  # e.g. "ACTIVATE_BUS_PRIORITY"
    priority_level: str  # e.g. "PUBLIC_TRANSPORT"
    reason: str  # human-readable explanation
    target_config: Optional[List[LaneFunction]] = None
    confidence: float = 1.0


# ── Allocation decision ───────────────────────────────────────────────────────


@dataclass
class AllocationDecision:
    """
    Full allocation decision including before / transition / after configs.

    previous_config  — configuration before this decision
    transition_config — lanes in TRANSITION state during reconfiguration
    new_config       — configuration after transition completes
    """

    previous_config: List[LaneFunction]
    transition_config: List[LaneFunction]
    new_config: List[LaneFunction]
    decision: str
    reason: str
    expected_effect: str
    is_safe: bool
    safety_notes: List[str] = field(default_factory=list)


# ── Metrics ──────────────────────────────────────────────────────────────────


@dataclass
class MetricsSnapshot:
    """
    Per-step performance metrics derived from simulation state.

    All values are computed from the simulation — never hard-coded.
    Label as "Simulated result — not a real-world measurement."
    """

    timestamp: int
    travel_times: Dict[str, float]  # minutes, by vehicle type
    queue_lengths: Dict[str, float]  # vehicle count, by type
    throughput: Dict[str, float]  # vehicles cleared, by type
    total_throughput: float
    bus_delay: float  # minutes above free-flow for buses
    lane_config: Optional[List[LaneFunction]] = None
    system_state: str = "NORMAL"


@dataclass
class ScenarioMetrics:
    """Aggregated metrics over a complete scenario run."""

    scenario_name: str
    avg_travel_times: Dict[str, float] = field(default_factory=dict)
    avg_queue_lengths: Dict[str, float] = field(default_factory=dict)
    avg_throughput: float = 0.0
    total_vehicles_served: float = 0.0
    avg_bus_delay: float = 0.0
    snapshots: List[MetricsSnapshot] = field(default_factory=list)
