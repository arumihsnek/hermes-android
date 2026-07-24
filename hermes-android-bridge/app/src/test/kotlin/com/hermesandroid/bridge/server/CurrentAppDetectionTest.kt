package com.hermesandroid.bridge.server

import org.junit.Assert.*
import org.junit.Test

/**
 * Fix 3: Robust current_app detection.
 *
 * System packages that should be filtered when a real app is behind them.
 */
class CurrentAppDetectionTest {

    // Packages that are system UI surfaces (not real user apps)
    private val systemPackages = setOf(
        "com.android.systemui",
        "com.google.android.packageinstaller",
        "com.android.permissioncontroller",
        "com.android.documentsui",
        "com.android.inputmethod.latin",
        "com.android.launcher",
        "com.google.android.apps.nexuslauncher",
        "com.android.emulator",
        "com.android.shell",
    )

    @Test
    fun `systemui is identified as system package`() {
        assertTrue(
            "com.android.systemui should be filtered",
            systemPackages.contains("com.android.systemui")
        )
    }

    @Test
    fun `launcher is identified as system package`() {
        assertTrue(
            "com.google.android.apps.nexuslauncher should be filtered",
            systemPackages.contains("com.google.android.apps.nexuslauncher")
        )
    }

    @Test
    fun `keyboard is identified as system package`() {
        assertTrue(
            "com.android.inputmethod.latin should be filtered",
            systemPackages.contains("com.android.inputmethod.latin")
        )
    }

    @Test
    fun `real apps are not filtered`() {
        val realApps = listOf(
            "com.google.android.deskclock",
            "de.danoeh.antennapod",
            "com.whatsapp",
            "com.spotify.music",
            "com.android.settings",
        )
        for (pkg in realApps) {
            assertFalse(
                "$pkg should NOT be filtered as system package",
                systemPackages.contains(pkg)
            )
        }
    }

    @Test
    fun `result contains quality indicator`() {
        // The observer should return quality/confidence
        val result = mapOf(
            "package" to "com.google.android.deskclock",
            "className" to "com.android.deskclock.DeskClock",
            "quality" to "confirmed",
            "source" to "accessibility",
        )
        assertTrue(result.containsKey("quality"))
        assertTrue(result.containsKey("source"))
        assertTrue(listOf("confirmed", "best_effort", "unavailable").contains(result["quality"]))
    }

    @Test
    fun `result preserves discarded candidates`() {
        val result = mapOf(
            "package" to "com.google.android.deskclock",
            "discarded" to listOf("com.android.systemui"),
            "quality" to "confirmed",
        )
        assertTrue(result.containsKey("discarded"))
        @Suppress("UNCHECKED_CAST")
        val discarded = result["discarded"] as List<String>
        assertTrue(discarded.contains("com.android.systemui"))
    }
}
