# Pre-Install Report: Tasker Hardened Executor — Pixel 8

## Artifact Verification

- **CI APK SHA-256:** `d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876`
- **Downloaded APK SHA-256:** `d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876`
- **Match:** ✅ Yes

## Installed Package

- **Package:** com.hermesandroid.bridge
- **Version:** 0.4.1 (versionCode=3)
- **Signing:** APK Signing v2, debug keystore (installed)

## CI APK

- **Package:** com.hermesandroid.bridge
- **Version:** 0.4.1 (versionCode=3)
- **Signing:** APK Signing v2, different debug keystore (CI runner)

## Compatibility

- **Result:** ❌ SIGNATURE_MISMATCH
- **Error:** `INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package com.hermesandroid.bridge signatures do not match newer version`
- **Cause:** The installed APK was signed with a different debug keystore than the CI runner's debug keystore. Debug keystores are per-machine, so OCI CI and the original dev machine produce different signatures.

## Decision

Per plan: **STOP installation.** Do not uninstall or clear data.

## Migration Options

1. **Sign with same keystore as installed APK** — extract the installed APK's signing key, use it to sign the CI build. Requires access to the original keystore.
2. **Uninstall + reinstall** — loses all app data (pairing code, preferences, accessibility settings). User must re-pair and reconfigure.
3. **Use a release keystore** — configure CI with a shared release keystore for consistent signing.
4. **ADB install with `-t` flag** — allows test/debug APK overrides. Use: `adb install -r -t app-debug.apk`

Option 4 is the quickest path for dogfood. The `-t` flag allows installing debug APKs over different-signed debug APKs.
