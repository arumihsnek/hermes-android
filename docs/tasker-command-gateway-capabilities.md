# Tasker Command Gateway - Capability Registry

**Version:** 1.0.0  
**Date:** 2026-07-24

---

## Registry Overview

This document defines the initial set of allowed capabilities for the
Tasker Command Gateway. Each capability has a defined interface, security
requirements, and implementation.

---

## Capability: runtime.status

**Risk Level:** LOW  
**Timeout:** 5000ms  
**Idempotent:** Yes  
**Permissions:** None

### Description
Returns runtime status information about the Tasker Command Gateway.

### Input Schema
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### Output Schema
```json
{
  "type": "object",
  "properties": {
    "gateway_version": {"type": "string"},
    "contract_version": {"type": "integer"},
    "device_model": {"type": "string"},
    "sdk_version": {"type": "integer"},
    "uptime_ms": {"type": "integer"},
    "accessibility_available": {"type": "boolean"},
    "notification_listener_available": {"type": "boolean"},
    "shizuku_available": {"type": "boolean"},
    "device_owner_available": {"type": "boolean"}
  }
}
```

### Implementation Notes
- Check runtime environment
- Return static information where possible
- Check service availability dynamically

---

## Capability: device_owner.status

**Risk Level:** LOW  
**Timeout:** 5000ms  
**Idempotent:** Yes  
**Permissions:** Device Owner

### Description
Returns Device Owner status and capabilities.

### Input Schema
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### Output Schema
```json
{
  "type": "object",
  "properties": {
    "is_device_owner": {"type": "boolean"},
    "package_name": {"type": "string"},
    "admin_receiver": {"type": "string"},
    "capabilities": {
      "type": "array",
      "items": {"type": "string"}
    },
    "errors": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

### Implementation Notes
- Query DevicePolicyManager
- Check admin receiver status
- List active policies

---

## Capability: device.info

**Risk Level:** LOW  
**Timeout:** 5000ms  
**Idempotent:** Yes  
**Permissions:** None

### Description
Returns non-sensitive device information.

### Input Schema
```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

### Output Schema
```json
{
  "type": "object",
  "properties": {
    "model": {"type": "string"},
    "manufacturer": {"type": "string"},
    "device": {"type": "string"},
    "sdk_version": {"type": "integer"},
    "release": {"type": "string"},
    "fingerprint": {"type": "string"}
  }
}
```

### Implementation Notes
- Read Android Build properties
- Return only non-sensitive information
- No IMEI, MAC address, or serial number

---

## Capability: app.state

**Risk Level:** LOW  
**Timeout:** 5000ms  
**Idempotent:** Yes  
**Permissions:** None

### Description
Returns installation and state information for a specific app.

### Input Schema
```json
{
  "type": "object",
  "properties": {
    "package_name": {
      "type": "string",
      "pattern": "^[a-zA-Z][a-zA-Z0-9._]*$"
    }
  },
  "required": ["package_name"]
}
```

### Output Schema
```json
{
  "type": "object",
  "properties": {
    "installed": {"type": "boolean"},
    "enabled": {"type": "boolean"},
    "suspended": {"type": "boolean"},
    "hidden": {"type": "boolean"},
    "system_app": {"type": "boolean"},
    "version": {"type": ["string", "null"]},
    "execution_state": {
      "type": "string",
      "enum": ["available", "not_installed", "disabled", "suspended"]
    }
  }
}
```

### Implementation Notes
- Query PackageManager
- Handle package not found gracefully
- Check suspension state (API 24+)
- Return execution state

---

## Rejected Capabilities

The following capabilities are explicitly rejected:

| Capability | Reason |
|------------|--------|
| `raw_java` | Arbitrary Java execution |
| `raw_shell` | Arbitrary shell execution |
| `task.*` | Arbitrary task execution |
| `intent.*` | Arbitrary intent sending |
| `reflection.*` | Arbitrary reflection |
| `file.*` | Arbitrary file operations |
| `network.*` | Arbitrary network access |
| `permission.*` | Permission modification |
| `restrictions.*` | Restrictions modification |
| `app.uninstall` | Destructive operation |
| `app.disable` | Destructive operation |
| `app.suspend` | Destructive operation |
| `app.hide` | Destructive operation |
| `device.reboot` | Destructive operation |
| `device.wipe` | Destructive operation |

---

## Adding New Capabilities

To add a new capability:

1. Define input/output schemas
2. Assess risk level
3. Set timeout and idempotency
4. Implement in Tasker task
5. Add to allowlist
6. Update this registry
7. Test thoroughly

### Risk Assessment Criteria

| Risk Level | Criteria |
|------------|----------|
| LOW | Read-only, no side effects |
| MEDIUM | Write operations, limited side effects |
| HIGH | Destructive operations, system-wide effects |
| CRITICAL | Security-sensitive, requires explicit approval |

---

## Versioning

- Capability schemas versioned with contract
- Breaking changes require new contract version
- Backward compatibility maintained within major version
- Deprecated capabilities logged but not removed
