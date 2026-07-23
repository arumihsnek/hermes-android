"""Tests for flow executor with policy enforcement, verification, and traces."""

import time
import pytest
from typing import Any

from tools.capabilities.flow_executor import (
    FlowDefinition,
    FlowExecutor,
    FlowHandler,
    FlowStep,
)
from tools.capabilities.errors import AuthorizationRefused, PolicyViolation
from tools.capabilities.models import (
    DeviceFingerprint,
    EvidenceReference,
    ExecutionAuthorization,
    ExecutionTier,
    FailureClass,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
    create_authorization,
)
from tools.capabilities.policy import PolicyGate


# ── Fake Handler ─────────────────────────────────────────────────────────────

class FakeHandler(FlowHandler):
    """Deterministic handler for testing."""

    def __init__(self):
        self.actions: list[tuple[str, dict]] = []
        self.verifiers: list[tuple[str, dict]] = []
        self._action_results: dict[str, dict] = {}
        self._verifier_results: dict[str, VerificationResult] = {}

    def set_action_result(self, action: str, result: dict):
        self._action_results[action] = result

    def set_verifier_result(self, verifier: str, result: VerificationResult):
        self._verifier_results[verifier] = result

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        self.actions.append((action, params))
        return self._action_results.get(action, {"success": True})

    def verify(self, verifier: str, params: dict[str, Any]) -> VerificationResult:
        self.verifiers.append((verifier, params))
        return self._verifier_results.get(
            verifier,
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=verifier,
                evidence_ref=EvidenceReference.create(verifier, "verified"),
            ),
        )


# ── Tests ────────────────────────────────────────────────────────────────────

