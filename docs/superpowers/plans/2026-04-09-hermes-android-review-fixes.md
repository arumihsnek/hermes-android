# hermes-android Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical and important issues identified in the code review for hermes-android.

**Architecture:** Targeted fixes to 5 Kotlin files and 2 Python files (both copies). Focus on: TLS-aware WebSocket URL, missing relay POST endpoints, runtime permission guards, blocking `Thread.sleep` calls, auth middleware, and code quality improvements.

**Tech Stack:** Kotlin (Android), Python (aiohttp relay), OkHttp WebSocket client, Ktor HTTP server

---

### Task 1: Fix TLS-aware WebSocket URL in RelayClient

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/client/RelayClient.kt:180-191`

- [ ] **Step 1: Fix `buildWsUrl` to detect TLS and use `wss://`**

Replace the `buildWsUrl` method:

```kotlin
private fun buildWsUrl(serverUrl: String, pairingCode: String): String {
    val trimmed = serverUrl.trim().trimEnd('/')
    val useTls = trimmed.startsWith("https://") || trimmed.startsWith("wss://")
    var base = trimmed
        .removePrefix("http://").removePrefix("https://")
        .removePrefix("ws://").removePrefix("wss://")
    if (!base.contains(":")) {
        base = "$base:8766"
    }
    val scheme = if (useTls) "wss" else "ws"
    val url = "$scheme://$base/ws?token=$pairingCode"
    Log.i(TAG, "Built WebSocket URL: $url")
    return url
}
```

- [ ] **Step 2: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/client/RelayClient.kt
git commit -m "fix(relay): detect TLS from server URL and use wss:// when appropriate"
```

---

### Task 2: Add missing relay POST endpoints in both android_relay.py copies

**Files:**
- Modify: `tools/android_relay.py:204-215`
- Modify: `hermes-android-plugin/android_relay.py:204-215`

- [ ] **Step 1: Update the POST endpoint list in `tools/android_relay.py`**

Replace lines 204-215 with the complete endpoint list:

```python
    # HTTP bridge endpoints (POST)
    for path in (
        "/tap",
        "/tap_text",
        "/type",
        "/swipe",
        "/open_app",
        "/press_key",
        "/scroll",
        "/wait",
        "/long_press",
        "/drag",
        "/describe_node",
        "/find_nodes",
        "/diff_screen",
        "/pinch",
        "/send_sms",
        "/call",
        "/media",
        "/intent",
        "/broadcast",
        "/speak",
        "/stop_speaking",
        "/screen_record",
        "/events/stream",
    ):
        app.router.add_post(path, lambda req, p=path: _handle_http(req, state, p))

    # HTTP bridge endpoints (GET) — additional beyond the basic ones above
    for path in (
        "/clipboard",
        "/notifications",
        "/contacts",
        "/events",
        "/screen_hash",
        "/location",
        "/widgets",
    ):
        app.router.add_get(path, lambda req, p=path: _handle_http(req, state, p))
```

Note: Add these new GET routes *after* the existing GET block (lines 201-202). The existing block handles `/ping`, `/screen`, `/screenshot`, `/apps`, `/current_app`. Add the new block right after it.

- [ ] **Step 2: Apply identical change to `hermes-android-plugin/android_relay.py`**

Same replacement as Step 1 in the plugin copy.

- [ ] **Step 3: Commit**

```bash
git add tools/android_relay.py hermes-android-plugin/android_relay.py
git commit -m "fix(relay): register all POST/GET endpoints so new tools work via relay"
```

---

### Task 3: Fix `ScreenRecorder.record()` — make it suspend with `delay()`

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/media/ScreenRecorder.kt:26-83`

- [ ] **Step 1: Convert `record()` to a suspend function using `delay()`**

Replace the entire `record` function:

```kotlin
suspend fun record(durationMs: Long = 5000): Map<String, Any?> {
    val service = BridgeAccessibilityService.instance
        ?: return mapOf("success" to false, "message" to "Accessibility service not running")
    val proj = projection
        ?: return mapOf("success" to false, "message" to "No MediaProjection. Grant permission first via android_screen_record_permission.")

    val outputFile = File(service.cacheDir, "screen_record_${System.currentTimeMillis()}.mp4")
    val metrics = service.resources.displayMetrics
    val width = metrics.widthPixels
    val height = metrics.heightPixels
    val density = metrics.densityDpi

    val mr = MediaRecorder(service).apply {
        setVideoSource(MediaRecorder.VideoSource.SURFACE)
        setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        setOutputFile(outputFile.absolutePath)
        setVideoSize(width, height)
        setVideoEncoder(MediaRecorder.VideoEncoder.H264)
        setVideoEncodingBitRate(2_000_000)
        setVideoFrameRate(30)
        prepare()
    }
    recorder = mr

    val vd = proj.createVirtualDisplay(
        "ScreenRecorder", width, height, density,
        DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
        mr.surface, null, null
    )
    virtualDisplay = vd

    mr.start()

    kotlinx.coroutines.delay(durationMs)

    mr.stop()
    mr.release()
    vd.release()
    recorder = null
    virtualDisplay = null

    val bytes = outputFile.readBytes()
    val base64Video = Base64.encodeToString(bytes, Base64.NO_WRAP)
    outputFile.delete()

    return mapOf(
        "success" to true,
        "message" to "Recorded ${durationMs}ms",
        "data" to mapOf(
            "video" to base64Video,
            "width" to width,
            "height" to height,
            "durationMs" to durationMs,
            "sizeBytes" to bytes.size,
            "mimeType" to "video/mp4"
        )
    )
}
```

