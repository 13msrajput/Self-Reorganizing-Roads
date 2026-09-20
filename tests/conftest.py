"""
Shared pytest fixtures.

Uses an inline config dict so tests do not depend on the YAML file path.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.models import LaneFunction


@pytest.fixture
def config() -> dict:
    return {
        "simulation": {
            "random_seed": 42,
            "time_steps": 10,
            "road": {
                "num_lanes": 4,
                "lane_capacity": 20,
                "free_flow_time": 2.0,
            },
            "arrival_rates": {
                "normal": {
                    "car": 12.0,
                    "bus": 1.5,
                    "bicycle": 2.0,
                    "pedestrian": 8.0,
                    "emergency": 0.0,
                },
                "high_bus": {
                    "car": 10.0,
                    "bus": 5.5,
                    "bicycle": 2.0,
                    "pedestrian": 8.0,
                    "emergency": 0.0,
                },
                "emergency": {
                    "car": 12.0,
                    "bus": 2.0,
                    "bicycle": 2.0,
                    "pedestrian": 8.0,
                    "emergency": 0.8,
                },
                "pedestrian_surge": {
                    "car": 8.0,
                    "bus": 2.0,
                    "bicycle": 5.0,
                    "pedestrian": 22.0,
                    "emergency": 0.0,
                },
            },
        },
        "demand": {
            "thresholds": {
                "bus_priority": 7.0,
                "bicycle_priority": 8.0,
                "pedestrian_priority": 18.0,
            },
        },
        "priority": {
            "emergency_clearance_duration": 5,
        },
        "lanes": {
            "default_config": ["GENERAL", "GENERAL", "GENERAL", "BICYCLE"],
            "safe_fallback": ["GENERAL", "GENERAL", "GENERAL", "BICYCLE"],
            "min_general_lanes": 1,
            "transition_duration": 2,
        },
    }


@pytest.fixture
def normal_config():
    return [
        LaneFunction.GENERAL,
        LaneFunction.GENERAL,
        LaneFunction.GENERAL,
        LaneFunction.BICYCLE,
    ]


@pytest.fixture
def bus_priority_config():
    return [
        LaneFunction.GENERAL,
        LaneFunction.BUS_PRIORITY,
        LaneFunction.GENERAL,
        LaneFunction.BICYCLE,
    ]


@pytest.fixture
def emergency_config():
    return [
        LaneFunction.EMERGENCY,
        LaneFunction.GENERAL,
        LaneFunction.GENERAL,
        LaneFunction.BICYCLE,
    ]
