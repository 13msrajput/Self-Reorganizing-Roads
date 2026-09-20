"""
Priority engine.

HIERARCHY (highest → lowest)
─────────────────────────────
1. SAFETY             — hard constraints; reverts to fallback if violated
2. EMERGENCY          — protect life; create corridor for emergency vehicles
3. PEDESTRIAN/CYCLIST — protect vulnerable road users during surges
4. PUBLIC TRANSPORT   — bus-priority lane when bus demand is high
5. GENERAL TRAFFIC    — maintain or revert to default configuration

Each level is evaluated in order. The first matching condition produces
the decision. This makes the decision process fully transparent and auditable.

All thresholds come from config (settings.yaml), not from this file.
"""

from __future__ import annotations
from typing import List

from src.models import (
    DemandEstimate, LaneFunction, PriorityDecision, SafetyAssessment
)
from src.demand.demand_estimator import DemandEstimator


class PriorityEngine:
    """
    Hierarchical, rule-based priority decision engine.

    Produces a PriorityDecision with a human-readable reason for every call.
    No machine-learning model is used; the decision logic is fully inspectable.
    """

    def __init__(self, config: dict, demand_estimator: DemandEstimator) -> None:
        self.config            = config
        self.demand_estimator  = demand_estimator
        self.num_lanes         = config["simulation"]["road"]["num_lanes"]
        self._thresholds       = config["demand"]["thresholds"]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def decide(
        self,
        demand:           DemandEstimate,
        current_config:   List[LaneFunction],
        safety_assessment: SafetyAssessment,
    ) -> PriorityDecision:
        """
        Evaluate demand and safety state; return the highest-priority action.

        The returned PriorityDecision contains:
        • action       — what to do
        • priority_level — which tier of the hierarchy triggered this
        • reason       — plain-English explanation shown in the dashboard
        • target_config — proposed lane configuration (validated by allocator)
        """

        # ── LEVEL 1: SAFETY ──────────────────────────────────────────────
        if not safety_assessment.is_safe:
            return PriorityDecision(
                action         = "ENFORCE_SAFE_FALLBACK",
                priority_level = "SAFETY",
                reason         = (
                    "Safety constraint violated in current configuration. "
                    f"Violations: {'; '.join(safety_assessment.violations)} "
                    "Reverting to safe default configuration."
                ),
                target_config  = None,   # SafetyManager provides the fallback
                confidence     = 1.0,
            )

        # ── LEVEL 2: EMERGENCY VEHICLES ──────────────────────────────────
        if demand.emergency_flag:
            target = self._build_emergency_config(current_config)
            return PriorityDecision(
                action         = "ACTIVATE_EMERGENCY_CORRIDOR",
                priority_level = "EMERGENCY",
                reason         = (
                    "Emergency vehicle detected. "
                    "Creating protected emergency corridor on lane 1. "
                    "All other traffic directed to remaining lanes. "
                    "Corridor maintained for clearance period after detection."
                ),
                target_config  = target,
                confidence     = 0.95,
            )

        # ── LEVEL 3: PEDESTRIAN / CYCLIST SURGE ──────────────────────────
        if self.demand_estimator.is_pedestrian_surge(demand):
            target = self._build_pedestrian_config(current_config)
            return PriorityDecision(
                action         = "ACTIVATE_PEDESTRIAN_BUFFER",
                priority_level = "PEDESTRIAN_CYCLIST",
                reason         = (
                    f"Pedestrian demand score {demand.pedestrian_demand:.1f} exceeds "
                    f"threshold {self._thresholds['pedestrian_priority']:.1f}. "
                    "Allocating additional protected space for pedestrians and cyclists. "
                    "Vehicle capacity temporarily reduced on one lane."
                ),
                target_config  = target,
                confidence     = 0.85,
            )

        # ── LEVEL 4: PUBLIC TRANSPORT ─────────────────────────────────────
        already_bus = LaneFunction.BUS_PRIORITY in current_config
        # Hysteresis: once activated, only deactivate when demand falls to 60 % of
        # the activation threshold — prevents oscillation near the threshold.
        bus_threshold = self._thresholds["bus_priority"] * (0.6 if already_bus else 1.0)

        if demand.bus_demand >= bus_threshold:
            target = self._build_bus_priority_config(current_config)
            return PriorityDecision(
                action         = "ACTIVATE_BUS_PRIORITY",
                priority_level = "PUBLIC_TRANSPORT",
                reason         = (
                    f"Bus demand score {demand.bus_demand:.1f} exceeds "
                    f"threshold {self._thresholds['bus_priority']:.1f}. "
                    "Allocating dedicated bus-priority lane to reduce public-transport delay. "
                    "General traffic retains remaining lanes."
                ),
                target_config  = target,
                confidence     = 0.90,
            )

        # ── LEVEL 5: GENERAL TRAFFIC — maintain / revert to normal ────────
        already_ped = LaneFunction.PEDESTRIAN_BUFFER in current_config
        ped_threshold = self._thresholds["pedestrian_priority"] * (0.6 if already_ped else 1.0)

        if demand.pedestrian_demand >= ped_threshold and already_ped:
            # Maintain pedestrian buffer while demand remains elevated
            return PriorityDecision(
                action         = "ACTIVATE_PEDESTRIAN_BUFFER",
                priority_level = "PEDESTRIAN_CYCLIST",
                reason         = (
                    f"Pedestrian demand score {demand.pedestrian_demand:.1f} remains above "
                    f"deactivation level {ped_threshold:.1f}. Maintaining pedestrian buffer."
                ),
                target_config  = list(current_config),
                confidence     = 0.85,
            )

        return PriorityDecision(
            action         = "MAINTAIN_NORMAL",
            priority_level = "GENERAL_TRAFFIC",
            reason         = (
                "No special-priority condition detected. "
                "All demand scores are within normal parameters. "
                "Maintaining general-purpose lane configuration."
            ),
            target_config  = self._build_normal_config(),
            confidence     = 0.95,
        )

    # ------------------------------------------------------------------
    # Configuration builders
    # ------------------------------------------------------------------

    def _build_normal_config(self) -> List[LaneFunction]:
        """Default: (n-1) general lanes + 1 bicycle lane."""
        n = self.num_lanes
        return [LaneFunction.GENERAL] * (n - 1) + [LaneFunction.BICYCLE]

    def _build_bus_priority_config(
        self, current: List[LaneFunction]
    ) -> List[LaneFunction]:
        """
        Convert one GENERAL lane to BUS_PRIORITY.

        If BUS_PRIORITY already exists in the configuration, maintain it
        rather than adding a second one (which would cause instability).

        Preference: use the second lane (index 1) to minimise disruption
        to the kerbside lane (index 0, often used for turning traffic).
        """
        # If already in bus-priority mode, hold the current configuration.
        if LaneFunction.BUS_PRIORITY in current:
            return list(current)

        config = list(current)
        n = len(config)
        # Prefer lane 1 (0-indexed), otherwise first available GENERAL lane
        preferred = [1, 2, 0]
        for idx in preferred:
            if idx < n and config[idx] == LaneFunction.GENERAL:
                config[idx] = LaneFunction.BUS_PRIORITY
                return config
        return config  # no GENERAL lane available; return unchanged

    def _build_emergency_config(
        self, current: List[LaneFunction]
    ) -> List[LaneFunction]:
        """
        Establish emergency corridor on lane 0 (innermost / contraflow position).

        Avoids the bicycle lane (last lane).
        Maintains any existing BUS_PRIORITY assignment on other lanes.
        """
        config = list(current)
        if config[0] != LaneFunction.EMERGENCY:
            config[0] = LaneFunction.EMERGENCY
        return config

    def _build_pedestrian_config(
        self, current: List[LaneFunction]
    ) -> List[LaneFunction]:
        """
        Convert one GENERAL lane to PEDESTRIAN_BUFFER.

        If PEDESTRIAN_BUFFER already exists, maintain the configuration.
        Works from the last lane backwards to keep outermost lanes for motor traffic.
        """
        # If already in pedestrian-buffer mode, hold the current configuration.
        if LaneFunction.PEDESTRIAN_BUFFER in current:
            return list(current)

        config = list(current)
        n = len(config)
        for idx in range(n - 1, -1, -1):
            if config[idx] == LaneFunction.GENERAL:
                config[idx] = LaneFunction.PEDESTRIAN_BUFFER
                return config
        return config  # no GENERAL lane available; unchanged
