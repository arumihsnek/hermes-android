# Run Metadata: Tasker Hardened Executor — Pixel 8 Dogfood

- **CI Run:** 30137381724
- **Code SHA:** 01a7462
- **APK SHA-256:** d30fb095ad84da076ba14eb3a127809a96c98bf601968b02d0821ac7887ee876
- **APK Size:** 8,544,043 bytes
- **Device:** Pixel 8 (Shiba)
- **Tailscale IP:** 100.64.0.1
- **Bridge Endpoint:** 100.64.0.1:8765
- **Bridge Version (pre-install):** 0.4.1 (versionCode=3)
- **Tasker Version:** 6.7.6-beta (versionCode=5452)
- **Tasker Package:** net.dinglisch.android.taskerm
- **Bridge Package:** com.hermesandroid.bridge
- **Run Start:** 2026-07-25T09:35:00Z
- **Tester:** Hermes Agent (automated)

## Redaction Rules

NEVER include in evidence:
- HMAC secret
- Bridge token / pairing code
- Complete request payloads with auth.signature
- Private key material

ALWAYS include:
- command_id
- adapter_id
- request_hash (SHA-256, not HMAC)
- issued_at_ms / deadline_at_ms
- Timestamps (start, end)
- Latency (ms)
- Outcome (ok/error)
- Error code (if any)
- Executor PID/UID (when available)
- DPM execution observed (yes/no)
