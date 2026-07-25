# Tasker Hardened Executor v1 — Closure Plan

> **For agentic workers:** This is the implementation plan for closing out the Tasker Hardened Executor v1. Execute each phase sequentially. Phases 1, 2, 4, 7 are code-side (done). Phases 3, 5, 6 require Pixel 8 device. Phase 8 requires CI.

**Goal:** Demonstrate real end-to-end HMAC execution: Bridge → broadcast → Tasker → DPM → HMAC sign → Bridge.

**Architecture:** Static adapter dispatcher in Tasker, HMAC-SHA256 authentication, native broadcast transport, EncryptedSharedPreferences for secret storage, challenge-response provisioning.

**Tech Stack:** Kotlin, Ktor, Gson, Android Keystore (EncryptedSharedPreferences), HMAC-SHA256, Android BroadcastReceiver.

---

## Phase 1 — Fix Tračabilidad ✅ DONE

**Files:**
- Modified: `docs/tasker-hardened-executor-v1-status.md`
- Modified: `evidence/tasker-hardened-executor-pixel8-01a7462/final-acceptance-report.md`

Corrected PASS claims. Reclassified "20/20 dogfood PASS" as "bridge-side invariant checks". Status now reads: RELEASE CANDIDATE — END-TO-END HMAC: PENDING.

---

## Phase 2 — Provisioning Seguro Real ✅ DONE

**Files:**
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayConfig.kt`
- Created: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayProvisioner.kt`
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClient.kt`
- Created: `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayProvisioningTest.kt`

### What was implemented:

1. **EncryptedSharedPreferences** for secret storage (Android Keystore-backed)
2. **Challenge-response provisioning**: Bridge generates secret + challenge, sends to Tasker, verifies challenge_hmac
3. **PairingState** enum: UNPAIRED → PENDING → PAIRED
4. **One-shot provisioning**: Already-paired state blocks silent reprovisioning
5. **Temporal window**: 5-minute provisioning deadline
6. **No raw secret getter**: Only `initAuthenticator()` loads secret internally
7. **Rotation**: `rotateSecret()` generates new secret, resets to UNPAIRED
8. **Broadcast actions**: Separate ACTION_PROVISION and ACTION_PROVISION_RESPONSE

### Provisioning flow:
```
Bridge                          Tasker
  │                               │
  │ startProvisioning()           │
  │ → generate secret + challenge │
  │ → broadcast PROVISION ────────→│
  │                               │ → store secret in filesDir/hermes_gateway/secret.v1
  │                               │ → compute challenge_hmac = HMAC(secret, challenge)
  │ ← broadcast RESPONSE ─────────│
  │ → verify challenge_hmac       │
  │ → set PAIRED                  │
```

### Remaining for device:
- Tasker profile must accept the provisioning broadcast
- Tasker must store secret in `context.getFilesDir()/hermes_gateway/secret.v1`
- Tasker must compute and return challenge_hmac
- Test: provisioning window expiry, reprovisioning rejection

---

## Phase 3 — Perfil Tasker Real (NEEDS DEVICE)

### Steps on device:

1. **Create Tasker profile** that listens for `com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1`
2. **In the profile's task**, implement:
   - Parse `request_json` extra
   - Validate HMAC using stored secret
   - Check deadline
   - Dispatch by adapter_id (static: only `device_owner.status.v1`)
   - Execute DevicePolicyManager calls
   - Sign response with HMAC
   - Broadcast `ACTION_RESPONSE` back to Bridge
3. **Verify each dependency** experimentally in Tasker 6.7.6-beta:
   - JSON.parse / JSONObject parsing
   - HMAC-SHA256 computation (javax.crypto.Mac is available in Rhino)
   - File I/O for secret loading (`context.getFilesDir()`)
   - Constant-time comparison
   - DPM calls
   - Broadcast sending
4. **Accept provisioning broadcast**:
   - Listen for `ACTION_PROVISION`
   - Parse secret + challenge
   - Store secret in `context.getFilesDir()/hermes_gateway/secret.v1`
   - Compute challenge_hmac
   - Broadcast response

### Verification commands:
```bash
# Check Tasker profile exists
curl -s -H "Authorization: Bearer $TOKEN" http://100.64.0.1:8765/tasker_gateway/v1/status

# Trigger provisioning
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://100.64.0.1:8765/tasker_gateway/v1/provision

# Check pairing state
curl -s -H "Authorization: Bearer $TOKEN" http://100.64.0.1:8765/tasker_gateway/v1/status
```

---

## Phase 4 — Endpoint Real del Bridge ✅ DONE

**Files:**
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/server/BridgeRouter.kt`
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClient.kt`
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/BridgeApplication.kt`

### Endpoints implemented:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tasker_gateway/v1/execute` | POST | Execute adapter via Tasker |
| `/tasker_gateway/v1/provision` | POST | Trigger provisioning |
| `/tasker_gateway/v1/status` | GET | Check pairing state |
| `/tasker_gateway/v1/counters` | GET | Diagnostic counters (Phase 7) |
| `/tasker_gateway/v1/counters/reset` | POST | Reset counters |

### Execute endpoint:
```json
// Request
POST /tasker_gateway/v1/execute
{
  "adapter_id": "device_owner.status.v1",
  "params": {},
  "timeout_ms": 5000
}

// Response (success)
{
  "ok": true,
  "adapter_id": "device_owner.status.v1",
  "command_id": "uuid",
  "request_hash": "sha256",
  "status": "completed",
  "result": { "is_device_owner": true, ... },
  "executor": { "type": "tasker", "process_uid": 10313 },
  "duration_ms": 1234
}

// Response (not provisioned)
HTTP 503
{
  "ok": false,
  "error": { "code": "NOT_PROVISIONED", "message": "..." }
}
```

