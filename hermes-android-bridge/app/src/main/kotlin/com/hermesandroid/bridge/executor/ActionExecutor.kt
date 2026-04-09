package com.hermesandroid.bridge.executor

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Path
import android.os.Build
import android.os.Bundle
import android.telephony.SmsManager
import android.util.Base64
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import com.hermesandroid.bridge.model.ActionResult
import com.hermesandroid.bridge.model.ScreenNode
import com.hermesandroid.bridge.power.WakeLockManager
import com.hermesandroid.bridge.service.BridgeAccessibilityService
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executor
import kotlin.coroutines.resume

object ActionExecutor {

    suspend fun tap(x: Int? = null, y: Int? = null, nodeId: String? = null): ActionResult =
        WakeLockManager.wakeForAction {
        val service = BridgeAccessibilityService.instance
            ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

        if (nodeId != null) {
            val node = findNodeById(nodeId)
                ?: return@wakeForAction ActionResult(false, "Node not found: $nodeId")
            val result = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            node.recycle()
            return@wakeForAction ActionResult(result, if (result) "Tapped node $nodeId" else "Click action failed")
        }

        if (x != null && y != null) {
            val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
                .build()
            var done = false
            var success = false
            service.dispatchGesture(gesture, object : android.accessibilityservice.AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription) { success = true; done = true }
                override fun onCancelled(gestureDescription: GestureDescription) { success = false; done = true }
            }, null)
            var waited = 0
            while (!done && waited < 2000) { delay(50); waited += 50 }
            return@wakeForAction ActionResult(success, if (success) "Tapped ($x, $y)" else "Tap gesture cancelled")
        }

        ActionResult(false, "Provide either (x, y) or nodeId")
    }

    suspend fun tapText(text: String, exact: Boolean = false): ActionResult =
        WakeLockManager.wakeForAction {
        val node = ScreenReader.findNodeByText(text, exact)
            ?: return@wakeForAction ActionResult(false, "Element with text '$text' not found")
        val result = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        node.recycle()
        ActionResult(result, if (result) "Tapped '$text'" else "Click failed on '$text'")
    }

    suspend fun typeText(text: String, clearFirst: Boolean = false): ActionResult =
        WakeLockManager.wakeForAction {
        val service = BridgeAccessibilityService.instance
            ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

        val focusedNode = service.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

        if (clearFirst) {
            val bundle = Bundle()
            bundle.putInt(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0
            )
            bundle.putInt(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT,
                focusedNode?.text?.length ?: 0
            )
            focusedNode?.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, bundle)
            focusedNode?.performAction(AccessibilityNodeInfo.ACTION_CUT)
        }

        val arguments = Bundle().apply {
            putCharSequence(
                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text
            )
        }
        val result = focusedNode?.performAction(
            AccessibilityNodeInfo.ACTION_SET_TEXT, arguments
        ) ?: false
        ActionResult(result, if (result) "Typed text" else "No focused input found")
    }

    suspend fun swipe(direction: String, distance: String = "medium"): ActionResult =
        WakeLockManager.wakeForAction {
        val service = BridgeAccessibilityService.instance
            ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

        val displayMetrics = service.resources.displayMetrics
        val w = displayMetrics.widthPixels
        val h = displayMetrics.heightPixels

        val shortDist = 0.2f
        val mediumDist = 0.4f
        val longDist = 0.7f
        val dist = when (distance) { "short" -> shortDist; "long" -> longDist; else -> mediumDist }

        val (startX, startY, endX, endY) = when (direction) {
            "up" ->    arrayOf(w / 2f, h * 0.7f, w / 2f, h * (0.7f - dist))
            "down" ->  arrayOf(w / 2f, h * 0.3f, w / 2f, h * (0.3f + dist))
            "left" ->  arrayOf(w * 0.8f, h / 2f, w * (0.8f - dist), h / 2f)
            "right" -> arrayOf(w * 0.2f, h / 2f, w * (0.2f + dist), h / 2f)
            else -> return@wakeForAction ActionResult(false, "Unknown direction: $direction")
        }

        val path = Path().apply {
            moveTo(startX, startY)
            lineTo(endX, endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        service.dispatchGesture(gesture, null, null)
        delay(400)
        ActionResult(true, "Swiped $direction ($distance)")
    }

    fun openApp(packageName: String): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val intent = service.packageManager.getLaunchIntentForPackage(packageName)
            ?: return ActionResult(false, "App not found: $packageName")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        service.startActivity(intent)
        return ActionResult(true, "Opening $packageName")
    }

    fun pressKey(key: String): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val action = when (key) {
            "back" -> AccessibilityService.GLOBAL_ACTION_BACK
            "home" -> AccessibilityService.GLOBAL_ACTION_HOME
            "recents" -> AccessibilityService.GLOBAL_ACTION_RECENTS
            "notifications" -> AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS
            "power" -> AccessibilityService.GLOBAL_ACTION_POWER_DIALOG
            "quick_settings" -> AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS
            "lock_screen" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)
                AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN else -1
            "take_screenshot" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P)
                AccessibilityService.GLOBAL_ACTION_TAKE_SCREENSHOT else -1
            "volume_up", "volume_down", "enter", "delete", "tab", "escape", "search" ->
                return ActionResult(false, "Key '$key' is not supported via AccessibilityService global actions")
            else -> return ActionResult(false, "Unknown key: $key")
        }
        if (action == -1) {
            return ActionResult(false, "Key '$key' requires Android 9+ (API 28)")
        }
        val result = service.performGlobalAction(action)
        return ActionResult(result, if (result) "Pressed $key" else "Key press failed")
    }

    suspend fun waitForElement(
        text: String? = null,
        className: String? = null,
        timeoutMs: Int = 5000
    ): ActionResult {
        val interval = 500L
        var elapsed = 0L
        while (elapsed < timeoutMs) {
            val nodes = ScreenReader.readCurrentScreen(false)
            val found = findInTree(nodes, text, className)
            if (found != null) {
                return ActionResult(true, "Element found", found)
            }
            delay(interval)
            elapsed += interval
        }
        return ActionResult(false, "Timeout waiting for element (text=$text, class=$className)")
    }

    suspend fun takeScreenshot(): ActionResult {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return ActionResult(false, "Screenshot requires Android 11 (API 30) or higher")
        }
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")

        return suspendCancellableCoroutine { cont ->
            val executor = Executor { it.run() }
            service.takeScreenshot(
                Display.DEFAULT_DISPLAY,
                executor,
                object : AccessibilityService.TakeScreenshotCallback {
                    override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                        val hwBitmap = Bitmap.wrapHardwareBuffer(
                            result.hardwareBuffer, result.colorSpace
                        )
                        if (hwBitmap == null) {
                            cont.resume(ActionResult(false, "Failed to create bitmap"))
                            result.hardwareBuffer.close()
                            return
                        }
                        // Convert to software bitmap for compression
                        val bitmap = hwBitmap.copy(Bitmap.Config.ARGB_8888, false)
                        hwBitmap.recycle()
                        result.hardwareBuffer.close()

                        val w = bitmap.width
                        val h = bitmap.height
                        val stream = ByteArrayOutputStream()
                        bitmap.compress(Bitmap.CompressFormat.JPEG, 50, stream)
                        val base64 = Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
                        bitmap.recycle()

                        cont.resume(ActionResult(true, "Screenshot captured", mapOf(
                            "image" to base64,
                            "width" to w,
                            "height" to h,
                            "format" to "jpeg",
                            "encoding" to "base64"
                        )))
                    }

                    override fun onFailure(errorCode: Int) {
                        cont.resume(ActionResult(false, "Screenshot failed with error code $errorCode"))
                    }
                }
            )
        }
    }

    fun getInstalledApps(): List<Map<String, String>> {
        val service = BridgeAccessibilityService.instance ?: return emptyList()
        val pm = service.packageManager
        // Use queryIntentActivities to get all launchable apps (works on Android 11+)
        val launchIntent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        return pm.queryIntentActivities(launchIntent, 0).mapNotNull { resolveInfo ->
            val appInfo = resolveInfo.activityInfo?.applicationInfo ?: return@mapNotNull null
            mapOf(
                "packageName" to appInfo.packageName,
                "label" to pm.getApplicationLabel(appInfo).toString()
            )
        }.distinctBy { it["packageName"] }.sortedBy { it["label"] }
    }

    suspend fun scroll(direction: String, nodeId: String? = null): ActionResult =
        WakeLockManager.wakeForAction {
            val service = BridgeAccessibilityService.instance
                ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

            if (nodeId != null) {
                val node = findNodeById(nodeId)
                    ?: return@wakeForAction ActionResult(false, "Node not found: $nodeId")
                val action = when (direction) {
                    "down", "right" -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    "up", "left" -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                    else -> return@wakeForAction ActionResult(false, "Unknown direction: $direction")
                }
                val result = node.performAction(action)
                node.recycle()
                return@wakeForAction ActionResult(result, if (result) "Scrolled $direction in node $nodeId" else "Scroll failed on node $nodeId")
            }

            swipe(direction, "medium")
        }

    fun clipboardRead(): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val cm = service.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (!cm.hasPrimaryClip()) {
            return ActionResult(true, "Clipboard is empty", "")
        }
        val clip = cm.primaryClip ?: return ActionResult(true, "Clipboard is empty", "")
        if (clip.itemCount == 0) {
            return ActionResult(true, "Clipboard is empty", "")
        }
        val text = clip.getItemAt(0)?.text?.toString() ?: ""
        return ActionResult(true, "Clipboard read", text)
    }

    fun clipboardWrite(text: String): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val cm = service.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("hermes", text)
        cm.setPrimaryClip(clip)
        return ActionResult(true, "Copied to clipboard", text)
    }

    suspend fun longPress(x: Int? = null, y: Int? = null, nodeId: String? = null, duration: Long = 500): ActionResult =
        WakeLockManager.wakeForAction {
        val service = BridgeAccessibilityService.instance
            ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

        if (nodeId != null) {
            val node = findNodeById(nodeId)
                ?: return@wakeForAction ActionResult(false, "Node not found: $nodeId")
            val result = node.performAction(AccessibilityNodeInfo.ACTION_LONG_CLICK)
            node.recycle()
            return@wakeForAction ActionResult(result, if (result) "Long pressed node $nodeId" else "Long click action failed")
        }

        if (x != null && y != null) {
            val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, duration))
                .build()
            var done = false
            var success = false
            service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(g: GestureDescription) { success = true; done = true }
                override fun onCancelled(g: GestureDescription) { success = false; done = true }
            }, null)
            var waited = 0
            while (!done && waited < 3000) { delay(50); waited += 50 }
            return@wakeForAction ActionResult(success, if (success) "Long pressed ($x, $y) ${duration}ms" else "Long press gesture cancelled")
        }

        ActionResult(false, "Provide either (x, y) or nodeId")
    }

    suspend fun drag(startX: Int, startY: Int, endX: Int, endY: Int, duration: Long = 500): ActionResult =
        WakeLockManager.wakeForAction {
        val service = BridgeAccessibilityService.instance
            ?: return@wakeForAction ActionResult(false, "Accessibility service not running")

        val path = Path().apply {
            moveTo(startX.toFloat(), startY.toFloat())
            lineTo(endX.toFloat(), endY.toFloat())
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, duration))
            .build()
        var done = false
        var success = false
        service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(g: GestureDescription) { success = true; done = true }
            override fun onCancelled(g: GestureDescription) { success = false; done = true }
        }, null)
        var waited = 0
        while (!done && waited < 3000) { delay(50); waited += 50 }
        ActionResult(success, if (success) "Dragged ($startX,$startY) to ($endX,$endY)" else "Drag gesture cancelled")
    }

    fun describeNode(nodeId: String): ActionResult {
        val node = findNodeById(nodeId)
            ?: return ActionResult(false, "Node not found: $nodeId")
        val r = android.graphics.Rect()
        node.getBoundsInScreen(r)
        val result = mutableMapOf<String, Any?>(
            "nodeId" to nodeId,
            "className" to node.className?.toString(),
            "packageName" to node.packageName?.toString(),
            "text" to node.text?.toString(),
            "contentDescription" to node.contentDescription?.toString(),
            "hintText" to if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) node.hintText?.toString() else null,
            "bounds" to mapOf("left" to r.left, "top" to r.top, "right" to r.right, "bottom" to r.bottom),
            "clickable" to node.isClickable,
            "longClickable" to node.isLongClickable,
            "focusable" to node.isFocusable,
            "editable" to node.isEditable,
            "scrollable" to node.isScrollable,
            "checkable" to node.isCheckable,
            "checked" to if (node.isCheckable) node.isChecked else null,
            "enabled" to node.isEnabled,
            "selected" to node.isSelected,
            "childCount" to node.childCount,
            "viewIdResourceName" to node.viewIdResourceName,
            "isChecked" to node.isChecked,
            "isFocusable" to node.isFocusable,
            "isFocused" to node.isFocused,
            "isAccessibilityFocused" to node.isAccessibilityFocused
        )
        node.recycle()
        return ActionResult(true, "Node details", result)
    }

    fun location(): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val lm = service.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
        val providers = lm.getProviders(true)
        var best: android.location.Location? = null
        for (provider in providers) {
            @Suppress("DEPRECATION")
            val loc = lm.getLastKnownLocation(provider) ?: continue
            if (best == null || loc.accuracy < best.accuracy) {
                best = loc
            }
        }
        if (best == null) {
            return ActionResult(false, "No location available. Enable GPS/Location.")
        }
        return ActionResult(true, "Location", mapOf(
            "latitude" to best.latitude,
            "longitude" to best.longitude,
            "accuracy" to best.accuracy,
            "altitude" to best.altitude,
            "provider" to (best.provider ?: "unknown"),
            "timestamp" to best.time
        ))
    }

    fun sendSms(to: String, body: String): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val smsManager = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            service.getSystemService(SmsManager::class.java)
        } else {
            @Suppress("DEPRECATION")
            SmsManager.getDefault()
        }
        smsManager.sendTextMessage(to, null, body, null, null)
        return ActionResult(true, "SMS sent to $to")
    }

    fun makeCall(number: String): ActionResult {
        val service = BridgeAccessibilityService.instance
            ?: return ActionResult(false, "Accessibility service not running")
        val intent = Intent(Intent.ACTION_CALL).apply {
            data = android.net.Uri.parse("tel:$number")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        service.startActivity(intent)
        return ActionResult(true, "Calling $number")
    }

    fun screenHash(): ActionResult {
        val nodes = ScreenReader.readCurrentScreen(false)
        if (nodes.isEmpty()) {
            return ActionResult(false, "No screen content")
        }
        val hash = nodes.joinToString("|") { it.computeHash() }
        val count = nodes.sumOf { countNodes(it) }
        return ActionResult(true, "Screen hash", mapOf("hash" to hash, "nodeCount" to count))
    }

    private fun countNodes(node: ScreenNode): Int {
        return 1 + node.children.sumOf { countNodes(it) }
    }

    private fun findNodeById(nodeId: String): AccessibilityNodeInfo? {
        val service = BridgeAccessibilityService.instance ?: return null
        val roots = service.windows.mapNotNull { it.root }
        var found: AccessibilityNodeInfo? = null
        for ((wi, root) in roots.withIndex()) {
            val matches = findNodeByIdInTree(root, nodeId, "$wi")
            if (matches.isNotEmpty()) {
                found = matches.first()
                for (r in roots.subList(wi + 1, roots.size)) r.recycle()
                break
            }
            root.recycle()
        }
        return found
    }

    /** DFS search matching the stable ID format from ScreenReader.buildNode */
    private fun findNodeByIdInTree(
        info: AccessibilityNodeInfo, targetId: String, path: String
    ): List<AccessibilityNodeInfo> {
        val r = android.graphics.Rect()
        info.getBoundsInScreen(r)
        val id = "${info.packageName ?: "?"}_${info.className ?: "?"}_${path}_${r.left}_${r.top}_${r.right}_${r.bottom}"
        if (id == targetId) return listOf(info)
        val results = mutableListOf<AccessibilityNodeInfo>()
        for (i in 0 until info.childCount) {
            val child = info.getChild(i) ?: continue
            val found = findNodeByIdInTree(child, targetId, "${path}_$i")
            if (found.isNotEmpty()) {
                results.addAll(found)
                break
            } else {
                child.recycle()
            }
        }
        return results
    }

    private fun findInTree(
        nodes: List<com.hermesandroid.bridge.model.ScreenNode>,
        text: String?,
        className: String?
    ): com.hermesandroid.bridge.model.ScreenNode? {
        for (node in nodes) {
            val textMatch = text == null || node.text?.contains(text, true) == true ||
                    node.contentDescription?.contains(text, true) == true
            val classMatch = className == null || node.className == className
            if (textMatch && classMatch) return node
            val childMatch = findInTree(node.children, text, className)
            if (childMatch != null) return childMatch
        }
        return null
    }
}
