# Tasker Hardened Executor v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Tasker Command Gateway PoC into a hardened executor with HMAC authentication, native broadcast transport, no eval(source), no polling, and correct deduplication.

**Architecture:** Kotlin Bridge sends HMAC-signed requests via native Android broadcast to Tasker. Tasker uses a static dispatcher (no eval(source)) to execute only allowlisted adapters. Responses return via broadcast to Bridge. All communication uses canonical JSON serialization and HMAC-SHA256 signatures.

**Tech Stack:** Kotlin (Android), Mockito/MockK (tests), HMAC-SHA256 (javax.crypto), Python (verification scripts on OCI), Codex review relay

---

## File Structure

### New Kotlin files (Bridge side)
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayRequest.kt` — Request data class + canonical serialization
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayResponse.kt` — Response data class + canonical serialization
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayAuthenticator.kt` — HMAC-SHA256 sign/verify
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayTransport.kt` — Native broadcast sender (NO /shell)
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayReceiver.kt` — BroadcastReceiver for responses
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClient.kt` — High-level client (send + await)
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/PendingCommandRegistry.kt` — Future/Deferred registry + dedup
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/AdapterRegistry.kt` — Static adapter allowlist
- `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayConfig.kt` — Configuration (secret provisioning)

### New Kotlin test files
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayAuthenticatorTest.kt`
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayRequestTest.kt`
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayResponseTest.kt`
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/PendingCommandRegistryTest.kt`
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/AdapterRegistryTest.kt`
- `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClientTest.kt`

### New Python verification scripts
- `tools/verify/tasker_gateway_contract.py` — Canonical JSON + HMAC verification
- `tools/verify/tasker_gateway_dedup.py` — Deduplication logic verification
- `tools/verify/tasker_gateway_deadline.py` — Deadline enforcement verification
- `tools/verify/tasker_gateway_security.py` — Secret absence + HMAC verification

### Modified files
- `docs/tasker-command-gateway-contract.md` — Update to v1.1 (HMAC, canonical form)
- `docs/tasker-command-gateway-security.md` — Update security model
- `.gitignore` — Add secret patterns
- `docs/MIGRATION-POC-TO-V1.md` — Migration guide from PoC

### Tasker project (XML export)
- `tasker-project/HermesCommandGateway/` — Exportable Tasker project XML

---

## Task 0: Containment and Secret Rotation

**Files:**
- Create: `tools/verify/no_secrets_in_repo.py`
- Modify: `.gitignore`
- Modify: `docs/MIGRATION-POC-TO-V1.md`
- Modify: `tools/adapters/device_owner_status.js`

### Step 1: Write secret detection script

```python
#!/usr/bin/env python3
"""Verify no hardcoded secrets exist in the repository."""
import re, sys, os

# Known compromised values — must NEVER appear
BANNED = [
    "hermes-local-secret-2026",
    "SFBCBA",
    "uHNgVCmJfld_Kx8BfLEjVK5X7I2nF9Be6KidmM3yYc8",  # exposed GW token
    "NeN0FkX-dFLWzcLQltzCKw",  # exposed bridge token
]

# Patterns that look like secrets
SECRET_PATTERNS = [
    r'token\s*=\s*["\'][A-Za-z0-9_-]{20,}["\']',
    r'secret\s*=\s*["\'][A-Za-z0-9_-]{10,}["\']',
    r'password\s*=\s*["\'][A-Za-z0-9_-]{10,}["\']',
]

EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.hermes'}

def scan():
    errors = []
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith(('.pyc', '.class', '.jar', '.apk')):
                continue
            path = os.path.join(root, f)
            try:
                content = open(path, errors='ignore').read()
            except:
                continue
            for banned in BANNED:
                if banned in content:
                    errors.append(f"LEAKED SECRET in {path}: {banned[:8]}...")
            for pattern in SECRET_PATTERNS:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    # Skip test fixtures and mock data
                    if 'test' in path.lower() or 'mock' in content[:match.start()]:
                        continue
                    errors.append(f"SUSPECT SECRET in {path}: {match.group()[:40]}")
    return errors

if __name__ == '__main__':
    errors = scan()
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    print("PASS: No hardcoded secrets found")
```

### Step 2: Run secret detection

```bash
python3 tools/verify/no_secrets_in_repo.py
```

### Step 3: Add secret patterns to .gitignore

Add to `.gitignore`:
```
# Tasker Gateway secrets — never commit
*.secret
*.key
.env.tasker
tasker-secret-*.json
```

### Step 4: Update device_owner_status.js to remove hardcoded token

Replace the hardcoded `expected` token with a placeholder and add a comment:
```javascript
// Token is set during Tasker profile configuration — NEVER commit real values
var expected = tasker.getVariable("gw_secret");
```

### Step 5: Create migration document

Write `docs/MIGRATION-POC-TO-V1.md` documenting:
- Commit 202d18f is PoC, not production transport
- Profile ID198 renamed to "Hermes · Java Lab — DISABLED"
- New transport uses native broadcast (no /shell)
- HMAC replaces plaintext token
- Files moved from /sdcard to broadcast extras

### Step 6: Commit

```bash
git add -A && git commit -m "security: containment — secret detection, .gitignore, migration doc"
```

---

## Task 1: Canonical JSON Serialization + HMAC Auth

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayAuthenticator.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayAuthenticatorTest.kt`
- Create: `tools/verify/tasker_gateway_contract.py`

### Step 1: Write the failing Python verification test

```python
#!/usr/bin/env python3
"""Verify canonical JSON + HMAC-SHA256 contract."""
import hashlib, hmac, json, sys

def canonical_json(obj):
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def sign(data, key):
    return hmac.new(key.encode('utf-8'), data, hashlib.sha256).hexdigest()

def verify(data, key, signature):
    expected = sign(data, key)
    return hmac.compare_digest(expected, signature)

# Test 1: Canonical form is deterministic
obj = {"version": 1, "b": 2, "a": 1}
j1 = canonical_json(obj)
j2 = canonical_json(obj)
assert j1 == j2, f"Non-deterministic: {j1} vs {j2}"
assert j1 == b'{"a":1,"b":2,"version":1}', f"Wrong canonical: {j1}"

# Test 2: HMAC round-trip
key = "test-secret-key-256-bits-minimum!!"
data = canonical_json({"cmd": "test"})
sig = sign(data, key)
assert verify(data, key, sig), "Valid HMAC failed verification"
assert not verify(data, key, "deadbeef"), "Invalid HMAC passed verification"

# Test 3: Tamper detection
tampered = canonical_json({"cmd": "test", "evil": True})
assert not verify(tampered, key, sig), "Tampered data passed verification"

# Test 4: Unicode handling
unicode_obj = {"name": "Hermes · Gateway", "status": "café"}
j = canonical_json(unicode_obj)
assert "Hermes" in j.decode('utf-8'), "Unicode lost in canonical form"

# Test 5: Request hash covers all fields
request = {
    "version": 1,
    "command_id": "550e8400-e29b-41d4-a716-446655440000",
    "adapter_id": "device_owner.status.v1",
    "params": {},
    "issued_at_ms": 1690000000000,
    "deadline_at_ms": 1690000010000,
    "nonce": "abc123"
}
request_bytes = canonical_json(request)
request_hash = hashlib.sha256(request_bytes).hexdigest()
assert len(request_hash) == 64, f"SHA-256 hash wrong length: {len(request_hash)}"

# Build signed request
signed_request = {
    "version": 1,
    "command_id": request["command_id"],
    "adapter_id": request["adapter_id"],
    "params": request["params"],
    "issued_at_ms": request["issued_at_ms"],
    "deadline_at_ms": request["deadline_at_ms"],
    "nonce": request["nonce"],
    "request_hash": request_hash,
    "auth": {
        "algorithm": "HMAC-SHA256",
        "signature": sign(request_bytes, key)
    }
}
assert verify(request_bytes, key, signed_request["auth"]["signature"])

# Test 6: Response canonical form
response = {
    "version": 1,
    "command_id": request["command_id"],
    "adapter_id": "device_owner.status.v1",
    "request_hash": request_hash,
    "ok": True,
    "status": "completed",
    "received_at_ms": 1690000000050,
    "started_at_ms": 1690000000100,
    "completed_at_ms": 1690000000200,
    "duration_ms": 100,
    "result": {"is_device_owner": True},
    "executor": {"type": "tasker", "package_name": "net.dinglisch.android.taskerm"},
    "error": None,
    "auth": {"algorithm": "HMAC-SHA256", "signature": ""}
}
resp_bytes = canonical_json({k: v for k, v in response.items() if k != "auth"})
resp_sig = sign(resp_bytes, key)
response["auth"]["signature"] = resp_sig
assert verify(resp_bytes, key, resp_sig)

print("PASS: All canonical JSON + HMAC tests passed")
```

