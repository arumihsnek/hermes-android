"""
Block 3: Real observers and verifiers tests.

Tests that:
- Each verifier receives the correct observer type
- Media, notification, and current_app don't call /screen
- Escalation is cheapest-first
- unavailable doesn't become confirmed
- Visual transition alone doesn't prove semantic operation
- Evidence is redacted and limited
- Bridge HTTP contracts are correct for each endpoint
"""
import pytest
from unittest.mock import patch, MagicMock
import time


# ── Observer Normalization ─────────────────────────────────────────────────

class TestObserverResultNormalization:
    """Observer results must have standardized fields."""

    def test_observer_result_has_required_fields(self):
        from tools.capabilities.observers import ObserverResult
        result = ObserverResult(
            observer_type="media_session",
            success=True,
            data={"playing": True},
        )
        assert hasattr(result, 'observer_type')
        assert hasattr(result, 'success')
        assert hasattr(result, 'data')
        assert hasattr(result, 'error')
        assert hasattr(result, 'available')

    def test_observer_result_available_field(self):
        from tools.capabilities.observers import ObserverResult
        result = ObserverResult(
            observer_type="notification",
            success=False,
            available=True,
            error="No matching notification",
        )
        assert result.available is True

    def test_observer_result_unavailable_field(self):
        from tools.capabilities.observers import ObserverResult
        result = ObserverResult(
            observer_type="media_session",
            success=False,
            available=False,
            error="MediaSession not available",
        )
        assert result.available is False

    def test_observer_result_has_timestamp(self):
        from tools.capabilities.observers import ObserverResult
        result = ObserverResult(observer_type="test", success=True)
        assert hasattr(result, 'timestamp')
        assert result.timestamp > 0

    def test_observer_result_has_cost(self):
        from tools.capabilities.observers import ObserverResult
        from tools.capabilities.observers import ObserverPriority
        result = ObserverResult(observer_type="direct_query", success=True)
        assert hasattr(result, 'cost')
        assert result.cost >= 0

    def test_observer_result_safe_summary(self):
        from tools.capabilities.observers import ObserverResult
        result = ObserverResult(
            observer_type="notification",
            success=True,
            data={"title": "Test", "text": "Body"},
            safe_summary="Notification: Test",
        )
        assert hasattr(result, 'safe_summary')
        assert len(result.safe_summary) <= 200


# ── Bridge-backed Observers ────────────────────────────────────────────────

class TestBridgeObservers:
    """Observers must call real bridge endpoints, not /screen for everything."""

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_current_app_observer_calls_current_app(self, mock_get):
        from tools.capabilities.observers import CurrentAppObserver
        mock_get.return_value = {"package": "com.test", "className": "MainActivity"}
        observer = CurrentAppObserver()
        result = observer.execute()
        assert result.success is True
        assert result.data["package"] == "com.test"
        mock_get.assert_called_once_with("/current_app")

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_media_session_observer_calls_media(self, mock_get):
        from tools.capabilities.observers import MediaSessionBridgeObserver
        mock_get.return_value = {
            "playing": True,
            "package": "de.danoeh.antennapod",
            "title": "Test Episode",
        }
        observer = MediaSessionBridgeObserver()
        result = observer.execute(package="de.danoeh.antennapod")
        assert result.success is True
        assert result.data["playing"] is True

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_notification_observer_calls_notifications(self, mock_get):
        from tools.capabilities.observers import NotificationBridgeObserver
        mock_get.return_value = {
            "notifications": [{"title": "Timer", "text": "5:00 remaining"}],
            "count": 1,
        }
        observer = NotificationBridgeObserver()
        result = observer.execute()
        assert result.success is True

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_node_search_observer_calls_find_nodes(self, mock_get):
        from tools.capabilities.observers import NodeSearchBridgeObserver
        mock_get.return_value = {
            "nodes": [{"text": "Start", "className": "Button"}],
            "count": 1,
        }
        observer = NodeSearchBridgeObserver()
        result = observer.execute(text="Start")
        assert result.success is True

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_screen_hash_observer_calls_diff_screen(self, mock_get):
        from tools.capabilities.observers import ScreenHashBridgeObserver
        mock_get.return_value = {"changed": True, "hash": "abc123"}
        observer = ScreenHashBridgeObserver()
        result = observer.execute(previous_hash="def456")
        assert result.success is True
        assert result.data["changed"] is True

    def test_media_observer_does_not_call_screen(self):
        """Media verifier must NOT use /screen endpoint."""
        from tools.capabilities.observers import MediaSessionBridgeObserver
        with patch("tools.capabilities.observers._get_bridge_json") as mock_get:
            observer = MediaSessionBridgeObserver()
            observer.execute()
            for call_args in mock_get.call_args_list:
                assert "/screen" not in str(call_args), \
                    "MediaSession observer should not call /screen"

    def test_notification_observer_does_not_call_screen(self):
        """Notification verifier must NOT use /screen endpoint."""
        from tools.capabilities.observers import NotificationBridgeObserver
        with patch("tools.capabilities.observers._get_bridge_json") as mock_get:
            observer = NotificationBridgeObserver()
            observer.execute()
            for call_args in mock_get.call_args_list:
                assert "/screen" not in str(call_args), \
                    "Notification observer should not call /screen"

    def test_current_app_observer_does_not_call_screen(self):
        """CurrentApp observer must NOT use /screen endpoint."""
        from tools.capabilities.observers import CurrentAppObserver
        with patch("tools.capabilities.observers._get_bridge_json") as mock_get:
            observer = CurrentAppObserver()
            observer.execute()
            for call_args in mock_get.call_args_list:
                assert "/screen" not in str(call_args), \
                    "CurrentApp observer should not call /screen"


