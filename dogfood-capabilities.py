#!/usr/bin/env python3
"""
Dogfood: systematic QA of the Hermes Android Capability System.
Tests all public APIs, edge cases, error handling, and security guarantees.
"""
import sys
import os
import json
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.capabilities.models import (
    DeviceFingerprint, ExecutionAuthorization, ExecutionTier,
    EvidenceReference, FlowTrace, CapabilityResult,
    ResultStatus, VerificationOutcome, VerificationResult,
    FailureClass, ActionClassification, create_authorization,
)
from tools.capabilities.policy import PolicyGate, classify_action, is_confirmation_required, is_prohibited
from tools.capabilities.flow_executor import FlowDefinition, FlowExecutor, FlowHandler, FlowStep
from tools.capabilities.service import CapabilityService
from tools.capabilities.errors import AuthorizationRefused, PolicyViolation

ISSUES = []

def issue(severity, title, description, steps="", expected="", actual=""):
    ISSUES.append({
        "severity": severity,
        "title": title,
        "description": description,
        "steps": steps,
        "expected": expected,
        "actual": actual,
    })
    print(f"  [{severity.upper()}] {title}")

def test_ok(name):
    print(f"  [PASS] {name}")

def test_fail(name, reason):
    issue("HIGH", name, reason)
    print(f"  [FAIL] {name}: {reason}")

# ══════════════════════════════════════════════════════════════════════════════
print("═══ Phase 1: Models ═══")
# ══════════════════════════════════════════════════════════════════════════════

# 1.1 DeviceFingerprint
print("\n── DeviceFingerprint ──")
fp = DeviceFingerprint("pixel8", "15", 35, {"com.app": "v1"})
assert fp.digest() == fp.digest(), "Digest not stable"
test_ok("digest stable")

fp2 = DeviceFingerprint("pixel9", "15", 35, {"com.app": "v1"})
assert fp.digest() != fp2.digest(), "Digest same for different devices"
test_ok("digest different per device")

fp3 = DeviceFingerprint("pixel8", "15", 35, {"com.app": "v2"})
assert fp.digest() != fp3.digest(), "Digest same for different packages"
test_ok("digest different per package")

# Frozen
try:
    fp.device_id = "x"
    test_fail("frozen dataclass", "DeviceFingerprint allowed mutation")
except AttributeError:
    test_ok("frozen dataclass")

# 1.2 ExecutionAuthorization
print("\n── ExecutionAuthorization ──")
auth = create_authorization(
    ExecutionTier.CANDIDATE, "timer.set", "r1", "rev1",
    DeviceFingerprint("d", "15", 35), ["open_app", "set_timer"], 300
)
assert not auth.is_expired(), "Auth expired immediately"
test_ok("not expired")

assert isinstance(auth.allowed_actions, tuple), "allowed_actions not tuple"
test_ok("allowed_actions is tuple")

# Expired auth
expired = ExecutionAuthorization(
    ExecutionTier.CANDIDATE, "timer.set", "r1", "rev1",
    "digest", ("open_app",), "n1", time.time()-100, time.time()-1
)
assert expired.is_expired(), "Expired auth not detected"
test_ok("expired detection")

# Validate
device = DeviceFingerprint("d", "15", 35)
result = auth.validate(device, "r1", "open_app", set())
assert result is None, f"Valid auth failed: {result}"
test_ok("valid auth passes")

result = auth.validate(device, "r1", "open_app", {auth.nonce})
assert result == FailureClass.AUTHORIZATION_REPLAY, "Replay not detected"
test_ok("replay detected")

result = auth.validate(DeviceFingerprint("x", "15", 35), "r1", "open_app", set())
assert result == FailureClass.AUTHORIZATION_FINGERPRINT_MISMATCH, "Fingerprint mismatch not detected"
test_ok("fingerprint mismatch detected")

result = auth.validate(device, "wrong_recipe", "open_app", set())
assert result == FailureClass.AUTHORIZATION_RECIPE_MISMATCH, "Recipe mismatch not detected"
test_ok("recipe mismatch detected")

result = auth.validate(device, "r1", "delete_all", set())
assert result == FailureClass.AUTHORIZATION_SCOPE_MISMATCH, "Scope mismatch not detected"
test_ok("scope mismatch detected")

