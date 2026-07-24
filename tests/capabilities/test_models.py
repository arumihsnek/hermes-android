"""Tests for capability system models — contracts, authorization, evidence, traces."""

import time
import pytest

from tools.capabilities.models import (
    ActionClassification,
    DeviceFingerprint,
    EvidenceReference,
    ExecutionAuthorization,
    ExecutionTier,
    FailureClass,
    FlowTrace,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
    CapabilityResult,
    create_authorization,
)


# ── Device Fingerprint ───────────────────────────────────────────────────────

class TestDeviceFingerprint:
    def test_digest_is_stable(self):
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.app": "v1"})
        assert fp.digest() == fp.digest()

    def test_digest_changes_with_device_id(self):
        fp1 = DeviceFingerprint("pixel8", "15", 35)
        fp2 = DeviceFingerprint("pixel9", "15", 35)
        assert fp1.digest() != fp2.digest()

    def test_digest_changes_with_packages(self):
        fp1 = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.app": "v1"})
        fp2 = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.app": "v2"})
        assert fp1.digest() != fp2.digest()

    def test_digest_is_deterministic(self):
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.a": "v1", "com.b": "v2"})
        d1 = fp.digest()
        d2 = fp.digest()
        assert d1 == d2
        assert len(d1) == 16


# ── Execution Authorization ──────────────────────────────────────────────────

class TestExecutionAuthorization:
    @pytest.fixture
    def device(self):
        return DeviceFingerprint("pixel8", "15", 35)

    @pytest.fixture
    def auth(self, device):
        return create_authorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer.set",
            recipe_id="android-clock.timer.set.v1",
            recipe_revision="abc123",
            device=device,
            allowed_actions=["open_clock", "set_timer"],
            ttl_seconds=300,
        )

    def test_valid_authorization_passes(self, device, auth):
        result = auth.validate(
            device=device,
            recipe_id="android-clock.timer.set.v1",
            action="open_clock",
            used_nonces=set(),
        )
        assert result is None

    def test_expired_authorization_rejected(self, device):
        auth = ExecutionAuthorization(
            tier=ExecutionTier.CANDIDATE,
            capability="timer.set",
            recipe_id="r1",
            recipe_revision="rev1",
            device_fingerprint_digest=device.digest(),
            allowed_actions=["a1"],
            nonce="nonce1",
            issued_at=time.time() - 600,
            expires_at=time.time() - 1,
        )
        result = auth.validate(
            device=device,
            recipe_id="r1",
            action="a1",
            used_nonces=set(),
        )
        assert result == FailureClass.AUTHORIZATION_EXPIRED

    def test_replay_rejected(self, device, auth):
        result = auth.validate(
            device=device,
            recipe_id="android-clock.timer.set.v1",
            action="open_clock",
            used_nonces={auth.nonce},
        )
        assert result == FailureClass.AUTHORIZATION_REPLAY

    def test_fingerprint_mismatch_rejected(self, device, auth):
        other_device = DeviceFingerprint("pixel9", "15", 35)
        result = auth.validate(
            device=other_device,
            recipe_id="android-clock.timer.set.v1",
            action="open_clock",
            used_nonces=set(),
        )
        assert result == FailureClass.AUTHORIZATION_FINGERPRINT_MISMATCH

    def test_recipe_mismatch_rejected(self, device, auth):
        result = auth.validate(
            device=device,
            recipe_id="wrong.recipe.v1",
            action="open_clock",
            used_nonces=set(),
        )
        assert result == FailureClass.AUTHORIZATION_RECIPE_MISMATCH

    def test_scope_mismatch_rejected(self, device, auth):
        result = auth.validate(
            device=device,
            recipe_id="android-clock.timer.set.v1",
            action="delete_all_timers",
            used_nonces=set(),
        )
        assert result == FailureClass.AUTHORIZATION_SCOPE_MISMATCH


# ── Evidence References ──────────────────────────────────────────────────────

