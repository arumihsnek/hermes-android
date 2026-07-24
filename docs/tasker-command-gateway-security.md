# Tasker Command Gateway Security

**Version:** 1.0.0  
**Date:** 2026-07-24

---

## Security Model

The Tasker Command Gateway follows a **fail-closed** security model.
All requests are rejected by default unless explicitly allowed.

---

## Authentication

### Token Validation
- Every request must include a valid `token` field
- Token is validated before any processing
- Invalid tokens result in immediate rejection
- Token is a high-entropy local secret (not network-exposed)

### Token Storage
- Token stored in Bridge configuration
- Token transmitted only via local file system
- Never exposed to network
- Never logged in plaintext

---

## Authorization

### Capability Allowlist
Only explicitly approved capabilities are accepted:

| Capability | Risk Level | Required Permissions |
|------------|------------|---------------------|
| runtime.status | LOW | None |
| device_owner.status | LOW | Device Owner |
| device.info | LOW | None |
| app.state | LOW | None |

### Rejected Capabilities
The gateway MUST reject:

- `raw_java` - Direct Java execution
- `raw_shell` - Direct shell execution
- `task.*` - Arbitrary task execution
- `intent.*` - Arbitrary intent sending
- `reflection.*` - Arbitrary reflection
- `file.*` - Arbitrary file operations
- `network.*` - Arbitrary network access
- Any capability not in the allowlist

---

## Input Validation

### Request Schema Validation
1. **version**: Must be exactly 1 (integer)
2. **command_id**: Must be valid UUID v4 format
3. **capability**: Must match `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`
4. **timeout_ms**: Must be between 1000 and 30000
5. **params**: Must be a valid JSON object

### Parameter Validation
Each capability has its own parameter schema:

#### app.state
```json
{
  "package_name": "string (required, matches ^[a-zA-Z][a-zA-Z0-9._]*$)"
}
```

### Rejected Inputs
- Null or missing required fields
- Capability names with special characters
- Timeout values outside allowed range
- Package names with path traversal attempts
- JSON with nesting depth > 10
- Request size > 64 KB

---

## File System Security

### Directory Structure
```
/sdcard/Tasker/gateway/
├── requests/     # Incoming requests (Bridge writes)
├── responses/    # Outgoing responses (Tasker writes)
└── logs/         # Audit logs
```

### File Permissions
- Files created with restrictive permissions (600)
- Only Bridge and Tasker can access gateway directory
- No other apps should access gateway files

### File Naming
- Request files: `{command_id}.json` (UUID v4)
- Response files: `{command_id}.json` (UUID v4)
- No special characters allowed in filenames
- No path traversal possible

### Cleanup
- Request files deleted after processing
- Response files deleted after reading
- Orphaned files cleaned up periodically

---

## Broadcast Security

### Intent Restrictions
- Broadcasts sent with explicit component
- Only `ReceiverStaticRunTasks` receives commands
- No implicit broadcasts allowed
- Package name required in intent

### Intent Extras
- Only `task_name` extra is used
- No arbitrary intent data accepted
- JSON payload transmitted via file, not intent

---

## Response Security

### Response Size
- Maximum response size: 256 KB
- Result field maximum: 240 KB
- Error message maximum: 1 KB

### Sensitive Data
- No passwords or secrets in responses
- No file paths in responses
- No internal implementation details
- Only non-sensitive device information

---

## Audit Logging

### Logged Events
- Request received (command_id, capability, timestamp)
- Validation failed (command_id, error_code)
- Execution started (command_id, capability)
- Execution completed (command_id, duration_ms)
- Response sent (command_id, status)
- Errors occurred (command_id, error_code, message)

### Log Format
```json
{
  "timestamp": "ISO 8601",
  "event": "request_received|validation_failed|execution_started|execution_completed|response_sent|error",
  "command_id": "UUID",
  "capability": "string",
  "duration_ms": 0,
  "error_code": "string",
  "message": "string"
}
```

### Log Retention
- Logs retained for 7 days
- Old logs automatically deleted
- Logs stored in `/sdcard/Tasker/gateway/logs/`

---

## Threat Model

### Threat 1: Unauthorized Access
**Mitigation:** Token validation on every request

### Threat 2: Capability Escalation
**Mitigation:** Strict allowlist, no dynamic capabilities

### Threat 3: Code Injection
**Mitigation:** No raw Java/shell execution, no arbitrary code

### Threat 4: Path Traversal
**Mitigation:** Fixed directory structure, filename validation

### Threat 5: Denial of Service
**Mitigation:** Timeout enforcement, file size limits

### Threat 6: Information Disclosure
**Mitigation:** Minimal responses, no internal details

---

## Compliance

### Security Principles
1. **Fail-closed**: Reject by default
2. **Least privilege**: Only necessary capabilities
3. **Defense in depth**: Multiple validation layers
4. **Audit trail**: All actions logged
5. **No secrets in logs**: Token redacted

### Regular Reviews
- Capability list reviewed monthly
- Security logs reviewed weekly
- Access patterns monitored
- Anomalies investigated
