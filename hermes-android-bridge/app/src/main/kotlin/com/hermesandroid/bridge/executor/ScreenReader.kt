package com.hermesandroid.bridge.executor

import android.view.accessibility.AccessibilityNodeInfo
import com.hermesandroid.bridge.model.NodeBounds
import com.hermesandroid.bridge.model.ScreenNode
import com.hermesandroid.bridge.service.BridgeAccessibilityService

object ScreenReader {

    fun readCurrentScreen(includeBounds: Boolean): List<ScreenNode> {
        val service = BridgeAccessibilityService.instance
            ?: return listOf()

        val roots = service.windows.mapNotNull { it.root }
        val result = roots.mapIndexed { i, root -> buildNode(root, includeBounds, "$i") }
        roots.forEach { it.recycle() }
        return result
    }

    private fun buildNode(info: AccessibilityNodeInfo, includeBounds: Boolean, path: String = "0"): ScreenNode {
        // Always get bounds for stable ID generation
        val r = android.graphics.Rect()
        info.getBoundsInScreen(r)
        val rect = if (includeBounds) NodeBounds(r.left, r.top, r.right, r.bottom) else null

        // Stable ID: path in tree + bounds (survives re-reads unlike hashCode)
        val nodeId = "${info.packageName ?: "?"}_${info.className ?: "?"}_${path}_${r.left}_${r.top}_${r.right}_${r.bottom}"

        val children = (0 until info.childCount)
            .mapNotNull { i ->
                val child = info.getChild(i) ?: return@mapNotNull null
                val node = buildNode(child, includeBounds, "${path}_$i")
                child.recycle()
                node
            }

        return ScreenNode(
            nodeId = nodeId,
            text = info.text?.toString()?.takeIf { it.isNotBlank() },
            contentDescription = info.contentDescription?.toString()?.takeIf { it.isNotBlank() },
            className = info.className?.toString(),
            packageName = info.packageName?.toString(),
            clickable = info.isClickable,
            focusable = info.isFocusable,
            scrollable = info.isScrollable,
            editable = info.isEditable,
            checked = if (info.isCheckable) info.isChecked else null,
            bounds = rect,
            children = children
        )
    }

    fun findNodeByText(
        text: String,
        exact: Boolean = false
    ): AccessibilityNodeInfo? {
        val service = BridgeAccessibilityService.instance ?: return null
        val roots = service.windows.mapNotNull { it.root }
        for (root in roots) {
            val found = findNodeByTextDfs(root, text, exact)
            if (found != null) return found
            root.recycle()
        }
        return null
    }

    private fun findNodeByTextDfs(
        node: AccessibilityNodeInfo,
        text: String,
        exact: Boolean
    ): AccessibilityNodeInfo? {
        val nodeText = node.text?.toString() ?: node.contentDescription?.toString() ?: ""
        if ((exact && nodeText == text) || (!exact && nodeText.contains(text, ignoreCase = true))) {
            return node
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findNodeByTextDfs(child, text, exact)
            if (found != null) return found
            child.recycle()
        }
        return null
    }
}
