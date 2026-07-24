"""Tests for Task 7: Observer selection and semantic verifiers."""

import json
import time
import pytest
from typing import Any

from tools.capabilities.observers import (
    Observer,
    ObserverPriority,
    ObserverResult,
    DirectQueryObserver,
    MediaSessionObserver,
    NotificationObserver,
    NodeSearchObserver,
    ScreenHashObserver,
    ScreenshotObserver,
    RecordingObserver,
    select_observers,
)
from tools.capabilities.verifiers import (
    Verifier,
    TimerExistsVerifier,
    MediaStateVerifier,
    NotificationPatternVerifier,
    NodePredicateVerifier,
    ScreenTransitionVerifier,
    verify_flow_outcome,
)
from tools.capabilities.evidence import (
    EvidenceCollector,
    EvidenceEntry,
    RedactedEvidence,
)
from tools.capabilities.models import (
    VerificationOutcome,
    EvidenceReference,
    VerificationResult,
)


# ── Observer Priority Tests ──────────────────────────────────────────────────

class TestObserverPriority:
    """Observers must be ordered by cost (cheapest first)."""

    def test_observer_priorities_defined(self):
        assert ObserverPriority.DIRECT_QUERY.value < ObserverPriority.EVENT.value
        assert ObserverPriority.EVENT.value < ObserverPriority.MEDIA_SESSION.value
        assert ObserverPriority.MEDIA_SESSION.value < ObserverPriority.NOTIFICATION.value
        assert ObserverPriority.NOTIFICATION.value < ObserverPriority.NODE_SEARCH.value
        assert ObserverPriority.NODE_SEARCH.value < ObserverPriority.SCREEN_HASH.value
        assert ObserverPriority.SCREEN_HASH.value < ObserverPriority.TREE.value
        assert ObserverPriority.TREE.value < ObserverPriority.SCREENSHOT.value
        assert ObserverPriority.SCREENSHOT.value < ObserverPriority.RECORDING.value

    def test_select_observers_returns_cheapest_first(self):
        """select_observers should return observers ordered by priority."""
        observers = select_observers(["direct_query", "screenshot", "media_session"])
        priorities = [o.priority for o in observers]
        assert priorities == sorted(priorities)

    def test_select_observers_filters_by_name(self):
        """Only requested observers should be returned."""
        observers = select_observers(["direct_query", "media_session"])
        names = [type(o).__name__ for o in observers]
        assert len(names) == 2
        assert "DirectQueryObserver" in names
        assert "MediaSessionObserver" in names

    def test_select_observers_all_when_empty_list(self):
        """Empty list means all available observers."""
        observers = select_observers([])
        assert len(observers) >= 6


# ── Observer Query Tests ─────────────────────────────────────────────────────

class TestDirectQueryObserver:
    """Direct query is the cheapest observer."""

    def test_execute_returns_result(self):
        obs = DirectQueryObserver()
        result = obs.execute(package="com.example", query="timer_state")
        assert isinstance(result, ObserverResult)
        assert result.observer_type == "direct_query"

    def test_execute_with_success(self):
        obs = DirectQueryObserver()
        result = obs.execute(package="com.example", query="timer_state",
                            mock_data={"timer_active": True})
        assert result.success is True
        assert result.data == {"timer_active": True}

    def test_execute_with_failure(self):
        obs = DirectQueryObserver()
        result = obs.execute(package="com.example", query="nonexistent")
        assert result.success is False


class TestMediaSessionObserver:
    """Media session observer queries active media sessions."""

    def test_execute_returns_media_data(self):
        obs = MediaSessionObserver()
        result = obs.execute(package="com.antennapod",
                            mock_data={"title": "Test Podcast", "playing": True})
        assert result.success is True
        assert result.data["title"] == "Test Podcast"
        assert result.data["playing"] is True

    def test_execute_filters_by_package(self):
        obs = MediaSessionObserver()
        result = obs.execute(package="com.wrong.app",
                            mock_data={"title": "Test", "package": "com.antennapod"})
        assert result.success is False