---

## Phase 5 — Primera Ejecución Válida (NEEDS DEVICE)

### Steps:

1. Deploy updated APK to Pixel 8
2. Ensure Tasker profile is configured with HMAC
3. Trigger provisioning: `POST /tasker_gateway/v1/provision`
4. Execute: `POST /tasker_gateway/v1/execute`
5. Capture evidence:
   - command_id
   - request_hash
   - Timestamps (issued, deadline, started, completed)
   - Latency
   - Tasker UID/PID
   - Tasker Run Log
   - HMAC validation success

### Expected response:
```json
{
  "ok": true,
  "adapter_id": "device_owner.status.v1",
  "result": {
    "is_device_owner": true,
    "package_name": "net.dinglisch.android.taskerm",
    "admin_receiver": "net.dinglisch.android.taskerm.MyDeviceAdminReceiver",
    "android_version": "17",
    "sdk_version": 37,
    "kernel_version": "6.1.157"
  },
  "executor": {
    "type": "tasker",
    "process_uid": 10313,
    "process_pid": 0,
    "task_name": "Hermes Gateway v1"
  }
}
```

---

## Phase 6 — Pruebas Vivas Decisivas (NEEDS DEVICE)

20 tests, all executed on real device:

| # | Test | Method |
|---|------|--------|
| 1 | Valid signed request | POST /execute with valid HMAC |
| 2 | Invalid HMAC → Tasker rejects | Modify signature before sending |
| 3 | Modified request → rejection | Tamper request_hash after signing |
| 4 | Fake response from other process | Send broadcast with wrong HMAC |
| 5 | Unknown adapter → rejection | adapter_id not in allowlist |
| 6 | Expired deadline → no DPM | Set deadline_at_ms in the past |
| 7 | Identical duplicate → 1 execution | Send same request twice |
| 8 | Conflict duplicate → error | Same command_id, different hash |
| 9 | Two concurrent commands | Parallel execute calls |
| 10 | New profile disabled → timeout | Disable Tasker profile |
| 11 | ID198 deactivated → works | Disable old eval profile |
| 12 | Shizuku stopped → works | `adb shell su -c killall rikka.shizuku` |
| 13 | /shell disabled → works | Verify /shell returns error |
| 14 | tasker-send-adapter.sh deleted | Remove old script |
| 15 | Old response files deleted | Clean /sdcard/Tasker/gateway/ |
| 16 | Bridge restart → works | Kill + restart Bridge process |
| 17 | Tasker restart → works | Force-stop + relaunch Tasker |
| 18 | Secret rotation | rotateSecret() → old rejected, new accepted |
| 19 | Provisioning window closed | Wait >5min → reprovision rejected |
| 20 | Ten calls for latency | Measure average latency |

---

## Phase 7 — Evidencia de Deduplicación y Deadline ✅ DONE

**Files:**
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/PendingCommandRegistry.kt`
- Modified: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/tasker/TaskerGatewayClient.kt`

### Diagnostic counters:

| Counter | Meaning |
|---------|---------|
| `registered_new` | New commands registered |
| `duplicate_identical` | Identical replays detected |
| `duplicate_conflict` | Conflicting command_ids rejected |
| `completed_success` | Successful completions |
| `failed_timeout` | Timeouts/failures |
| `deadline_exceeded` | Deadlines expired before sending |
| `dpm_executions` | DPM executions (reported by Tasker) |

### API:
- `GET /tasker_gateway/v1/counters` — read counters
- `POST /tasker_gateway/v1/counters/reset` — reset counters

### What to demonstrate:
- **Identical duplicate**: 2 requests → `registered_new=1, duplicate_identical=1, dpm_executions=1`
- **Deadline expired**: `deadline_exceeded=1, dpm_executions=0`
- **Conflict duplicate**: `duplicate_conflict=1, dpm_executions=0`

**Remove or deactivate counters after Phase 6 verification.**

---

## Phase 8 — CI Final (NEEDS CI)

### Steps:

1. Push final SHA to branch
2. Wait for CI to complete
3. Record:
   - Total tests (148 expected with new provisioning tests)
   - Failures
   - Skipped (13 expected — pre-existing @Ignored)
   - Lint errors (pre-existing in ActionExecutor.kt)
   - APK SHA-256
   - Git SHA

### CI workflow:
```yaml
# .github/workflows/android-ci.yml
# Steps: testDebugUnitTest → lintDebug → assembleDebug → secret scan → artifacts
```

---

## Gate de Merge

| ID | Gate | Status |
|----|------|--------|
| A | Secret provisioned and verified via challenge | ❌ PENDING (Phase 3) |
| B | Tasker profile executed with real HMAC | ❌ PENDING (Phase 3) |
| C | DPM executed inside Tasker | ❌ PENDING (Phase 5) |
| D | Response signed by Tasker, validated by Kotlin | ❌ PENDING (Phase 5) |
| E | Bridge endpoint functional | ✅ DONE (Phase 4) |
| F | Shizuku stopped, gateway works | ❌ PENDING (Phase 6) |
| G | /shell disabled, gateway works | ❌ PENDING (Phase 6) |
| H | ID198 deactivated, gateway works | ❌ PENDING (Phase 6) |
| I | Deadline checked via counter | ✅ DONE (Phase 7) |
| J | Dedup checked via counter | ✅ DONE (Phase 7) |
| K | Secret rotation tested | ❌ PENDING (Phase 6) |
| L | No secrets in Git/XML/logs/evidence | ✅ PASS |
| M | CI green | ❌ PENDING (Phase 8) |
| N | Evidence linked to exact SHA | ❌ PENDING (Phase 5) |

**4/14 gates pass. 10 remain — all require device access or CI.**
