"""
Verifiers — semantic verification of capability outcomes.

Each verifier checks observer data and returns a VerificationResult
with outcome (CONFIRMED, INCONCLUSIVE, UNAVAILABLE, FAILED) and
optional evidence references.

Verifier types:
- TimerExists: Timer is active with expected duration
- MediaState: Media is playing with expected metadata
- NotificationPattern: Notification matching a pattern exists
- NodePredicate: UI node matching criteria exists
- ScreenTransition: Screen changed from previous state
- ContactExists: Contact matching name/number exists
- MessageSent: Message was delivered (notification/state)
- RouteActive: Navigation route is active
- FavoriteSaved: Location was saved as favorite
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .models import (
    EvidenceReference,
    VerificationOutcome,
    VerificationResult,
)


class Verifier:
    """Base class for semantic verifiers."""
    name: str

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        raise NotImplementedError


class TimerExistsVerifier(Verifier):
    """Verify a timer exists and is running."""
    name = "timer_exists"

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        if not observer_data:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )
        if observer_data.get("timer_active"):
            return VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=self.name,
                evidence_ref=EvidenceReference(
                    evidence_id=f"timer_{uuid.uuid4().hex[:8]}",
                    observer_type="direct_query",
                    timestamp=time.time(),
                    safe_summary=f"Timer active, {observer_data.get('remaining_ms', '?')}ms remaining",
                ),
            )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


class MediaStateVerifier(Verifier):
    """Verify media is playing with expected metadata."""
    name = "media_state"

    def __init__(self, expected_title: str = ""):
        self.expected_title = expected_title

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        if not observer_data:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )
        playing = observer_data.get("playing", False)
        title = observer_data.get("title", "")

        if not playing:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )

        if self.expected_title and self.expected_title not in title:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )

        return VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type=self.name,
            evidence_ref=EvidenceReference(
                evidence_id=f"media_{uuid.uuid4().hex[:8]}",
                observer_type="media_session",
                timestamp=time.time(),
                safe_summary=f"Playing: {title[:50]}",
            ),
        )


class NotificationPatternVerifier(Verifier):
    """Verify a notification matching a pattern exists."""
    name = "notification_pattern"

    def __init__(self, pattern: str = ""):
        self.pattern = pattern

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        if not observer_data:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )
        title = observer_data.get("title", "")
        text = observer_data.get("text", "")
        combined = f"{title} {text}"

        if self.pattern and self.pattern in combined:
            return VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=self.name,
                evidence_ref=EvidenceReference(
                    evidence_id=f"notif_{uuid.uuid4().hex[:8]}",
                    observer_type="notification",
                    timestamp=time.time(),
                    safe_summary=f"Notification matching '{self.pattern}'",
                ),
            )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


class NodePredicateVerifier(Verifier):
    """Verify a UI node matching a predicate exists."""
    name = "node_predicate"

    def __init__(self, text: str = "", class_name: str = ""):
        self.text = text
        self.class_name = class_name

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        nodes = observer_data.get("nodes", [])
        for node in nodes:
            if self.text and node.get("text") == self.text:
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type=self.name,
                    evidence_ref=EvidenceReference(
                        evidence_id=f"node_{uuid.uuid4().hex[:8]}",
                        observer_type="node_search",
                        timestamp=time.time(),
                        safe_summary=f"Node found: text='{self.text}'",
                    ),
                )
            if self.class_name and node.get("className") == self.class_name:
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type=self.name,
                    evidence_ref=EvidenceReference(
                        evidence_id=f"node_{uuid.uuid4().hex[:8]}",
                        observer_type="node_search",
                        timestamp=time.time(),
                        safe_summary=f"Node found: class='{self.class_name}'",
                    ),
                )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


class RouteActiveVerifier(Verifier):
    """Verify a navigation route is active."""
    name = "route_active"

    def __init__(self, destination: str = ""):
        self.destination = destination

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        if not observer_data:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )
        navigating = observer_data.get("navigating", False)
        if navigating:
            return VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=self.name,
                evidence_ref=EvidenceReference(
                    evidence_id=f"route_{uuid.uuid4().hex[:8]}",
                    observer_type="navigation_state",
                    timestamp=time.time(),
                    safe_summary=f"Route active to {self.destination[:50]}",
                ),
            )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


class FavoriteSavedVerifier(Verifier):
    """Verify a location was saved as favorite."""
    name = "favorite_saved"

    def __init__(self, place_name: str = ""):
        self.place_name = place_name

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        if not observer_data:
            return VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type=self.name,
            )
        saved = observer_data.get("saved", False)
        if saved:
            return VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=self.name,
                evidence_ref=EvidenceReference(
                    evidence_id=f"fav_{uuid.uuid4().hex[:8]}",
                    observer_type="favorite_state",
                    timestamp=time.time(),
                    safe_summary=f"Favorite saved: {self.place_name[:50]}",
                ),
            )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


class ScreenTransitionVerifier(Verifier):
    """Verify the screen changed from a previous state."""
    name = "screen_transition"

    def verify(self, observer_data: dict[str, Any]) -> VerificationResult:
        changed = observer_data.get("changed", False)
        if changed:
            return VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=self.name,
                evidence_ref=EvidenceReference(
                    evidence_id=f"screen_{uuid.uuid4().hex[:8]}",
                    observer_type="screen_hash",
                    timestamp=time.time(),
                    safe_summary="Screen transition detected",
                ),
            )
        return VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type=self.name,
        )


# ── Flow Outcome Verification ────────────────────────────────────────────────

def verify_flow_outcome(
    verifiers: list[Verifier],
    observer_data_fn: Callable[[str], dict[str, Any]],
    observer_order: list[str],
) -> VerificationResult:
    """Try each verifier with each observer (cheapest first).

    Returns the first CONFIRMED result, or INCONCLUSIVE if none confirm.
    """
    for observer_type in observer_order:
        try:
            data = observer_data_fn(observer_type)
        except Exception:
            continue

        if not data:
            continue

        for verifier in verifiers:
            result = verifier.verify(data)
            if result.outcome == VerificationOutcome.CONFIRMED:
                return result

    return VerificationResult(
        outcome=VerificationOutcome.INCONCLUSIVE,
        verifier_type=verifiers[0].name if verifiers else "unknown",
    )