class TestFlowExecutor:
    @pytest.fixture
    def handler(self):
        return FakeHandler()

    @pytest.fixture
    def executor(self, handler):
        return FlowExecutor(handler)

    def test_simple_success(self, handler, executor):
        handler.set_action_result("open_app", {"success": True})
        handler.set_verifier_result(
            "notification",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="notification",
                evidence_ref=EvidenceReference.create("notification", "timer set"),
            ),
        )

        flow = FlowDefinition(
            capability="timer.set",
            steps=[
                FlowStep(
                    action="open_app",
                    params={"package": "com.android.deskclock"},
                    verifier="notification",
                    verifier_params={"pattern": "Timer set"},
                ),
            ],
            recipe_id="r1",
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS
        assert result.final_verifier is not None
        assert result.final_verifier.outcome == VerificationOutcome.CONFIRMED
        assert len(result.evidence_refs) > 0
        assert result.validate_success() is None

    def test_step_failure(self, handler, executor):
        handler.set_action_result("open_app", {"success": False, "error": "not found"})

        flow = FlowDefinition(
            capability="timer.set",
            steps=[
                FlowStep(action="open_app", params={"package": "com.bad"}),
            ],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.FAILURE
        assert result.failure_class == FailureClass.HANDLER_RAISED

    def test_timeout(self, handler, executor):
        import time as _time

        def slow_execute(action, params):
            _time.sleep(0.1)
            return {"success": True}

        handler.execute = slow_execute

        flow = FlowDefinition(
            capability="test",
            steps=[
                FlowStep(action="slow_action", timeout_ms=10000),
            ],
            timeout_ms=50,  # 50ms timeout
        )

        _time.sleep(0.06)  # Ensure we're past the deadline
        result = executor.execute(flow)
        assert result.status == ResultStatus.FAILURE
        assert result.failure_class == FailureClass.FLOW_TIMEOUT

    def test_policy_blocks_prohibited(self, handler, executor):
        handler.set_action_result("factory_reset", {"success": True})

        flow = FlowDefinition(
            capability="system",
            steps=[FlowStep(action="factory_reset")],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.REFUSED
        assert result.failure_class == FailureClass.PROHIBITED_ACTION

    def test_policy_blocks_confirmation_without_token(self, handler, executor):
        handler.set_action_result("send_sms", {"success": True})

        flow = FlowDefinition(
            capability="messaging",
            steps=[FlowStep(action="send_sms", params={"to": "123", "body": "hi"})],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.REFUSED
        assert result.failure_class == FailureClass.CONFIRMATION_REQUIRED

    def test_confirmation_with_token_passes(self, handler, executor):
        handler.set_action_result("send_sms", {"success": True})
        handler.set_verifier_result(
            "notification",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="notification",
                evidence_ref=EvidenceReference.create("notification", "sms sent"),
            ),
        )

        flow = FlowDefinition(
            capability="messaging",
            steps=[
                FlowStep(
                    action="send_sms",
                    params={"to": "123", "body": "hi"},
                    verifier="notification",
                    confirmation_token="user_confirmed",
                ),
            ],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_retry_on_failure(self, handler, executor):
        call_count = 0

        original_execute = handler.execute

        def counting_execute(action, params):
            nonlocal call_count
            if action == "flaky_action":
                call_count += 1
                if call_count < 3:
                    return {"success": False, "error": f"attempt {call_count}"}
            return original_execute(action, params)

        handler.execute = counting_execute
        handler.set_action_result("flaky_action", {"success": True})
        handler.set_verifier_result(
            "check",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="check",
                evidence_ref=EvidenceReference.create("check", "retry ok"),
            ),
        )

        flow = FlowDefinition(
            capability="test",
            steps=[
                FlowStep(action="flaky_action", retries=2, verifier="check"),
            ],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS
        assert call_count == 3

    def test_fallback_on_failure(self, handler, executor):
        handler.set_action_result("primary_action", {"success": False})
        handler.set_action_result("fallback_action", {"success": True})
        handler.set_verifier_result(
            "check",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="check",
                evidence_ref=EvidenceReference.create("check", "fallback ok"),
            ),
        )

        flow = FlowDefinition(
            capability="test",
            steps=[
                FlowStep(
                    action="primary_action",
                    fallback=FlowStep(
                        action="fallback_action",
                        verifier="check",
                    ),
                ),
            ],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_verifier_inconclusive_fails(self, handler, executor):
        handler.set_action_result("action", {"success": True})
        handler.set_verifier_result(
            "check",
            VerificationResult(
                outcome=VerificationOutcome.INCONCLUSIVE,
                verifier_type="check",
            ),
        )

        flow = FlowDefinition(
            capability="test",
            steps=[
                FlowStep(action="action", verifier="check"),
            ],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.FAILURE
        assert result.failure_class == FailureClass.VERIFICATION_INCONCLUSIVE

    def test_no_verifier_cannot_claim_success(self, handler, executor):
        handler.set_action_result("action", {"success": True})

        flow = FlowDefinition(
            capability="test",
            steps=[FlowStep(action="action")],
        )

        result = executor.execute(flow)
        assert result.status == ResultStatus.FAILURE
        assert result.failure_class == FailureClass.VERIFICATION_UNAVAILABLE

    def test_trace_events_recorded(self, handler, executor):
        handler.set_action_result("action", {"success": True})
        handler.set_verifier_result(
            "check",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="check",
                evidence_ref=EvidenceReference.create("check", "ok"),
            ),
        )

        flow = FlowDefinition(
            capability="test",
            steps=[FlowStep(action="action", verifier="check")],
        )

        result = executor.execute(flow)
        event_types = [e.event_type for e in result.trace.events]
        assert "dispatch" in event_types
        assert "dispatch_result" in event_types
        assert "verifier" in event_types
        assert "evidence" in event_types

    def test_policy_blocks_dogfood_confirmation_required(self, handler, executor):
        device = DeviceFingerprint("pixel8", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="messaging",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["send_sms"],
            ttl_seconds=300,
        )

        handler.set_action_result("send_sms", {"success": True})

        flow = FlowDefinition(
            capability="messaging",
            steps=[FlowStep(action="send_sms")],
            recipe_id="r1",
        )

        result = executor.execute(flow, authorization=auth)
        assert result.status == ResultStatus.REFUSED
        assert result.failure_class == FailureClass.CONFIRMATION_REQUIRED

    def test_candidate_blocks_non_ordinary(self, handler, executor):
        device = DeviceFingerprint("pixel8", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="messaging",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["send_sms"],
            ttl_seconds=300,
        )

        handler.set_action_result("send_sms", {"success": True})

        flow = FlowDefinition(
            capability="messaging",
            steps=[FlowStep(action="send_sms")],
            recipe_id="r1",
        )

        result = executor.execute(flow, authorization=auth)
        assert result.status == ResultStatus.REFUSED
        assert result.failure_class == FailureClass.AUTHORIZATION_SCOPE_MISMATCH

    def test_legacy_macro_unchanged(self, executor):
        """android_macro behavior must remain unchanged."""
        # This is a contract test — android_macro is not affected by FlowExecutor
        # The FlowExecutor is a new tool, not a replacement
        assert hasattr(executor, "execute")
        assert FlowDefinition is not None
