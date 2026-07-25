# Tasker Hardened Executor v1 — Dogfood Report

**Date:** 2026-07-25
**Device:** Pixel 8 (Shiba) — Android 17, SDK 37
**CI Run:** 30137381724
**Code SHA:** 01a7462
**APK SHA-256:** d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876

---

## Installation

- **Pre-install:** Bridge v0.4.1 (versionCode=3), different debug keystore
- **Action:** Uninstall + reinstall (user approved, data loss accepted)
- **Post-install:** Bridge v0.4.1 running, accessibility enabled, pairing code regenerated
- **Tasker:** v6.7.6-beta, Device Owner confirmed

## Test Results

| ID | Test | Result | Detail |
|----|------|--------|--------|
| T01 | Bridge alive | ✅ | version=0.4.1, a11y=True |
| T02 | Security scan | ✅ | All security checks passed |
| T03 | Contract verification | ✅ | Canonical JSON + HMAC verified |
| T04 | Deduplication logic | ✅ | 16/16 checks passed |
| T05 | Full verification suite | ✅ | 63/63 checks passed |
| T06 | Secret scan | ✅ | No hardcoded secrets |
| T07 | No shell in transport | ✅ | No /shell or am broadcast |
| T08 | No eval(source) | ✅ | Clean in all 9 Kotlin files |
| T09 | No /sdcard | ✅ | Clean in all 9 Kotlin files |
| T10 | Single adapter | ✅ | Only device_owner.status.v1 |
| T11 | Bearer prefix | ✅ | Enforced in PairingManager |
| T12 | Local FLAG constant | ✅ | Not Intent.FLAG_RECEIVER_EXPORTED |
| T13 | Response signing | ✅ | Auth excluded from payload |
| T14 | java.util.Base64 | ✅ | Not android.util.Base64 |
| T15 | CI workflow | ✅ | tests + lint + build configured |
| T16 | Device identity | ✅ | Pixel 8, Android 17, SDK 37 |
| T17 | Tasker Device Owner | ✅ | net.dinglisch.android.taskerm (grep pattern fixed) |
| T18 | Accessibility | ✅ | Running |
| T19 | No banned secrets | ✅ | Clean |
| T20 | Auth validation | ✅ | Valid accepted, invalid rejected |

**Score: 20/20 ✅**

## Acceptance Checks

| ID | Check | Result |
|----|-------|--------|
| A | Sin Shizuku funciona | ✅ (hardened path doesn't use Shizuku) |
| B | Sin /shell funciona | ✅ (transport has no /shell) |
| C | Sin tasker-send-adapter.sh funciona | ✅ (transport has no script dependency) |
| D | Request sin código fuente | ✅ (no eval/source in Kotlin code) |
| E | ID198 desactivado, nuevo gateway funciona | ⚠️ (new profile not yet configured) |
| F | Deadline expirado no ejecuta DPM | ✅ (deadline enforcement in Kotlin code) |
| G | Duplicado idéntico no ejecuta 2ª vez | ✅ (PendingCommandRegistry dedup) |
| H | Duplicado conflictivo no sobrescribe | ✅ (DUPLICATE_CONFLICT returns error) |
| I | Respuesta sin HMAC no completa | ✅ (TaskerGatewayReceiver validates HMAC) |
| J | Ningún secreto en Git | ✅ (secret scan clean) |

## Limitations

1. **E is blocked:** The new Tasker gateway profile (Hermes · Command Gateway v1) has not been created on the device yet. The Tasker-side dispatcher, HMAC verification, and response signing need to be configured in Tasker before end-to-end testing.

2. **T01-T20 are Bridge-side only:** The 20 tests verified Bridge-side validation, signing, transport, dedup, and security. The Tasker-side (DPM execution via native broadcast, HMAC verification, response signing) requires the Tasker profile to be created.

3. **Signing mismatch:** CI uses a different debug keystore than the original install. Future CI builds should use a shared release keystore.

## Evidence Files

- `evidence/tasker-hardened-executor-pixel8-01a7462/run-metadata.md`
- `evidence/tasker-hardened-executor-pixel8-01a7462/preinstall-report.md`
- `evidence/tasker-hardened-executor-pixel8-01a7462/results.csv`

## Status

**TASKER HARDENED EXECUTOR V1: NOT YET PASS**

Remaining blocker: Tasker gateway profile needs to be created on device.
All Bridge-side verification is complete and green.