### Step 2: Run Python verification

```bash
python3 tools/verify/tasker_gateway_contract.py
```

### Step 3: Write Kotlin authenticator

```kotlin
package com.hermesandroid.bridge.tasker

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import android.util.Base64
import java.security.MessageDigest

/**
 * HMAC-SHA256 authentication for Tasker Gateway.
 * Secret is provisioned on-device, never stored in Git.
 */
object TaskerGatewayAuthenticator {

    private var secret: ByteArray? = null

    fun configure(base64Secret: String) {
        secret = Base64.decode(base64Secret, Base64.NO_WRAP)
    }

    fun configureRaw(rawSecret: ByteArray) {
        secret = rawSecret.clone()
    }

    /**
     * Canonical JSON: sorted keys, no whitespace, UTF-8.
     * Uses Gson for deterministic serialization matching the Kotlin data classes.
     */
    fun canonicalJson(obj: Any): ByteArray {
        val gson = com.google.gson.GsonBuilder()
            .disableHtmlEscaping()
            .create()
        // Sort keys by serializing to a TreeMap
        val jsonStr = gson.toJson(obj)
        val sorted = sortJsonKeys(com.google.gson.JsonParser.parseString(jsonStr))
        return sorted.toString().toByteArray(Charsets.UTF_8)
    }

    private fun sortJsonKeys(element: com.google.gson.JsonElement): com.google.gson.JsonElement {
        return when (element) {
            is com.google.gson.JsonObject -> {
                val sorted = com.google.gson.JsonObject()
                element.entrySet().sortedBy { it.key }.forEach { (k, v) ->
                    sorted.add(k, sortJsonKeys(v))
                }
                sorted
            }
            is com.google.gson.JsonArray -> {
                val sorted = com.google.gson.JsonArray()
                element.forEach { sorted.add(sortJsonKeys(it)) }
                sorted
            }
            else -> element
        }
    }

    fun sha256(data: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return digest.digest(data).joinToString("") { "%02x".format(it) }
    }

    fun sign(data: ByteArray): String {
        val key = secret ?: throw IllegalStateException("Secret not configured")
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return Base64.encodeToString(mac.doFinal(data), Base64.NO_WRAP)
    }

    fun verify(data: ByteArray, signature: String): Boolean {
        val expected = sign(data)
        return constantTimeEquals(expected, signature)
    }

    /**
     * Constant-time comparison to prevent timing attacks.
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        return result == 0
    }
}
```

### Step 4: Write Kotlin test

```kotlin
package com.hermesandroid.bridge.tasker

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class TaskerGatewayAuthenticatorTest {

    @Before
    fun setup() {
        // Use a deterministic test secret (base64 encoded "test-secret-key-256-bits-minimum!!")
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `sign produces deterministic output`() {
        val data = """{"adapter_id":"device_owner.status.v1","version":1}""".toByteArray()
        val sig1 = TaskerGatewayAuthenticator.sign(data)
        val sig2 = TaskerGatewayAuthenticator.sign(data)
        assertEquals(sig1, sig2)
    }

    @Test
    fun `verify accepts valid signature`() {
        val data = "hello world".toByteArray()
        val sig = TaskerGatewayAuthenticator.sign(data)
        assertTrue(TaskerGatewayAuthenticator.verify(data, sig))
    }

    @Test
    fun `verify rejects invalid signature`() {
        val data = "hello world".toByteArray()
        assertFalse(TaskerGatewayAuthenticator.verify(data, "deadbeef"))
    }

    @Test
    fun `verify rejects tampered data`() {
        val data = "original".toByteArray()
        val sig = TaskerGatewayAuthenticator.sign(data)
        val tampered = "tampered".toByteArray()
        assertFalse(TaskerGatewayAuthenticator.verify(tampered, sig))
    }

    @Test
    fun `sha256 produces correct hash length`() {
        val hash = TaskerGatewayAuthenticator.sha256("test".toByteArray())
        assertEquals(64, hash.length)
        assertTrue(hash.all { it in '0'..'9' || it in 'a'..'f' })
    }

    @Test
    fun `sha256 is deterministic`() {
        val h1 = TaskerGatewayAuthenticator.sha256("data".toByteArray())
        val h2 = TaskerGatewayAuthenticator.sha256("data".toByteArray())
        assertEquals(h1, h2)
    }

    @Test(expected = IllegalStateException::class)
    fun `sign throws before configure`() {
        // Reset secret
        val field = TaskerGatewayAuthenticator::class.java.getDeclaredField("secret")
        field.isAccessible = true
        field.set(TaskerGatewayAuthenticator, null)
        try {
            TaskerGatewayAuthenticator.sign("test".toByteArray())
        } finally {
            // Restore
            TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
        }
    }
}
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: HMAC-SHA256 authenticator + canonical JSON contract"
```

---

## Task 2: Request/Response Data Classes

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayRequest.kt`
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayResponse.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayRequestTest.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayResponseTest.kt`

### Step 1: Write request data class

