# Implementation Plan: Tasker Hardened Executor — Pixel 8 Dogfood

## Overview

Install CI-tested APK (`01a7462`, SHA-256 `d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876`) onto Pixel 8, then execute 20 live dogfood tests against the hardened Tasker executor path. Produce timestamped, redacted evidence per command and a final acceptance decision.

## Prerequisites

- CI artifact `app-debug-01a7462/app-debug.apk` downloaded
- Pixel 8 reachable at `100.64.0.1:8765`
- Tasker installed as Device Owner
- No real secrets in logs, exports, or evidence

## Test Matrix (20 tests + 10 acceptance checks)

### T01 — Valid request
- **adapter_id:** `device_owner.status.v1`
- **Expected:** `ok=true`, `status=completed`, `result.is_device_owner=true`
- **Latency:** < 5000ms (deadline)
- **DPM observed:** yes (via `isDeviceOwnerApp`)

### T02 — Invalid HMAC
- **adapter_id:** `device_owner.status.v1`
- **auth.signature:** `deadbeef0000` (synthetic invalid)
- **Expected:** `ok=false`, `error.code=AUTH_FAILED` or HMAC verification failure
- **DPM observed:** no

### T03 — Post-signature alteration
- **adapter_id:** `device_owner.status.v1` → altered to `device_owner.status.v2` after signing
- **Expected:** `ok=false`, `error.code=INVALID_REQUEST_HASH` or HMAC failure
- **DPM observed:** no

### T04 — Unknown adapter
- **adapter_id:** `arbitrary.code.exec`
- **Expected:** `ok=false`, `error.code=UNKNOWN_ADAPTER`
- **DPM observed:** no

### T05 — Invalid JSON
- **Raw payload:** `THIS IS NOT VALID JSON {{{`
- **Expected:** parse error or rejection
- **DPM observed:** no

### T06 — Expired deadline
- **adapter_id:** `device_owner.status.v1`
- **deadline_at_ms:** 1ms from now (already expired before execution)
- **Expected:** `ok=false`, `error.code=deadline_exceeded`
- **DPM observed:** no

### T07 — Bridge timeout
- **adapter_id:** `device_owner.status.v1`
- **timeoutMs:** 1 (1ms — impossible to complete)
- **Expected:** `ok=false`, `error.code=timeout`
- **DPM observed:** no (or partial)

### T08 — Identical replay
- **Step 1:** Send valid request, record response
- **Step 2:** Re-send same command_id + same request_hash
- **Expected:** `DUPLICATE_IDENTICAL`, cached response returned
- **DPM observed:** once only (not twice)

### T09 — Conflicting replay
- **Step 1:** Send valid request, complete it
- **Step 2:** Send same command_id with different request_hash
- **Expected:** `error.code=command_id_conflict`
- **DPM observed:** once only

### T10 — Two distinct sequential
- **Step 1:** Send cmd-A, wait for response
- **Step 2:** Send cmd-B, wait for response
- **Expected:** Both succeed with unique command_ids
- **DPM observed:** twice

### T11 — Two distinct concurrent
- **Step 1:** Send cmd-C and cmd-D simultaneously
- **Expected:** Both succeed, no interference
- **DPM observed:** twice

### T12 — Tasker profile disabled
- **Action:** Disable the hardened gateway Tasker profile
- **Expected:** timeout (no response from Tasker)
- **Restore:** Re-enable profile immediately

