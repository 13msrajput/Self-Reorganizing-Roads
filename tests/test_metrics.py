"""Tests for src/metrics/metrics_calculator.py"""

import pytest
from src.models import LaneFunction, MetricsSnapshot, ScenarioMetrics, TrafficState
from src.metrics.metrics_calculator import MetricsCalculator
from src.simulation.traffic_simulator import TrafficSimulator

G = LaneFunction.GENERAL
BP = LaneFunction.BUS_PRIORITY
BI = LaneFunction.BICYCLE


def _state(
    queues: dict, arrivals: dict = None, departures: dict = None
) -> TrafficState:
    a = arrivals or {k: 0.0 for k in queues}
    d = departures or {k: 0.0 for k in queues}
    return TrafficState(
        timestamp=1,
        arrivals=a,
        queues=queues,
        departures=d,
        occupancy=0.0,
    )


def _cap(bus: float = 4.0, car: float = 20.0) -> dict:
    return {"car": car, "bus": bus, "bicycle": 0.0, "pedestrian": 0.0, "emergency": 0.0}


# ── Travel time computation ───────────────────────────────────────────────────


def test_travel_time_at_zero_queue_equals_free_flow(config):
    calc = MetricsCalculator(config)
    state = _state({"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    snap = calc.record(state, _cap(), [G, G, G, BI])
    free_flow = config["simulation"]["road"]["free_flow_time"]
    assert snap.travel_times["car"] == pytest.approx(free_flow, rel=0.01)


def test_travel_time_increases_with_queue(config):
    calc = MetricsCalculator(config)
    s1 = _state({"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    s2 = _state({"car": 50, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    snap1 = calc.record(s1, _cap(), [G, G, G, BI])
    calc.reset()
    snap2 = calc.record(s2, _cap(), [G, G, G, BI])
    assert snap2.travel_times["car"] > snap1.travel_times["car"]


def test_bus_delay_is_zero_at_free_flow(config):
    calc = MetricsCalculator(config)
    state = _state({"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    snap = calc.record(state, _cap(), [G, G, G, BI])
    assert snap.bus_delay == pytest.approx(0.0, abs=0.001)


# ── Throughput ────────────────────────────────────────────────────────────────


def test_throughput_matches_departures(config):
    """road_user_flow must equal the sum of all departures."""
    calc = MetricsCalculator(config)
    deps = {
        "car": 10.0,
        "bus": 3.0,
        "bicycle": 2.0,
        "pedestrian": 0.0,
        "emergency": 0.0,
    }
    state = TrafficState(
        timestamp=1,
        arrivals={k: 0.0 for k in deps},
        queues={k: 0.0 for k in deps},
        departures=deps,
        occupancy=0.0,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])
    assert snap.road_user_flow == pytest.approx(15.0, rel=0.01)
    # vehicle_throughput same here (no pedestrians)
    assert snap.vehicle_throughput == pytest.approx(15.0, rel=0.01)


# ── Aggregation ───────────────────────────────────────────────────────────────


def test_average_queue_length_correct(config):
    calc = MetricsCalculator(config)
    s1 = _state({"car": 4, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    s2 = _state({"car": 8, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    calc.record(s1, _cap(), [G, G, G, BI])
    s2.timestamp = 2
    calc.record(s2, _cap(), [G, G, G, BI])
    summary = calc.get_summary("test")
    assert summary.avg_queue_lengths["car"] == pytest.approx(6.0, rel=0.01)


def test_empty_calculator_returns_empty_summary(config):
    calc = MetricsCalculator(config)
    summary = calc.get_summary("test")
    assert summary.avg_throughput == 0.0
    assert summary.snapshots == []


def test_reset_clears_snapshots(config):
    calc = MetricsCalculator(config)
    state = _state({"car": 5, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0})
    calc.record(state, _cap(), [G, G, G, BI])
    assert len(calc.snapshots) == 1
    calc.reset()
    assert len(calc.snapshots) == 0


# ── Comparison ────────────────────────────────────────────────────────────────


def test_comparison_shows_improvement_when_bus_time_lower(config):
    base = ScenarioMetrics(
        scenario_name="base",
        avg_travel_times={
            "car": 2.5,
            "bus": 4.0,
            "bicycle": 2.0,
            "pedestrian": 2.0,
            "emergency": 2.0,
        },
        avg_queue_lengths={
            "car": 5,
            "bus": 10,
            "bicycle": 0,
            "pedestrian": 0,
            "emergency": 0,
        },
        avg_vehicle_throughput=15.0,
        avg_bus_delay=2.0,
    )
    opt = ScenarioMetrics(
        scenario_name="opt",
        avg_travel_times={
            "car": 2.6,
            "bus": 2.2,
            "bicycle": 2.0,
            "pedestrian": 2.0,
            "emergency": 2.0,
        },
        avg_queue_lengths={
            "car": 6,
            "bus": 2,
            "bicycle": 0,
            "pedestrian": 0,
            "emergency": 0,
        },
        avg_vehicle_throughput=16.0,
        avg_bus_delay=0.2,
    )
    cmp = MetricsCalculator.compare(base, opt)
    assert cmp["bus_travel_time"]["improved"] is True
    assert cmp["bus_queue"]["improved"] is True
    assert cmp["vehicle_throughput"]["improved"] is True


def test_comparison_shows_degradation_when_car_time_higher(config):
    base = ScenarioMetrics(
        scenario_name="base",
        avg_travel_times={
            "car": 2.0,
            "bus": 2.0,
            "bicycle": 2.0,
            "pedestrian": 2.0,
            "emergency": 2.0,
        },
        avg_queue_lengths={
            "car": 0,
            "bus": 0,
            "bicycle": 0,
            "pedestrian": 0,
            "emergency": 0,
        },
        avg_vehicle_throughput=15.0,
        avg_bus_delay=0.0,
    )
    opt = ScenarioMetrics(
        scenario_name="opt",
        avg_travel_times={
            "car": 2.4,
            "bus": 2.0,
            "bicycle": 2.0,
            "pedestrian": 2.0,
            "emergency": 2.0,
        },
        avg_queue_lengths={
            "car": 2,
            "bus": 0,
            "bicycle": 0,
            "pedestrian": 0,
            "emergency": 0,
        },
        avg_vehicle_throughput=15.0,
        avg_bus_delay=0.0,
    )
    cmp = MetricsCalculator.compare(base, opt)
    assert cmp["car_travel_time"]["improved"] is False


# ── Simulation integration ─────────────────────────────────────────────────────


def test_metrics_generated_from_simulation_not_hardcoded(config):
    """Verify metrics change between runs with different scenarios (not fixed values)."""
    sim1 = TrafficSimulator(config, seed=42)
    sim1.reset("normal")
    calc1 = MetricsCalculator(config)
    cfg = [G, G, G, BI]
    for _ in range(10):
        s = sim1.step(cfg)
        cap = sim1.compute_effective_capacity(cfg)
        calc1.record(s, cap, cfg)
    normal_summary = calc1.get_summary("normal")

    sim2 = TrafficSimulator(config, seed=42)
    sim2.reset("high_bus")
    calc2 = MetricsCalculator(config)
    for _ in range(10):
        s = sim2.step(cfg)
        cap = sim2.compute_effective_capacity(cfg)
        calc2.record(s, cap, cfg)
    bus_summary = calc2.get_summary("high_bus")

    assert (
        normal_summary.avg_queue_lengths["bus"] != bus_summary.avg_queue_lengths["bus"]
    ), "Bus queue should differ between normal and high_bus scenarios"


# ── Throughput separation regression tests (Issue 4) ─────────────────────────


def test_vehicle_throughput_excludes_pedestrians(config):
    """Pedestrian departures must NOT appear in vehicle_throughput."""
    calc = MetricsCalculator(config)
    deps = {
        "car": 10.0,
        "bus": 3.0,
        "bicycle": 2.0,
        "pedestrian": 25.0,
        "emergency": 0.0,
    }
    state = TrafficState(
        timestamp=1,
        arrivals={k: 0.0 for k in deps},
        queues={k: 0.0 for k in deps},
        departures=deps,
        occupancy=0.0,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])

    # vehicle_throughput = car + bus + bicycle + emergency = 15.0
    assert snap.vehicle_throughput == pytest.approx(
        15.0, rel=0.01
    ), "vehicle_throughput must be car+bus+bicycle+emergency, not include pedestrians"
    # pedestrian_flow should be 25.0
    assert snap.pedestrian_flow == pytest.approx(25.0, rel=0.01)
    # road_user_flow is the combined total
    assert snap.road_user_flow == pytest.approx(40.0, rel=0.01)
    # Confirm pedestrians are not mixed in
    assert snap.vehicle_throughput != snap.road_user_flow


def test_motor_throughput_correct(config):
    """motor_throughput = car + bus + emergency only."""
    calc = MetricsCalculator(config)
    deps = {
        "car": 10.0,
        "bus": 3.0,
        "bicycle": 5.0,
        "pedestrian": 20.0,
        "emergency": 1.0,
    }
    state = TrafficState(
        timestamp=1,
        arrivals={k: 0.0 for k in deps},
        queues={k: 0.0 for k in deps},
        departures=deps,
        occupancy=0.0,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])
    # motor_throughput = car(10) + bus(3) + emergency(1) = 14
    assert snap.motor_throughput == pytest.approx(14.0, rel=0.01)


def test_pedestrian_flow_isolated(config):
    """pedestrian_flow must equal pedestrian departures only."""
    calc = MetricsCalculator(config)
    deps = {
        "car": 5.0,
        "bus": 2.0,
        "bicycle": 1.0,
        "pedestrian": 30.0,
        "emergency": 0.0,
    }
    state = TrafficState(
        timestamp=1,
        arrivals={k: 0.0 for k in deps},
        queues={k: 0.0 for k in deps},
        departures=deps,
        occupancy=0.0,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])
    assert snap.pedestrian_flow == pytest.approx(30.0, rel=0.01)
    assert snap.vehicle_throughput == pytest.approx(8.0, rel=0.01)  # 5+2+1+0


# ── Emergency metrics regression tests (Issue 5) ──────────────────────────────


def test_emergency_queue_recorded(config):
    """emergency_queue must be populated from simulation state."""
    calc = MetricsCalculator(config)
    state = TrafficState(
        timestamp=1,
        arrivals={"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 2},
        queues={"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 3},
        departures={"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 2},
        occupancy=0.0,
        emergency_detected=True,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])
    assert snap.emergency_queue == pytest.approx(3.0, rel=0.01)
    assert snap.emergency_arrivals == pytest.approx(2.0, rel=0.01)
    assert snap.emergency_departures == pytest.approx(2.0, rel=0.01)


def test_scenario_emergency_aggregates(config):
    """ScenarioMetrics must aggregate emergency metrics correctly."""
    calc = MetricsCalculator(config)
    zeros = {"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 0}
    emerg = {"car": 0, "bus": 0, "bicycle": 0, "pedestrian": 0, "emergency": 1}

    for q_val in [0.0, 2.0, 4.0]:
        state = TrafficState(
            timestamp=1,
            arrivals=emerg,
            departures=emerg,
            queues={**zeros, "emergency": q_val},
            occupancy=0.0,
            emergency_detected=(q_val > 0),
        )
        calc.record(state, _cap(), [G, G, G, BI])

    summary = calc.get_summary("test_emerg")
    assert summary.avg_emergency_queue == pytest.approx(2.0, rel=0.01)  # (0+2+4)/3
    assert summary.max_emergency_queue == pytest.approx(4.0, rel=0.01)
    assert summary.total_emergency_arrivals == pytest.approx(3.0, rel=0.01)
    assert summary.total_emergency_departures == pytest.approx(3.0, rel=0.01)


# ── Back-compat alias ─────────────────────────────────────────────────────────


def test_total_throughput_alias_still_works(config):
    """MetricsSnapshot.total_throughput must alias road_user_flow for back-compat."""
    calc = MetricsCalculator(config)
    deps = {
        "car": 5.0,
        "bus": 2.0,
        "bicycle": 1.0,
        "pedestrian": 10.0,
        "emergency": 0.0,
    }
    state = TrafficState(
        timestamp=1,
        arrivals={k: 0.0 for k in deps},
        queues={k: 0.0 for k in deps},
        departures=deps,
        occupancy=0.0,
    )
    snap = calc.record(state, _cap(), [G, G, G, BI])
    assert snap.total_throughput == snap.road_user_flow