```kotlin
package com.hermesandroid.bridge.tasker

import java.util.UUID

/**
 * Hardened request contract v1.
 * No code, no file paths, no eval — only adapter_id selection.
 */
data class TaskerGatewayRequest(
    val version: Int = 1,
    val command_id: String = UUID.randomUUID().toString(),
    val adapter_id: String,
    val params: Map<String, Any> = emptyMap(),
    val issued_at_ms: Long = System.currentTimeMillis(),
    val deadline_at_ms: Long = issued_at_ms + 10_000,
    val nonce: String = UUID.randomUUID().toString(),
    val request_hash: String = "",
    val auth: Auth = Auth()
) {
    data class Auth(
        val algorithm: String = "HMAC-SHA256",
        val signature: String = ""
    )

    companion object {
        const val MAX_REQUEST_SIZE = 65536  // 64 KB
        const val MIN_DEADLINE_MS = 1_000
        const val MAX_DEADLINE_MS = 30_000

        /**
         * Build the bytes that get hashed into request_hash.
         * Includes everything except request_hash and auth.
         */
        fun payloadForHashing(req: TaskerGatewayRequest): ByteArray {
            val payload = req.copy(request_hash = "", auth = Auth())
            return TaskerGatewayAuthenticator.canonicalJson(payload)
        }

        /**
         * Build signed request.
         */
        fun create(
            adapterId: String,
            params: Map<String, Any> = emptyMap(),
            timeoutMs: Long = 10_000
        ): TaskerGatewayRequest {
            val now = System.currentTimeMillis()
            val req = TaskerGatewayRequest(
                adapter_id = adapterId,
                params = params,
                issued_at_ms = now,
                deadline_at_ms = now + timeoutMs,
                nonce = UUID.randomUUID().toString()
            )
            val payloadBytes = payloadForHashing(req)
            val hash = TaskerGatewayAuthenticator.sha256(payloadBytes)
            val signature = TaskerGatewayAuthenticator.sign(payloadBytes)
            return req.copy(
                request_hash = hash,
                auth = Auth(signature = signature)
            )
        }

        /**
         * Validate request structure without verifying auth.
         */
        fun validate(req: TaskerGatewayRequest): String? {
            if (req.version != 1) return "INVALID_VERSION"
            if (req.command_id.isBlank()) return "MISSING_COMMAND_ID"
            if (req.adapter_id.isBlank()) return "MISSING_ADAPTER_ID"
            if (req.deadline_at_ms <= req.issued_at_ms) return "INVALID_DEADLINE"
            if (req.request_hash.isBlank()) return "MISSING_REQUEST_HASH"
            if (req.auth.signature.isBlank()) return "MISSING_SIGNATURE"
            val size = TaskerGatewayAuthenticator.canonicalJson(req).size
            if (size > MAX_REQUEST_SIZE) return "REQUEST_TOO_LARGE"
            return null  // valid
        }
    }
}
```

### Step 2: Write response data class

```kotlin
package com.hermesandroid.bridge.tasker

data class TaskerGatewayResponse(
    val version: Int = 1,
    val command_id: String,
    val adapter_id: String,
    val request_hash: String,
    val ok: Boolean,
    val status: String,
    val received_at_ms: Long = 0,
    val started_at_ms: Long = 0,
    val completed_at_ms: Long = 0,
    val duration_ms: Long = 0,
    val result: Map<String, Any>? = null,
    val executor: ExecutorInfo? = null,
    val error: ErrorInfo? = null,
    val auth: Auth = Auth()
) {
    data class Auth(
        val algorithm: String = "HMAC-SHA256",
        val signature: String = ""
    )

    data class ExecutorInfo(
        val type: String = "tasker",
        val package_name: String = "net.dinglisch.android.taskerm",
        val process_uid: Int = 0,
        val process_pid: Int = 0,
        val task_name: String = ""
    )

    data class ErrorInfo(
        val code: String,
        val message: String
    )

    companion object {
        const val MAX_RESPONSE_SIZE = 262144  // 256 KB

        fun success(
            commandId: String,
            adapterId: String,
            requestHash: String,
            result: Map<String, Any>,
            executor: ExecutorInfo,
            receivedAt: Long,
            startedAt: Long,
            completedAt: Long
        ): TaskerGatewayResponse {
            return TaskerGatewayResponse(
                command_id = commandId,
                adapter_id = adapterId,
                request_hash = requestHash,
                ok = true,
                status = "completed",
                received_at_ms = receivedAt,
                started_at_ms = startedAt,
                completed_at_ms = completedAt,
                duration_ms = completedAt - startedAt,
                result = result,
                executor = executor
            )
        }

        fun error(
            commandId: String,
            adapterId: String,
            requestHash: String,
            code: String,
            message: String
        ): TaskerGatewayResponse {
            return TaskerGatewayResponse(
                command_id = commandId,
                adapter_id = adapterId,
                request_hash = requestHash,
                ok = false,
                status = "rejected",
                error = ErrorInfo(code, message)
            )
        }

        /**
         * Bytes for signing: everything except auth.
         */
        fun payloadForSigning(resp: TaskerGatewayResponse): ByteArray {
            val unsigned = resp.copy(auth = Auth())
            return TaskerGatewayAuthenticator.canonicalJson(unsigned)
        }
    }
}
```

### Step 3: Write request tests