### T13 — Shizuku stopped
- **Action:** Force-stop Shizuku
- **Expected:** valid request still completes (hardened path doesn't use Shizuku)
- **Restore:** Restart Shizuku

### T14 — /shell unavailable
- **Action:** Verify /shell endpoint returns error or is disabled
- **Expected:** valid request still completes via native broadcast
- **Restore:** N/A (should never be used)

### T15 — Legacy script absent
- **Action:** Rename `tasker-send-adapter.sh`
- **Expected:** valid request still completes (new path doesn't use script)
- **Restore:** Rename back

### T16 — Malicious par1
- **Action:** Send request with par1 containing JS code `eval("alert(1)")`
- **Expected:** ignored or rejected (par1 not in contract)
- **DPM observed:** no

### T17 — Forged response
- **Action:** Send a broadcast with ACTION_RESPONSE but invalid HMAC
- **Expected:** HMAC verification fails, command not completed
- **DPM observed:** no

### T18 — Bridge restart
- **Step 1:** Force-stop Bridge
- **Step 2:** Send valid request
- **Expected:** succeeds after Bridge restarts
- **DPM observed:** yes

### T19 — Tasker restart
- **Step 1:** Force-stop Tasker
- **Step 2:** Send valid request
- **Expected:** succeeds after Tasker restarts
- **DPM observed:** yes

### T20 — Performance (10 calls)
- **Action:** Send 10 valid independent requests
- **Expected:** median latency < 1000ms, zero polling, zero shell calls
- **Record:** min, max, median, mean, p95, executions, cache hits, rejections

## Acceptance Checks

| ID | Check | Pass criterion |
|----|-------|---------------|
| A | Sin Shizuku funciona | T13 passes |
| B | Sin /shell funciona | T14 passes |
| C | Sin tasker-send-adapter.sh funciona | T15 passes |
| D | Request sin código fuente | T16 passes |
| E | ID198 desactivado, nuevo gateway funciona | T01 passes with new profile |
| F | Deadline expirado no ejecuta DPM | T06 DPM observed=no |
| G | Duplicado idéntico no ejecuta DPM 2ª vez | T08 DPM observed=once |
| H | Duplicado conflictivo no sobrescribe | T09 returns command_id_conflict |
| I | Respuesta sin HMAC no completa comando | T17 passes |
| J | Ningún secreto en Git/exports/logs/evidence | Secret scan clean |

## Tasks

### Task 1: Evidence workspace + redaction rules
- Create `evidence/tasker-hardened-executor-pixel8-01a7462/`
- Create `run-metadata.md` with CI run, SHA, APK hash, device info
- Create `results.csv` with all 20 test rows
- Create `redaction-checklist.md`
- **Verify:** Secret scan on evidence dir

### Task 2: Artifact provenance + install
- Download APK, verify SHA-256 matches
- Check installed version + signing cert
- Install if signatures match; stop + document if mismatch
- Post-install health check: `/ping`, accessibility, relay
- **Verify:** Package version matches, data preserved

### Task 3: Baseline capture
- Bridge PID/UID, Tasker PID/UID
- Tasker profile state, Shizuku state
- Assign 20 unique command_ids + replay/conflict IDs
- **Verify:** Baseline recorded, command IDs assigned

### Task 4: Core validation (T01-T07)
- Execute T01-T07 sequentially
- Record command_id, timestamps, latency, outcome, DPM observation
- **Verify:** T01 passes, T02-T07 rejected correctly

### Task 5: Dedup (T08-T11)
- Execute T08-T11
- Record DPM execution counts
- **Verify:** Replay semantics correct, no last-write-wins

### Task 6: Resilience (T12-T15)
- Execute T12-T15 with restore between each
- **Verify:** Device returns to original state after each

### Task 7: Security + recovery (T16-T19)
- Execute T16-T19
- **Verify:** Malicious input rejected, forged response rejected, restarts recover

### Task 8: Performance (T20) + final report
- Execute T20 (10 calls)
- Calculate min/max/median/mean/p95
- Audit all evidence for A-J
- Issue acceptance decision
- **Verify:** median < 1s, all A-J pass

## Verification
- [ ] CI provenance recorded and matches
- [ ] All 20 tests have command_id, timestamps, outcome, latency
- [ ] A-J individually marked pass/fail
- [ ] Evidence dir passes secret scan
- [ ] Median latency < 1s

## Risks
- **Signing mismatch:** Stop, document, propose migration
- **Connectivity loss:** Record interruption, rerun affected tests with new IDs
- **Tasker state differs:** Capture in baseline, mark affected checks as blocked
- **HMAC exposure:** Use synthetic invalid values only, never export real auth
