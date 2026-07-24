"""Negative learning — record incompatible routes to avoid repeated failures."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IncompatibleRoute:
    """A route that failed for a specific device fingerprint."""
    capability: str
    package: str
    fingerprint_digest: str
    method: str
    failure_reason: str
    evidence: str
    retest_after: str = ""  # e.g. "app_update", "version_bump"
    recorded_at: float = field(default_factory=time.time)

    def is_retestable(self, trigger: str) -> bool:
        """Check if this route can be retried after a specific trigger."""
        return self.retest_after == trigger


class NegativeLearningStore:
    """Store of incompatible routes indexed by fingerprint."""

    def __init__(self):
        self._routes: list[IncompatibleRoute] = []

    def record(self, route: IncompatibleRoute) -> None:
        self._routes.append(route)

    def get_incompatible(
        self,
        fingerprint_digest: str,
        capability: Optional[str] = None,
    ) -> list[IncompatibleRoute]:
        """Get all incompatible routes for a fingerprint."""
        results = []
        for r in self._routes:
            if r.fingerprint_digest != fingerprint_digest:
                continue
            if capability and r.capability != capability:
                continue
            results.append(r)
        return results

    def should_skip(
        self,
        fingerprint_digest: str,
        capability: str,
        method: str,
    ) -> bool:
        """Check if a route should be skipped based on negative learning."""
        for r in self._routes:
            if (r.fingerprint_digest == fingerprint_digest
                    and r.capability == capability
                    and r.method == method):
                return True
        return False

    def count(self) -> int:
        return len(self._routes)
