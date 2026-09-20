"""
Scenario orchestrator.

Runs a complete paired simulation — one baseline run (no lane changes)
and one self-reorganising run — and returns all data needed by the dashboard.

This module contains only coordination logic.  All domain logic lives in
the individual src/ modules; this file just wires them together.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from src.models import (
    AllocationDecision,
    DemandEstimate,
    LaneFunction,
    PriorityDecision,
    ScenarioMetrics,
)
from src.simulation.traffic_simulator import TrafficSimulator
from src.demand.demand_estimator import DemandEstimator
from src.priority.priority_engine import PriorityEngine
from src.safety.safety_manager import SafetyManager
from src.allocation.lane_allocator import LaneAllocator
from src.metrics.metrics_calculator import MetricsCalculator


def run_scenario_pair(
    scenario: str,
    config: dict,
) -> Tuple[List[Dict], ScenarioMetrics, ScenarioMetrics, Dict]:
    """
    Run scenario with baseline (fixed config) and self-reorganising (adaptive).

    Returns
    ───────
    step_history    : list of per-step dicts for the reorganising run
    baseline_metrics: ScenarioMetrics for the fixed-config run
    reorg_metrics   : ScenarioMetrics for the adaptive run
    comparison      : dict of delta / pct_change per key metric

    NOTE: All values are simulation outputs — not real-world measurements.
    """
    seed = config["simulation"]["random_seed"]
    steps = config["simulation"]["time_steps"]
    initial_config = [LaneFunction(f) for f in config["lanes"]["default_config"]]
    trans_duration = config["lanes"]["transition_duration"]
    clearance_window = config["priority"].get("emergency_clearance_duration", 5)
    min_active_steps = config["priority"].get("min_activation_duration", 8)

    # ── BASELINE ──────────────────────────────────────────────────────────
    # Fixed lane configuration throughout; no adaptive reorganisation.
    baseline_sim = TrafficSimulator(config, seed=seed)
    baseline_sim.reset(scenario)
    baseline_calc = MetricsCalculator(config)

    for _ in range(steps):
        b_state = baseline_sim.step(initial_config)
        b_cap = baseline_sim.compute_effective_capacity(initial_config)
        baseline_calc.record(b_state, b_cap, initial_config, "NORMAL")

    baseline_metrics = baseline_calc.get_summary(f"{scenario}_baseline")

    # ── SELF-REORGANISING ────────────────────────────────────────────────
    reorg_sim = TrafficSimulator(config, seed=seed)
    reorg_sim.reset(scenario)

    demand_estimator = DemandEstimator(config)
    safety_manager = SafetyManager(config)
    priority_engine = PriorityEngine(config, demand_estimator)
    lane_allocator = LaneAllocator(config, safety_manager)
    reorg_calc = MetricsCalculator(config)

    current_config = list(initial_config)
    target_config = list(initial_config)
    in_transition = False
    trans_counter = 0
    emerg_timer = 0  # clearance steps remaining after last detection

    last_demand: Optional[DemandEstimate] = None
    last_priority: Optional[PriorityDecision] = None
    last_allocation: Optional[AllocationDecision] = None
    system_state = "NORMAL"
    steps_in_mode = 0  # how long the current config has been active

    step_history: List[Dict] = []

    for step_idx in range(steps):
        r_state = reorg_sim.step(current_config)

        # ── Transition management ───────────────────────────────────────
        if in_transition:
            trans_counter += 1
            system_state = "TRANSITIONING"
            if trans_counter >= trans_duration:
                current_config = list(target_config)
                in_transition = False
                trans_counter = 0
                system_state = _derive_state(current_config)
        else:
            # ── Decision cycle ──────────────────────────────────────────
            demand = demand_estimator.estimate(r_state)

            # Emergency clearance: maintain emergency mode for N steps after
            # the last detection so the vehicle has time to clear.
            if demand.emergency_flag:
                emerg_timer = clearance_window
            elif emerg_timer > 0:
                emerg_timer -= 1
                demand.emergency_flag = True  # hold emergency mode

            safety_check = safety_manager.assess(current_config)
            priority = priority_engine.decide(demand, current_config, safety_check)
            allocation = lane_allocator.allocate(current_config, priority)

            last_demand = demand
            last_priority = priority
            last_allocation = allocation

            # ── Commit change if config differs ─────────────────────────
            is_emergency_action = allocation.decision == "ACTIVATE_EMERGENCY_CORRIDOR"
            # Emergency always triggers immediately; other reconfigurations are
            # locked for min_active_steps to prevent rapid oscillation.
            mode_lock_cleared = steps_in_mode >= min_active_steps

            if (
                allocation.decision not in ("NO_CHANGE",)
                and allocation.new_config != current_config
                and (mode_lock_cleared or is_emergency_action)
            ):
                target_config = list(allocation.new_config)
                current_config = list(allocation.transition_config)
                in_transition = True
                trans_counter = 0
                system_state = "TRANSITIONING"
                steps_in_mode = 0
            else:
                steps_in_mode += 1
                system_state = _derive_state(current_config)

        # ── Record metrics ───────────────────────────────────────────────
        r_cap = reorg_sim.compute_effective_capacity(current_config)
        snap = reorg_calc.record(r_state, r_cap, current_config, system_state)

        step_history.append(
            {
                "step": step_idx + 1,
                "state": r_state,
                "config": list(current_config),
                "snap": snap,
                "demand": last_demand,
                "priority": last_priority,
                "allocation": last_allocation,
                "system_state": system_state,
                "in_transition": in_transition,
            }
        )

    reorg_metrics = reorg_calc.get_summary(scenario)
    comparison = MetricsCalculator.compare(baseline_metrics, reorg_metrics)

    return step_history, baseline_metrics, reorg_metrics, comparison


def _derive_state(config: List[LaneFunction]) -> str:
    """Infer a human-readable system-state label from a lane configuration."""
    funcs = set(config)
    if LaneFunction.EMERGENCY in funcs:
        return "EMERGENCY_ACTIVE"
    if LaneFunction.BUS_PRIORITY in funcs:
        return "BUS_PRIORITY_ACTIVE"
    if LaneFunction.PEDESTRIAN_BUFFER in funcs:
        return "PEDESTRIAN_BUFFER_ACTIVE"
    if LaneFunction.TRANSITION in funcs:
        return "TRANSITIONING"
    return "NORMAL"
