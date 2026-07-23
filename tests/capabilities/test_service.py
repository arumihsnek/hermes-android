"""Tests for capability service — public entry point for android_flow."""

import json
import time
import pytest

from tools.capabilities.service import CapabilityService
from tools.capabilities.flow_executor import FlowHandler
from tools.capabilities.models import VerificationOutcome, VerificationResult, EvidenceReference


class FakeHandler(FlowHandler):
    def __init__(self):
        self._action_results = {}
        self._verifier_results = {}

    def set_action_result(self, action, result):
        self._action_results[action] = result

    def set_verifier_result(self, verifier, result):
        self._verifier_results[verifier] = result

    def execute(self, action, params):
        return self._action_results.get(action, {"success": True})

    def verify(self, verifier, params):
        return self._verifier_results.get(
            verifier,
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=verifier,
                evidence_ref=EvidenceReference.create(verifier, "ok"),
            ),
        )


class TestCapabilityService:
    @pytest.fixture
    def service(self):
        handler = FakeHandler()
        handler.set_action_result("open_app", {"success": True})
        handler.set_verifier_result(
            "notification",
            VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type="notification",
                evidence_ref=EvidenceReference.create("notification", "timer set"),
            ),
        )
        return CapabilityService(handler)

    def test_execute_simple_flow(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "open_app", "params": {"package": "com.app"}, "verifier": "notification"}],
            capability="test",
        ))
        assert result["status"] == "success"
        assert result["final_verifier"]["outcome"] == "confirmed"
        assert len(result["evidence_refs"]) > 0

    def test_execute_flow_blocked_prohibited(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "factory_reset"}],
            capability="system",
        ))
        assert result["status"] == "refused"
        assert result["failure_class"] == "prohibited_action"

    def test_execute_flow_blocked_confirmation(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "send_sms", "params": {"to": "123"}}],
            capability="messaging",
        ))
        assert result["status"] == "refused"
        assert result["failure_class"] == "confirmation_required"

    def test_execute_flow_with_confirmation(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "send_sms", "params": {"to": "123"}, "confirmation_token": "ok"}],
            capability="messaging",
        ))
        # send_sms needs a verifier too for success
        assert result["status"] == "failure"  # no verifier declared

    def test_check_action_ordinary(self, service):
        result = json.loads(service.check_action("open_app"))
        assert result["allowed"] is True
        assert result["classification"] == "ordinary_reversible"

    def test_check_action_prohibited(self, service):
        result = json.loads(service.check_action("factory_reset"))
        assert result["allowed"] is False
        assert result["failure_class"] == "prohibited_action"

    def test_check_action_confirmation_required(self, service):
        result = json.loads(service.check_action("send_sms"))
        assert result["allowed"] is False
        assert result["failure_class"] == "confirmation_required"

    def test_check_action_with_token(self, service):
        result = json.loads(service.check_action("send_sms", confirmation_token="confirmed"))
        assert result["allowed"] is True

    def test_candidate_tier_blocks_sensitive(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "send_sms"}],
            capability="messaging",
            tier="candidate",
            authorization={
                "capability": "messaging",
                "recipe_id": "r1",
                "recipe_revision": "rev1",
                "device_fingerprint_digest": "abc",
                "allowed_actions": ["send_sms"],
                "nonce": "n1",
                "issued_at": time.time(),
                "expires_at": time.time() + 300,
            },
        ))
        assert result["status"] == "refused"
        assert result["failure_class"] == "authorization_scope_mismatch"

    def test_dogfood_tier_blocks_without_confirmation(self, service):
        result = json.loads(service.execute_flow(
            steps=[{"action": "send_sms"}],
            capability="messaging",
            tier="dogfood",
            authorization={
                "capability": "messaging",
                "recipe_id": "r1",
                "recipe_revision": "rev1",
                "device_fingerprint_digest": "abc",
                "allowed_actions": ["send_sms"],
                "nonce": "n2",
                "issued_at": time.time(),
                "expires_at": time.time() + 300,
            },
        ))
        assert result["status"] == "refused"
        assert result["failure_class"] == "confirmation_required"