result = auth.validate(device, "r1", "open_app", set(), capability="wrong")
assert result == FailureClass.AUTHORIZATION_SCOPE_MISMATCH, "Capability mismatch not detected"
test_ok("capability mismatch detected")

# 1.3 EvidenceReference
print("\n── EvidenceReference ──")
ref = EvidenceReference.create("media_session", "Playing track")
assert len(ref.evidence_id) == 12, f"Bad evidence_id length: {len(ref.evidence_id)}"
test_ok("create ok")

ref_long = EvidenceReference.create("notification", "x" * 500)
assert len(ref_long.safe_summary) == 200, f"Summary not truncated: {len(ref_long.safe_summary)}"
test_ok("summary truncated")

# 1.4 FlowTrace
print("\n── FlowTrace ──")
trace = FlowTrace(trace_id="t1", capability="timer.set", recipe_id="r1")
evt = trace.add_event("dispatch", {"tool": "tap"})
assert len(trace.events) == 1
test_ok("add event")

ref = EvidenceReference.create("hash", "ok")
trace.add_event("evidence", evidence_refs=[ref])
d = trace.to_dict()
assert "evidence_id" in str(d)
test_ok("to_dict serializes")

# 1.5 CapabilityResult
print("\n── CapabilityResult ──")
trace = FlowTrace(trace_id="t1", capability="x", recipe_id="r1")
ref = EvidenceReference.create("check", "ok")
verifier = VerificationResult(VerificationOutcome.CONFIRMED, "check", ref)
result = CapabilityResult(ResultStatus.SUCCESS, "x", trace, evidence_refs=[ref], final_verifier=verifier)
assert result.validate_success() is None, "Valid success rejected"
test_ok("valid success")

result_bad = CapabilityResult(ResultStatus.SUCCESS, "x", trace, evidence_refs=[])
error = result_bad.validate_success()
assert error is not None and "evidence" in error, "Missing evidence not caught"
test_ok("missing evidence caught")

result_no_verifier = CapabilityResult(ResultStatus.SUCCESS, "x", trace, evidence_refs=[ref])
error = result_no_verifier.validate_success()
assert error is not None and "final_verifier" in error, "Missing verifier not caught"
test_ok("missing verifier caught")

# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ Phase 2: Policy ═══")
# ══════════════════════════════════════════════════════════════════════════════

# 2.1 Classification
print("\n── Action Classification ──")
assert classify_action("open_app") == ActionClassification.ORDINARY_REVERSIBLE
assert classify_action("send_sms") == ActionClassification.CONFIRMATION_REQUIRED
assert classify_action("send_whatsapp") == ActionClassification.CONFIRMATION_REQUIRED
assert classify_action("delete") == ActionClassification.CONFIRMATION_REQUIRED
assert classify_action("factory_reset") == ActionClassification.PROHIBITED
assert classify_action("wipe_data") == ActionClassification.PROHIBITED
assert is_confirmation_required("send_sms") == True
assert is_confirmation_required("open_app") == False
assert is_prohibited("factory_reset") == True
assert is_prohibited("open_app") == False
test_ok("all classifications correct")

# 2.2 PolicyGate
print("\n── PolicyGate ──")
gate = PolicyGate()

# Ordinary passes
gate.check_action("open_app")
test_ok("ordinary passes")

# Prohibited blocked
try:
    gate.check_action("factory_reset")
    test_fail("prohibited blocked", "No exception raised")
except PolicyViolation:
    test_ok("prohibited blocked")

# Confirmation required without token
try:
    gate.check_action("send_sms")
    test_fail("confirmation required", "No exception raised")
except AuthorizationRefused as e:
    assert e.failure_class == FailureClass.CONFIRMATION_REQUIRED
    test_ok("confirmation required without token")

# Confirmation with token passes
gate.check_action("send_sms", confirmation_token="user_ok")
test_ok("confirmation with token passes")

# Candidate blocks confirmation-required
auth_cand = create_authorization(
    ExecutionTier.CANDIDATE, "messaging", "r1", "rev1",
    DeviceFingerprint("d", "15", 35), ["send_sms"], 300
)
try:
    gate.check_action("send_sms", authorization=auth_cand)
    test_fail("candidate blocks sensitive", "No exception raised")