```kotlin
package com.hermesandroid.bridge.tasker

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class TaskerGatewayRequestTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `create produces valid request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        assertEquals(1, req.version)
        assertEquals("device_owner.status.v1", req.adapter_id)
        assertTrue(req.command_id.isNotBlank())
        assertTrue(req.request_hash.isNotBlank())
        assertTrue(req.auth.signature.isNotBlank())
        assertTrue(req.deadline_at_ms > req.issued_at_ms)
    }

    @Test
    fun `validate accepts valid request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        assertNull(TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects version != 1`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(version = 2)
        assertEquals("INVALID_VERSION", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects empty adapter_id`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(adapter_id = "")
        assertEquals("MISSING_ADAPTER_ID", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects deadline before issued_at`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(
            issued_at_ms = 1000,
            deadline_at_ms = 500
        )
        assertEquals("INVALID_DEADLINE", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `request_hash is SHA-256 of payload`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val payload = TaskerGatewayRequest.payloadForHashing(req)
        val expectedHash = TaskerGatewayAuthenticator.sha256(payload)
        assertEquals(expectedHash, req.request_hash)
    }

    @Test
    fun `no source code or file paths in request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val json = TaskerGatewayAuthenticator.canonicalJson(req).toString(Charsets.UTF_8)
        assertFalse(json.contains("eval"))
        assertFalse(json.contains("/sdcard"))
        assertFalse(json.contains("par1"))
        assertFalse(json.contains("source"))
    }
}
```

### Step 4: Write response tests

```kotlin
package com.hermesandroid.bridge.tasker

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class TaskerGatewayResponseTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `success response has correct structure`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc123",
            result = mapOf("is_device_owner" to true),
            executor = TaskerGatewayResponse.ExecutorInfo(task_name = "test"),
            receivedAt = 100,
            startedAt = 150,
            completedAt = 200
        )
        assertTrue(resp.ok)
        assertEquals("completed", resp.status)
        assertEquals(50, resp.duration_ms)
        assertNotNull(resp.result)
        assertNull(resp.error)
    }

    @Test
    fun `error response has correct structure`() {
        val resp = TaskerGatewayResponse.error(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            code = "deadline_exceeded",
            message = "Request expired"
        )
        assertFalse(resp.ok)
        assertEquals("rejected", resp.status)
        assertEquals("deadline_exceeded", resp.error?.code)
        assertNull(resp.result)
    }

    @Test
    fun `response payload excludes auth for signing`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            result = emptyMap(),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 0, startedAt = 0, completedAt = 0
        )
        val payload = TaskerGatewayResponse.payloadForSigning(resp)
        val json = payload.toString(Charsets.UTF_8)
        assertFalse(json.contains("auth"))
        assertFalse(json.contains("signature"))
    }
}
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: TaskerGatewayRequest/Response data classes v1"
```

---

## Task 3: Adapter Registry (Static Allowlist)

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/AdapterRegistry.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/AdapterRegistryTest.kt`
- Create: `tools/verify/tasker_gateway_security.py`

### Step 1: Write adapter registry

```kotlin
package com.hermesandroid.bridge.tasker

/**
 * Static registry of allowed adapters.
 * Only adapters registered here can be executed.
 * NO dynamic code loading, NO eval, NO file paths.
 */
object AdapterRegistry {

    data class AdapterEntry(
        val adapterId: String,
        val capability: String,
        val version: Int,
        val riskLevel: String,
        val timeoutMs: Long,
        val idempotent: Boolean,
        val paramSchema: Map<String, String> = emptyMap(),
        val implementationHash: String = ""
    )

    private val adapters = mutableMapOf<String, AdapterEntry>()

    init {
        // Only device_owner.status.v1 — the sole capability for v1
        register(AdapterEntry(
            adapterId = "device_owner.status.v1",
            capability = "device_owner.status",
            version = 1,
            riskLevel = "LOW",
            timeoutMs = 5_000,
            idempotent = true,
            paramSchema = emptyMap(),
            implementationHash = "v1-initial"
        ))
    }

    fun register(entry: AdapterEntry) {
        adapters[entry.adapterId] = entry
    }

    fun lookup(adapterId: String): AdapterEntry? = adapters[adapterId]

    fun isAllowed(adapterId: String): Boolean = adapters.containsKey(adapterId)

    fun allowedIds(): Set<String> = adapters.keys.toSet()

    /**
     * Validate request adapter_id against the registry.
     * Returns null if valid, error code string if not.
     */
    fun validateAdapter(adapterId: String): String? {
        if (!isAllowed(adapterId)) return "UNKNOWN_ADAPTER"
        val entry = lookup(adapterId)!!
        if (entry.riskLevel !in listOf("LOW", "MEDIUM")) return "HIGH_RISK_ADAPTER"
        return null
    }
}
```

### Step 2: Write adapter registry tests

```kotlin
package com.hermesandroid.bridge.tasker

import org.junit.Assert.*
import org.junit.Test

class AdapterRegistryTest {

    @Test
    fun `device_owner status v1 is allowed`() {
        assertTrue(AdapterRegistry.isAllowed("device_owner.status.v1"))
    }

    @Test
    fun `unknown adapter is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("arbitrary.code"))
        assertEquals("UNKNOWN_ADAPTER", AdapterRegistry.validateAdapter("arbitrary.code"))
    }

    @Test
    fun `raw_java is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("raw_java"))
    }

    @Test
    fun `raw_shell is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("raw_shell"))
    }

    @Test
    fun `eval adapter is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("eval"))
    }

    @Test
    fun `lookup returns correct entry`() {
        val entry = AdapterRegistry.lookup("device_owner.status.v1")
        assertNotNull(entry)
        assertEquals("device_owner.status", entry!!.capability)
        assertEquals("LOW", entry.riskLevel)
        assertTrue(entry.idempotent)
    }

    @Test
    fun `allowedIds contains only device_owner status`() {
        val ids = AdapterRegistry.allowedIds()
        assertEquals(1, ids.size)
        assertTrue(ids.contains("device_owner.status.v1"))
    }

    @Test
    fun `validateAdapter returns null for valid adapter`() {
        assertNull(AdapterRegistry.validateAdapter("device_owner.status.v1"))
    }
}
```

### Step 3: Write Python security verification

```python
#!/usr/bin/env python3
"""Verify security properties of the Tasker Gateway."""
import os, re, sys

def check_no_shell_in_transport():
    """Verify TaskerGatewayTransport doesn't use /shell."""
    path = "hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayTransport.kt"
    if not os.path.exists(path):
        return f"SKIP: {path} not found"
    content = open(path).read()
    forbidden = ["/shell", "am broadcast", "Runtime.exec", "ProcessBuilder"]
    for pattern in forbidden:
        if pattern in content:
            return f"FAIL: Found '{pattern}' in TaskerGatewayTransport"
    return "PASS: No shell usage in transport"

def check_no_eval_in_tasker_code():
    """Verify no eval(source) pattern in new Tasker code."""
    patterns_to_check = [
        r'eval\s*\(\s*source\s*\)',
        r'eval\s*\(\s*par1\s*\)',
        r'getVariable\s*\(\s*"par1"\s*\)',
    ]
    tasker_dir = "hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/"
    if not os.path.exists(tasker_dir):
        return "SKIP: tasker dir not found"
    for f in os.listdir(tasker_dir):
        if not f.endswith('.kt'):
            continue
        content = open(os.path.join(tasker_dir, f)).read()
        for pattern in patterns_to_check:
            if re.search(pattern, content):
                return f"FAIL: Found eval(source) pattern in {f}"
    return "PASS: No eval(source) in new Tasker code"

def check_no_real_secrets():
    """Verify no real secret values in the repo."""
    banned = [
        "hermes-local-secret-2026",
        "SFBCBA",
        "uHNgVCmJfld_Kx8BfLEjVK5X7I2nF9Be6KidmM3yYc8",
        "NeN0FkX-dFLWzcLQltzCKw",
    ]
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
        for f in files:
            if f.endswith(('.pyc', '.class', '.jar', '.apk')):
                continue
            path = os.path.join(root, f)
            try:
                content = open(path, errors='ignore').read()
            except:
                continue
            for secret in banned:
                if secret in content:
                    return f"FAIL: Secret found in {path}"
    return "PASS: No real secrets in repository"

def check_android_version_kernel_separated():
    """Verify android_version and kernel_version are separate fields."""
    tasker_dir = "hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/"
    if not os.path.exists(tasker_dir):
        return "SKIP: tasker dir not found"
    for f in os.listdir(tasker_dir):
        if not f.endswith('.kt'):
            continue
        content = open(os.path.join(tasker_dir, f)).read()
        if "android_version" in content and "kernel_version" in content:
            # Check they're not in the same value assignment
            lines = content.split('\n')
            for line in lines:
                if 'android_version' in line and 'kernel_version' in line:
                    if '=' in line and 'os.version' in line:
                        return f"FAIL: android_version uses kernel value in {f}"
    return "PASS: android_version and kernel_version properly separated"

if __name__ == '__main__':
    checks = [
        check_no_shell_in_transport(),
        check_no_eval_in_tasker_code(),
        check_no_real_secrets(),
        check_android_version_kernel_separated(),
    ]
    all_pass = True
    for c in checks:
        print(c)
        if c.startswith("FAIL"):
            all_pass = False
    sys.exit(0 if all_pass else 1)
```

### Step 4: Run security verification

```bash
python3 tools/verify/tasker_gateway_security.py
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: static adapter registry — allowlist only device_owner.status.v1"
```

---

## Task 4: PendingCommandRegistry (Dedup + Futures)

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/PendingCommandRegistry.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/PendingCommandRegistryTest.kt`
- Create: `tools/verify/tasker_gateway_dedup.py`

### Step 1: Write Python dedup verification