class TestNotificationObserver:
    """Notification observer reads notification content."""

    def test_execute_returns_notification(self):
        obs = NotificationObserver()
        result = obs.execute(package="com.example",
                            mock_data={"title": "Timer", "text": "05:00 remaining"})
        assert result.success is True
        assert "Timer" in result.data["title"]

    def test_execute_filters_by_package(self):
        obs = NotificationObserver()
        result = obs.execute(package="com.example",
                            mock_data={"title": "Other", "package": "com.other"})
        assert result.success is False


class TestNodeSearchObserver:
    """Node search reads accessibility tree nodes."""

    def test_execute_finds_node(self):
        obs = NodeSearchObserver()
        result = obs.execute(text="Pause",
                            mock_nodes=[{"id": 1, "text": "Pause", "clickable": True}])
        assert result.success is True
        assert result.data["text"] == "Pause"

    def test_execute_no_match(self):
        obs = NodeSearchObserver()
        result = obs.execute(text="Nonexistent",
                            mock_nodes=[{"id": 1, "text": "Play"}])
        assert result.success is False


class TestScreenHashObserver:
    """Screen hash detects visual changes."""

    def test_execute_detects_change(self):
        obs = ScreenHashObserver()
        result = obs.execute(previous_hash="abc123",
                            mock_current_hash="def456")
        assert result.success is True
        assert result.data["changed"] is True

    def test_execute_no_change(self):
        obs = ScreenHashObserver()
        result = obs.execute(previous_hash="abc123",
                            mock_current_hash="abc123")
        assert result.success is True
        assert result.data["changed"] is False


class TestScreenshotObserver:
    """Screenshot is expensive — used only as last resort."""

    def test_priority_is_high(self):
        obs = ScreenshotObserver()
        assert obs.priority.value >= ObserverPriority.SCREENSHOT.value


# ── Verifier Tests ───────────────────────────────────────────────────────────

class TestTimerExistsVerifier:
    """Verify a timer exists and is running."""

    def test_confirmed_when_timer_active(self):
        v = TimerExistsVerifier()
        result = v.verify(observer_data={"timer_active": True, "remaining_ms": 30000})
        assert result.outcome == VerificationOutcome.CONFIRMED
        assert result.evidence_ref is not None

    def test_inconclusive_when_no_data(self):
        v = TimerExistsVerifier()
        result = v.verify(observer_data={})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE

    def test_refuted_when_timer_not_active(self):
        v = TimerExistsVerifier()
        result = v.verify(observer_data={"timer_active": False})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE


class TestMediaStateVerifier:
    """Verify media is playing with expected metadata."""

    def test_confirmed_when_playing(self):
        v = MediaStateVerifier(expected_title="Test Song")
        result = v.verify(observer_data={"playing": True, "title": "Test Song"})
        assert result.outcome == VerificationOutcome.CONFIRMED

    def test_refuted_when_not_playing(self):
        v = MediaStateVerifier(expected_title="Test Song")
        result = v.verify(observer_data={"playing": False, "title": "Test Song"})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE

    def test_confirmed_when_title_matches(self):
        v = MediaStateVerifier(expected_title="Podcast")
        result = v.verify(observer_data={"playing": True, "title": "Podcast EP5"})
        assert result.outcome == VerificationOutcome.CONFIRMED

    def test_refuted_when_title_wrong(self):
        v = MediaStateVerifier(expected_title="Song A")
        result = v.verify(observer_data={"playing": True, "title": "Song B"})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE


class TestNotificationPatternVerifier:
    """Verify a notification matching a pattern exists."""

    def test_confirmed_when_pattern_matches(self):
        v = NotificationPatternVerifier(pattern="Timer")
        result = v.verify(observer_data={"title": "Timer", "text": "03:00 left"})
        assert result.outcome == VerificationOutcome.CONFIRMED

    def test_inconclusive_when_no_notification(self):
        v = NotificationPatternVerifier(pattern="Timer")
        result = v.verify(observer_data={})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE


