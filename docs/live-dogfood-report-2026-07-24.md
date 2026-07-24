# Live Dogfood Report — 2026-07-24

## Device
- Pixel 8 (Shiba), Android 15, SDK 35
- Bridge APK v0.4.0 (not rebuilt with new endpoints)
- Relay: localhost:18766, token SFBCBA

## Results

| Check | Status | Detail |
|-------|--------|--------|
| Bridge connectivity | ✅ PASS | `/ping` returns ok, a11y=true, auth=true |
| Fingerprint `/device/info` | ⚠️ BLOCKED | 404 — APK doesn't have this endpoint yet |
| Fingerprint synthetic fallback | ✅ PASS | digest=116fb09c9eaed9aa, sdk_int=35 |
| Adapter selection | ✅ PASS | `clock_timer` selected for `timer.set` |
| Recipe selection | ✅ PASS | `clock.timer.set.v1` |
| Policy gate | ✅ PASS | stable tier, no envelope required |
| Intent dispatch (SET_TIMER) | ❌ FAIL | `Permission Denial: requires com.android.alarm.permission.SET_ALARM` |
| Broadcast dispatch (SET_TIMER) | ⚠️ INCONCLUSIVE | Broadcast sent successfully but Clock app ignores it |
| Verification (timer_exists) | ❌ INCONCLUSIVE | No timer created → observer has no data |
| Trace persistence | ✅ PASS | trace_id=54bf89f3eb03, 4 events, retrievable |
| Trace survives restart | ✅ PASS | CapabilityService re-opens same DB |
| Negative learning | ✅ PASS | Incompatible route persisted and retrieved |
| Nonce persistence | ✅ PASS | Nonces survive across service instances |
| `open_app` endpoint | ⚠️ BUG | Expects `package` (old) but repo uses `packageName` (new) |
| `current_app` observer | ⚠️ BUG | Shows `systemui` even when Clock is in foreground |

## Bugs Found (requiring APK rebuild)

### 1. Missing `SET_ALARM` permission (CRITICAL)
- Bridge APK manifest doesn't declare `com.android.alarm.permission.SET_ALARM`
- SET_TIMER intent always fails with Permission Denial
- **Fix**: Add `<uses-permission android:name="com.android.alarm.permission.SET_ALARM"/>` to bridge AndroidManifest.xml, rebuild APK

### 2. `open_app` field name drift
- Deployed APK expects `{"package": "..."}` 
- Repo code (BridgeRouter.kt) expects `{"packageName": "..."}`
- **Fix**: Rebuild APK from current source, or add `package` as alias

### 3. `current_app` observer inaccuracy
- Returns `systemui` even when Clock is in foreground
- Likely because `rootInActiveWindow` returns the overlay/status bar
- **Fix**: Use `windows.firstOrNull()?.root` or iterate windows to find app window

### 4. `/device/info` not deployed
- Endpoint added to BridgeRouter.kt source but APK v0.4.0 doesn't have it
- **Fix**: Rebuild APK

## What Worked End-to-End
- Connectivity → fingerprint (synthetic) → adapter selection → policy gate → intent dispatch attempt → trace persistence → retrieval → negative learning → nonce replay protection
- The entire Python-side circuit works correctly
- The blockers are all on the Kotlin bridge APK side

## Next Steps
1. Add `SET_ALARM` permission to bridge manifest
2. Rebuild and deploy bridge APK
3. Re-run live dogfood
4. Fix `current_app` observer to detect correct foreground window
