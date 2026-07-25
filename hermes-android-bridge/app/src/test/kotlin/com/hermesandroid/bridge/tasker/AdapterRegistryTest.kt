package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AdapterRegistryTest {

    @Test
    fun `device_owner status v1 is allowed`() {
        assertTrue(AdapterRegistry.isAllowed("device_owner.status.v1"))
    }

    @Test
    fun `unknown adapter is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("arbitrary.code"))
        assertEquals("UNKNOWN_ADAPTER", AdapterRegistry.validateAdapter("arbitrary.code"))
    }

    @Test
    fun `raw_java is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("raw_java"))
        assertEquals("UNKNOWN_ADAPTER", AdapterRegistry.validateAdapter("raw_java"))
    }

    @Test
    fun `raw_shell is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("raw_shell"))
        assertEquals("UNKNOWN_ADAPTER", AdapterRegistry.validateAdapter("raw_shell"))
    }

    @Test
    fun `eval adapter is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("eval"))
    }

    @Test
    fun `app_state is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("app.state"))
    }

    @Test
    fun `app_suspend is rejected`() {
        assertFalse(AdapterRegistry.isAllowed("app.suspend"))
    }

    @Test
    fun `intents arbitrarios rejected`() {
        assertFalse(AdapterRegistry.isAllowed("intent.arbitrary"))
    }

    @Test
    fun `lookup returns correct entry`() {
        val entry = AdapterRegistry.lookup("device_owner.status.v1")
        assertNotNull(entry)
        assertEquals("device_owner.status", entry!!.capability)
        assertEquals("LOW", entry.riskLevel)
        assertTrue(entry.idempotent)
        assertEquals(5_000L, entry.timeoutMs)
    }

    @Test
    fun `allowedIds contains only device_owner status`() {
        val ids = AdapterRegistry.allowedIds()
        assertEquals(1, ids.size)
        assertTrue(ids.contains("device_owner.status.v1"))
    }

    @Test
    fun `validateAdapter returns null for valid adapter`() {
        assertNull(AdapterRegistry.validateAdapter("device_owner.status.v1"))
    }

    @Test
    fun `lookup returns null for unknown`() {
        assertNull(AdapterRegistry.lookup("nonexistent"))
    }
}
