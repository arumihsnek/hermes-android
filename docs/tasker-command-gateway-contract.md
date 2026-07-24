# Tasker Command Gateway Contract

**Version:** 1.0.0  
**Date:** 2026-07-24  
**Status:** Active

---

## Overview

This document defines the versioned JSON contract between Hermes Android Bridge
and the Tasker Command Gateway. The contract ensures reliable, secure, and
correlated communication.

---

## Request Schema

```json
{
  "version": 1,
  "command_id": "string (UUID v4)",
  "capability": "string (dot-separated namespace)",
  "params": {},
  "timeout_ms": 10000,
  "token": "string (local-secret)"
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| version | integer | Yes | Contract version (currently 1) |
| command_id | string | Yes | Unique identifier (UUID v4) |
| capability | string | Yes | Target capability (e.g., "device_owner.status") |
| params | object | Yes | Capability-specific parameters |
| timeout_ms | integer | Yes | Maximum execution time in milliseconds |
| token | string | Yes | Local authentication token |

---

## Response Schema

```json
{
  "version": 1,
  "command_id": "string (UUID v4)",
  "ok": true,
  "status": "completed",
  "capability": "string",
  "duration_ms": 0,
  "result": {},
  "error": null
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| version | integer | Contract version |
| command_id | string | Correlation ID (matches request) |
| ok | boolean | Success indicator |
| status | string | Execution status |
| capability | string | Executed capability |
| duration_ms | integer | Execution time in milliseconds |
| result | object | Capability-specific result |
| error | object | Error details (null if ok=true) |

---

## Status Values

| Status | Description |
|--------|-------------|
| completed | Execution finished successfully |
| error | Execution failed |
| timeout | Execution exceeded timeout_ms |
| rejected | Request rejected (validation/security) |
| unknown_capability | Capability not found |

---

## Error Schema

```json
{
  "code": "string",
  "message": "string",
  "details": {}
}
```

### Error Codes

| Code | Description |
|------|-------------|
| INVALID_VERSION | Contract version not supported |
| INVALID_TOKEN | Authentication failed |
| INVALID_JSON | Malformed JSON request |
| MISSING_FIELD | Required field missing |
| UNKNOWN_CAPABILITY | Capability not in allowlist |
| INVALID_PARAMS | Parameters failed validation |
| TIMEOUT | Execution exceeded timeout |
| INTERNAL_ERROR | Unexpected internal error |
| RESULT_TOO_LARGE | Response exceeds size limit |
| DUPLICATE_COMMAND | command_id already processed |
| UNAUTHORIZED_CAPABILITY | Capability requires higher privileges |

---

## Validation Rules

1. **Version**: Must be exactly 1 (integer)
2. **command_id**: Must be valid UUID v4
3. **capability**: Must match `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`
4. **timeout_ms**: Must be between 1000 and 30000
5. **token**: Must match configured local secret
6. **params**: Must be a valid JSON object

---

## Allowed Capabilities (v1)

| Capability | Risk Level | Timeout | Idempotent |
|------------|------------|---------|------------|
| runtime.status | LOW | 5000 | Yes |
| device_owner.status | LOW | 5000 | Yes |
| device.info | LOW | 5000 | Yes |
| app.state | LOW | 5000 | Yes |

---

## Rejected Capabilities

The gateway MUST reject:

- `raw_java` - Direct Java execution
- `raw_shell` - Direct shell execution
- `task.*` - Arbitrary task execution
- `intent.*` - Arbitrary intent sending
- `reflection.*` - Arbitrary reflection
- Any capability not in the allowlist

---

## Timeout Handling

1. Gateway starts timer on receipt
2. If execution exceeds timeout_ms:
   - Abort execution
   - Return `status: "timeout"`
   - Include partial results if available
3. Bridge enforces its own timeout independently

---

## Deduplication

1. Bridge tracks command_id for timeout_ms * 2
2. If duplicate command_id received:
   - Return `error: "DUPLICATE_COMMAND"`
   - Do not re-execute
3. Gateway should also track for safety

---

## Size Limits

| Item | Limit |
|------|-------|
| Request size | 64 KB |
| Response size | 256 KB |
| Result field | 240 KB |
| Error message | 1 KB |

---

## Versioning

- Contract version incremented for breaking changes
- v1: Initial release
- Backward compatibility maintained within major version
- Unknown fields ignored (forward compatibility)

---

## Security Requirements

1. Token validated before any processing
2. Capability validated against allowlist
3. Parameters validated against schema
4. No arbitrary code execution allowed
5. No file path manipulation allowed
6. No network access from gateway
7. All execution logged with command_id