class TestNodePredicateVerifier:
    """Verify a UI node matching a predicate exists."""

    def test_confirmed_when_node_exists(self):
        v = NodePredicateVerifier(text="Pause")
        result = v.verify(observer_data={"nodes": [{"text": "Pause"}]})
        assert result.outcome == VerificationOutcome.CONFIRMED

    def test_refuted_when_node_missing(self):
        v = NodePredicateVerifier(text="Pause")
        result = v.verify(observer_data={"nodes": [{"text": "Play"}]})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE


class TestScreenTransitionVerifier:
    """Verify the screen changed from a previous state."""

    def test_confirmed_on_change(self):
        v = ScreenTransitionVerifier()
        result = v.verify(observer_data={"changed": True})
        assert result.outcome == VerificationOutcome.CONFIRMED

    def test_refuted_on_no_change(self):
        v = ScreenTransitionVerifier()
        result = v.verify(observer_data={"changed": False})
        assert result.outcome == VerificationOutcome.INCONCLUSIVE


class TestVerifyFlowOutcome:
    """Integration: verify_flow_outcome picks the cheapest confirming observer."""

    def test_direct_query_wins(self):
        """Direct query is cheapest — if it confirms, no need for screenshot."""
        observers_used = []
        data = {"timer_active": True}

        def fake_observe(observer_type, **kwargs):
            observers_used.append(observer_type)
            if observer_type == "direct_query":
                return {"timer_active": True}
            return {}

        result = verify_flow_outcome(
            verifiers=[TimerExistsVerifier()],
            observer_data_fn=fake_observe,
            observer_order=["direct_query", "media_session", "screenshot"],
        )
        assert result.outcome == VerificationOutcome.CONFIRMED
        assert "direct_query" in observers_used
        assert "screenshot" not in observers_used

    def test_escalates_to_media_session(self):
        """If direct query fails, try media session."""
        observers_used = []

        def fake_observe(observer_type, **kwargs):
            observers_used.append(observer_type)
            if observer_type == "direct_query":
                return {}  # no data
            if observer_type == "media_session":
                return {"playing": True, "title": "Song"}
            return {}

        result = verify_flow_outcome(
            verifiers=[MediaStateVerifier(expected_title="Song")],
            observer_data_fn=fake_observe,
            observer_order=["direct_query", "media_session", "screenshot"],
        )
        assert result.outcome == VerificationOutcome.CONFIRMED
        assert "direct_query" in observers_used
        assert "media_session" in observers_used
        assert "screenshot" not in observers_used


# ── Evidence Collector Tests ─────────────────────────────────────────────────

class TestEvidenceCollector:
    """Evidence collector stores and redacts evidence entries."""

    def test_add_entry(self):
        collector = EvidenceCollector()
        entry = EvidenceEntry(
            observer_type="media_session",
            raw_data={"title": "Secret Song", "token": "abc123"},
            safe_summary="Media playing",
        )
        collector.add(entry)
        assert len(collector.entries) == 1

    def test_redact_sensitive_fields(self):
        collector = EvidenceCollector()
        entry = EvidenceEntry(
            observer_type="notification",
            raw_data={"title": "Meeting", "phone": "+1234567890", "token": "secret"},
            safe_summary="Notification received",
        )
        collector.add(entry)
        redacted = collector.get_redacted()
        assert len(redacted) == 1
        assert "phone" not in redacted[0].raw_data
        assert "token" not in redacted[0].raw_data

    def test_to_references(self):
        collector = EvidenceCollector()
        entry = EvidenceEntry(
            observer_type="hash",
            raw_data={"hash": "abc"},
            safe_summary="Screen hash",
        )
        collector.add(entry)
        refs = collector.to_references()
        assert len(refs) == 1
        assert isinstance(refs[0], EvidenceReference)
        assert refs[0].observer_type == "hash"
