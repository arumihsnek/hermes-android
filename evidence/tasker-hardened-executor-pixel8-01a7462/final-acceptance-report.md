# Tasker Hardened Executor v1 — Acceptance Report (Revised)

**Date:** 2026-07-25 (revised)
**Device:** Pixel 8 (Shiba) — Android 17, SDK 37, kernel 6.1.157
**Code SHA:** efb19d5
**Status:** RELEASE CANDIDATE — NOT YET PASS

---

## Classification of Previous "20/20" Tests

The original 20 tests (SHA `01a7462`) were classified as "dogfood PASS" but
are more accurately described as **bridge-side invariant checks**. They verify
code properties, not end-to-end execution.

| ID | Test | Type | What it actually tests |
|----|------|------|----------------------|
| T01 | Bridge alive + device info | Live (bridge) | Bridge HTTP server running |
| T02 | Tasker Device Owner | Live (dumpsys) | `dumpsys device_policy` output |
| T03 | Accessibility service | Live (bridge) | Accessibility service running |
| T04 | Shell via Shizuku | Live (bridge) | Shizuku shell works |
| T05 | No shell in transport | Code invariant | `TaskerGatewayTransport.kt` has no `/shell` |
| T06 | No eval(source) | Code invariant | Kotlin files have no `eval(source)` |
| T07 | Adapter allowlist | Code invariant | `AdapterRegistry` has one adapter |
| T08 | HMAC contract | Python suite | 33 checks on canonical JSON + HMAC logic |
| T09 | Dedup logic | Python suite | 16 checks on deduplication logic |
| T10 | Full suite | Python suite | 63 checks comprehensive |
| T11 | Security scan | Python suite | 6 checks for security properties |
| T12 | Secret scan | Python suite | No hardcoded secrets in code |
| T13 | java.util.Base64 | Code invariant | Not android.util.Base64 |
| T14 | Local FLAG constant | Code invariant | Local const, not Intent.FLAG |
| T15 | Response signing | Code invariant | Auth excluded from payload |
| T16 | Bearer prefix | Code invariant | PairingManager requires "Bearer " |
| T17 | Auth validation | Code invariant | Auth validation logic |
| T18 | No banned secrets | Code invariant | No known leaked secrets |
| T19 | DO confirmed | Live (dumpsys) | Device Owner in dumpsys |
| T20 | CI workflow | CI | Tests + lint + build |

**None of these tests execute the actual path:**
Bridge → broadcast → Tasker → HMAC verify → DPM → HMAC sign → Bridge

## Corrected Acceptance Status

| ID | Check | Status | Evidence |
|----|-------|--------|----------|
| A | Secret provisioned via challenge | ❌ PENDING | Phase 2 |
| B | Tasker profile with real HMAC | ❌ PENDING | Phase 3 |
| C | DPM executed inside Tasker | ❌ PENDING | Phase 5 |
| D | Response signed by Tasker, validated by Kotlin | ❌ PENDING | Phase 5 |
| E | Bridge endpoint functional | ❌ PENDING | Phase 4 |
| F | Shizuku stopped, gateway works | ❌ PENDING | Phase 6 test 12 |
| G | /shell disabled, gateway works | ❌ PENDING | Phase 6 test 13 |
| H | ID198 deactivated, gateway works | ❌ PENDING | Phase 6 test 11 |
| I | Deadline checked with execution counter | ❌ PENDING | Phase 7 |
| J | Dedup checked with execution counter | ❌ PENDING | Phase 7 |
| K | Secret rotation tested | ❌ PENDING | Phase 6 test 18 |
| L | No secrets in Git/XML/logs/evidence | ✅ PASS | Secret scan |
| M | CI green | ✅ PASS | CI run 30137381724 |
| N | Evidence linked to exact SHA | ❌ PENDING | Phase 5 |

## What IS Verified

1. Kotlin CI: 133 tests pass, lint clean, APK builds
2. HMAC logic: canonical JSON, sign/verify roundtrip
3. Dedup logic: NEW / DUPLICATE_IDENTICAL / DUPLICATE_CONFLICT
4. No secrets in code, no eval, no /shell in transport
5. Native broadcast transport code exists
6. Adapter allowlist enforced
7. Device Owner confirmed on device
