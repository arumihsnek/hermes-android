# Tasker Command Gateway Dogfood Report

**Date:** 2026-07-24  
**Device:** Pixel 8 (Shiba) - Android 15  
**Tasker:** 6.7.6-beta (versionCode=5452)  
**Bridge:** Hermes Bridge v0.4.1

---

## Prerequisites

Before running dogfood tests, the following must be completed:

1. ✅ Tasker is Device Owner
2. ✅ Bridge v0.4.1 is running
3. ✅ Gateway directory structure exists
4. ⏳ Tasker task `Hermes_Command_Gateway` must be created
5. ⏳ Tasker task must be configured with capabilities

---

## Test Plan

### Test 1: runtime.status (10 calls)

**Purpose:** Verify runtime status capability works consistently.

**Steps:**
1. Call `runtime.status` 10 times
2. Measure response time for each call
3. Verify all responses are successful
4. Calculate min/max/avg response times

**Expected Result:**
- All 10 calls succeed
- Response times < 500ms
- Consistent results across calls

**Actual Result:** ⏳ Pending (Tasker task not yet created)

---

### Test 2: device_owner.status (10 calls)

**Purpose:** Verify Device Owner status capability works consistently.

**Steps:**
1. Call `device_owner.status` 10 times
2. Measure response time for each call
3. Verify all responses are successful
4. Calculate min/max/avg response times

**Expected Result:**
- All 10 calls succeed
- Response times < 500ms
- Consistent Device Owner information

**Actual Result:** ⏳ Pending

---

### Test 3: app.state (Tasker)

**Purpose:** Verify app.state capability for Tasker itself.

**Steps:**
1. Call `app.state` with `package_name: "net.dinglisch.android.taskerm"`
2. Verify response indicates installed and enabled

**Expected Result:**
- `installed: true`
- `enabled: true`
- `version: "6.7.6-beta"`

**Actual Result:** ⏳ Pending

---

### Test 4: app.state (Bridge)

**Purpose:** Verify app.state capability for Hermes Bridge.

**Steps:**
1. Call `app.state` with `package_name: "com.hermesandroid.bridge"`
2. Verify response indicates installed and enabled

**Expected Result:**
- `installed: true`
- `enabled: true`

**Actual Result:** ⏳ Pending

---

### Test 5: app.state (non-existent)

**Purpose:** Verify app.state handles non-existent packages gracefully.

**Steps:**
1. Call `app.state` with `package_name: "com.nonexistent.app"`
2. Verify response indicates not installed

**Expected Result:**
- `installed: false`
- `execution_state: "not_installed"`

**Actual Result:** ⏳ Pending

---

### Test 6: Unknown capability

**Purpose:** Verify gateway rejects unknown capabilities.

**Steps:**
1. Call `unknown.capability`
2. Verify response indicates error

**Expected Result:**
- `ok: false`
- `status: "error"`
- `error.code: "UNKNOWN_CAPABILITY"`

**Actual Result:** ⏳ Pending

---

### Test 7: Invalid token

**Purpose:** Verify gateway rejects invalid tokens.

**Steps:**
1. Call `runtime.status` with invalid token
2. Verify response indicates authentication failure

**Expected Result:**
- `ok: false`
- `status: "rejected"`
- `error.code: "INVALID_TOKEN"`

**Actual Result:** ⏳ Pending

---

### Test 8: Invalid JSON

**Purpose:** Verify gateway handles malformed JSON.

**Steps:**
1. Write invalid JSON to request file
2. Send broadcast to trigger Tasker
3. Verify gateway handles error gracefully

**Expected Result:**
- Gateway logs error
- No response file created
- No crash

**Actual Result:** ⏳ Pending

---

### Test 9: Duplicate command_id

**Purpose:** Verify gateway handles duplicate command IDs.

**Steps:**
1. Write request with command_id "test-duplicate"
2. Send broadcast
3. Wait for response
4. Write another request with same command_id
5. Send broadcast
6. Verify second request is rejected

**Expected Result:**
- First request succeeds
- Second request returns `error.code: "DUPLICATE_COMMAND"`

**Actual Result:** ⏳ Pending

---

### Test 10: Timeout

**Purpose:** Verify gateway respects timeout.

**Steps:**
1. Call capability with very short timeout (1ms)
2. Verify response indicates timeout

**Expected Result:**
- `ok: false`
- `status: "timeout"`
- `error.code: "TIMEOUT"`

**Actual Result:** ⏳ Pending

---

## Performance Metrics

### Response Times

| Test | Min | Max | Avg | Count |
|------|-----|-----|-----|-------|
| runtime.status | ⏳ | ⏳ | ⏳ | 10 |
| device_owner.status | ⏳ | ⏳ | ⏳ | 10 |
| app.state | ⏳ | ⏳ | ⏳ | 4 |

### Error Rates

| Error Type | Count | Rate |
|------------|-------|------|
| SUCCESS | ⏳ | ⏳ |
| UNKNOWN_CAPABILITY | ⏳ | ⏳ |
| INVALID_TOKEN | ⏳ | ⏳ |
| TIMEOUT | ⏳ | ⏳ |
| INTERNAL_ERROR | ⏳ | ⏳ |

---

## Consistency Checks

### Command ID Correlation
- [ ] All responses contain matching command_id from request
- [ ] No response is missing command_id
- [ ] No duplicate responses for same command_id

### Response Schema
- [ ] All responses have required fields (version, command_id, ok, status, capability, duration_ms, result, error)
- [ ] All responses have valid JSON
- [ ] All responses are valid UTF-8

### File Cleanup
- [ ] Request files deleted after processing
- [ ] Response files deleted after reading
- [ ] No orphaned files in gateway directory

---

## Known Issues

1. ⏳ Tasker task not yet created
2. ⏳ Token not yet configured
3. ⏳ Full integration test pending

---

## Next Steps

1. Create Tasker task `Hermes_Command_Gateway`
2. Configure task with capabilities
3. Run all dogfood tests
4. Document actual results
5. Fix any issues found
6. Repeat until all tests pass

---

## Conclusion

The dogfood test plan is complete and ready to execute once the Tasker task is created. All test cases cover the required scenarios and will validate the gateway implementation.