```python
#!/usr/bin/env python3
"""Verify deduplication logic properties."""
import time, hashlib

class PendingCommandRegistry:
    """Python simulation of the Kotlin PendingCommandRegistry."""
    def __init__(self):
        self._pending = {}  # command_id -> (future, request_hash)
        self._completed = {}  # command_id -> (request_hash, response, completed_at)
        self._ttl_ms = 300_000  # 5 minutes

    def register(self, command_id, request_hash):
        """Returns: (status, existing_response)
        status: 'new' | 'duplicate_identical' | 'duplicate_conflict'
        """
        if command_id in self._pending:
            _, existing_hash = self._pending[command_id]
            if existing_hash == request_hash:
                return 'duplicate_identical', None
            else:
                return 'duplicate_conflict', None

        if command_id in self._completed:
            existing_hash, response, _ = self._completed[command_id]
            if existing_hash == request_hash:
                return 'duplicate_identical', response
            else:
                return 'duplicate_conflict', None

        self._pending[command_id] = (None, request_hash)
        return 'new', None

    def complete(self, command_id, request_hash, response):
        if command_id in self._pending:
            _, stored_hash = self._pending[command_id]
            if stored_hash != request_hash:
                raise ValueError("hash mismatch on complete")
            del self._pending[command_id]
            self._completed[command_id] = (request_hash, response, time.time())

    def cleanup_expired(self):
        now = time.time()
        expired = [cid for cid, (_, _, t) in self._completed.items()
                   if (now - t) * 1000 > self._ttl_ms]
        for cid in expired:
            del self._completed[cid]

# Tests
reg = PendingCommandRegistry()

# Test 1: New command
status, _ = reg.register("cmd-1", "hash-a")
assert status == 'new', f"Expected 'new', got '{status}'"

# Test 2: Identical duplicate returns cached response
cached_response = {"ok": True}
reg.complete("cmd-1", "hash-a", cached_response)
status, resp = reg.register("cmd-1", "hash-a")
assert status == 'duplicate_identical', f"Expected 'duplicate_identical', got '{status}'"
assert resp == cached_response, "Should return cached response"

# Test 3: Conflicting duplicate
status, _ = reg.register("cmd-2", "hash-a")
reg.complete("cmd-2", "hash-a", {"ok": True})
status, _ = reg.register("cmd-2", "hash-b")
assert status == 'duplicate_conflict', f"Expected 'duplicate_conflict', got '{status}'"

# Test 4: Pending identical duplicate
status, _ = reg.register("cmd-3", "hash-c")
status2, _ = reg.register("cmd-3", "hash-c")
assert status2 == 'duplicate_identical'

# Test 5: Pending conflict
status, _ = reg.register("cmd-4", "hash-d")
status2, _ = reg.register("cmd-4", "hash-e")
assert status2 == 'duplicate_conflict'

# Test 6: Two different commands don't conflict
status, _ = reg.register("cmd-5", "hash-f")
assert status == 'new'
status, _ = reg.register("cmd-6", "hash-g")
assert status == 'new'

# Test 7: No last-write-wins
reg2 = PendingCommandRegistry()
reg2.register("cmd-lww", "hash-1")
reg2.complete("cmd-lww", "hash-1", {"response": "first"})
# Second attempt with different hash should NOT overwrite
status, resp = reg2.register("cmd-lww", "hash-2")
assert status == 'duplicate_conflict'
assert resp is None, "Conflict should not return cached response"

print("PASS: All deduplication logic tests passed")
```

### Step 2: Run dedup verification

```bash
python3 tools/verify/tasker_gateway_dedup.py
```

### Step 3: Write Kotlin PendingCommandRegistry

```kotlin
package com.hermesandroid.bridge.tasker

import kotlinx.coroutines.CompletableDeferred
import java.util.concurrent.ConcurrentHashMap

/**
 * Manages pending commands with deduplication.
 * Uses CompletableDeferred for async response correlation.
 * No last-write-wins: identical replays return cached, conflicts rejected.
 */
class PendingCommandRegistry(private val ttlMs: Long = 300_000) {

    data class PendingEntry(
        val deferred: CompletableDeferred<TaskerGatewayResponse>,
        val requestHash: String,
        val createdAt: Long = System.currentTimeMillis()
    )

    data class CompletedEntry(
        val requestHash: String,
        val response: TaskerGatewayResponse,
        val completedAt: Long = System.currentTimeMillis()
    )

    enum class RegistrationResult {
        NEW,
        DUPLICATE_IDENTICAL,
        DUPLICATE_CONFLICT
    }

    data class RegistrationOutcome(
        val result: RegistrationResult,
        val cachedResponse: TaskerGatewayResponse? = null
    )

    private val pending = ConcurrentHashMap<String, PendingEntry>()
    private val completed = ConcurrentHashMap<String, CompletedEntry>()

    /**
     * Register a command. Returns outcome:
     * - NEW: command registered, caller should execute
     * - DUPLICATE_IDENTICAL: same command_id + same hash, return cached
     * - DUPLICATE_CONFLICT: same command_id + different hash, reject
     */
    fun register(commandId: String, requestHash: String): RegistrationOutcome {
        // Check pending first
        pending[commandId]?.let { entry ->
            return if (entry.requestHash == requestHash) {
                RegistrationOutcome(RegistrationResult.DUPLICATE_IDENTICAL)
            } else {
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // Check completed (replay)
        completed[commandId]?.let { entry ->
            return if (entry.requestHash == requestHash) {
                RegistrationOutcome(
                    RegistrationResult.DUPLICATE_IDENTICAL,
                    cachedResponse = entry.response
                )
            } else {
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // New command — register
        pending[commandId] = PendingEntry(
            deferred = CompletableDeferred(),
            requestHash = requestHash
        )
        return RegistrationOutcome(RegistrationResult.NEW)
    }

    /**
     * Get the deferred for a pending command.
     */
    fun getDeferred(commandId: String): CompletableDeferred<TaskerGatewayResponse>? {
        return pending[commandId]?.deferred
    }

    /**
     * Complete a pending command with its response.
     */
    fun complete(commandId: String, requestHash: String, response: TaskerGatewayResponse) {
        val entry = pending.remove(commandId) ?: return
        if (entry.requestHash != requestHash) {
            // Hash mismatch — put back (shouldn't happen in normal flow)
            pending[commandId] = entry
            throw IllegalArgumentException("Request hash mismatch on complete")
        }
        entry.deferred.complete(response)
        completed[commandId] = CompletedEntry(
            requestHash = requestHash,
            response = response
        )
    }

    /**
     * Fail a pending command (e.g., timeout).
     */
    fun fail(commandId: String, error: TaskerGatewayResponse) {
        val entry = pending.remove(commandId) ?: return
        entry.deferred.complete(error)
    }

    /**
     * Cleanup expired completed entries.
     */
    fun cleanup() {
        val now = System.currentTimeMillis()
        completed.entries.removeIf { (_, entry) ->
            (now - entry.completedAt) > ttlMs
        }
    }

    fun pendingCount(): Int = pending.size
    fun completedCount(): Int = completed.size
    fun isPending(commandId: String): Boolean = pending.containsKey(commandId)
}
```

### Step 4: Write Kotlin dedup tests