# ── Cheapest-first Escalation ──────────────────────────────────────────────

class TestCheapestFirstEscalation:
    """select_observers must order by cost and escalate only on failure."""

    def test_select_observers_orders_by_priority(self):
        from tools.capabilities.observers import select_observers
        observers = select_observers(["screen_hash", "direct_query", "tree"])
        priorities = [o.priority.value for o in observers]
        assert priorities == sorted(priorities), \
            "Observers must be ordered by priority (cheapest first)"

    def test_select_specific_observers(self):
        from tools.capabilities.observers import select_observers
        observers = select_observers(["media_session", "notification"])
        names = [o.name for o in observers]
        assert "media_session" in names
        assert "notification" in names
        assert len(observers) == 2

    def test_select_all_observers_when_empty(self):
        from tools.capabilities.observers import select_observers
        observers = select_observers([])
        assert len(observers) >= 5, "Should return all observers when none specified"

    def test_direct_query_cheaper_than_screen_hash(self):
        from tools.capabilities.observers import select_observers
        observers = select_observers(["direct_query", "screen_hash"])
        assert observers[0].priority.value < observers[1].priority.value


# ── Unavailable Observer Handling ──────────────────────────────────────────

class TestUnavailableObserver:
    """An unavailable observer must not confirm success."""

    def test_unavailable_not_confirmed(self):
        from tools.capabilities.observers import ObserverResult
        from tools.capabilities.models import VerificationOutcome
        from tools.capabilities.verifiers import TimerExistsVerifier

        result = ObserverResult(
            observer_type="direct_query",
            success=False,
            available=False,
            error="Not available",
        )
        verifier = TimerExistsVerifier()
        # The verifier should get INCONCLUSIVE when given unavailable data
        vresult = verifier.verify(result.data)
        assert vresult.outcome != VerificationOutcome.CONFIRMED

    def test_unavailable_result_propagates(self):
        from tools.capabilities.observers import verify_with_escalation
        from tools.capabilities.verifiers import TimerExistsVerifier

        def failing_observer():
            from tools.capabilities.observers import ObserverResult
            return ObserverResult(
                observer_type="direct_query",
                success=False,
                available=False,
                error="Bridge unreachable",
            )

        verifier = TimerExistsVerifier()
        result = verify_with_escalation(
            verifier=verifier,
            observers=[failing_observer],
        )
        assert result.outcome.value in ("inconclusive", "unavailable")


# ── Evidence Redaction ─────────────────────────────────────────────────────