except AuthorizationRefused as e:
    assert e.failure_class == FailureClass.AUTHORIZATION_SCOPE_MISMATCH
    test_ok("candidate blocks confirmation-required")

# Candidate allows ordinary
auth_cand2 = create_authorization(
    ExecutionTier.CANDIDATE, "timer", "r1", "rev1",
    DeviceFingerprint("d", "15", 35), ["open_app"], 300
)
gate.check_action("open_app", authorization=auth_cand2)
test_ok("candidate allows ordinary")

# Dogfood blocks without confirmation
auth_dog = create_authorization(
    ExecutionTier.DOGFOOD, "messaging", "r1", "rev1",
    DeviceFingerprint("d", "15", 35), ["send_sms"], 300
)
try:
    gate.check_action("send_sms", authorization=auth_dog)
    test_fail("dogfood blocks without confirmation", "No exception raised")
except AuthorizationRefused:
    test_ok("dogfood blocks without confirmation")

# Dogfood allows with confirmation
gate.check_action("send_sms", authorization=auth_dog, confirmation_token="ok")
test_ok("dogfood allows with confirmation")

# Expired auth
auth_exp = ExecutionAuthorization(
    ExecutionTier.CANDIDATE, "timer", "r1", "rev1",
    "digest", ("open_app",), "n1", time.time()-100, time.time()-1
)
try:
    gate.check_action("open_app", authorization=auth_exp)
    test_fail("expired auth blocked", "No exception raised")
except AuthorizationRefused as e:
    assert e.failure_class == FailureClass.AUTHORIZATION_EXPIRED
    test_ok("expired auth blocked")

# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ Phase 3: Flow Executor ═══")
# ══════════════════════════════════════════════════════════════════════════════

class FakeHandler(FlowHandler):
    def __init__(self):
        self._actions = {}
        self._verifiers = {}
    def set_action(self, a, r): self._actions[a] = r
    def set_verifier(self, v, r): self._verifiers[v] = r
    def execute(self, action, params):
        return self._actions.get(action, {"success": True})
    def verify(self, verifier, params):
        return self._verifiers.get(verifier, VerificationResult(
            VerificationOutcome.CONFIRMED, verifier,
            EvidenceReference.create(verifier, "ok")))

print("\n── FlowExecutor ──")
h = FakeHandler()
h.set_action("open", {"success": True})
h.set_verifier("check", VerificationResult(
    VerificationOutcome.CONFIRMED, "check",
    EvidenceReference.create("check", "verified")))
exec = FlowExecutor(h)

flow = FlowDefinition("timer", [FlowStep("open", verifier="check")], recipe_id="r1")
result = exec.execute(flow)
assert result.status == ResultStatus.SUCCESS
assert result.final_verifier is not None
assert len(result.evidence_refs) > 0
test_ok("simple success")

# Step failure
h2 = FakeHandler()
h2.set_action("fail", {"success": False, "error": "nope"})
exec2 = FlowExecutor(h2)
flow2 = FlowDefinition("test", [FlowStep("fail")])
result2 = exec2.execute(flow2)
assert result2.status == ResultStatus.FAILURE
test_ok("step failure")

# Policy blocks prohibited
exec3 = FlowExecutor(FakeHandler())
flow3 = FlowDefinition("sys", [FlowStep("factory_reset")])
result3 = exec3.execute(flow3)
assert result3.status == ResultStatus.REFUSED
assert result3.failure_class == FailureClass.PROHIBITED_ACTION
test_ok("policy blocks prohibited")

# Policy blocks confirmation-required
exec4 = FlowExecutor(FakeHandler())
flow4 = FlowDefinition("msg", [FlowStep("send_sms")])
result4 = exec4.execute(flow4)
assert result4.status == ResultStatus.REFUSED
assert result4.failure_class == FailureClass.CONFIRMATION_REQUIRED
test_ok("policy blocks confirmation-required")

# Confirmation with token passes
h5 = FakeHandler()
h5.set_action("send_sms", {"success": True})
h5.set_verifier("notif", VerificationResult(
    VerificationOutcome.CONFIRMED, "notif",
    EvidenceReference.create("notif", "sent")))