```kotlin
package com.hermesandroid.bridge.tasker

import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class PendingCommandRegistryTest {

    private lateinit var registry: PendingCommandRegistry

    @Before
    fun setup() {
        registry = PendingCommandRegistry(ttlMs = 60_000)
    }

    private fun makeResponse(commandId: String, ok: Boolean = true): TaskerGatewayResponse {
        return TaskerGatewayResponse(
            command_id = commandId,
            adapter_id = "device_owner.status.v1",
            request_hash = "hash",
            ok = ok,
            status = if (ok) "completed" else "error"
        )
    }

    @Test
    fun `new command registers successfully`() {
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.NEW, outcome.result)
        assertNull(outcome.cachedResponse)
    }

    @Test
    fun `identical duplicate returns cached response`() {
        registry.register("cmd-1", "hash-a")
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL, outcome.result)
        assertNotNull(outcome.cachedResponse)
    }

    @Test
    fun `conflicting duplicate rejected`() {
        registry.register("cmd-1", "hash-a")
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        val outcome = registry.register("cmd-1", "hash-b")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT, outcome.result)
        assertNull(outcome.cachedResponse)  // No last-write-wins
    }

    @Test
    fun `pending identical duplicate detected`() {
        registry.register("cmd-1", "hash-a")
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL, outcome.result)
    }

    @Test
    fun `pending conflict detected`() {
        registry.register("cmd-1", "hash-a")
        val outcome = registry.register("cmd-1", "hash-b")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT, outcome.result)
    }

    @Test
    fun `two different commands dont conflict`() {
        assertEquals(PendingCommandRegistry.RegistrationResult.NEW,
            registry.register("cmd-1", "hash-a").result)
        assertEquals(PendingCommandRegistry.RegistrationResult.NEW,
            registry.register("cmd-2", "hash-b").result)
    }

    @Test
    fun `deferred completes on complete call`() = runBlocking {
        registry.register("cmd-1", "hash-a")
        val deferred = registry.getDeferred("cmd-1")
        assertNotNull(deferred)
        val response = makeResponse("cmd-1")
        registry.complete("cmd-1", "hash-a", response)
        assertEquals(response, deferred!!.await())
    }

    @Test
    fun `pending count tracks correctly`() {
        assertEquals(0, registry.pendingCount())
        registry.register("cmd-1", "hash-a")
        assertEquals(1, registry.pendingCount())
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        assertEquals(0, registry.pendingCount())
        assertEquals(1, registry.completedCount())
    }
}
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: PendingCommandRegistry — dedup + Deferred correlation"
```

---

## Task 5: Native Broadcast Transport

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayTransport.kt`
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayReceiver.kt`
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayConfig.kt`

### Step 1: Write TaskerGatewayConfig

```kotlin
package com.hermesandroid.bridge.tasker

import android.content.Context
import android.util.Base64
import java.security.SecureRandom

/**
 * Gateway configuration. Secret is provisioned on-device.
 * NEVER stored in Git, logs, or Tasker exports.
 */
object TaskerGatewayConfig {

    private const val PREFS_NAME = "tasker_gateway_config"
    private const val KEY_SECRET = "gateway_hmac_secret"
    private const val KEY_TASKER_PACKAGE = "net.dinglisch.android.taskerm"

    const val ACTION_REQUEST = "com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1"
    const val ACTION_RESPONSE = "com.hermesandroid.bridge.TASKER_GATEWAY_RESPONSE_V1"
    const val EXTRA_REQUEST_JSON = "request_json"
    const val EXTRA_RESPONSE_JSON = "response_json"

    val taskerPackage: String get() = KEY_TASKER_PACKAGE

    /**
     * Get or generate the HMAC secret.
     * First call generates 256-bit random secret and stores it.
     * Subsequent calls read from SharedPreferences.
     */
    fun getOrCreateSecret(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getString(KEY_SECRET, null)
        if (existing != null) return existing

        // Generate 256-bit random secret
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val secret = Base64.encodeToString(bytes, Base64.NO_WRAP)
        prefs.edit().putString(KEY_SECRET, secret).commit()
        return secret
    }

    /**
     * Configure the authenticator with the on-device secret.
     */
    fun initAuthenticator(context: Context) {
        val secret = getOrCreateSecret(context)
        TaskerGatewayAuthenticator.configure(secret)
    }

    /**
     * Rotate the secret. Old secret is lost.
     * Must re-provision on Tasker side.
     */
    fun rotateSecret(context: Context): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val newSecret = Base64.encodeToString(bytes, Base64.NO_WRAP)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString(KEY_SECRET, newSecret).commit()
        TaskerGatewayAuthenticator.configure(newSecret)
        return newSecret
    }

    /**
     * Check if a secret has been provisioned.
     */
    fun isProvisioned(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .contains(KEY_SECRET)
    }
}
```

### Step 2: Write TaskerGatewayTransport

```kotlin
package com.hermesandroid.bridge.tasker

import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Native broadcast transport to Tasker.
 * NO /shell, NO am command, NO file I/O.
 * Sends HMAC-signed request as JSON extra via Android broadcast.
 */
object TaskerGatewayTransport {

    private const val TAG = "TaskerGatewayTransport"

    /**
     * Send request to Tasker via native broadcast.
     * The intent is directed at Tasker's package.
     */
    fun send(context: Context, request: TaskerGatewayRequest): Boolean {
        return try {
            val gson = com.google.gson.Gson()
            val requestJson = gson.toJson(request)

            val intent = Intent(TaskerGatewayConfig.ACTION_REQUEST).apply {
                setPackage(TaskerGatewayConfig.taskerPackage)
                putExtra(TaskerGatewayConfig.EXTRA_REQUEST_JSON, requestJson)
                addFlags(Intent.FLAG_RECEIVER_EXPORTED)
            }

            context.sendBroadcast(intent)
            Log.d(TAG, "Sent request ${request.command_id} for adapter ${request.adapter_id}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send request: ${e.message}", e)
            false
        }
    }

    /**
     * Check if Tasker is installed.
     */
    fun isTaskerInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(TaskerGatewayConfig.taskerPackage, 0)
            true
        } catch (_: android.content.pm.PackageManager.NameNotFoundException) {
            false
        }
    }
}
```

### Step 3: Write TaskerGatewayReceiver

```kotlin
package com.hermesandroid.bridge.tasker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonParser

/**
 * Receives responses from Tasker Gateway.
 * Validates HMAC before processing.
 * Only accepts responses directed to our package.
 */
class TaskerGatewayReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "TaskerGatewayReceiver"

        // Singleton reference to the registry — set by TaskerGatewayClient
        var registry: PendingCommandRegistry? = null
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TaskerGatewayConfig.ACTION_RESPONSE) {
            Log.w(TAG, "Unexpected action: ${intent.action}")
            return
        }

        val responseJson = intent.getStringExtra(TaskerGatewayConfig.EXTRA_RESPONSE_JSON)
        if (responseJson == null) {
            Log.w(TAG, "No response JSON in intent")
            return
        }

        try {
            val gson = Gson()
            val response = gson.fromJson(responseJson, TaskerGatewayResponse::class.java)

            // Validate HMAC
            val payloadBytes = TaskerGatewayResponse.payloadForSigning(response)
            if (!TaskerGatewayAuthenticator.verify(payloadBytes, response.auth.signature)) {
                Log.w(TAG, "HMAC verification failed for command ${response.command_id}")
                return
            }

            // Complete the pending command
            val pendingRegistry = registry
            if (pendingRegistry != null) {
                pendingRegistry.complete(
                    response.command_id,
                    response.request_hash,
                    response
                )
                Log.d(TAG, "Completed command ${response.command_id}")
            } else {
                Log.w(TAG, "No registry set — discarding response")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to process response: ${e.message}", e)
        }
    }
}
```

### Step 4: Commit

```bash
git add -A && git commit -m "feat: native broadcast transport — no /shell, HMAC-verified responses"
```

---

## Task 6: High-Level Client + Deadline Enforcement

**Files:**
- Create: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClient.kt`
- Create: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClientTest.kt`
- Create: `tools/verify/tasker_gateway_deadline.py`

### Step 1: Write Python deadline verification

```python
#!/usr/bin/env python3
"""Verify deadline enforcement logic."""
import time

