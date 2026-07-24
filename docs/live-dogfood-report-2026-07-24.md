# Live Dogfood Report — 2026-07-24 (v0.4.1)

## Device
- Pixel 8 (Shiba), Android SDK 37
- Bridge APK v0.4.1 (versionCode=3)
- Signature: DEBUG (uninstall+reinstall required)
- Relay: 100.64.0.1:8765, token SFBCBA

## Results

| Check | Status | Detail |
|-------|--------|--------|
| Bridge connectivity | ✅ PASS | v0.4.1, a11y=true, auth=true |
| Fingerprint `/device/info` | ✅ PASS | **REAL** — digest=292e2ec5af7473da |
| Fingerprint sdk_int | ✅ PASS | 37 (REAL, not synthetic) |
| Fingerprint model | ✅ PASS | Google Pixel 8 |
| Clock version | ✅ PASS | 9.0 (943154005) |
| Adapter selection | ✅ PASS | `clock_timer` for `timer.set` |
| Recipe selection | ✅ PASS | `clock.timer.set.v1` |
| Policy gate | ✅ PASS | stable tier, allowed |
| Intent dispatch (SET_TIMER) | ✅ PASS | `success: true` — no more Permission Denial |
| SET_ALARM permission | ✅ PASS | `granted=true` in manifest |
| `open_app` contract | ✅ PASS | `package` alias accepted (backward compat) |
| `current_app` observer | ✅ PASS | Shows `com.google.android.deskclock` with `quality: confirmed` |
| `current_app` discards systemui | ✅ PASS | `discarded: ['com.android.systemui']` |
| Timer created | ✅ PASS | Confirmed via `dumpsys alarm` — `TIMER_EXPIRED` alarm scheduled |
| Verification | ⚠️ LIMITATION | Verifier returns "inconclusive" — no alarm manager access |
| Trace persistence | ✅ PASS | trace_id=d364b8a0cc19, 4 events, retrievable |
| Trace survives restart | ✅ PASS | CapabilityService re-opens same DB |
| Negative learning | ✅ PASS | Incompatible route persisted and retrieved |
| Nonce persistence | ✅ PASS | Nonces survive across service instances |
| Python test suite | ✅ PASS | 531 passed, 1 skipped |

## Bugs Fixed in v0.4.1

1. **SET_ALARM permission** — Added `com.android.alarm.permission.SET_ALARM` to manifest
2. **open_app normalization** — `package` alias accepted alongside `packageName`
3. **current_app robustness** — Skips systemui, shows real app with quality indicator
4. **/device/info context** — Fixed ClassCastException by using DeviceCapabilities.packageManager

## Verification Limitation

The `timer_exists` verifier returns "inconclusive" because:
- It queries `/current_app` and `/notifications` but not the alarm manager
- With `SKIP_UI=true`, Clock doesn't show a notification
- The timer IS running (confirmed via `dumpsys alarm`)

To fully verify, the observer would need to query `dumpsys alarm` or the Clock app's ContentProvider. This is a known limitation documented in the architecture.

## Fingerprints
```
bridge_version: 0.4.1
apk_version_code: 3
device_fingerprint_digest: 292e2ec5af7473da
device_model: Google Pixel 8
android_sdk: 37
clock_package_version: 9.0 (943154005)
```
