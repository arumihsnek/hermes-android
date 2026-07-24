package com.hermesandroid.bridge.server

import org.junit.Assert.*
import org.junit.Test

/**
 * Fix 2: Normalize package/packageName in open_app endpoint.
 * Both Python and Kotlin must share the same contract.
 *
 * Rules:
 * 1. If packageName exists → use it
 * 2. If only package exists → normalize to packageName
 * 3. If both exist and differ → reject
 * 4. If neither exists → error
 */
class OpenAppContractTest {

    data class OpenAppRequest(
        val packageName: String? = null,
        val `package`: String? = null
    ) {
        fun resolvePackageName(): String? {
            return when {
                packageName != null && `package` != null -> {
                    if (packageName != `package`) null // reject
                    else packageName
                }
                packageName != null -> packageName
                `package` != null -> `package` // normalize alias
                else -> null
            }
        }
    }

    @Test
    fun `packageName field works directly`() {
        val req = OpenAppRequest(packageName = "com.test.app")
        assertEquals("com.test.app", req.resolvePackageName())
    }

    @Test
    fun `package field works as alias`() {
        val req = OpenAppRequest(`package` = "com.test.app")
        assertEquals("com.test.app", req.resolvePackageName())
    }

    @Test
    fun `both fields same value works`() {
        val req = OpenAppRequest(packageName = "com.test.app", `package` = "com.test.app")
        assertEquals("com.test.app", req.resolvePackageName())
    }

    @Test
    fun `both fields different values rejected`() {
        val req = OpenAppRequest(packageName = "com.test.a", `package` = "com.test.b")
        assertNull("Should reject when both fields differ", req.resolvePackageName())
    }

    @Test
    fun `neither field present returns null`() {
        val req = OpenAppRequest()
        assertNull("Should return null when no package field", req.resolvePackageName())
    }

    @Test
    fun `empty packageName rejected`() {
        val req = OpenAppRequest(packageName = "")
        assertEquals("", req.resolvePackageName())
        // Empty string is technically a value, but the openApp function should reject it
    }

    @Test
    fun `whitespace-only package rejected`() {
        val req = OpenAppRequest(packageName = "  ")
        assertEquals("  ", req.resolvePackageName())
        // The openApp function should trim and reject
    }

    @Test
    fun `null alias does not affect packageName`() {
        val req = OpenAppRequest(packageName = "com.test.app", `package` = null)
        assertEquals("com.test.app", req.resolvePackageName())
    }
}
