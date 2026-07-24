# Tasker Command Gateway Transport Decision

**Date:** 2026-07-24  
**Status:** Decided

---

## Transport Options Evaluated

### Option A: Tasker HTTP API
**Result:** ❌ Not available  
**Evidence:** No Tasker HTTP ports listening on device  
**Conclusion:** Tasker does not expose an HTTP API in this configuration

### Option B: Broadcast/Intent
**Result:** ⚠️ Partial  
**Evidence:** 
- `ReceiverStaticRunTasks` responds to `net.dinglisch.android.tasker.ACTION_TASK`
- Broadcast is fire-and-forget (result=0, no response data)
- Cannot return structured results

**Conclusion:** Useful for triggering Tasker, but not for request/response

### Option C: File-Based Communication
**Result:** ✅ Selected  
**Evidence:**
- Bridge can write to `/sdcard/Tasker/gateway/requests/`
- Bridge can read from `/sdcard/Tasker/gateway/responses/`
- Tasker can read/write files in its own directory
- Atomic operations via command_id filename

**Conclusion:** Most reliable for structured request/response

---

## Selected Architecture

```
Hermes Android Bridge                    Tasker Command Gateway
         │                                        │
         │  1. Write request.json                 │
         │  ─────────────────────►                │
         │     /sdcard/Tasker/gateway/requests/   │
         │                                        │
         │  2. Send broadcast                     │
         │  ─────────────────────►                │
         │     ACTION_TASK                        │
         │                                        │
         │                   3. Read request.json │
         │                   ◄─────────────────── │
         │                                        │
         │                   4. Process command   │
         │                                        │
         │                   5. Write response    │
         │  6. Read response.json                 │
         │  ◄─────────────────────                │
         │     /sdcard/Tasker/gateway/responses/  │
         │                                        │
         │  7. Cleanup files                      │
         │  ─────────────────────►                │
```

---

## Why File-Based Over Pure Broadcast

1. **Structured Data**: JSON files can contain complex nested structures
2. **Correlation**: command_id in filename ensures request/response matching
3. **Reliability**: File I/O is atomic and reliable
4. **No Custom Receiver**: Uses existing Tasker file access
5. **Audit Trail**: Files can be logged for debugging
6. **Timeout Handling**: Bridge can check for response file existence

---

## Security Considerations

1. **Token Validation**: Request includes token, Tasker validates before processing
2. **File Permissions**: Files created with restrictive permissions
3. **Command ID Validation**: UUID v4 format enforced
4. **Capability Allowlist**: Only approved capabilities accepted
5. **No Arbitrary Paths**: Fixed directory structure only

---

## Implementation Details

### Directory Structure
```
/sdcard/Tasker/gateway/
├── requests/
│   └── {command_id}.json
├── responses/
│   └── {command_id}.json
└── logs/
    └── {date}.log
```

### Request Flow
1. Bridge generates command_id (UUID v4)
2. Bridge writes request to `requests/{command_id}.json`
3. Bridge sends broadcast to trigger Tasker
4. Tasker reads request, validates, processes
5. Tasker writes response to `responses/{command_id}.json`
6. Bridge polls for response file (with timeout)
7. Bridge reads response, validates, returns to caller
8. Bridge cleans up both files

### Timeout Handling
- Bridge checks for response file every 100ms
- After timeout_ms, Bridge returns timeout error
- Tasker should abort processing if possible
- Orphaned files cleaned up periodically

---

## Alternatives Rejected

1. **Content Provider**: Would require custom provider in Tasker app
2. **HTTP Callback**: Tasker cannot make HTTP requests to Bridge
3. **Socket Communication**: Too complex, requires persistent connection
4. **Shared Memory**: Not available across apps
5. **Content Observer**: Requires custom content provider

---

## Conclusion

File-based communication is the optimal transport for the Tasker Command Gateway.
It provides structured data exchange, reliable correlation, and audit capabilities
while leveraging existing Tasker file access without requiring custom receivers.