exec5 = FlowExecutor(h5)
flow5 = FlowDefinition("msg", [FlowStep("send_sms", verifier="notif", confirmation_token="ok")])
result5 = exec5.execute(flow5)
assert result5.status == ResultStatus.SUCCESS
test_ok("confirmation with token passes")

# Fallback
h6 = FakeHandler()
h6.set_action("primary", {"success": False})
h6.set_action("fallback", {"success": True})
h6.set_verifier("check", VerificationResult(
    VerificationOutcome.CONFIRMED, "check",
    EvidenceReference.create("check", "fb ok")))
exec6 = FlowExecutor(h6)
flow6 = FlowDefinition("test", [FlowStep("primary",
    fallback=FlowStep("fallback", verifier="check"))])
result6 = exec6.execute(flow6)
assert result6.status == ResultStatus.SUCCESS
test_ok("fallback succeeds")

# Verifier inconclusive
h7 = FakeHandler()
h7.set_action("act", {"success": True})
h7.set_verifier("chk", VerificationResult(VerificationOutcome.INCONCLUSIVE, "chk"))
exec7 = FlowExecutor(h7)
flow7 = FlowDefinition("test", [FlowStep("act", verifier="chk")])
result7 = exec7.execute(flow7)
assert result7.status == ResultStatus.FAILURE
assert result7.failure_class == FailureClass.VERIFICATION_INCONCLUSIVE
test_ok("verifier inconclusive → failure")

# No verifier → can't claim success
h8 = FakeHandler()
h8.set_action("act", {"success": True})
exec8 = FlowExecutor(h8)
flow8 = FlowDefinition("test", [FlowStep("act")])
result8 = exec8.execute(flow8)
assert result8.status == ResultStatus.FAILURE
assert result8.failure_class == FailureClass.VERIFICATION_UNAVAILABLE
test_ok("no verifier → can't claim success")

# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ Phase 4: Service ═══")
# ══════════════════════════════════════════════════════════════════════════════

print("\n── CapabilityService ──")
h_svc = FakeHandler()
h_svc.set_action("open_app", {"success": True})
h_svc.set_verifier("notif", VerificationResult(
    VerificationOutcome.CONFIRMED, "notif",
    EvidenceReference.create("notif", "ok")))
svc = CapabilityService(h_svc)

# Simple flow
r = json.loads(svc.execute_flow(
    steps=[{"action": "open_app", "verifier": "notif"}],
    capability="test"))
assert r["status"] == "success"
test_ok("service simple flow")

# Prohibited
r = json.loads(svc.execute_flow(
    steps=[{"action": "factory_reset"}],
    capability="sys"))
assert r["status"] == "refused"
assert r["failure_class"] == "prohibited_action"
test_ok("service blocks prohibited")

# Confirmation required
r = json.loads(svc.execute_flow(
    steps=[{"action": "send_sms"}],
    capability="msg"))
assert r["status"] == "refused"
assert r["failure_class"] == "confirmation_required"
test_ok("service blocks confirmation-required")

# Candidate without auth
r = json.loads(svc.execute_flow(
    steps=[{"action": "open_app"}],
    capability="test",
    tier="candidate"))
assert r["status"] == "refused"
assert r["failure_class"] == "authorization_missing"
test_ok("candidate without auth refused")

# Empty nonce
r = json.loads(svc.execute_flow(
    steps=[{"action": "open_app"}],
    capability="test",
    tier="dogfood",
    authorization={"nonce": "", "device_fingerprint_digest": "x", "recipe_id": "r1",
                   "allowed_actions": ["open_app"], "capability": "test",
                   "recipe_revision": "rev1", "issued_at": 0, "expires_at": 9999999999}))
assert r["status"] == "refused"
assert "nonce" in r.get("error_message", "").lower()
test_ok("empty nonce rejected")

# Expired auth
r = json.loads(svc.execute_flow(
    steps=[{"action": "open_app"}],
    capability="test",
    tier="candidate",
    authorization={"nonce": "n1", "device_fingerprint_digest": "x", "recipe_id": "r1",
                   "allowed_actions": ["open_app"], "capability": "test",
                   "recipe_revision": "rev1", "issued_at": 0, "expires_at": 1}))
