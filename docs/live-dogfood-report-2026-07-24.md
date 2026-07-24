# Live Dogfood Report — 2026-07-24 (FINAL)

## Device
- Pixel 8, Android SDK 37
- Bridge APK v0.4.1 (versionCode=3)
- `dumpsys package`: `com.android.alarm.permission.SET_ALARM: granted=true`

## Evidence

```
bridge_version:           0.4.1
apk_version_code:         3
apk_signature:            DEBUG (uninstall+reinstall required)
device_fingerprint_digest: 292e2ec5af7473da
sdk_int:                  37 (REAL)
device_model:             Google Pixel 8
clock_package:            9.0 (943154005):76073631
fingerprint_source:       LIVE /device/info
selected_adapter:         clock_timer
selected_recipe:          clock.timer.set.v1
recipe_maturity:          stable
dispatched_action:        android_send_intent (SET_TIMER)
no_permission_denial:     true  ← SET_ALARM works
timer_alarm_in_dumpsys:   true  ← timer is running
trace_id:                 897a99b2cd26
trace_events:             4
trace_retrieved:          yes
persisted_after_restart:  yes
neg_learning_recorded:    true
neg_learning_cross_restart: true
nonce_block:              true
python_suite:             531 passed, 1 skipped
```

## Gate Decision: PASS ✓

### What works end-to-end
1. Bridge v0.4.1 with SET_ALARM permission — **no more Permission Denial**
2. Real device fingerprint from `/device/info` — sdk=37, not synthetic
3. `current_app` identifies real apps (filters systemui, shows quality)
4. `open_app` accepts both `package` (deprecated) and `packageName` (canonical)
5. Timer intent dispatched and confirmed running via `dumpsys alarm`
6. Trace persisted and survived CapabilityService restart
7. Negative learning persisted cross-service
8. Nonce replay blocked
9. Python suite: 531 passed, no regressions

### Known limitation (not a blocker)
The `timer_exists` verifier returns "inconclusive" because it lacks alarm
manager access. The timer IS running (confirmed via `dumpsys alarm`), but
the observer cannot query `AlarmManager` or Clock's ContentProvider directly.
This would require adding a `/alarm_manager` endpoint to the bridge —
documented as future work.

## Files Modified
- `hermes-android-bridge/app/src/main/AndroidManifest.xml` — +SET_ALARM permission
- `hermes-android-bridge/app/src/main/kotlin/.../BridgeRouter.kt` — open_app normalization, current_app robustness, /device/info fix
- `hermes-android-bridge/app/src/main/kotlin/.../DeviceCapabilities.kt` — +packageManager field
- `hermes-android-bridge/app/build.gradle.kts` — versionCode=3, versionName=0.4.1
- 4 Kotlin test files (manifest, open_app, current_app, device_info)
- `docs/live-dogfood-report-2026-07-24.md` — this report
