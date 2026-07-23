"""Tests for safety policy and authorization validation."""

import time
import pytest

from tools.capabilities.errors import AuthorizationRefused, PolicyViolation
from tools.capabilities.models import (
    ActionClassification,
    DeviceFingerprint,
    ExecutionAuthorization,
    ExecutionTier,
    FailureClass,
    create_authorization,
)
from tools.capabilities.policy import (
    PolicyGate,
    classify_action,
    is_confirmation_required,
    is_prohibited,
)


# ── Action Classification ────────────────────────────────────────────────────

class TestActionClassification:
    def test_ordinary_action(self):
        assert classify_action("open_app") == ActionClassification.ORDINARY_REVERSIBLE

    def test_confirmation_required_send(self):
        assert classify_action("send_sms") == ActionClassification.CONFIRMATION_REQUIRED

    def test_confirmation_required_whatsapp(self):
        assert classify_action("send_whatsapp") == ActionClassification.CONFIRMATION_REQUIRED

    def test_confirmation_required_delete(self):
        assert classify_action("delete") == ActionClassification.CONFIRMATION_REQUIRED

    def test_prohibited_factory_reset(self):
        assert classify_action("factory_reset") == ActionClassification.PROHIBITED

    def test_prohibited_wipe_data(self):
        assert classify_action("wipe_data") == ActionClassification.PROHIBITED

    def test_is_confirmation_required(self):
        assert is_confirmation_required("send_sms") is True
        assert is_confirmation_required("open_app") is False

    def test_is_prohibited(self):
        assert is_prohibited("factory_reset") is True
        assert is_prohibited("open_app") is False


# ── Policy Gate ──────────────────────────────────────────────────────────────

class TestPolicyGate:
    @pytest.fixture
    def gate(self):
        return PolicyGate()

    @pytest.fixture
    def device(self):
        return DeviceFingerprint("pixel8", "15", 35)

    def test_ordinary_action_passes(self, gate):
        gate.check_action("open_app")
        # No exception = pass

    def test_prohibited_action_blocked(self, gate):
        with pytest.raises(PolicyViolation) as exc_info:
            gate.check_action("factory_reset")
        assert exc_info.value.classification == ActionClassification.PROHIBITED.value

    def test_confirmation_required_without_token_blocked(self, gate):
        with pytest.raises(AuthorizationRefused) as exc_info:
            gate.check_action("send_sms")
        assert exc_info.value.failure_class == FailureClass.CONFIRMATION_REQUIRED

    def test_confirmation_required_with_token_passes(self, gate):
        gate.check_action("send_sms", confirmation_token="user_confirmed")
        # No exception = pass

    def test_candidate_tier_blocks_confirmation_required(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="messaging",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["send_sms"],
            ttl_seconds=300,
        )
        with pytest.raises(AuthorizationRefused) as exc_info:
            gate.check_action("send_sms", authorization=auth)
        assert exc_info.value.failure_class == FailureClass.AUTHORIZATION_SCOPE_MISMATCH

    def test_candidate_tier_allows_ordinary(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        gate.check_action("open_app", authorization=auth)
        # No exception = pass

    def test_dogfood_tier_allows_confirmation_with_token(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="messaging",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["send_sms"],
            ttl_seconds=300,
        )
        gate.check_action(
            "send_sms",
            authorization=auth,
            confirmation_token="user_confirmed",
        )
        # No exception = pass

    def test_dogfood_tier_blocks_without_confirmation(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="messaging",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["send_sms"],
            ttl_seconds=300,
        )
        with pytest.raises(AuthorizationRefused):
            gate.check_action("send_sms", authorization=auth)

    def test_expired_authorization_rejected(self, gate, device):
        auth = ExecutionAuthorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device_fingerprint_digest=device.digest(),
            allowed_actions=["open_app"],
            nonce="nonce1",
            issued_at=time.time() - 600,
            expires_at=time.time() - 1,
        )
        with pytest.raises(AuthorizationRefused) as exc_info:
            gate.check_action("open_app", authorization=auth)
        assert exc_info.value.failure_class == FailureClass.AUTHORIZATION_EXPIRED

    def test_replay_rejected(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        gate.check_action("open_app", authorization=auth)
        # Second use of same nonce
        with pytest.raises(AuthorizationRefused) as exc_info:
            gate.check_action("open_app", authorization=auth)
        assert exc_info.value.failure_class == FailureClass.AUTHORIZATION_REPLAY

    def test_scope_mismatch_rejected(self, gate, device):
        auth = create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        with pytest.raises(AuthorizationRefused) as exc_info:
            gate.check_action("delete_all_timers", authorization=auth)
        assert exc_info.value.failure_class == FailureClass.AUTHORIZATION_SCOPE_MISMATCH


# ── Validate Authorization ───────────────────────────────────────────────────

class TestValidateAuthorization:
    @pytest.fixture
    def device(self):
        return DeviceFingerprint("pixel8", "15", 35)

    def test_valid(self, device):
        gate = PolicyGate()
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        result = gate.validate_authorization(auth, device.digest(), "r1")
        assert result is None

    def test_expired(self, device):
        gate = PolicyGate()
        auth = ExecutionAuthorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device_fingerprint_digest=device.digest(),
            allowed_actions=["open_app"],
            nonce="nonce1",
            issued_at=time.time() - 600,
            expires_at=time.time() - 1,
        )
        result = gate.validate_authorization(auth, device.digest(), "r1")
        assert result == FailureClass.AUTHORIZATION_EXPIRED

    def test_fingerprint_mismatch(self, device):
        gate = PolicyGate()
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        other = DeviceFingerprint("pixel9", "15", 35)
        result = gate.validate_authorization(auth, other.digest(), "r1")
        assert result == FailureClass.AUTHORIZATION_FINGERPRINT_MISMATCH

    def test_recipe_mismatch(self, device):
        gate = PolicyGate()
        auth = create_authorization(
            tier=ExecutionTier.DOGFOOD,
            capability="timer",
            recipe_id="r1",
            recipe_revision="rev1",
            device=device,
            allowed_actions=["open_app"],
            ttl_seconds=300,
        )
        result = gate.validate_authorization(auth, device.digest(), "wrong_recipe")
        assert result == FailureClass.AUTHORIZATION_RECIPE_MISMATCH
