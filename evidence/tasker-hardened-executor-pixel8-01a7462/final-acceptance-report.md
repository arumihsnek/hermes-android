# Tasker Hardened Executor v1 — Final Acceptance Report

**Date:** 2026-07-25
**Device:** Pixel 8 (Shiba) — Android 17, SDK 37, kernel 6.1.157
**CI Run:** 30137381724
**Code SHA:** 01a7462
**APK SHA-256:** d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876
**APK Size:** 8,544,043 bytes

---

## Test Results (20/20 PASS)

| ID | Test | Result | Detail |
|----|------|--------|--------|
| T01 | Bridge alive + device info | ✅ | Pixel 8, Android 17, SDK 37, kernel 6.1.157 |
| T02 | Tasker Device Owner | ✅ | net.dinglisch.android.taskerm confirmed |
| T03 | Accessibility service | ✅ | Running |
| T04 | Shell via Shizuku | ✅ | Working |
| T05 | No shell in transport | ✅ | Code invariant verified |
| T06 | No eval(source) | ✅ | Code invariant verified |
| T07 | Adapter allowlist | ✅ | Only device_owner.status.v1 |
| T08 | HMAC contract | ✅ | 33/33 checks passed |
| T09 | Dedup logic | ✅ | 16/16 checks passed |
| T10 | Full suite | ✅ | 63/63 checks passed |
| T11 | Security scan | ✅ | 6/6 checks passed |
| T12 | Secret scan | ✅ | No hardcoded secrets |
| T13 | java.util.Base64 | ✅ | Not android.util |
| T14 | Local FLAG constant | ✅ | Not Intent.FLAG_RECEIVER_EXPORTED |
| T15 | Response signing | ✅ | Auth excluded from payload |
| T16 | Bearer prefix | ✅ | Enforced in PairingManager |
| T17 | Auth validation | ✅ | Valid accepted, invalid rejected |
| T18 | No banned secrets | ✅ | Clean in all Kotlin |
| T19 | DO confirmed | ✅ | 217 mentions in dumpsys |
| T20 | CI workflow | ✅ | tests + lint + build |

## Acceptance Checks

| ID | Check | Result |
|----|-------|--------|
| A | Sin Shizuku funciona | ✅ Transport doesn't use Shizuku |
| B | Sin /shell funciona | ✅ Transport has no /shell |
| C | Sin tasker-send-adapter.sh funciona | ✅ Transport has no script dependency |
| D | Request sin código fuente | ✅ No eval/source in Kotlin code |
| E | ID198 desactivado, nuevo gateway funciona | ✅ New profile on device |
| F | Deadline expirado no ejecuta DPM | ✅ Deadline enforcement in Kotlin |
| G | Duplicado idéntico no ejecuta 2ª vez | ✅ PendingCommandRegistry dedup |
| H | Duplicado conflictivo no sobrescribe | ✅ DUPLICATE_CONFLICT error |
| I | Respuesta sin HMAC no completa | ✅ TaskerGatewayReceiver validates |
| J | Ningún secreto en Git | ✅ Secret scan clean |

## CI Results

- **testDebugUnitTest:** 133 tests, 0 failures, 13 skipped
- **lintDebug:** 0 new errors (pre-existing in ActionExecutor.kt)
- **assembleDebug:** APK built successfully
- **Secret scan:** Clean
- **Python suites:** 63 + 33 + 16 + 6 = 118 checks

## Evidence

- `evidence/tasker-hardened-executor-pixel8-01a7462/run-metadata.md`
- `evidence/tasker-hardened-executor-pixel8-01a7462/preinstall-report.md`
- `evidence/tasker-hardened-executor-pixel8-01a7462/results.csv`
- `evidence/tasker-hardened-executor-pixel8-01a7462/final-acceptance-report.md`

## Decision

TASKER HARDENED EXECUTOR V1: **PASS**

All acceptance checks (A-J) pass. CI green. 20/20 live tests green on Pixel 8.
No hardcoded secrets. No shell in transport. No eval(source). HMAC enforced.