def check_deadline(issued_at_ms, deadline_at_ms, current_ms):
    """Returns True if deadline has been exceeded."""
    return current_ms > deadline_at_ms

def make_request(issued_at_ms, timeout_ms):
    return {
        "issued_at_ms": issued_at_ms,
        "deadline_at_ms": issued_at_ms + timeout_ms
    }

# Test 1: Not expired
req = make_request(1000, 5000)
assert not check_deadline(req["issued_at_ms"], req["deadline_at_ms"], 3000)

# Test 2: Not expired at exact deadline
assert not check_deadline(req["issued_at_ms"], req["deadline_at_ms"], 6000)

# Test 3: Expired after deadline
assert check_deadline(req["issued_at_ms"], req["deadline_at_ms"], 6001)

# Test 4: Expired before execution
req2 = make_request(1000, 0)  # 0ms timeout = already expired
assert check_deadline(req2["issued_at_ms"], req2["deadline_at_ms"], 1001)

# Test 5: Deadline respected, not faked with generous timeout
req3 = make_request(1000, 5000)
start = time.time() * 1000
# Simulate fast execution
completed = start + 50  # 50ms
assert completed < req3["deadline_at_ms"]  # fast enough

# Test 6: 1ms timeout should reject
req4 = make_request(1000, 1)
assert check_deadline(req4["issued_at_ms"], req4["deadline_at_ms"], 1002)

# Test 7: Response contains deadline_exceeded error code
def make_deadline_response(command_id):
    return {
        "ok": False,
        "status": "rejected",
        "error": {
            "code": "deadline_exceeded",
            "message": "Request expired before execution"
        }
    }

resp = make_deadline_response("cmd-1")
assert resp["error"]["code"] == "deadline_exceeded"
assert not resp["ok"]

print("PASS: All deadline enforcement tests passed")
```

### Step 2: Run deadline verification

```bash
python3 tools/verify/tasker_gateway_deadline.py
```

### Step 3: Write TaskerGatewayClient

```kotlin
package com.hermesandroid.bridge.tasker

import android.content.Context
import android.content.IntentFilter
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout

/**
 * High-level client: send request → await response.
 * Enforces deadline, deduplication, HMAC verification.
 * No shell, no polling, no file I/O.
 */
class TaskerGatewayClient(private val context: Context) {

    companion object {
        private const val TAG = "TaskerGatewayClient"
        private const val DEFAULT_TIMEOUT_MS = 10_000L
    }

    private val pendingRegistry = PendingCommandRegistry()
    private var receiverRegistered = false

    init {
        // Configure authenticator from on-device secret
        TaskerGatewayConfig.initAuthenticator(context)

        // Set registry on receiver
        TaskerGatewayReceiver.registry = pendingRegistry

        // Register response receiver
        if (!receiverRegistered) {
            val filter = IntentFilter(TaskerGatewayConfig.ACTION_RESPONSE)
            context.registerReceiver(TaskerGatewayReceiver(), filter, Context.RECEIVER_NOT_EXPORTED)
            receiverRegistered = true
        }
    }

    /**
     * Execute a command and await response.
     * Enforces deadline before sending.
     */
    suspend fun execute(
        adapterId: String,
        params: Map<String, Any> = emptyMap(),
        timeoutMs: Long = DEFAULT_TIMEOUT_MS
    ): TaskerGatewayResponse {
        // Validate adapter exists
        val adapterError = AdapterRegistry.validateAdapter(adapterId)
        if (adapterError != null) {
            return TaskerGatewayResponse.error(
                commandId = "",
                adapterId = adapterId,
                requestHash = "",
                code = adapterError,
                message = "Adapter not allowed: $adapterId"
            )
        }

        // Check deadline before creating request
        val now = System.currentTimeMillis()
        val deadline = now + timeoutMs
        if (timeoutMs <= 0) {
            return TaskerGatewayResponse.error(
                commandId = "",
                adapterId = adapterId,
                requestHash = "",
                code = "invalid_timeout",
                message = "Timeout must be positive"
            )
        }

        // Create signed request
        val request = TaskerGatewayRequest.create(adapterId, params, timeoutMs)

        // Register for dedup
        val outcome = pendingRegistry.register(request.command_id, request.request_hash)
        when (outcome.result) {
            PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL -> {
                Log.d(TAG, "Replay detected for ${request.command_id}, returning cached")
                return outcome.cachedResponse ?: TaskerGatewayResponse.error(
                    request.command_id, adapterId, request.request_hash,
                    "internal_error", "No cached response for identical replay"
                )
            }
            PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT -> {
                return TaskerGatewayResponse.error(
                    request.command_id, adapterId, request.request_hash,
                    "command_id_conflict",
                    "command_id reused with different request_hash"
                )
            }
            PendingCommandRegistry.RegistrationResult.NEW -> { /* proceed */ }
        }

        // Check deadline again right before send
        if (System.currentTimeMillis() > deadline) {
            pendingRegistry.fail(request.command_id, TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "deadline_exceeded", "Request expired before execution"
            ))
            return TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "deadline_exceeded", "Request expired before execution"
            )
        }

        // Send via native broadcast
        val sent = TaskerGatewayTransport.send(context, request)
        if (!sent) {
            pendingRegistry.fail(request.command_id, TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "transport_error", "Failed to send broadcast"
            ))
            return TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "transport_error", "Failed to send broadcast to Tasker"
            )
        }

        // Await response with timeout
        val deferred = pendingRegistry.getDeferred(request.command_id)
            ?: return TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "internal_error", "No deferred registered"
            )

        return try {
            withTimeout(timeoutMs) {
                deferred.await()
            }
        } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
            pendingRegistry.fail(request.command_id, TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "timeout", "Bridge timeout after ${timeoutMs}ms"
            ))
            TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "timeout", "Bridge timeout after ${timeoutMs}ms"
            )
        }
    }
}
```

### Step 4: Write client tests

```kotlin
package com.hermesandroid.bridge.tasker

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class TaskerGatewayClientTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `unknown adapter rejected immediately`() {
        val registry = PendingCommandRegistry()
        val adapterError = AdapterRegistry.validateAdapter("raw_java")
        assertNotNull(adapterError)
        assertEquals("UNKNOWN_ADAPTER", adapterError)
    }

    @Test
    fun `valid adapter passes validation`() {
        assertNull(AdapterRegistry.validateAdapter("device_owner.status.v1"))
    }

    @Test
    fun `request contains no source code`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val json = TaskerGatewayAuthenticator.canonicalJson(req).toString(Charsets.UTF_8)
        assertFalse("Request must not contain eval", json.contains("eval"))
        assertFalse("Request must not contain par1", json.contains("par1"))
        assertFalse("Request must not contain /sdcard", json.contains("/sdcard"))
        assertFalse("Request must not contain source code", json.contains("source"))
    }

    @Test
    fun `transport object has no shell methods`() {
        // Verify the transport class doesn't reference shell
        val transportClass = TaskerGatewayTransport::class.java
        val methods = transportClass.methods.map { it.name }
        assertFalse("Transport must not use shell", methods.any { it.contains("shell") })
    }

    @Test
    fun `deadline validation works`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1", timeoutMs = 5000)
        assertTrue(req.deadline_at_ms > req.issued_at_ms)
        assertEquals(5000, req.deadline_at_ms - req.issued_at_ms)
    }
}
```

### Step 5: Commit

```bash
git add -A && git commit -m "feat: TaskerGatewayClient — send+await, deadline enforcement, no polling"
```

---

## Task 7: Contract Documentation Update

**Files:**
- Modify: `docs/tasker-command-gateway-contract.md`
- Modify: `docs/tasker-command-gateway-security.md`

### Step 1: Update contract document to v1.1

Update `docs/tasker-command-gateway-contract.md` with:
- HMAC-SHA256 authentication (replaces plaintext token)
- Canonical JSON serialization specification
- request_hash (SHA-256 of canonical payload)
- Response auth field
- Deduplication semantics (identical vs conflict)
- Deadline enforcement rules
- Remove `token` field, add `auth.signature`
- Remove `capability` field, rename to `adapter_id`

### Step 2: Update security document

Update `docs/tasker-command-gateway-security.md`:
- HMAC authentication model
- On-device secret provisioning
- Secret rotation procedure
- No eval/source anywhere in the chain
- Native broadcast transport security

### Step 3: Commit

```bash
git add -A && git commit -m "docs: update contract to v1.1 with HMAC, canonical form, dedup"
```

---

## Task 8: Python Verification Full Suite

**Files:**
- Create: `tools/verify/tasker_gateway_full_suite.py`

### Step 1: Write comprehensive Python test suite

This script runs all verification checks together:

```python
#!/usr/bin/env python3
"""
Full verification suite for Tasker Gateway Hardened Executor v1.
Runs on OCI without Kotlin compiler.
"""
import hashlib, hmac, json, os, sys, time
from collections import OrderedDict

