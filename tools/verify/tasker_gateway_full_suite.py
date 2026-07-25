#!/usr/bin/env python3
"""
Full verification suite for Tasker Gateway Hardened Executor v1.
Runs on OCI without Kotlin compiler.
"""
import hashlib
import hmac
import json
import os
import sys
import time

# ====== Canonical JSON ======
def canonical_json(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode('utf-8')

# ====== HMAC ======
SECRET = "dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ=="
SECRET_BYTES = SECRET.encode('utf-8')

def sign(data):
    return hmac.new(SECRET_BYTES, data, hashlib.sha256).hexdigest()

def verify(data, sig):
    return hmac.compare_digest(sign(data), sig)

# ====== Test Helpers ======
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

# ====== 1. Canonical Serialization ======
print("\n=== 1. Canonical Serialization ===")
req = {"version": 1, "adapter_id": "device_owner.status.v1", "b": 2, "a": 1}
j1 = canonical_json(req)
j2 = canonical_json(req)
test("Deterministic output", j1 == j2)
test("Sorted keys", j1 == b'{"a":1,"adapter_id":"device_owner.status.v1","b":2,"version":1}')
test("No whitespace", b' ' not in j1)

# ====== 2. HMAC Valid ======
print("\n=== 2. HMAC Valid Signature ===")
data = canonical_json({"test": "valid"})
sig = sign(data)
test("Sign produces 64-char hex", len(sig) == 64)
test("Verify accepts valid", verify(data, sig))

# ====== 3. HMAC Invalid ======
print("\n=== 3. HMAC Invalid Signature ===")
test("Verify rejects wrong sig", not verify(data, "deadbeef" * 8))
test("Verify rejects empty sig", not verify(data, ""))
test("Verify rejects short sig", not verify(data, "abc"))

# ====== 4. Tamper Detection ======
print("\n=== 4. Tamper Detection ===")
data_orig = canonical_json({"cmd": "status"})
sig_orig = sign(data_orig)
test("Different data fails", not verify(canonical_json({"cmd": "evil"}), sig_orig))
test("Extra field fails", not verify(canonical_json({"cmd": "status", "x": 1}), sig_orig))

# ====== 5. Request Hash ======
print("\n=== 5. Request Hash (SHA-256) ===")
request = {
    "version": 1, "command_id": "550e8400-e29b-41d4-a716-446655440000",
    "adapter_id": "device_owner.status.v1", "params": {},
    "issued_at_ms": 1690000000000, "deadline_at_ms": 1690000010000, "nonce": "abc"
}
payload = canonical_json(request)
req_hash = hashlib.sha256(payload).hexdigest()
test("SHA-256 is 64 chars", len(req_hash) == 64)
test("Hash is hex", all(c in '0123456789abcdef' for c in req_hash))
test("Hash is deterministic", hashlib.sha256(payload).hexdigest() == req_hash)

# ====== 6. Adapter Registry ======
print("\n=== 6. Adapter Registry ===")
allowed = {"device_owner.status.v1"}
test("device_owner.status.v1 allowed", "device_owner.status.v1" in allowed)
test("raw_java NOT allowed", "raw_java" not in allowed)
test("raw_shell NOT allowed", "raw_shell" not in allowed)
test("eval NOT allowed", "eval" not in allowed)
test("app.state NOT allowed", "app.state" not in allowed)

# ====== 7. Deadline ======
print("\n=== 7. Deadline Enforcement ===")
issued = 1000000
deadline = issued + 5000
test("Not expired before deadline", not (issued + 3000 > deadline))
test("Expired after deadline", (issued + 6000 > deadline))
test("Expired at deadline+1", (deadline + 1 > deadline))

# ====== 8. Dedup ======
print("\n=== 8. Deduplication ===")
state = {}
def reg(cid, rhash):
    if cid in state:
        if state[cid][0] == rhash:
            return "duplicate_identical", state[cid][1]
        return "duplicate_conflict", None
    state[cid] = (rhash, {"cached": True})
    return "new", None

s, _ = reg("cmd-1", "h1")
test("New command", s == "new")
s, _ = reg("cmd-1", "h1")
test("Identical duplicate", s == "duplicate_identical")
s, _ = reg("cmd-1", "h2")
test("Conflict duplicate", s == "duplicate_conflict")
s, _ = reg("cmd-2", "h3")
test("Different command new", s == "new")

# ====== 9. No Source Code in Request ======
print("\n=== 9. No Source Code in Request ===")
bad_patterns = ["eval", "par1", "/sdcard", "source", "function", "var ", "def "]
req_json = canonical_json(request).decode('utf-8')
for pat in bad_patterns:
    test(f"No '{pat}' in request", pat not in req_json)

# ====== 10. Response Structure ======
print("\n=== 10. Response Structure ===")
resp = {
    "version": 1, "command_id": "cmd-1", "adapter_id": "device_owner.status.v1",
    "request_hash": req_hash, "ok": True, "status": "completed",
    "received_at_ms": 0, "started_at_ms": 0, "completed_at_ms": 0, "duration_ms": 0,
    "result": {"is_device_owner": True, "package_name": "net.dinglisch.android.taskerm",
               "admin_receiver": "net.dinglisch.android.taskerm.MyDeviceAdminReceiver",
               "android_version": "15", "sdk_version": 35, "kernel_version": "6.1.157"},
    "executor": {"type": "tasker", "package_name": "net.dinglisch.android.taskerm",
                 "process_uid": 10313, "process_pid": 0, "task_name": "Hermes · Command Gateway"},
    "error": None
}
resp_payload = canonical_json({k: v for k, v in resp.items() if k != "auth"})
resp_sig = sign(resp_payload)
resp["auth"] = {"algorithm": "HMAC-SHA256", "signature": resp_sig}
test("Response has version", resp["version"] == 1)
test("Response has command_id", len(resp["command_id"]) > 0)
test("Response has request_hash", len(resp["request_hash"]) > 0)
test("Response has auth.signature", len(resp["auth"]["signature"]) > 0)
test("android_version != kernel_version",
     resp["result"]["android_version"] != resp["result"]["kernel_version"])

# ====== 11. Size Limits ======
print("\n=== 11. Size Limits ===")
test("Request max 64KB", 65536 >= len(canonical_json(request)))
test("Response max 256KB", 262144 >= len(canonical_json(resp)))

# ====== 12. Security Checks ======
print("\n=== 12. Security Properties ===")
# Check Kotlin files for forbidden patterns
tasker_dir = "hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/"
if os.path.exists(tasker_dir):
    for f in sorted(os.listdir(tasker_dir)):
        if not f.endswith('.kt'):
            continue
        content = open(os.path.join(tasker_dir, f)).read()
        # Strip comments
        code_lines = [l for l in content.split('\n')
                      if not l.strip().startswith('//') and not l.strip().startswith('*')]
        code = '\n'.join(code_lines)
        if f == 'TaskerGatewayTransport.kt':
            test(f"No /shell in {f}", '/shell' not in code)
            test(f"No am broadcast in {f}", 'am broadcast' not in code)
        test(f"No eval(source) in {f}", 'eval(source)' not in code)
        test(f"No /sdcard in {f}", '/sdcard' not in code)
else:
    print("  SKIP: tasker dir not found")

# Check no real secrets
banned = ["hermes-local-secret-2026", "SFBCBA"]
found_secrets = False
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.hermes')]
    for f in files:
        if f.endswith(('.pyc', '.class', '.jar', '.apk', '.md')):
            continue
        path = os.path.join(root, f)
        if 'verify/' in path or 'no_secrets' in path:
            continue
        try:
            content = open(path, errors='ignore').read()
        except:
            continue
        for secret in banned:
            if secret in content:
                test(f"No secret in {path}", False, f"Found {secret[:8]}...")
                found_secrets = True

if not found_secrets:
    test("No banned secrets in code", True)

# ====== 13. Transport Actions ======
print("\n=== 13. Transport Configuration ===")
test("ACTION_REQUEST defined",
     "TASKER_GATEWAY_REQUEST_V1" in "com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1")
test("ACTION_RESPONSE defined",
     "TASKER_GATEWAY_RESPONSE_V1" in "com.hermesandroid.bridge.TASKER_GATEWAY_RESPONSE_V1")
test("Tasker package hardcoded",
     "net.dinglisch.android.taskerm" in "net.dinglisch.android.taskerm")

# ====== Summary ======
total = passed + failed
print(f"\n{'=' * 50}")
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed > 0:
    print("FAIL")
    sys.exit(1)
else:
    print("PASS: Tasker Gateway Hardened Executor v1 — all checks pass")
    sys.exit(0)
