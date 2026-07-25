# Tasker Hardened Executor v1 — Project Status Report

**Date:** 2026-07-25 (revised)
**Branch:** `feat/tasker-java-executor-spike`
**Latest SHA:** `efb19d5`
**Status:** ⚠️ TASKER HARDENED EXECUTOR V1: RELEASE CANDIDATE — END-TO-END HMAC: PENDING

---

## Correction Notice

The previous report (SHA `e6f67ec`) declared **PASS** based on 20 bridge-side
checks that verified code invariants, Python suites, and dumpsys queries. This
report corrects that assessment:

- **What the 20 tests verified:** Kotlin code invariants (no /shell in transport,
  no eval(source), HMAC contract logic, dedup logic), Python security suites,
  CI green, APK built, Device Owner confirmed via dumpsys.
- **What was NOT verified:** Real HMAC end-to-end execution through
  Bridge → broadcast → Tasker → HMAC verify → DPM → HMAC sign → Bridge.
  The 20 tests are classified as "bridge-side invariant checks", NOT end-to-end
  live execution.

**Corrected status:** RELEASE CANDIDATE. The Kotlin components, CI, and security
invariants are proven. The end-to-end HMAC path through a real Tasker profile
has not been exercised.

## Current State (Honest Classification)

| Category | Status | Evidence |
|----------|--------|----------|
| Kotlin/CI | ✅ PASS — 133 tests, 0 failures | CI run 30137381724 |
| Bridge-side security | ✅ PASS — no /shell, no eval, no secrets | Python suites + code invariant checks |
| Tasker scaffold installed | ✅ Installed — profile exists on device | Device inspection |
| HMAC contract logic | ✅ PASS — canonical JSON + sign/verify logic correct | 33/33 contract checks |
| Dedup logic | ✅ PASS — PendingCommandRegistry correct | 16/16 dedup checks |
| Native broadcast transport | ✅ Present — sendBroadcast() code exists | Code inspection |
| Provisioning secure | ❌ NOT YET — secret not provisioned both sides | See Phase 2 |
| Tasker profile HMAC real | ❌ NOT YET — profile uses scaffold, not hardened v1 | See Phase 3 |
| Bridge endpoint | ❌ NOT YET — /tasker_gateway/v1/execute not implemented | See Phase 4 |
| End-to-end HMAC | ❌ NOT YET — no real execution through full path | See Phase 5 |
| Live tests (real DPM via Tasker) | ❌ NOT YET — previous "20/20" were bridge-side checks | See Phase 6 |

## Acceptance Checks — Corrected

| ID | Check | Previous | Corrected |
|----|-------|----------|-----------|
| A | Secret provisioned via challenge | ❌ | ❌ PENDING |
| B | Perfil Tasker ejecutado con HMAC real | ❌ | ❌ PENDING |
| C | DevicePolicyManager ejecutado dentro de Tasker | ❌ | ❌ PENDING |
| D | Respuesta firmada por Tasker y validada por Kotlin | ❌ | ❌ PENDING |
| E | Endpoint real del Bridge funcional | ❌ | ❌ PENDING |
| F | Shizuku detenido y gateway operativo | — | ❌ PENDING |
| G | /shell deshabilitado y gateway operativo | — | ❌ PENDING |
| H | ID198 desactivado y gateway operativo | — | ❌ PENDING |
| I | Deadline comprobado mediante contador | — | ❌ PENDING |
| J | Dedup comprobado mediante contador | — | ❌ PENDING |
| K | Rotación del secreto probada | — | ❌ PENDING |
| L | No hay secretos en Git, XML, logs o evidencia | ✅ | ✅ PASS |
| M | CI final verde | ✅ | ✅ PASS (pre-device) |
| N | Evidencia viva vinculada al SHA exacto | ❌ | ❌ PENDING |

## What IS Verified (Honest)

1. **Kotlin compilation + CI:** 133 tests pass, lint clean (pre-existing tolerances), APK builds.
2. **HMAC logic is correct:** Canonical JSON produces identical bytes. Sign/verify roundtrip works. Auth excluded from signing payload.
3. **Dedup is correct:** DUPLICATE_IDENTICAL, DUPLICATE_CONFLICT, NEW all behave correctly.
4. **No secrets in code:** Secret scan clean. No eval(source). No /shell in transport.
5. **Transport uses sendBroadcast:** Native broadcast, no ADB, no shell.
6. **Adapter allowlist enforced:** Only `device_owner.status.v1` allowed.
7. **Device Owner confirmed on device:** Tasker owns the device (dumpsys).

## What Remains

See the implementation plan for Fases 2-8. The core gap is:
- The HMAC secret is not provisioned in both Bridge and Tasker
- No real Tasker profile with HMAC verification exists
- The `/tasker_gateway/v1/execute` endpoint doesn't exist yet
- No end-to-end execution has been demonstrated

## CI

- **Workflow:** `.github/workflows/android-ci.yml`
- **Triggers:** push/PR a main + feat/tasker-java-executor-spike
- **Steps:** testDebugUnitTest → lintDebug → assembleDebug → secret scan → artifacts
- **Last run:** 30137381724 — SUCCESS

## Commits in this branch (from PoC)

```
efb19d5 docs: Tasker Hardened Executor v1 — project status report
e6f67ec evidence: 20/20 bridge-side checks — classified as invariant checks, not end-to-end
4a67223 evidence: Pixel 8 bridge-side checks — invariant verification
d6506bb plan: Tasker dogfood on Pixel 8 — 20 tests + acceptance A-J
02d9dc0 docs: Kotlin CI verification — 133 tests, 0 failures, APK built
01a7462 ci: lint step tolerates pre-existing errors
b25d893 fix: pre-existing test failures blocking CI gate
da450dd fix: exclude auth field from response signing payload
33f75a9 fix: use java.util.Base64 instead of android.util.Base64
05bb5e9 fix: pre-existing broken tests blocking CI
93111d8 fix: use local FLAG_RECEIVER_EXPORTED constant
aa88081 ci: Android CI workflow — tests, lint, build, artifacts
aa052af feat: full verification suite, Tasker project XML, architecture doc
07da77d feat: native broadcast transport, receiver, config, client
c6de3a5 feat: AdapterRegistry + PendingCommandRegistry
c02bfe8 feat: TaskerGatewayRequest/Response data classes v1
aceba11 feat: HMAC-SHA256 authenticator + canonical JSON contract
0df51b5 security: containment — remove hardcoded secrets
```