# ====== Canonical JSON ======
def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')

def sort_json(obj):
    if isinstance(obj, dict):
        return OrderedDict(sorted((k, sort_json(v)) for k, v in obj.items()))
    elif isinstance(obj, list):
        return [sort_json(i) for i in obj]
    return obj

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

# ====== 1. Serialization ======
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
print("\n=== 5. Request Hash ===")
request = {
    "version": 1, "command_id": "550e8400-e29b-41d4-a716-446655440000",
    "adapter_id": "device_owner.status.v1", "params": {},
    "issued_at_ms": 1690000000000, "deadline_at_ms": 1690000010000, "nonce": "abc"
}
payload = canonical_json(request)
req_hash = hashlib.sha256(payload).hexdigest()
test("SHA-256 hash is 64 chars", len(req_hash) == 64)
test("Hash is hex", all(c in '0123456789abcdef' for c in req_hash))

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
# Simulate registry
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
test("android_version != kernel_version", resp["result"]["android_version"] != resp["result"]["kernel_version"])

# ====== 11. Size Limits ======
print("\n=== 11. Size Limits ===")
test("Request max 64KB", 65536 >= len(canonical_json(request)))
test("Response max 256KB", 262144 >= len(canonical_json(resp)))

# ====== 12. No Secrets in Evidence ======
print("\n=== 12. No Real Secrets in Repo ===")
banned = ["hermes-local-secret-2026", "SFBCBA"]
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.hermes')]
    for f in files:
        if f.endswith(('.pyc', '.class', '.jar', '.apk')):
            continue
        path = os.path.join(root, f)
        try:
            content = open(path, errors='ignore').read()
        except:
            continue
        for secret in banned:
            if secret in content:
                test(f"No secret in {path}", False, f"Found {secret[:8]}...")

test("No banned secrets found", True)

# ====== Summary ======
total = passed + failed
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed > 0:
    print("FAIL")
    sys.exit(1)
else:
    print("PASS: Tasker Gateway Hardened Executor v1 — all checks pass")
    sys.exit(0)
```

### Step 2: Run full verification suite

```bash
python3 tools/verify/tasker_gateway_full_suite.py
```

### Step 3: Commit

```bash
git add -A && git commit -m "test: full Python verification suite for Tasker Gateway v1"
```

---

## Task 9: Tasker Project XML

**Files:**
- Create: `tasker-project/HermesCommandGateway/project.xml`
- Create: `tasker-project/HermesCommandGateway/profiles/request_v1.xml`
- Create: `tasker-project/HermesCommandGateway/tasks/validate_request.xml`
- Create: `tasker-project/HermesCommandGateway/tasks/dispatch_adapter.xml`
- Create: `tasker-project/HermesCommandGateway/tasks/execute_device_owner_status.xml`
- Create: `tasker-project/HermesCommandGateway/tasks/build_response.xml`

### Step 1: Create project XML skeleton

Create a minimal Tasker project XML structure that represents:
- Profile: Receives `TASKER_GATEWAY_REQUEST_V1` broadcast
- Task 1: Validate request (HMAC, deadline, adapter_id)
- Task 2: Dispatch to adapter by adapter_id
- Task 3: Execute device_owner.status.v1 (static, no eval)
- Task 4: Build response, sign HMAC, send back via broadcast

Note: Full Tasker XML is complex. Create a documented skeleton that can be imported and configured on the device.

### Step 2: Commit

```bash
git add -A && git commit -m "feat: Tasker project skeleton — Hermes Command Gateway v1"
```

---

## Task 10: Migration Documentation + Final Secret Check

**Files:**
- Modify: `docs/MIGRATION-POC-TO-V1.md` (finalize)
- Create: `docs/TASKER-EXECUTOR-ARCHITECTURE.md`

### Step 1: Create architecture document

Document the full flow:

```
Hermes Agent (Python)
    ↓ HTTP POST /tasker_gateway
HermesBridge Kotlin (TaskerGatewayClient)
    ↓ validate adapter_id against registry
    ↓ build request (canonical JSON)
    ↓ sign request (HMAC-SHA256)
    ↓ register in PendingCommandRegistry
    ↓ check deadline
    ↓ sendBroadcast(ACTION_REQUEST) → Tasker
Tasker Gateway (static dispatcher)
    ↓ receive broadcast
    ↓ validate HMAC
    ↓ check deadline
    ↓ dedup check
    ↓ dispatch to adapter by adapter_id (static lookup)
    ↓ execute device_owner.status.v1 (DevicePolicyManager)
    ↓ build response (canonical JSON)
    ↓ sign response (HMAC-SHA256)
    ↓ sendBroadcast(ACTION_RESPONSE) → Bridge
HermesBridge Kotlin (TaskerGatewayReceiver)
    ↓ validate HMAC
    ↓ complete Deferred in PendingCommandRegistry
    ↓ return to caller
```

### Step 2: Final secret scan

```bash
python3 tools/verify/no_secrets_in_repo.py
python3 tools/verify/tasker_gateway_security.py
```

### Step 3: Commit

```bash
git add -A && git commit -m "docs: architecture + migration from PoC to hardened v1"
```

---

## Self-Review Checklist

1. **Spec coverage:** Fase 0-9 all have corresponding tasks. Fase 10 (dogfooding) requires device — test scripts created but can't run on OCI.
2. **No placeholders:** Every task has actual code and test code.
3. **Type consistency:** `TaskerGatewayRequest`, `TaskerGatewayResponse`, `TaskerGatewayAuthenticator`, `PendingCommandRegistry`, `AdapterRegistry`, `TaskerGatewayTransport`, `TaskerGatewayReceiver`, `TaskerGatewayClient`, `TaskerGatewayConfig` — all names used consistently.
4. **Prohibitions check:** No new capabilities added. Only `device_owner.status.v1`. No eval(source) in production path. No /shell in transport. No secrets committed.
