"""
Block 5: Maturity, authorization, and invalidation tests.

Tests that stable/dogfood/candidate tiers, authorization envelopes,
nonce replay protection, and recipe invalidation work end-to-end
with persistence.
"""
import time
import pytest
from unittest.mock import patch, MagicMock


# ── Stable Tier ────────────────────────────────────────────────────────────

class TestStableTier:
    """Stable recipes can execute without authorization envelope."""

    def test_stable_ordinary_action_works(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler, FlowStep

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome, EvidenceReference
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type=verifier,
                    evidence_ref=EvidenceReference.create(verifier, "ok"),
                )

        service = CapabilityService(Handler())
        result = service.execute_flow(
            steps=[{"action": "android_open_app", "params": {"packageName": "com.test"},
                    "verifier": "screen_transition"}],
            capability="test.cap",
            tier="stable",
        )
        import json
        data = json.loads(result)
        assert data["status"] == "success"

    def test_stable_still_subject_to_policy(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        # Prohibited action should be refused even for stable
        result = service.execute_flow(
            steps=[{"action": "factory_reset", "params": {}}],
            capability="test.cap",
            tier="stable",
        )
        import json
        data = json.loads(result)
        assert data["status"] == "refused"

    def test_stable_confirmation_required_needs_token(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        result = service.execute_flow(
            steps=[{"action": "message.send", "params": {"contact": "test", "message": "hi"},
                    "verifier": "notification_pattern"}],
            capability="message.send",
            tier="stable",
        )
        import json
        data = json.loads(result)
        assert data["status"] == "refused"
        assert "confirmation" in data.get("failure_class", "")


# ── Candidate Tier ─────────────────────────────────────────────────────────

class TestCandidateTier:
    """Candidate tier restrictions."""

    def test_candidate_requires_envelope(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        result = service.execute_flow(
            steps=[{"action": "android_open_app", "params": {"packageName": "com.test"},
                    "verifier": "screen_transition"}],
            capability="test.cap",
            tier="candidate",
            # No authorization envelope
        )
        import json
        data = json.loads(result)
        assert data["status"] == "refused"
        assert "authorization" in data.get("failure_class", "") or "envelope" in data.get("error_message", "").lower()

    def test_candidate_cannot_send_messages(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler
        from tools.capabilities.models import DeviceFingerprint, ExecutionTier, create_authorization

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        device = DeviceFingerprint("test", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="message.send",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["message.send"],
            ttl_seconds=300,
        )
        from dataclasses import asdict
        auth_dict = {
            "tier": auth.tier.value,
            "capability": auth.capability,
            "recipe_id": auth.recipe_id,
            "recipe_revision": auth.recipe_revision,
            "device_fingerprint_digest": auth.device_fingerprint_digest,
            "allowed_actions": list(auth.allowed_actions),
            "nonce": auth.nonce,
            "issued_at": auth.issued_at,
            "expires_at": auth.expires_at,
        }
        result = service.execute_flow(
            steps=[{"action": "message.send", "params": {"contact": "test", "message": "hi"},
                    "verifier": "notification_pattern", "confirmation_token": "real_confirmation"}],
            capability="message.send",
            tier="candidate",
            authorization=auth_dict,
        )
        import json
        data = json.loads(result)
        # Candidate tier should block confirmation_required actions
        assert data["status"] == "refused"


# ── Dogfood Tier ───────────────────────────────────────────────────────────

class TestDogfoodTier:
    """Dogfood tier with proper authorization."""

    def test_dogfood_with_valid_envelope_works(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler
        from tools.capabilities.models import DeviceFingerprint, ExecutionTier, create_authorization

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome, EvidenceReference
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type=verifier,
                    evidence_ref=EvidenceReference.create(verifier, "ok"),
                )

        service = CapabilityService(Handler())
        device = DeviceFingerprint("test", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer.set",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["android_send_intent"],
            ttl_seconds=300,
        )
        from dataclasses import asdict
        auth_dict = {
            "tier": auth.tier.value,
            "capability": auth.capability,
            "recipe_id": auth.recipe_id,
            "recipe_revision": auth.recipe_revision,
            "device_fingerprint_digest": auth.device_fingerprint_digest,
            "allowed_actions": list(auth.allowed_actions),
            "nonce": auth.nonce,
            "issued_at": auth.issued_at,
            "expires_at": auth.expires_at,
        }
        result = service.execute_flow(
            steps=[{"action": "android_send_intent", "params": {"action": "SET_TIMER"},
                    "verifier": "timer_exists"}],
            capability="timer.set",
            tier="dogfood",
            authorization=auth_dict,
        )
        import json
        data = json.loads(result)
        assert data["status"] == "success"


# ── Nonce Replay Protection ────────────────────────────────────────────────

class TestNonceReplay:
    """Nonce must not be reusable across instances."""

    def test_nonce_replay_rejected(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler
        from tools.capabilities.models import DeviceFingerprint, ExecutionTier, create_authorization

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome, EvidenceReference
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type=verifier,
                    evidence_ref=EvidenceReference.create(verifier, "ok"),
                )

        service = CapabilityService(Handler())
        device = DeviceFingerprint("test", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer.set",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["android_send_intent"],
            ttl_seconds=300,
        )
        auth_dict = {
            "tier": auth.tier.value,
            "capability": auth.capability,
            "recipe_id": auth.recipe_id,
            "recipe_revision": auth.recipe_revision,
            "device_fingerprint_digest": auth.device_fingerprint_digest,
            "allowed_actions": list(auth.allowed_actions),
            "nonce": auth.nonce,
            "issued_at": auth.issued_at,
            "expires_at": auth.expires_at,
        }

        # First use succeeds
        result1 = service.execute_flow(
            steps=[{"action": "android_send_intent", "params": {"action": "SET_TIMER"},
                    "verifier": "timer_exists"}],
            capability="timer.set",
            tier="dogfood",
            authorization=auth_dict,
        )
        import json
        data1 = json.loads(result1)
        assert data1["status"] == "success"

        # Second use with same nonce should fail
        result2 = service.execute_flow(
            steps=[{"action": "android_send_intent", "params": {"action": "SET_TIMER"},
                    "verifier": "timer_exists"}],
            capability="timer.set",
            tier="dogfood",
            authorization=auth_dict,
        )
        data2 = json.loads(result2)
        assert data2["status"] == "refused"
        assert "replay" in data2.get("failure_class", "").lower()


# ── Authorization Envelope Validation ──────────────────────────────────────

class TestAuthorizationEnvelope:
    """Envelope must bind to correct capability, recipe, and device."""

    def test_wrong_capability_rejected(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler
        from tools.capabilities.models import DeviceFingerprint, ExecutionTier, create_authorization

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        device = DeviceFingerprint("test", "15", 35)
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer.set",  # Bound to timer.set
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["android_open_app"],
            ttl_seconds=300,
        )
        auth_dict = {
            "tier": auth.tier.value,
            "capability": auth.capability,
            "recipe_id": auth.recipe_id,
            "recipe_revision": auth.recipe_revision,
            "device_fingerprint_digest": auth.device_fingerprint_digest,
            "allowed_actions": list(auth.allowed_actions),
            "nonce": auth.nonce,
            "issued_at": auth.issued_at,
            "expires_at": auth.expires_at,
        }
        result = service.execute_flow(
            steps=[{"action": "android_open_app", "params": {"packageName": "com.test"},
                    "verifier": "screen_transition"}],
            capability="media.play",  # Different from auth capability
            tier="dogfood",
            authorization=auth_dict,
        )
        import json
        data = json.loads(result)
        assert data["status"] == "refused"
        assert "mismatch" in data.get("failure_class", "").lower() or "scope" in data.get("failure_class", "").lower()

    def test_expired_envelope_rejected(self):
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.flow_executor import FlowHandler
        from tools.capabilities.models import DeviceFingerprint, ExecutionAuthorization, ExecutionTier

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.CONFIRMED, verifier_type=verifier)

        service = CapabilityService(Handler())
        device = DeviceFingerprint("test", "15", 35)
        auth = ExecutionAuthorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer.set",
            recipe_id="r1",
            recipe_revision="rev1",
            device_fingerprint_digest=device.digest(),
            allowed_actions=("android_send_intent",),
            nonce="expired_nonce",
            issued_at=time.time() - 600,
            expires_at=time.time() - 1,  # Already expired
        )
        auth_dict = {
            "tier": auth.tier.value,
            "capability": auth.capability,
            "recipe_id": auth.recipe_id,
            "recipe_revision": auth.recipe_revision,
            "device_fingerprint_digest": auth.device_fingerprint_digest,
            "allowed_actions": list(auth.allowed_actions),
            "nonce": auth.nonce,
            "issued_at": auth.issued_at,
            "expires_at": auth.expires_at,
        }
        result = service.execute_flow(
            steps=[{"action": "android_send_intent", "params": {"action": "SET_TIMER"},
                    "verifier": "timer_exists"}],
            capability="timer.set",
            tier="dogfood",
            authorization=auth_dict,
        )
        import json
        data = json.loads(result)
        assert data["status"] == "refused"
        assert "expired" in data.get("failure_class", "").lower()


# ── Recipe Invalidation ────────────────────────────────────────────────────

class TestRecipeInvalidation:
    """Recipes should be quarantined after repeated failures."""

    def test_three_failures_trigger_quarantine(self):
        from tools.capabilities.recipe_lifecycle import RecipeLifecycle
        from tools.capabilities.recipes import MaturityState

        lifecycle = RecipeLifecycle()
        lifecycle.record_failure("r1", "permission denied")
        lifecycle.record_failure("r1", "timeout")
        lifecycle.record_failure("r1", "element not found")
        assert lifecycle.should_quarantine("r1") is True

    def test_success_clears_failure_history(self):
        from tools.capabilities.recipe_lifecycle import RecipeLifecycle

        lifecycle = RecipeLifecycle()
        lifecycle.record_failure("r1", "error 1")
        lifecycle.record_failure("r1", "error 2")
        lifecycle.record_success("r1")
        assert lifecycle.failure_count("r1") == 0
        assert lifecycle.should_quarantine("r1") is False

    def test_invalidation_on_version_change(self):
        """Recipe should be invalidated when app version changes."""
        from tools.capabilities.persistence import CapabilityStateStore

        store = CapabilityStateStore(":memory:")
        store.set_recipe_state("r1", "stable")
        # Simulate version change by recording incompatible route
        store.record_incompatible_route(
            capability="timer.set",
            package="com.google.android.deskclock",
            fingerprint_digest="old_fp",
            method="intent",
            failure_reason="version_changed",
        )
        assert store.is_route_incompatible("old_fp", "timer.set", "intent") is True
        store.close()

    def test_quarantine_excludes_from_normal_selection(self):
        """Quarantined recipes should not appear in normal queries."""
        from tools.capabilities.recipes import RecipeRegistry, Recipe, MaturityState

        registry = RecipeRegistry()
        registry.register(Recipe(
            id="r1", capability="timer.set", maturity=MaturityState.STABLE,
            package="com.test",
        ))
        registry.register(Recipe(
            id="r2", capability="timer.set", maturity=MaturityState.QUARANTINED,
            package="com.test",
        ))
        # find_by_capability should only return stable/dogfood
        results = registry.find_by_capability("timer.set")
        ids = [r.id for r in results]
        assert "r1" in ids
        assert "r2" not in ids


# ── Policy on Retries and Fallbacks ────────────────────────────────────────

class TestPolicyOnRetries:
    """Policy must be checked on every dispatch, including retries and fallbacks."""

    def test_policy_blocks_fallback_action(self):
        from tools.capabilities.flow_executor import FlowExecutor, FlowHandler, FlowStep, FlowDefinition
        from tools.capabilities.policy import PolicyGate

        class Handler(FlowHandler):
            def execute(self, action, params):
                return {"success": False, "error": "failed"}
            def verify(self, verifier, params):
                from tools.capabilities.models import VerificationResult, VerificationOutcome
                return VerificationResult(outcome=VerificationOutcome.INCONCLUSIVE, verifier_type=verifier)

        executor = FlowExecutor(Handler(), PolicyGate())
        flow = FlowDefinition(
            capability="test",
            steps=[
                FlowStep(
                    action="android_open_app",
                    params={"packageName": "com.test"},
                    fallback=FlowStep(
                        action="factory_reset",  # Prohibited!
                        params={},
                    ),
                ),
            ],
        )
        result = executor.execute(flow)
        assert result.status.value == "refused"
