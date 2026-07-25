# Tasker Hardened Executor v1 — Architecture

**Date:** 2026-07-25  
**Status:** Implementation complete (Kotlin + verification)  
**Prerequisite:** Pixel 8 dogfooding (Fase 10)

---

## Overview

The Tasker Hardened Executor replaces the PoC (commit 202d18f) with a
production-grade transport that eliminates all security vulnerabilities:

- No remote code execution (eval/source)
- No plaintext authentication (HMAC-SHA256)
- No file-based polling (native broadcast)
- No /shell usage (native sendBroadcast)
- Correct deduplication (no last-write-wins)
- Real deadline enforcement

## Architecture Diagram

```
Hermes Agent (Python)
    │
    │  HTTP POST /tasker_gateway (future endpoint)
    ▼
HermesBridge Kotlin
    │
    ├── TaskerGatewayClient
    │   ├── validate adapter_id → AdapterRegistry
    │   ├── build request → TaskerGatewayRequest.create()
    │   │   ├── canonical JSON (sorted keys)
    │   │   ├── SHA-256 request_hash
    │   │   └── HMAC-SHA256 signature
    │   ├── dedup check → PendingCommandRegistry
    │   ├── deadline check → now > deadline_at_ms?
    │   └── send → TaskerGatewayTransport
    │
    ├── TaskerGatewayTransport
    │   └── sendBroadcast(ACTION_REQUEST) → Tasker
    │       (NO /shell, NO am, NO file I/O)
    │
    ├── TaskerGatewayReceiver
    │   ├── receive broadcast → ACTION_RESPONSE
    │   ├── validate HMAC → TaskerGatewayAuthenticator.verify()
    │   └── complete Deferred → PendingCommandRegistry
    │
    └── PendingCommandRegistry
        ├── NEW → register Deferred
        ├── DUPLICATE_IDENTICAL → return cached
        └── DUPLICATE_CONFLICT → reject
    │
    ▼ (broadcast)
Tasker Gateway (static dispatcher)
    │
    ├── receive intent → request_json extra
    ├── validate HMAC
    ├── check deadline
    ├── dispatch by adapter_id (static lookup)
    │
    ├── device_owner.status.v1
    │   ├── DevicePolicyManager.isDeviceOwnerApp()
    │   ├── DevicePolicyManager.isAdminActive()
    │   └── Build.VERSION fields
    │
    ├── build response → TaskerGatewayResponse
    ├── sign response → HMAC-SHA256
    └── sendBroadcast(ACTION_RESPONSE) → Bridge
```

## Kotlin Components

| Component | File | Responsibility |
|-----------|------|---------------|
| `TaskerGatewayAuthenticator` | `tasker/TaskerGatewayAuthenticator.kt` | HMAC-SHA256 sign/verify, canonical JSON, SHA-256 |
| `TaskerGatewayRequest` | `tasker/TaskerGatewayRequest.kt` | Request data class, creation, validation |
| `TaskerGatewayResponse` | `tasker/TaskerGatewayResponse.kt` | Response data class, success/error builders, signing |
| `AdapterRegistry` | `tasker/AdapterRegistry.kt` | Static allowlist (device_owner.status.v1 only) |
| `PendingCommandRegistry` | `tasker/PendingCommandRegistry.kt` | Dedup + CompletableDeferred correlation |
| `TaskerGatewayConfig` | `tasker/TaskerGatewayConfig.kt` | Secret provisioning, rotation, broadcast actions |
| `TaskerGatewayTransport` | `tasker/TaskerGatewayTransport.kt` | Native sendBroadcast to Tasker |
| `TaskerGatewayReceiver` | `tasker/TaskerGatewayReceiver.kt` | Receive + HMAC-verify responses |
| `TaskerGatewayClient` | `tasker/TaskerGatewayClient.kt` | High-level send+await orchestration |

## Contract v1

### Request
```json
{
  "version": 1,
  "command_id": "uuid",
  "adapter_id": "device_owner.status.v1",
  "params": {},
  "issued_at_ms": 1690000000000,
  "deadline_at_ms": 1690000010000,
  "nonce": "random",
  "request_hash": "sha256-of-canonical-payload",
  "auth": {
    "algorithm": "HMAC-SHA256",
    "signature": "base64-hmac"
  }
}
```

### Response
```json
{
  "version": 1,
  "command_id": "uuid",
  "adapter_id": "device_owner.status.v1",
  "request_hash": "...",
  "ok": true,
  "status": "completed",
  "received_at_ms": 0,
  "started_at_ms": 0,
  "completed_at_ms": 0,
  "duration_ms": 0,
  "result": {
    "is_device_owner": true,
    "package_name": "net.dinglisch.android.taskerm",
    "admin_receiver": "net.dinglisch.android.taskerm.MyDeviceAdminReceiver",
    "android_version": "15",
    "sdk_version": 35,
    "kernel_version": "6.1.157"
  },
  "executor": {
    "type": "tasker",
    "package_name": "net.dinglisch.android.taskerm",
    "process_uid": 10313,
    "process_pid": 0,
    "task_name": "Hermes · Command Gateway"
  },
  "error": null,
  "auth": {
    "algorithm": "HMAC-SHA256",
    "signature": "base64-hmac"
  }
}
```

## Canonical JSON

- Sorted keys (lexicographic)
- No whitespace
- UTF-8 encoding
- No HTML escaping
- Auth field excluded from signing payload

## Secret Provisioning

1. First run: `TaskerGatewayConfig.getOrCreateSecret()` generates 256-bit random
2. Stored in Android SharedPreferences (`tasker_gateway_config`)
3. Set as Tasker local variable `%gw_secret`
4. The Tasker JSlet reads it via `tasker.getVariable("gw_secret")`
5. Rotation: `TaskerGatewayConfig.rotateSecret()` generates new, requires re-provisioning
6. Never in Git, logs, exports, or evidence

## Verification

### Python verification (runs on OCI)
- `tools/verify/tasker_gateway_contract.py` — 33 checks (canonical JSON + HMAC)
- `tools/verify/tasker_gateway_dedup.py` — 16 checks (deduplication logic)
- `tools/verify/tasker_gateway_security.py` — 6 checks (no shell, no eval, no secrets)
- `tools/verify/tasker_gateway_full_suite.py` — 63 checks (comprehensive)
- `tools/verify/no_secrets_in_repo.py` — secret scanner

### Kotlin unit tests (run on device/CI)
- `TaskerGatewayAuthenticatorTest` — 13 tests
- `TaskerGatewayRequestTest` — 14 tests
- `TaskerGatewayResponseTest` — 7 tests
- `AdapterRegistryTest` — 12 tests
- `PendingCommandRegistryTest` — 10 tests
- `TaskerGatewayClientTest` — 9 tests

## Migration from PoC

See `docs/MIGRATION-POC-TO-V1.md` for detailed migration guide.

Key changes:
- File-based → broadcast transport
- Plaintext token → HMAC-SHA256
- eval(source) → static dispatcher
- Last-write-wins → replay-safe dedup
- Polling → Deferred-based async