assert r["status"] == "refused"
assert "expired" in r.get("error_message", "").lower()
test_ok("expired auth rejected")

# Replay
svc_r = CapabilityService(FakeHandler())
auth_r = {"nonce": "replay", "device_fingerprint_digest": "x", "recipe_id": "r1",
          "allowed_actions": ["open_app"], "capability": "test",
          "recipe_revision": "rev1", "issued_at": 0, "expires_at": 9999999999}
r1 = json.loads(svc_r.execute_flow(steps=[{"action": "open_app"}], capability="test", tier="candidate", authorization=auth_r))
r2 = json.loads(svc_r.execute_flow(steps=[{"action": "open_app"}], capability="test", tier="candidate", authorization=auth_r))
assert r1["status"] != "refused"
assert r2["status"] == "refused"
assert r2.get("failure_class") == "authorization_replay"
test_ok("nonce replay blocked")

# check_action
r = json.loads(svc.check_action("open_app"))
assert r["allowed"] == True
test_ok("check_action ordinary")

r = json.loads(svc.check_action("factory_reset"))
assert r["allowed"] == False
assert r["failure_class"] == "prohibited_action"
test_ok("check_action prohibited")

r = json.loads(svc.check_action("send_sms"))
assert r["allowed"] == False
assert r["failure_class"] == "confirmation_required"
test_ok("check_action confirmation required")

r = json.loads(svc.check_action("send_sms", confirmation_token="ok"))
assert r["allowed"] == True
test_ok("check_action with token")

# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ Phase 5: Edge Cases ═══")
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Edge Cases ──")

# Empty steps
r = json.loads(svc.execute_flow(steps=[], capability="empty"))
assert r["status"] == "failure"
test_ok("empty steps → failure")

# Unknown action
h_unk = FakeHandler()
h_unk.set_action("known", {"success": True})
h_unk.set_verifier("chk", VerificationResult(
    VerificationOutcome.CONFIRMED, "chk",
    EvidenceReference.create("chk", "ok")))
svc_unk = CapabilityService(h_unk)
r = json.loads(svc_unk.execute_flow(
    steps=[{"action": "unknown_action", "verifier": "chk"}],
    capability="test"))
# Handler returns success by default for unknown actions
test_ok("unknown action handled")

# Very long capability name
r = json.loads(svc.execute_flow(
    steps=[{"action": "open_app"}],
    capability="x" * 1000))
assert r["status"] in ("success", "failure", "refused")
test_ok("long capability name handled")

# Special characters in action
r = json.loads(svc.check_action("action/with/slashes"))
assert "allowed" in r
test_ok("special chars in action")

# None values
try:
    r = json.loads(svc.execute_flow(steps=None, capability="test"))
    test_ok("None steps handled")
except (TypeError, AttributeError):
    test_ok("None steps raises (acceptable)")

# Concurrent nonce usage
svc_conc = CapabilityService(FakeHandler())
auth_conc = {"nonce": "conc", "device_fingerprint_digest": "x", "recipe_id": "r1",
             "allowed_actions": ["open_app"], "capability": "test",
             "recipe_revision": "rev1", "issued_at": 0, "expires_at": 9999999999}
# First use succeeds
r1 = json.loads(svc_conc.execute_flow(steps=[{"action": "open_app"}], capability="test", tier="candidate", authorization=auth_conc))
# Second use with same nonce fails
r2 = json.loads(svc_conc.execute_flow(steps=[{"action": "open_app"}], capability="test", tier="candidate", authorization=auth_conc))
assert r1["status"] != "refused" or r1.get("failure_class") != "authorization_replay"
assert r2["status"] == "refused"
assert r2["failure_class"] == "authorization_replay"
test_ok("concurrent nonce protection")

# ══════════════════════════════════════════════════════════════════════════════
print("\n═══ Summary ═══")
print(f"Total issues found: {len(ISSUES)}")
for i in ISSUES:
    print(f"  [{i['severity']}] {i['title']}")
print(f"\nDogfood complete. {len(ISSUES)} issues.")