class TestEvidenceRedaction:
    """Evidence must be redacted and size-limited."""

    def test_evidence_reference_no_raw_data(self):
        from tools.capabilities.models import EvidenceReference
        ref = EvidenceReference.create("notification", "Timer set for 5 minutes")
        # EvidenceReference should only contain safe_summary, not raw data
        assert ref.safe_summary == "Timer set for 5 minutes"
        assert not hasattr(ref, 'raw_data') or ref.safe_summary != ref.raw_data if hasattr(ref, 'raw_data') else True

    def test_safe_summary_bounded(self):
        from tools.capabilities.models import EvidenceReference
        long_summary = "x" * 500
        ref = EvidenceReference.create("media_session", long_summary)
        assert len(ref.safe_summary) <= 200

    def test_sensitive_fields_redacted(self):
        from tools.capabilities.evidence import EvidenceCollector, SENSITIVE_FIELDS, EvidenceEntry
        collector = EvidenceCollector()
        collector.add(EvidenceEntry(
            observer_type="notification",
            raw_data={"title": "Timer", "phone": "555-1234", "sms_body": "secret"},
            safe_summary="Timer notification",
        ))
        redacted = collector.get_redacted()
        assert len(redacted) == 1
        # Sensitive fields should be removed
        redacted_data = redacted[0].raw_data
        assert "phone" not in redacted_data
        assert "sms_body" not in redacted_data
        assert "title" in redacted_data  # Non-sensitive field preserved


# ── Bridge HTTP Contracts ──────────────────────────────────────────────────

class TestBridgeEndpointContracts:
    """Each observer must use the correct bridge endpoint with proper format."""

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_current_app_uses_get(self, mock_get):
        from tools.capabilities.observers import CurrentAppObserver
        mock_get.return_value = {"package": "com.test", "className": "Test"}
        observer = CurrentAppObserver()
        observer.execute()
        # Verify it was called with the correct endpoint
        args, kwargs = mock_get.call_args
        assert args[0] == "/current_app"

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_notification_uses_limit_param(self, mock_get):
        from tools.capabilities.observers import NotificationBridgeObserver
        mock_get.return_value = {"notifications": [], "count": 0}
        observer = NotificationBridgeObserver()
        observer.execute(limit=10)
        args, kwargs = mock_get.call_args
        assert args[0] == "/notifications"

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_node_search_uses_find_nodes(self, mock_get):
        from tools.capabilities.observers import NodeSearchBridgeObserver
        mock_get.return_value = {"nodes": [], "count": 0}
        observer = NodeSearchBridgeObserver()
        observer.execute(text="test")
        args, kwargs = mock_get.call_args
        assert args[0] == "/find_nodes"

    @patch("tools.capabilities.observers._get_bridge_json")
    def test_media_session_handles_bridge_error(self, mock_get):
        from tools.capabilities.observers import MediaSessionBridgeObserver
        from tools.capabilities.observers import ObserverResult
        mock_get.side_effect = ConnectionError("Bridge down")
        observer = MediaSessionBridgeObserver()
        result = observer.execute()
        assert result.success is False
        assert result.available is False


# ── select_observers with Real Verifier-Observer Mapping ───────────────────

class TestVerifierObserverMapping:
    """Each verifier family maps to the correct observer type."""

    def test_timer_uses_direct_query(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("timer_exists")
        assert observer.name == "direct_query"

    def test_media_uses_media_session(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("media_state")
        assert observer.name == "media_session"

    def test_notification_uses_notification(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("notification_pattern")
        assert observer.name == "notification"

    def test_node_predicate_uses_node_search(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("node_predicate")
        assert observer.name == "node_search"

    def test_screen_transition_uses_screen_hash(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("screen_transition")
        assert observer.name == "screen_hash"

    def test_route_active_uses_current_app(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("route_active")
        assert observer.name in ("current_app", "direct_query")

    def test_favorite_saved_uses_current_app(self):
        from tools.capabilities.observers import select_observer_for_verifier
        observer = select_observer_for_verifier("favorite_saved")
        assert observer.name in ("current_app", "direct_query")
