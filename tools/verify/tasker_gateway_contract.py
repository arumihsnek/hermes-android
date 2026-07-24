#!/usr/bin/env python3
"""
Verify canonical JSON + HMAC-SHA256 contract for Tasker Gateway.
This is the source of truth for the contract — Kotlin must match.
"""
import hashlib
import hmac
import json
import sys

# ====== Canonical JSON ======
def canonical_json(obj):
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode('utf-8')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sign(data, key):
    return hmac.new(key.encode('utf-8'), data, hashlib.sha256).hexdigest()


def verify(data, key, signature):
    expected = sign(data, key)
    return hmac.compare_digest(expected, signature)


SECRET = "dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ=="

passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}: {detail}")


# ====== 1. Canonical form ======
print("\n=== 1. Canonical JSON ===")
obj = {"version": 1, "b": 2, "a": 1}
j1 = canonical_json(obj)
j2 = canonical_json(obj)
test("Deterministic output", j1 == j2)
test("Sorted keys", j1 == b'{"a":1,"b":2,"version":1}')
test("No whitespace", b' ' not in j1)
test("UTF-8 encoding", isinstance(j1, bytes))

# ====== 2. HMAC round-trip ======
print("\n=== 2. HMAC Round-Trip ===")
data = canonical_json({"test": "hello"})
sig = sign(data, SECRET)
test("Sign produces 64-char hex", len(sig) == 64)
test("Verify accepts valid sig", verify(data, SECRET, sig))

# ====== 3. HMAC rejection ======
print("\n=== 3. HMAC Rejection ===")
test("Rejects wrong sig", not verify(data, SECRET, "deadbeef" * 8))
test("Rejects empty sig", not verify(data, SECRET, ""))
test("Rejects short sig", not verify(data, SECRET, "abc"))
test("Rejects different key", not verify(data, "wrong-key", sig))

# ====== 4. Tamper detection ======
print("\n=== 4. Tamper Detection ===")
data_orig = canonical_json({"cmd": "status"})
sig_orig = sign(data_orig, SECRET)
test("Different data fails", not verify(canonical_json({"cmd": "evil"}), SECRET, sig_orig))
test("Extra field fails", not verify(canonical_json({"cmd": "status", "x": 1}), SECRET, sig_orig))
test("Missing field fails", not verify(canonical_json({}), SECRET, sig_orig))

# ====== 5. Request hash ======
print("\n=== 5. Request Hash (SHA-256) ===")
request = {
    "version": 1,
    "command_id": "550e8400-e29b-41d4-a716-446655440000",
    "adapter_id": "device_owner.status.v1",
    "params": {},
    "issued_at_ms": 1690000000000,
    "deadline_at_ms": 1690000010000,
    "nonce": "abc"
}
payload = canonical_json(request)
req_hash = sha256(payload)
test("SHA-256 is 64 chars", len(req_hash) == 64)
test("Hash is lowercase hex", all(c in '0123456789abcdef' for c in req_hash))
test("Hash is deterministic", sha256(payload) == req_hash)
test("Different data → different hash", sha256(canonical_json({"x": 1})) != req_hash)

# ====== 6. Full signed request ======
print("\n=== 6. Signed Request Construction ===")
sig = sign(payload, SECRET)
signed_request = {
    "version": 1,
    "command_id": request["command_id"],
    "adapter_id": request["adapter_id"],
    "params": request["params"],
    "issued_at_ms": request["issued_at_ms"],
    "deadline_at_ms": request["deadline_at_ms"],
    "nonce": request["nonce"],
    "request_hash": req_hash,
    "auth": {
        "algorithm": "HMAC-SHA256",
        "signature": sig
    }
}
test("Auth algorithm is HMAC-SHA256", signed_request["auth"]["algorithm"] == "HMAC-SHA256")
test("Signature is present", len(signed_request["auth"]["signature"]) > 0)

# Verify the payload matches
test("request_hash matches payload", signed_request["request_hash"] == sha256(payload))
test("Signature verifies against payload", verify(payload, SECRET, sig))

# ====== 7. Response signing ======
print("\n=== 7. Response Signing ===")
response = {
    "version": 1,
    "command_id": request["command_id"],
    "adapter_id": "device_owner.status.v1",
    "request_hash": req_hash,
    "ok": True,
    "status": "completed",
    "received_at_ms": 1690000000050,
    "started_at_ms": 1690000000100,
    "completed_at_ms": 1690000000200,
    "duration_ms": 100,
    "result": {"is_device_owner": True},
    "executor": {"type": "tasker"},
    "error": None,
}
# Sign everything except auth
resp_payload = canonical_json(response)
resp_sig = sign(resp_payload, SECRET)
response["auth"] = {"algorithm": "HMAC-SHA256", "signature": resp_sig}
test("Response payload excludes auth", b'"auth"' not in resp_payload)
test("Response signature verifies", verify(resp_payload, SECRET, resp_sig))

# ====== 8. Unicode handling ======
print("\n=== 8. Unicode ===")
unicode_obj = {"name": "Hermes · Gateway", "status": "café"}
j = canonical_json(unicode_obj)
decoded = j.decode('utf-8')
test("Unicode preserved", "Hermes" in decoded and "café" in decoded)
test("Deterministic unicode", canonical_json(unicode_obj) == j)

# ====== 9. No code in request ======
print("\n=== 9. No Source Code in Request ===")
bad = ["eval", "par1", "/sdcard", "source", "function", "var ", "def ", "import "]
req_json = canonical_json(request).decode('utf-8')
for pat in bad:
    test(f"No '{pat}' in request", pat not in req_json)

# ====== Summary ======
total = passed + failed
print(f"\n{'=' * 50}")
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed > 0:
    print("FAIL")
    sys.exit(1)
else:
    print("PASS: Canonical JSON + HMAC contract verified")
    sys.exit(0)
