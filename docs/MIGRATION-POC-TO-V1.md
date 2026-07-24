# Migration: Tasker PoC → Hardened Executor v1

**Date:** 2026-07-25  
**Status:** In Progress

---

## PoC Commit (Historical Reference)

- **Commit:** `202d18fa0c035628721b7ce53cd86c0bbd288796`
- **Branch:** `feat/tasker-java-executor-spike`
- **Nature:** Proof of concept — NOT production transport
- **Transport:** File-based polling via `/sdcard/Tasker/gateway/`
- **Authentication:** Plaintext token in `par2` envelope
- **Code Execution:** `eval(source)` with code from `par1`
- **Status:** Superseded by hardened v1

## What Changed

### Transport (Fase 3-4)
| Aspect | PoC | v1 |
|--------|-----|-----|
| Bridge → Tasker | `/shell` → `am broadcast` | Native `sendBroadcast()` |
| Request delivery | File on `/sdcard` | Intent extra (JSON) |
| Response delivery | File polling | Broadcast receiver |
| Response latency | ~3.6s (polling) | <1s (broadcast) |

### Authentication (Fase 1)
| Aspect | PoC | v1 |
|--------|-----|-----|
| Method | Plaintext token | HMAC-SHA256 |
| Secret storage | In code | On-device SharedPreferences |
| Secret provisioning | Hardcoded | Auto-generated 256-bit |
| Rotation | Requires recompile | `rotateSecret()` |
| Request integrity | None | `request_hash` (SHA-256) |
| Response integrity | None | HMAC signature |

### Contract (Fase 1)
| Field | PoC | v1 |
|-------|-----|-----|
| Capability field | `capability` | `adapter_id` |
| Authentication | `token: "string"` | `auth.signature: "hmac"` |
| Integrity | None | `request_hash` |
| Deduplication | None | `command_id` + `request_hash` |
| Deadline | `timeout_ms` (advisory) | `deadline_at_ms` (enforced) |
| Source code | `par1` (JavaScript source) | Not present |

### Code Execution (Fase 2, 7)
| Aspect | PoC | v1 |
|--------|-----|-----|
| Mechanism | `eval(source)` | Static dispatcher |
| Source of code | Remote `par1` | Pre-installed in Tasker |
| Allowed adapters | Any | `device_owner.status.v1` only |
| File I/O | Write response to `/sdcard` | Broadcast response |

### Deduplication (Fase 6)
| Aspect | PoC | v1 |
|--------|-----|-----|
| Semantic | Last-write-wins | Replay-safe |
| Identical replay | Overwrites | Returns cached |
| Conflicting command_id | Overwrites | Rejected |
| Persistence | None | In-memory with TTL |

## Profile ID198

The original Tasker profile (ID198, "Hermes · Java Lab") should be:

1. **Renamed** to: `Hermes · Java Lab — DISABLED`
2. **Disabled** (not deleted) — kept as PoC evidence
3. **Not used** for production traffic

The new gateway uses a separate Tasker project: `Hermes · Command Gateway v1`

## Secret Provisioning

### How secrets work in v1

1. **First run:** `TaskerGatewayConfig.getOrCreateSecret()` generates 256-bit random secret
2. **Storage:** Stored in Android SharedPreferences (`tasker_gateway_config`)
3. **Distribution:** Must be manually provisioned to Tasker profile (via Tasker variable)
4. **Rotation:** `TaskerGatewayConfig.rotateSecret()` generates new secret
5. **Never:** In Git, logs, exports, or evidence files

### Provisioning Steps

1. On device, run the Bridge once — it auto-generates a secret
2. Export the secret from SharedPreferences:
   ```bash
   adb shell run-as com.hermesandroid.bridge cat shared_prefs/tasker_gateway_config.xml
   ```
3. Set it as a Tasker local variable `%gw_secret` in the Tasker profile
4. The JS adapter reads it via `tasker.getVariable("gw_secret")`

### What Was Compromised

The following values appeared in the public repository and must NEVER be reused:

- `hermes-local-secret-2026` — old gateway token
- `SFBCBA` — old bridge token
- `uHNgVCmJfld_Kx8BfLEjVK5X7I2nF9Be6KidmM3yYc8` — exposed gateway token
- `NeN0FkX-dFLWzcLQltzCKw` — exposed bridge token

**Action required:** Run `git filter-repo` to purge these from history.

## Date Corrections

The PoC evidence files contained dates from 2025. This is a 2026 mission.
All new documentation uses correct 2026 dates.
The original PoC evidence is preserved with a versioned correction notice.
