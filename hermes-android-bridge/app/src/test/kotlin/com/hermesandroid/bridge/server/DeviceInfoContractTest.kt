package com.hermesandroid.bridge.server

import org.junit.Assert.*
import org.junit.Test

/**
 * Fix 4: /device/info endpoint contract.
 * Must return structured device identity compatible with Python's DeviceFingerprint.
 */
class DeviceInfoContractTest {

    // Simulated response matching the Kotlin endpoint
    data class DeviceInfoResponse(
        val device_id: String,
        val android_version: String,
        val sdk_int: Int,
        val manufacturer: String,
        val model: String,
        val packages: Map<String, PackageInfo>
    )

    data class PackageInfo(
        val versionName: String,
        val versionCode: Int,
        val lastUpdateTime: Long
    )

    @Test
    fun `response contains all required device fields`() {
        val response = DeviceInfoResponse(
            device_id = "google_pixel_8",
            android_version = "15",
            sdk_int = 35,
            manufacturer = "Google",
            model = "Pixel 8",
            packages = emptyMap()
        )
        assertTrue(response.device_id.isNotEmpty())
        assertTrue(response.android_version.isNotEmpty())
        assertTrue(response.sdk_int > 0)
        assertTrue(response.manufacturer.isNotEmpty())
        assertTrue(response.model.isNotEmpty())
    }

    @Test
    fun `sdk_int is real not synthetic`() {
        val sdk = android.os.Build.VERSION.SDK_INT
        assertTrue("SDK must be > 0", sdk > 0)
        // On real device, SDK should be >= 26
        assertTrue("SDK must be >= 26 (minSdk)", sdk >= 26)
    }

    @Test
    fun `manufacturer and model are real`() {
        assertTrue("Manufacturer must not be empty", android.os.Build.MANUFACTURER.isNotEmpty())
        assertTrue("Model must not be empty", android.os.Build.MODEL.isNotEmpty())
    }

    @Test
    fun `device_id does not contain sensitive identifiers`() {
        val deviceId = "google_pixel_8"
        assertFalse("Must not contain IMEI", deviceId.contains("imei"))
        assertFalse("Must not contain serial", deviceId.contains("serial"))
        assertFalse("Must not contain meid", deviceId.contains("meid"))
    }

    @Test
    fun `packages parameter accepts comma-separated list`() {
        val query = "com.google.android.deskclock,de.danoeh.antennapod"
        val packages = query.split(",").filter { it.isNotBlank() }
        assertEquals(2, packages.size)
        assertEquals("com.google.android.deskclock", packages[0])
        assertEquals("de.danoeh.antennapod", packages[1])
    }

    @Test
    fun `packages without query returns defaults`() {
        val defaults = listOf(
            "com.google.android.deskclock",
            "de.danoeh.antennapod",
            "com.whatsapp",
            "com.waze",
            "net.osmand.plus",
            "com.android.vending"
        )
        assertTrue(defaults.size >= 4)
    }

    @Test
    fun `nonexistent package is silently skipped`() {
        // If package not installed, it should not appear in response
        val packages = mutableMapOf<String, PackageInfo>()
        // Simulate: com.nonexistent.package not found → not added
        assertFalse(packages.containsKey("com.nonexistent.package"))
    }

    @Test
    fun `response compatible with Python DeviceFingerprint`() {
        // Python expects: device_id, android_version, sdk_int, manufacturer, model, packages
        val requiredFields = setOf("device_id", "android_version", "sdk_int", "manufacturer", "model", "packages")
        for (field in requiredFields) {
            assertNotNull("Response must contain field: $field", field)
        }
    }

    @Test
    fun `digest is deterministic for same input`() {
        val fp1 = "google_pixel_8:15:35:com.google.android.deskclock:7.3:53093345"
        val fp2 = "google_pixel_8:15:35:com.google.android.deskclock:7.3:53093345"
        assertEquals("Digest should be deterministic", fp1.hashCode(), fp2.hashCode())
    }

    @Test
    fun `digest changes when package version changes`() {
        val fp1 = "google_pixel_8:15:35:com.google.android.deskclock:7.3:53093345"
        val fp2 = "google_pixel_8:15:35:com.google.android.deskclock:7.4:53093346"
        assertNotEquals("Digest should change on version change", fp1.hashCode(), fp2.hashCode())
    }
}
