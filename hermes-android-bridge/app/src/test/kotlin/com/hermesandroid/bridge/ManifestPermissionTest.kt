package com.hermesandroid.bridge

import org.junit.Assert.*
import org.junit.Test

/**
 * Fix 1: Verify SET_ALARM permission is declared in AndroidManifest.xml.
 * The bridge must be able to send SET_TIMER intents to Clock.
 */
class ManifestPermissionTest {

    private val manifestContent: String by lazy {
        val manifestFile = java.io.File(
            "src/main/AndroidManifest.xml"
        )
        if (manifestFile.exists()) {
            manifestFile.readText()
        } else {
            // Fallback: read from test resources or classpath
            javaClass.classLoader!!.getResourceAsStream("AndroidManifest.xml")
                ?.bufferedReader()?.readText() ?: ""
        }
    }

    @Test
    fun `manifest declares SET_ALARM permission`() {
        assertTrue(
            "AndroidManifest.xml must declare com.android.alarm.permission.SET_ALARM",
            manifestContent.contains("com.android.alarm.permission.SET_ALARM")
        )
    }

    @Test
    fun `manifest uses correct permission namespace`() {
        // Must NOT be android.permission.SET_ALARM (wrong)
        assertFalse(
            "Must not use android.permission.SET_ALARM (wrong namespace)",
            manifestContent.contains("android.permission.SET_ALARM")
        )
        // Must be com.android.alarm.permission.SET_ALARM (correct)
        assertTrue(
            "Must use com.android.alarm.permission.SET_ALARM",
            manifestContent.contains("com.android.alarm.permission.SET_ALARM")
        )
    }

    @Test
    fun `SET_ALARM permission is outside application tag`() {
        val applicationIndex = manifestContent.indexOf("<application")
        val permissionIndex = manifestContent.indexOf("SET_ALARM")
        assertTrue(
            "SET_ALARM permission must be declared outside <application> tag",
            permissionIndex < applicationIndex
        )
    }
}
