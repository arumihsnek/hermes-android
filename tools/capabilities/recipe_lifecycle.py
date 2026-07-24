"""Recipe lifecycle — promotion, quarantine, and maturity management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .recipes import MaturityState, Recipe


# Promotion thresholds
_PROMOTE_TO_DOGFOOD_MIN_RUNS = 3
_PROMOTE_TO_STABLE_MIN_RUNS = 5
_MAX_FALSE_POSITIVE_RATE = 0.0  # zero tolerance for promotion
_QUARANTINE_FAILURE_THRESHOLD = 3


@dataclass
class PromotionEvidence:
    """Evidence required for recipe promotion."""
    successful_runs: int
    false_positives: int
    last_success_time: float
    required_min_runs: int = 0

    @property
    def false_positive_rate(self) -> float:
        total = self.successful_runs + self.false_positives
        return self.false_positives / total if total > 0 else 1.0


def can_promote(
    evidence: PromotionEvidence,
    from_state: str,
    to_state: str,
) -> bool:
    """Check if a recipe can be promoted based on evidence."""
    if from_state == "candidate" and to_state == "dogfood":
        return (
            evidence.successful_runs >= _PROMOTE_TO_DOGFOOD_MIN_RUNS
            and evidence.false_positives == 0
        )
    if from_state == "dogfood" and to_state == "stable":
        return (
            evidence.successful_runs >= _PROMOTE_TO_STABLE_MIN_RUNS
            and evidence.false_positive_rate <= _MAX_FALSE_POSITIVE_RATE
        )
    return False


class RecipeLifecycle:
    """Tracks recipe lifecycle events and manages quarantine."""

    def __init__(self):
        self._failures: dict[str, list[str]] = {}  # recipe_id -> list of failure reasons
        self._promotions: dict[str, str] = {}  # recipe_id -> current state

    def record_failure(self, recipe_id: str, reason: str) -> None:
        if recipe_id not in self._failures:
            self._failures[recipe_id] = []
        self._failures[recipe_id].append(reason)

    def record_success(self, recipe_id: str) -> None:
        # Clear failure history on success
        self._failures.pop(recipe_id, None)

    def should_quarantine(self, recipe_id: str) -> bool:
        """Check if a recipe should be quarantined due to repeated failures."""
        failures = self._failures.get(recipe_id, [])
        return len(failures) >= _QUARANTINE_FAILURE_THRESHOLD

    def failure_count(self, recipe_id: str) -> int:
        return len(self._failures.get(recipe_id, []))

    def set_state(self, recipe_id: str, state: str) -> None:
        self._promotions[recipe_id] = state

    def get_state(self, recipe_id: str) -> Optional[str]:
        return self._promotions.get(recipe_id)
