"""
Safety constraint engine.

DESIGN PRINCIPLE
────────────────
Safety constraints are NEVER overridden by the optimisation or priority logic.
If a proposed configuration violates any hard constraint, the system falls back
to the pre-configured safe default configuration regardless of demand signals.

Hard constraints enforced here
──────────────────────────────
1. Minimum general-traffic lanes: at least one lane must remain accessible
   to general traffic at all times (configurable via settings.yaml).
2. EMERGENCY + PEDESTRIAN_BUFFER cannot coexist in the same configuration:
   emergency corridor dynamics and pedestrian spaces conflict at transition zones.
3. Multiple EMERGENCY lanes are not permitted: a single, unambiguous corridor
   is safer than two competing ones.
4. No adjacent lane pair may be globally incompatible.

Safe fallback
─────────────
If any constraint is violated — or if the system cannot determine a safe
configuration — it falls back to the safe_fallback configuration from config.
This is the last line of defence: it means the road stays in a known-safe state.
"""

from __future__ import annotations
from typing import List, Tuple

from src.models import LaneFunction, SafetyAssessment


# Lane function pairs that must NOT appear together anywhere in one config.
_GLOBALLY_INCOMPATIBLE: List[frozenset] = [
    frozenset({LaneFunction.EMERGENCY, LaneFunction.PEDESTRIAN_BUFFER}),
]

# Adjacent lane pairs that are not permitted.
_ADJACENT_INCOMPATIBLE: set = {
    (LaneFunction.EMERGENCY, LaneFunction.PEDESTRIAN_BUFFER),
    (LaneFunction.PEDESTRIAN_BUFFER, LaneFunction.EMERGENCY),
}


class SafetyManager:
    """
    Checks proposed lane configurations against hard safety constraints
    and provides the safe fallback configuration.
    """

    def __init__(self, config: dict) -> None:
        self.config           = config
        self.min_general_lanes = config["lanes"]["min_general_lanes"]
        self._fallback        = [
            LaneFunction(f) for f in config["lanes"]["safe_fallback"]
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(self, proposed_config: List[LaneFunction]) -> SafetyAssessment:
        """
        Check a proposed configuration against all hard safety constraints.

        Returns SafetyAssessment(is_safe=True) if all constraints pass,
        otherwise is_safe=False with a list of violation descriptions.
        """
        violations: List[str] = []
        warnings:   List[str] = []

        # Constraint 1: minimum general-traffic lanes
        n_general = sum(1 for f in proposed_config if f == LaneFunction.GENERAL)
        if n_general < self.min_general_lanes:
            violations.append(
                f"Minimum general-traffic lanes violated: "
                f"{n_general} present, minimum is {self.min_general_lanes}."
            )

        # Constraint 2: globally incompatible function pairs
        func_set = frozenset(proposed_config)
        for incompatible_pair in _GLOBALLY_INCOMPATIBLE:
            if incompatible_pair.issubset(func_set):
                labels = " + ".join(f.value for f in incompatible_pair)
                violations.append(
                    f"Globally incompatible functions in same configuration: {labels}."
                )

        # Constraint 3: adjacent incompatibilities
        for i in range(len(proposed_config) - 1):
            pair = (proposed_config[i], proposed_config[i + 1])
            if pair in _ADJACENT_INCOMPATIBLE:
                violations.append(
                    f"Incompatible adjacent lanes at positions {i} and {i+1}: "
                    f"{pair[0].value} next to {pair[1].value}."
                )

        # Constraint 4: at most one EMERGENCY lane
        n_emergency = sum(1 for f in proposed_config if f == LaneFunction.EMERGENCY)
        if n_emergency > 1:
            violations.append(
                f"Only one EMERGENCY corridor permitted; {n_emergency} found."
            )

        # Warning: more than half the lanes are non-general
        n_non_general = sum(
            1 for f in proposed_config
            if f not in (LaneFunction.GENERAL, LaneFunction.TRANSITION)
        )
        if n_non_general > len(proposed_config) // 2:
            warnings.append(
                "Over half of lanes are non-general — monitor general-traffic flow."
            )

        return SafetyAssessment(
            is_safe    = len(violations) == 0,
            violations = violations,
            warnings   = warnings,
        )

    def get_fallback(self) -> List[LaneFunction]:
        """Return the safe fallback lane configuration (copy)."""
        return list(self._fallback)

    def make_transition_config(
        self,
        current: List[LaneFunction],
        target:  List[LaneFunction],
    ) -> List[LaneFunction]:
        """
        Build an intermediate transition configuration.

        Lanes that will change function are placed in TRANSITION state.
        Lanes that keep the same function remain unchanged.
        This prevents instant teleportation between configurations.
        """
        return [
            LaneFunction.TRANSITION if c != t else c
            for c, t in zip(current, target)
        ]

    def configs_differ(
        self,
        current: List[LaneFunction],
        target:  List[LaneFunction],
    ) -> bool:
        """Return True if the two configurations are not identical."""
        return current != target
