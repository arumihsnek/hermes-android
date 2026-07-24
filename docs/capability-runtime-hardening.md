# Capability Runtime Hardening

## Overview

This document describes the six-block hardening of the `hermes-android` capability runtime, making the circuit `discover → select → authorize → execute → observe → verify → trace → learn` work against the real Android Bridge instead of just mocks.

## Architecture (Final)

```
                    ┌─────────────────────────────┐
                    │     CapabilityService        │
                    │  ┌─────────────────────────┐ │
                    │  │   PolicyGate             │ │
                    │  │   (classification,       │ │
                    │  │    authorization,         │ │
                    │  │    confirmation)          │ │
                    │  └────────────┬────────────┘ │
                    │               │               │
                    │  ┌────────────▼────────────┐ │
                    │  │   FlowExecutor           │ │
                    │  │   (deterministic,        │ │
                    │  │    traces, evidence)     │ │
                    │  └────────────┬────────────┘ │
                    └───────────────┼───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  _BridgeFlowHandler            │
                    │  ┌─────────────────────────┐  │
                    │  │  Action Contract         │  │
                    │  │  (catalog, resolution,   │  │
                    │  │   alias, validation)     │  │
                    │  └────────────┬────────────┘  │
                    │               │               │
                    │  ┌────────────▼────────────┐  │
                    │  │  Verifier ↔ Observer     │  │
                    │  │  (cheapest-first,        │  │
                    │  │   bridge-backed)         │  │
                    │  └────────────┬────────────┘  │
                    └───────────────┼───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  SQLite Persistence            │
                    │  ~/.hermes/android-capabilities│
                    │  /state.db                     │
                    │  (traces, metrics, nonces,     │
                    │   negative learning, lifecycle) │
                    └───────────────────────────────┘
```

## Contracts

### Device Fingerprint (`/device/info`)
- Bridge returns: `device_id`, `android_version`, `sdk_int`, `manufacturer`, `model`, `packages`
- Packages encode `versionName:versionCode` for deterministic digest
- `DeviceFingerprint.from_bridge_response()` validates all fields
- Digest: `sha256(device_id:android_version:sdk_int:sorted_packages)[:16]`

### Action Contract
- `ACTION_CATALOG` in `action_contract.py` is the single source of truth
- Categories: `executable` (→ bridge endpoint), `semantic` (→ needs transformation), `verifier`
- Aliases documented: `android_type_text` → `android_type`
- `resolve_action()` handles aliases transparently
- `validate_action()` rejects unknown actions before execution
- `_BridgeFlowHandler` uses catalog instead of hardcoded endpoint_map

### Route Priority (A/B/C)
- **A** (INTENT_API=10): intent, API, provider, deep link
- **B** (BRIDGE_NATIVE=20): bridge native, shell, accessibility
- **C** (UI_AUTOMATOR=30): requires incompatibility evidence for A/B

### Observer-Verifier Mapping
| Verifier | Observer | Bridge Endpoint |
|----------|----------|-----------------|
| `timer_exists` | `direct_query` | `/current_app` |
| `media_state` | `media_session` | `/current_app` |
| `notification_pattern` | `notification` | `/notifications` |
| `node_predicate` | `node_search` | `/find_nodes` |
| `screen_transition` | `screen_hash` | `/screen_hash` |
| `route_active` | `current_app` | `/current_app` |
| `favorite_saved` | `current_app` | `/current_app` |

### Observer Result Fields
- `observer_type`, `success`, `data`, `error`
- `available` (whether observer could execute)
- `timestamp`, `cost`, `safe_summary`

## Persistence

### Schema (versioned, idempotent)
- `traces` — flow execution traces with events and evidence refs
- `metrics` — execution metrics (latency, success, false positives)
- `nonces` — used nonces for replay protection
- `incompatible_routes` — negative learning (fingerprint + capability + method)
- `discoveries` — discovery results
- `recipe_lifecycle` — recipe state and failure counts

### Key Guarantees
- `get_trace(trace_id)` retrieves full trace after restart
- Nonce replay blocked across process restarts
- Negative learning persists incompatible routes
- Evidence never contains raw sensitive data (only `safe_summary`)
- Corrupt database produces explicit errors

## Maturity Tiers

### Stable
- No authorization envelope required
- Still subject to policy gate
- Confirmation-required actions need real confirmation

### Dogfood
- Requires authorization envelope: capability, recipe, fingerprint, actions, expiry, nonce
- Nonce consumed on first use (replay protection)
- Expired/wrong-capability/wrong-recipe envelopes rejected

### Candidate
- Same validations as dogfood
- Only `ORDINARY_REVERSIBLE` actions allowed
- Cannot send messages, delete, buy, navigate while driving

### Invalidation
- Recipe quarantined after 3 consecutive failures
- Version change recorded as incompatible route
- Success clears failure history
- Quarantined recipes excluded from normal selection

## Decisions and Alternatives

1. **SQLite over JSON files**: Atomic transactions, indexed queries, WAL mode
2. **Action catalog over hardcoded map**: Single source of truth, alias support, validation at load time
3. **Bridge-backed observers over /screen for everything**: Each verifier gets the right data type
4. **Inspect signature for verifier params**: Avoids passing invalid kwargs to verifiers
5. **Lazy persistence init**: CapabilityService only opens DB when first trace is saved
6. **Best-effort trace persistence**: Flow execution doesn't fail if DB is unavailable

## Limitations and Pending Work

1. **Live dogfood**: Requires Pixel 8 connected via bridge; tests are prepared but skipped when unreachable
2. **UI Automator (Plan C)**: Contract defined but no executor implemented yet
3. **Media session observer**: Uses foreground app detection (not true MediaSession API)
4. **Nonce TTL cleanup**: Nonces grow unbounded; should add periodic cleanup
5. **Concurrent access**: SQLite handles single-process fine; multi-process needs WAL + retries
6. **Kotlin bridge `/device/info`**: Uses `getLastUpdateTime` via reflection for compatibility
