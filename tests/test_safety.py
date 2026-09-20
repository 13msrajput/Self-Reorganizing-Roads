"""Tests for src/safety/safety_manager.py"""

import pytest
from src.models import LaneFunction
from src.safety.safety_manager import SafetyManager

G = LaneFunction.GENERAL
BP = LaneFunction.BUS_PRIORITY
EM = LaneFunction.EMERGENCY
BI = LaneFunction.BICYCLE
PB = LaneFunction.PEDESTRIAN_BUFFER
TR = LaneFunction.TRANSITION


# ── Safe configurations ───────────────────────────────────────────────────────


def test_default_config_is_safe(config, normal_config):
    mgr = SafetyManager(config)
    result = mgr.assess(normal_config)
    assert result.is_safe
    assert result.violations == []


def test_bus_priority_config_is_safe(config, bus_priority_config):
    mgr = SafetyManager(config)
    result = mgr.assess(bus_priority_config)
    assert result.is_safe


def test_emergency_config_is_safe(config, emergency_config):
    mgr = SafetyManager(config)
    result = mgr.assess(emergency_config)
    assert result.is_safe


def test_pedestrian_buffer_config_is_safe(config):
    mgr = SafetyManager(config)
    cfg = [G, G, PB, BI]
    result = mgr.assess(cfg)
    assert result.is_safe


# ── Constraint violations ─────────────────────────────────────────────────────


def test_emergency_plus_pedestrian_buffer_is_unsafe(config):
    """EMERGENCY and PEDESTRIAN_BUFFER cannot coexist — they conflict at transition zones."""
    mgr = SafetyManager(config)
    cfg = [EM, G, PB, BI]
    result = mgr.assess(cfg)
    assert not result.is_safe
    assert any("incompatible" in v.lower() for v in result.violations)


def test_zero_general_lanes_is_unsafe(config):
    """At least 1 GENERAL lane must remain available."""
    mgr = SafetyManager(config)
    cfg = [BP, BP, BP, BI]  # no GENERAL lanes at all
    result = mgr.assess(cfg)
    assert not result.is_safe
    assert any("general" in v.lower() for v in result.violations)


def test_multiple_emergency_lanes_is_unsafe(config):
    """Only one EMERGENCY corridor is permitted."""
    mgr = SafetyManager(config)
    cfg = [EM, EM, G, BI]
    result = mgr.assess(cfg)
    assert not result.is_safe
    assert any("emergency" in v.lower() for v in result.violations)


# ── Fallback ──────────────────────────────────────────────────────────────────


def test_fallback_config_is_always_safe(config):
    mgr = SafetyManager(config)
    fallback = mgr.get_fallback()
    result = mgr.assess(fallback)
    assert result.is_safe


def test_fallback_is_a_copy(config):
    mgr = SafetyManager(config)
    fb1 = mgr.get_fallback()
    fb2 = mgr.get_fallback()
    fb1[0] = EM
    assert fb2[0] != EM, "get_fallback() should return a fresh copy each time"


# ── Transition config ─────────────────────────────────────────────────────────


def test_transition_config_marks_changed_lanes(config):
    mgr = SafetyManager(config)
    current = [G, G, G, BI]
    target = [G, BP, G, BI]
    trans = mgr.make_transition_config(current, target)
    assert trans[0] == G  # unchanged
    assert trans[1] == TR  # changing → TRANSITION
    assert trans[2] == G  # unchanged
    assert trans[3] == BI  # unchanged


def test_transition_config_when_no_change(config):
    mgr = SafetyManager(config)
    cfg = [G, G, G, BI]
    trans = mgr.make_transition_config(cfg, cfg)
    assert trans == cfg, "No change → transition = current config"


# ── Warnings (not violations) ─────────────────────────────────────────────────


def test_warning_when_many_non_general_lanes(config):
    mgr = SafetyManager(config)
    # 3 out of 4 lanes non-general → should warn but still be safe
    cfg = [G, BP, EM, BI]
    result = mgr.assess(cfg)
    # Safe (only 1 GENERAL but that satisfies min=1)
    assert result.is_safe
    assert len(result.warnings) > 0
