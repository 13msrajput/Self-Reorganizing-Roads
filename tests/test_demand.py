"""Tests for src/demand/demand_estimator.py"""

import pytest
from src.models import TrafficState
from src.demand.demand_estimator import DemandEstimator


def _make_state(
    arrivals: dict, queues: dict = None, emergency: bool = False
) -> TrafficState:
    q = queues or {k: 0.0 for k in arrivals}
    deps = {k: 0.0 for k in arrivals}
    return TrafficState(
        timestamp=1,
        arrivals=arrivals,
        queues=q,
        departures=deps,
        occupancy=0.0,
        emergency_detected=emergency,
    )


# ── Basic estimation ─────────────────────────────────────────────────────────


def test_demand_scores_are_positive(config):
    est = DemandEstimator(config)
    state = _make_state(
        {"car": 12, "bus": 2, "bicycle": 2, "pedestrian": 8, "emergency": 0}
    )
    demand = est.estimate(state)
    assert demand.car_demand >= 0
    assert demand.bus_demand >= 0
    assert demand.bicycle_demand >= 0
    assert demand.pedestrian_demand >= 0


def test_demand_includes_queue_pressure(config):
    est = DemandEstimator(config)
    # Same arrivals, but second state has a large bus queue
    state_no_q = _make_state(
        {"car": 5, "bus": 2, "bicycle": 1, "pedestrian": 4, "emergency": 0}
    )
    state_with_q = _make_state(
        {"car": 5, "bus": 2, "bicycle": 1, "pedestrian": 4, "emergency": 0},
        queues={"car": 0, "bus": 10, "bicycle": 0, "pedestrian": 0, "emergency": 0},
    )
    d1 = est.estimate(state_no_q)
    d2 = est.estimate(state_with_q)
    assert d2.bus_demand > d1.bus_demand, "Queue pressure should raise bus demand score"


def test_emergency_flag_propagates(config):
    est = DemandEstimator(config)
    state = _make_state(
        {"car": 10, "bus": 1, "bicycle": 1, "pedestrian": 5, "emergency": 1},
        emergency=True,
    )
    demand = est.estimate(state)
    assert demand.emergency_flag is True


def test_no_emergency_flag_when_clear(config):
    est = DemandEstimator(config)
    state = _make_state(
        {"car": 10, "bus": 1, "bicycle": 1, "pedestrian": 5, "emergency": 0},
        emergency=False,
    )
    demand = est.estimate(state)
    assert demand.emergency_flag is False


# ── Threshold checks ─────────────────────────────────────────────────────────


def test_bus_priority_not_warranted_below_threshold(config):
    est = DemandEstimator(config)
    # bus_demand = 1 arrival + 0.5 * 0 queue = 1.0 < threshold 7.0
    state = _make_state(
        {"car": 12, "bus": 1, "bicycle": 1, "pedestrian": 5, "emergency": 0}
    )
    demand = est.estimate(state)
    assert not est.is_bus_priority_warranted(demand)


def test_bus_priority_warranted_above_threshold(config):
    est = DemandEstimator(config)
    # bus_demand = 5 arrivals + 0.5 * 6 queue = 8.0 > threshold 7.0
    state = _make_state(
        {"car": 10, "bus": 5, "bicycle": 1, "pedestrian": 5, "emergency": 0},
        queues={"car": 0, "bus": 6, "bicycle": 0, "pedestrian": 0, "emergency": 0},
    )
    demand = est.estimate(state)
    assert est.is_bus_priority_warranted(demand)


def test_pedestrian_surge_above_threshold(config):
    est = DemandEstimator(config)
    # pedestrian_demand = 20 + 0.5*5 = 22.5 > threshold 18.0
    state = _make_state(
        {"car": 5, "bus": 1, "bicycle": 2, "pedestrian": 20, "emergency": 0},
        queues={"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 5, "emergency": 0},
    )
    demand = est.estimate(state)
    assert est.is_pedestrian_surge(demand)


def test_pedestrian_surge_below_threshold(config):
    est = DemandEstimator(config)
    # pedestrian_demand = 8 + 0 = 8.0 < threshold 18.0
    state = _make_state(
        {"car": 5, "bus": 1, "bicycle": 2, "pedestrian": 8, "emergency": 0}
    )
    demand = est.estimate(state)
    assert not est.is_pedestrian_surge(demand)


# ── Dominant demand ───────────────────────────────────────────────────────────


def test_dominant_demand_identifies_highest(config):
    est = DemandEstimator(config)
    # high pedestrian arrivals → dominant should be pedestrian
    state = _make_state(
        {"car": 5, "bus": 2, "bicycle": 1, "pedestrian": 30, "emergency": 0}
    )
    demand = est.estimate(state)
    assert demand.dominant_demand == "pedestrian"


def test_dominant_demand_is_always_set(config):
    est = DemandEstimator(config)
    state = _make_state(
        {"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0}
    )
    demand = est.estimate(state)
    assert demand.dominant_demand in ("car", "bus", "bicycle", "pedestrian")
