"""Tests for src/allocation/lane_allocator.py"""

import pytest
from src.models import LaneFunction, PriorityDecision
from src.safety.safety_manager import SafetyManager
from src.allocation.lane_allocator import LaneAllocator

G = LaneFunction.GENERAL
BP = LaneFunction.BUS_PRIORITY
EM = LaneFunction.EMERGENCY
BI = LaneFunction.BICYCLE
PB = LaneFunction.PEDESTRIAN_BUFFER
TR = LaneFunction.TRANSITION


def _priority(action, target_config=None, level="PUBLIC_TRANSPORT") -> PriorityDecision:
    return PriorityDecision(
        action=action,
        priority_level=level,
        reason="test reason",
        target_config=target_config,
    )


# ── Basic allocation ──────────────────────────────────────────────────────────


def test_bus_priority_allocation_is_safe(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ACTIVATE_BUS_PRIORITY", [G, BP, G, BI])
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.is_safe
    assert BP in dec.new_config


def test_emergency_allocation_is_safe(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ACTIVATE_EMERGENCY_CORRIDOR", [EM, G, G, BI], "EMERGENCY")
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.is_safe
    assert EM in dec.new_config


# ── Transition state ──────────────────────────────────────────────────────────


def test_transition_config_contains_transition_lanes(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ACTIVATE_BUS_PRIORITY", [G, BP, G, BI])
    dec = alloc.allocate([G, G, G, BI], prio)
    # Lane 1 changes G→BP, so it should be TRANSITION in the middle state
    assert dec.transition_config[1] == TR


def test_unchanged_lanes_stay_in_transition_config(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ACTIVATE_BUS_PRIORITY", [G, BP, G, BI])
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.transition_config[0] == G  # unchanged
    assert dec.transition_config[2] == G  # unchanged
    assert dec.transition_config[3] == BI  # unchanged


# ── Safety fallback ───────────────────────────────────────────────────────────


def test_unsafe_proposal_triggers_fallback(config):
    """A proposal that creates EMERGENCY + PEDESTRIAN_BUFFER must be rejected."""
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    bad_config = [EM, G, PB, BI]  # EMERGENCY + PEDESTRIAN_BUFFER → unsafe
    prio = _priority("CUSTOM_ACTION", bad_config)
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.decision == "SAFE_FALLBACK"
    assert dec.is_safe
    assert EM not in dec.new_config or PB not in dec.new_config


def test_explicit_safe_fallback_action_returns_fallback(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ENFORCE_SAFE_FALLBACK", None, "SAFETY")
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.decision == "SAFE_FALLBACK"
    assert dec.is_safe
    assert dec.new_config == sm.get_fallback()


# ── No-change path ────────────────────────────────────────────────────────────


def test_no_change_when_already_at_target(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    cfg = [G, G, G, BI]
    prio = _priority("MAINTAIN_NORMAL", cfg, "GENERAL_TRAFFIC")
    dec = alloc.allocate(cfg, prio)
    assert dec.decision == "NO_CHANGE"
    assert dec.previous_config == dec.new_config


# ── Decision fields ───────────────────────────────────────────────────────────


def test_allocation_decision_has_all_fields(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    prio = _priority("ACTIVATE_BUS_PRIORITY", [G, BP, G, BI])
    dec = alloc.allocate([G, G, G, BI], prio)
    assert dec.previous_config is not None
    assert dec.transition_config is not None
    assert dec.new_config is not None
    assert len(dec.reason) > 0
    assert len(dec.expected_effect) > 0


def test_previous_config_recorded_correctly(config):
    sm = SafetyManager(config)
    alloc = LaneAllocator(config, sm)
    original = [G, G, G, BI]
    prio = _priority("ACTIVATE_BUS_PRIORITY", [G, BP, G, BI])
    dec = alloc.allocate(original, prio)
    assert dec.previous_config == original