class TestEvidenceReference:
    def test_create(self):
        ref = EvidenceReference.create("media_session", "Playing track")
        assert len(ref.evidence_id) == 12
        assert ref.observer_type == "media_session"
        assert ref.safe_summary == "Playing track"
        assert ref.timestamp > 0

    def test_summary_truncated(self):
        ref = EvidenceReference.create("notification", "x" * 500)
        assert len(ref.safe_summary) == 200

    def test_frozen(self):
        ref = EvidenceReference.create("node_search", "found")
        with pytest.raises(AttributeError):
            ref.evidence_id = "changed"


# ── Flow Trace ───────────────────────────────────────────────────────────────

class TestFlowTrace:
    def test_add_event(self):
        trace = FlowTrace(trace_id="t1", capability="timer.set", recipe_id="r1")
        evt = trace.add_event("dispatch", {"tool": "android_tap"})
        assert evt.event_type == "dispatch"
        assert len(trace.events) == 1

    def test_to_dict_redacts_evidence(self):
        trace = FlowTrace(trace_id="t1", capability="timer.set", recipe_id="r1")
        ref = EvidenceReference.create("media_session", "Playing")
        trace.add_event("evidence", evidence_refs=[ref])
        d = trace.to_dict()
        assert d["events"][0]["evidence_refs"][0]["evidence_id"] == ref.evidence_id
        assert "safe_summary" in d["events"][0]["evidence_refs"][0]
        # Ensure no raw evidence values leaked
        serialized = str(d)
        assert "Playing" in serialized  # safe_summary is allowed


# ── Capability Result ────────────────────────────────────────────────────────

class TestCapabilityResult:
    def _make_success(self):
        trace = FlowTrace(trace_id="t1", capability="timer.set", recipe_id="r1")
        ref = EvidenceReference.create("notification", "Timer set")
        verifier = VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type="notification",
            evidence_ref=ref,
        )
        return CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability="timer.set",
            trace=trace,
            evidence_refs=[ref],
            final_verifier=verifier,
        )

    def test_success_without_verifier_fails_validation(self):
        trace = FlowTrace(trace_id="t1", capability="x", recipe_id="r1")
        ref = EvidenceReference.create("node_search", "found")
        result = CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability="x",
            trace=trace,
            evidence_refs=[ref],
            final_verifier=None,
        )
        error = result.validate_success()
        assert error is not None
        assert "final_verifier" in error

    def test_success_without_evidence_fails_validation(self):
        trace = FlowTrace(trace_id="t1", capability="x", recipe_id="r1")
        verifier = VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type="media_session",
        )
        result = CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability="x",
            trace=trace,
            evidence_refs=[],
            final_verifier=verifier,
        )
        error = result.validate_success()
        assert error is not None
        assert "evidence" in error

    def test_success_with_inconclusive_verifier_fails_validation(self):
        trace = FlowTrace(trace_id="t1", capability="x", recipe_id="r1")
        ref = EvidenceReference.create("hash", "changed")
        verifier = VerificationResult(
            outcome=VerificationOutcome.INCONCLUSIVE,
            verifier_type="hash",
        )
        result = CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability="x",
            trace=trace,
            evidence_refs=[ref],
            final_verifier=verifier,
        )
        error = result.validate_success()
        assert error is not None
        assert "confirmed" in error

    def test_failure_result_skips_success_validation(self):
        trace = FlowTrace(trace_id="t1", capability="x", recipe_id=None)
        result = CapabilityResult(
            status=ResultStatus.FAILURE,
            capability="x",
            trace=trace,
            failure_class=FailureClass.DEVICE_UNAVAILABLE,
        )
        error = result.validate_success()
        assert error is None

    def test_to_dict_shape(self):
        trace = FlowTrace(trace_id="t1", capability="x", recipe_id="r1")
        ref = EvidenceReference.create("node_search", "ok")
        verifier = VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type="node_search",
        )
        result = CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability="x",
            trace=trace,
            evidence_refs=[ref],
            final_verifier=verifier,
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["final_verifier"]["outcome"] == "confirmed"
        assert len(d["evidence_refs"]) == 1


# ── Failure Classes ──────────────────────────────────────────────────────────

class TestFailureClass:
    def test_all_classes_are_strings(self):
        for fc in FailureClass:
            assert isinstance(fc.value, str)

    def test_no_duplicate_values(self):
        values = [fc.value for fc in FailureClass]
        assert len(values) == len(set(values))
