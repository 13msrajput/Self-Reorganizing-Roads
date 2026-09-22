"""Tests for src/priority/priority_engine.py"""

import pytest
from src.models import DemandEstimate, LaneFunction, SafetyAssessment
from src.demand.demand_estimator import DemandEstimator
from src.priority.priority_engine import PriorityEngine

G = LaneFunction.GENERAL
BI = LaneFunction.BICYCLE


def _demand(
    car=5.0,
    bus=1.0,
    bicycle=1.0,
    pedestrian=5.0,
    emergency=False,
    dominant="car",
) -> DemandEstimate:
    return DemandEstimate(
        car_demand=car,
        bus_demand=bus,
        bicycle_demand=bicycle,
        pedestrian_demand=pedestrian,
        emergency_flag=emergency,
        dominant_demand=dominant,
    )


def _safe(violations=None) -> SafetyAssessment:
    return SafetyAssessment(is_safe=(not violations), violations=violations or [])


# ── Level 1: Safety ───────────────────────────────────────────────────────────


def test_safety_overrides_all_other_demands(config):
    """Even with high bus/emergency demand, unsafe config triggers fallback."""
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=20.0, emergency=True)
    sa = _safe(violations=["test violation"])
    dec = eng.decide(d, [G, G, G, BI], sa)
    assert dec.action == "ENFORCE_SAFE_FALLBACK"
    assert dec.priority_level == "SAFETY"


# ── Level 2: Emergency ────────────────────────────────────────────────────────


def test_emergency_beats_bus_priority(config):
    """Emergency takes precedence over high bus demand."""
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=10.0, emergency=True)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action == "ACTIVATE_EMERGENCY_CORRIDOR"
    assert dec.priority_level == "EMERGENCY"


def test_emergency_proposes_corridor_on_lane_0(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(emergency=True)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.target_config is not None
    assert dec.target_config[0] == LaneFunction.EMERGENCY


# ── Level 3: Pedestrian / cyclist ─────────────────────────────────────────────


def test_pedestrian_surge_beats_bus_priority(config):
    """Pedestrian surge takes priority over bus demand."""
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=10.0, pedestrian=22.0, emergency=False)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action == "ACTIVATE_PEDESTRIAN_BUFFER"
    assert dec.priority_level == "PEDESTRIAN_CYCLIST"


def test_normal_pedestrian_does_not_trigger_buffer(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=1.0, pedestrian=8.0, emergency=False)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action not in ("ACTIVATE_PEDESTRIAN_BUFFER",)


# ── Level 4: Bus priority ─────────────────────────────────────────────────────


def test_bus_priority_when_demand_exceeds_threshold(config):
    """bus_demand=9.0 > threshold 7.0 → BUS_PRIORITY."""
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=9.0, emergency=False)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action == "ACTIVATE_BUS_PRIORITY"
    assert dec.priority_level == "PUBLIC_TRANSPORT"


def test_bus_priority_config_has_one_bus_lane(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=9.0)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    n_bus = sum(1 for f in dec.target_config if f == LaneFunction.BUS_PRIORITY)
    assert n_bus == 1


def test_bus_priority_not_triggered_below_threshold(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(bus=3.0, emergency=False)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action == "MAINTAIN_NORMAL"


# ── Level 5: Normal ───────────────────────────────────────────────────────────


def test_normal_traffic_maintains_default(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand(car=5.0, bus=1.0, bicycle=1.0, pedestrian=5.0, emergency=False)
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert dec.action == "MAINTAIN_NORMAL"
    assert dec.priority_level == "GENERAL_TRAFFIC"


def test_normal_decision_has_reason(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    d = _demand()
    dec = eng.decide(d, [G, G, G, BI], _safe())
    assert len(dec.reason) > 10, "Decision should include a human-readable reason"


# ── Decision confidence ───────────────────────────────────────────────────────


def test_emergency_has_high_confidence(config):
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)
    dec = eng.decide(_demand(emergency=True), [G, G, G, BI], _safe())
    assert dec.confidence >= 0.9


# ── Emergency override regression tests (Issue 3) ─────────────────────────────


def test_emergency_from_normal_produces_safe_config(config):
    """Emergency from NORMAL state must produce a safety-valid configuration."""
    from src.safety.safety_manager import SafetyManager

    sm = SafetyManager(config)
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)

    current = [G, G, G, BI]
    dec = eng.decide(_demand(emergency=True), current, _safe())
    assert dec.target_config is not None
    assert sm.assess(dec.target_config).is_safe
    assert LaneFunction.EMERGENCY in dec.target_config


def test_emergency_from_bus_priority_produces_safe_config(config):
    """Emergency must safely override BUS_PRIORITY without a safety fallback."""
    from src.safety.safety_manager import SafetyManager

    sm = SafetyManager(config)
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)

    current = [G, LaneFunction.BUS_PRIORITY, G, BI]
    dec = eng.decide(_demand(emergency=True), current, _safe())
    assert dec.action == "ACTIVATE_EMERGENCY_CORRIDOR"
    assert dec.target_config is not None
    result = sm.assess(dec.target_config)
    assert result.is_safe, f"Config not safe: {result.violations}"
    assert LaneFunction.EMERGENCY in dec.target_config
    # BUS_PRIORITY should be cleared in the canonical emergency layout
    assert LaneFunction.BUS_PRIORITY not in dec.target_config


def test_emergency_from_pedestrian_buffer_produces_safe_config(config):
    """Emergency must safely override PEDESTRIAN_BUFFER.

    Previously, _build_emergency_config patched lane 0 onto the current config,
    which could produce [EMERGENCY, GENERAL, PEDESTRIAN_BUFFER, BICYCLE] — a
    globally incompatible combination that the safety manager would reject,
    preventing the emergency corridor from ever activating.
    """
    from src.safety.safety_manager import SafetyManager

    sm = SafetyManager(config)
    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)

    current = [G, G, LaneFunction.PEDESTRIAN_BUFFER, BI]
    dec = eng.decide(_demand(emergency=True), current, _safe())
    assert dec.action == "ACTIVATE_EMERGENCY_CORRIDOR"
    assert dec.target_config is not None

    result = sm.assess(dec.target_config)
    assert (
        result.is_safe
    ), f"Emergency config must be safe but got violations: {result.violations}"
    assert LaneFunction.EMERGENCY in dec.target_config
    assert (
        LaneFunction.PEDESTRIAN_BUFFER not in dec.target_config
    ), "PEDESTRIAN_BUFFER must not appear with EMERGENCY"


def test_emergency_canonical_layout_four_lanes(config):
    """For a 4-lane road the canonical emergency layout is exactly
    [EMERGENCY, GENERAL, GENERAL, BICYCLE]."""
    from src.models import LaneFunction as LF

    est = DemandEstimator(config)
    eng = PriorityEngine(config, est)

    for current in [
        [G, G, G, BI],
        [G, LaneFunction.BUS_PRIORITY, G, BI],
        [G, G, LaneFunction.PEDESTRIAN_BUFFER, BI],
    ]:
        dec = eng.decide(_demand(emergency=True), current, _safe())
        assert dec.target_config == [
            LF.EMERGENCY,
            LF.GENERAL,
            LF.GENERAL,
            LF.BICYCLE,
        ], f"Unexpected layout for current={current}: {dec.target_config}"
