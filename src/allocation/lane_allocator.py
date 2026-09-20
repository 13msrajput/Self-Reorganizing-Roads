"""
Lane allocator.

Translates a PriorityDecision into a concrete, safety-validated AllocationDecision.

Responsibilities
────────────────
1. Accept the proposed target configuration from the priority engine.
2. Run it through the safety manager; reject and fall back if unsafe.
3. Generate the TRANSITION intermediate configuration.
4. Return a fully documented AllocationDecision with before/transition/after.

The allocator is the last safety gate before a lane change is committed.
Even if the priority engine produces a valid-looking proposal, the allocator
re-validates it independently.  Safety has depth-of-defence.
"""

from __future__ import annotations
from typing import List

from src.models import (
    AllocationDecision, LaneFunction, PriorityDecision
)
from src.safety.safety_manager import SafetyManager


# Expected-effect descriptions per action — these are qualitative statements,
# NOT quantitative guarantees.  Actual metrics come from the simulation.
_EFFECTS = {
    "ACTIVATE_BUS_PRIORITY": (
        "Bus queue length and travel time expected to decrease. "
        "General-traffic capacity slightly reduced on one lane."
    ),
    "ACTIVATE_EMERGENCY_CORRIDOR": (
        "Emergency vehicle has an unimpeded corridor through the segment. "
        "General traffic redistributed to remaining lanes."
    ),
    "ACTIVATE_PEDESTRIAN_BUFFER": (
        "Protected pedestrian and cyclist space increased. "
        "Minor vehicle capacity reduction during peak pedestrian period."
    ),
    "MAINTAIN_NORMAL": (
        "System operating in default configuration. "
        "All lanes available for general traffic."
    ),
    "ENFORCE_SAFE_FALLBACK": (
        "Reverted to pre-configured safe default configuration."
    ),
    "SAFE_FALLBACK": (
        "Proposed configuration failed safety check. "
        "Reverted to pre-configured safe default configuration."
    ),
    "NO_CHANGE": (
        "Current configuration already matches the target. No lane change needed."
    ),
}


class LaneAllocator:
    """
    Validates priority-engine proposals and produces AllocationDecisions.
    """

    def __init__(self, config: dict, safety_manager: SafetyManager) -> None:
        self.config         = config
        self.safety_manager = safety_manager

    def allocate(
        self,
        current_config:    List[LaneFunction],
        priority_decision: PriorityDecision,
    ) -> AllocationDecision:
        """
        Determine the concrete lane configuration change.

        Always safe: if the proposed config cannot be validated, the
        allocator falls back to the safe default.
        """

        # ── Path 1: safety engine already flagged an issue ───────────────
        if priority_decision.action == "ENFORCE_SAFE_FALLBACK":
            fallback   = self.safety_manager.get_fallback()
            transition = self.safety_manager.make_transition_config(
                current_config, fallback
            )
            return AllocationDecision(
                previous_config   = list(current_config),
                transition_config = transition,
                new_config        = fallback,
                decision          = "SAFE_FALLBACK",
                reason            = priority_decision.reason,
                expected_effect   = _EFFECTS["SAFE_FALLBACK"],
                is_safe           = True,
                safety_notes      = ["Triggered by safety engine."],
            )

        # ── Path 2: validate the proposed target ─────────────────────────
        target = priority_decision.target_config
        if target is None:
            target = self.safety_manager.get_fallback()

        safety_check = self.safety_manager.assess(target)

        if not safety_check.is_safe:
            fallback   = self.safety_manager.get_fallback()
            transition = self.safety_manager.make_transition_config(
                current_config, fallback
            )
            return AllocationDecision(
                previous_config   = list(current_config),
                transition_config = transition,
                new_config        = fallback,
                decision          = "SAFE_FALLBACK",
                reason            = (
                    "Proposed configuration failed safety validation: "
                    + "; ".join(safety_check.violations)
                    + ". Reverting to safe default."
                ),
                expected_effect   = _EFFECTS["SAFE_FALLBACK"],
                is_safe           = True,
                safety_notes      = safety_check.violations,
            )

        # ── Path 3: no change required ────────────────────────────────────
        if current_config == target:
            return AllocationDecision(
                previous_config   = list(current_config),
                transition_config = list(current_config),
                new_config        = list(target),
                decision          = "NO_CHANGE",
                reason            = priority_decision.reason,
                expected_effect   = _EFFECTS.get("NO_CHANGE", ""),
                is_safe           = True,
                safety_notes      = safety_check.warnings,
            )

        # ── Path 4: valid reconfiguration ─────────────────────────────────
        transition = self.safety_manager.make_transition_config(
            current_config, target
        )
        effect = _EFFECTS.get(priority_decision.action, "Lane reconfiguration in progress.")

        return AllocationDecision(
            previous_config   = list(current_config),
            transition_config = transition,
            new_config        = list(target),
            decision          = priority_decision.action,
            reason            = priority_decision.reason,
            expected_effect   = effect,
            is_safe           = True,
            safety_notes      = safety_check.warnings,
        )