- [ ] **Step 2: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/media/ScreenRecorder.kt
git commit -m "fix(screen-recorder): use suspend delay() instead of blocking Thread.sleep()"
```

---

### Task 4: Fix `ActionExecutor.readWidgets()` — replace `Thread.sleep` with suspend `delay()`

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt:657-676`

- [ ] **Step 1: Make `readWidgets()` a suspend function and use `delay()`**

Replace the `readWidgets` function:

```kotlin
suspend fun readWidgets(): ActionResult {
    val service = BridgeAccessibilityService.instance
        ?: return ActionResult(false, "Accessibility service not running")

    val homeIntent = Intent(Intent.ACTION_MAIN).apply {
        addCategory(Intent.CATEGORY_HOME)
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    service.startActivity(homeIntent)
    delay(1000)

    val roots = service.windows.mapNotNull { it.root }
    val widgets = mutableListOf<Map<String, Any?>>()
    for (root in roots) {
        collectWidgetInfo(root, widgets, 0)
        root.recycle()
    }

    return ActionResult(true, "Found ${widgets.size} widget elements", mapOf("widgets" to widgets, "count" to widgets.size))
}
```

- [ ] **Step 2: Update callers in `BridgeRouter.kt:311-316`**

The existing code already uses `withContext(Dispatchers.Main)` around `readWidgets()`. Since `readWidgets()` is now a suspend function, no change is needed in BridgeRouter — it's already called from a coroutine context.

- [ ] **Step 3: Update caller in `RelayClient.kt:525-528`**

The existing code calls `ActionExecutor.readWidgets()` without `withContext`. Since it's now a suspend function and already inside a coroutine scope (`handleMessage` launches a coroutine), this is fine — no change needed.

- [ ] **Step 4: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt
git commit -m "fix(readWidgets): use suspend delay() instead of blocking Thread.sleep()"
```

---

### Task 5: Add runtime permission guards for SMS and call

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt:482-504`

- [ ] **Step 1: Add permission check to `sendSms()`**

Replace the `sendSms` function:

```kotlin
fun sendSms(to: String, body: String): ActionResult {
    val service = BridgeAccessibilityService.instance
        ?: return ActionResult(false, "Accessibility service not running")
    if (!service.hasSelfPermission(android.Manifest.permission.SEND_SMS)) {
        return ActionResult(false, "SEND_SMS permission not granted. Grant it in Settings > Apps > Hermes Bridge > Permissions.")
    }
    return try {
        val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            service.getSystemService(SmsManager::class.java)
        } else {
            @Suppress("DEPRECATION")
            SmsManager.getDefault()
        }
        smsManager.sendTextMessage(to, null, body, null, null)
        ActionResult(true, "SMS sent to $to")
    } catch (e: SecurityException) {
        ActionResult(false, "SMS permission denied: ${e.message}")
    }
}
```

- [ ] **Step 2: Add permission check to `makeCall()`, fall back to `ACTION_DIAL`**

Replace the `makeCall` function:

```kotlin
fun makeCall(number: String): ActionResult {
    val service = BridgeAccessibilityService.instance
        ?: return ActionResult(false, "Accessibility service not running")
    val hasCallPermission = service.hasSelfPermission(android.Manifest.permission.CALL_PHONE)
    val intent = Intent(if (hasCallPermission) Intent.ACTION_CALL else Intent.ACTION_DIAL).apply {
        data = android.net.Uri.parse("tel:$number")
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }
    return try {
        service.startActivity(intent)
        ActionResult(true, if (hasCallPermission) "Calling $number" else "Opened dialer for $number (grant CALL_PHONE permission to auto-dial)")
    } catch (e: SecurityException) {
        ActionResult(false, "Call failed: ${e.message}")
    }
}
```

- [ ] **Step 3: Add the `hasSelfPermission` helper inside `ActionExecutor`**

Add this private helper at the end of the `ActionExecutor` object, before the closing `}`:

```kotlin
private fun Context.hasSelfPermission(permission: String): Boolean {
    return android.content.pm.PackageManager.PERMISSION_GRANTED ==
        checkSelfPermission(permission)
}
```

- [ ] **Step 4: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt
git commit -m "fix(permissions): add runtime permission checks for SMS and call"
```

---

### Task 6: Add auth middleware to BridgeRouter

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/server/BridgeRouter.kt:22-329`

- [ ] **Step 1: Add an auth interceptor to all routes**

Add an auth check application-wide. Insert this right after the `routing {` opening in `configureRouting()`:

```kotlin
fun Application.configureRouting() {
    routing {

        // Auth interceptor for all routes except /ping (which reports auth status)
        intercept(ApplicationCallPipeline.Plugins) {
            val path = call.request.path()
            if (path != "/ping") {
                val authHeader = call.request.header(HttpHeaders.Authorization)
                if (!PairingManager.validateToken(authHeader)) {
                    call.respond(HttpStatusCode.Unauthorized, mapOf("error" to "Unauthorized"))
                    finish()
                }
            }
        }
```

- [ ] **Step 2: Remove the now-redundant individual auth check in /ping**

The `/ping` route already checks auth to *report* the status — that's fine, it stays as-is since it reports `authenticated: true/false`. No change needed there.

- [ ] **Step 3: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/server/BridgeRouter.kt
git commit -m "fix(auth): add auth middleware to all BridgeRouter endpoints except /ping"
```

---

### Task 7: Fix `collectWidgetInfo` operator precedence

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt:683`

- [ ] **Step 1: Fix the condition with explicit parentheses**

Replace line 683:

```kotlin
        if ((depth <= 3 && (text != null || desc != null) && className.contains("Widget", ignoreCase = true)) || (depth <= 2 && (text != null || desc != null))) {
```

This ensures the logic is: collect widget classes at depth <= 3 with text, OR any node at depth <= 2 with text.

- [ ] **Step 2: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt
git commit -m "fix(widgets): clarify collectWidgetInfo condition with explicit parentheses"
```

---

### Task 8: Remove duplicate fields in `describeNode()`

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt:447-450`

- [ ] **Step 1: Remove the duplicate entries**

Remove these four lines from the result map in `describeNode()`:

```kotlin
            "isChecked" to node.isChecked,
            "isFocusable" to node.isFocusable,
            "isFocused" to node.isFocused,
            "isAccessibilityFocused" to node.isAccessibilityFocused
```

These are already present as `"checked"`, `"focusable"`, etc. in lines 436-443.

- [ ] **Step 2: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt
git commit -m "fix(describeNode): remove duplicate fields already present with canonical names"
```

---

### Task 9: Fix `mediaControl()` — send both ACTION_DOWN and ACTION_UP, use consistent intent action

**Files:**
- Modify: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt:506-532`

- [ ] **Step 1: Replace `mediaControl` with consistent intent action and both key events**

```kotlin
fun mediaControl(action: String): ActionResult {
    val service = BridgeAccessibilityService.instance
        ?: return ActionResult(false, "Accessibility service not running")
    val keyCode = when (action) {
        "play" -> android.view.KeyEvent.KEYCODE_MEDIA_PLAY
        "pause" -> android.view.KeyEvent.KEYCODE_MEDIA_PAUSE
        "toggle" -> android.view.KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE
        "next" -> android.view.KeyEvent.KEYCODE_MEDIA_NEXT
        "previous" -> android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS
        else -> return ActionResult(false, "Unknown media action: $action. Use play, pause, toggle, next, previous.")
    }
    val downIntent = Intent(Intent.ACTION_MEDIA_BUTTON).apply {
        putExtra(Intent.EXTRA_KEY_EVENT, android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, keyCode))
    }
    val upIntent = Intent(Intent.ACTION_MEDIA_BUTTON).apply {
        putExtra(Intent.EXTRA_KEY_EVENT, android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, keyCode))
    }
    service.sendOrderedBroadcast(downIntent, null)
    service.sendOrderedBroadcast(upIntent, null)
    return ActionResult(true, "Media $action sent")
}
```

- [ ] **Step 2: Commit**

```bash
git add hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt
git commit -m "fix(media): send both ACTION_DOWN and ACTION_UP, use consistent intent action"
```

---

### Task 10: Run tests to verify

- [ ] **Step 1: Run existing tests**

```bash
cd /home/hermes/projects/hermes-android && python -m pytest tests/ -v
```

Expected: All 90 tests pass.

- [ ] **Step 2: Verify no regressions**

Check that test output shows all passing with no warnings about the relay changes.
