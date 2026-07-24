package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class TaskerGatewayAuthenticatorTest {

    // base64("test-secret-key-256-bits-minimum!!") — deterministic test secret
    private val testSecret = "dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ=="

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure(testSecret)
    }

    @Test
    fun `sign produces deterministic output`() {
        val data = """{"adapter_id":"device_owner.status.v1","version":1}""".toByteArray()
        val sig1 = TaskerGatewayAuthenticator.sign(data)
        val sig2 = TaskerGatewayAuthenticator.sign(data)
        assertEquals(sig1, sig2)
    }

    @Test
    fun `verify accepts valid signature`() {
        val data = "hello world".toByteArray()
        val sig = TaskerGatewayAuthenticator.sign(data)
        assertTrue(TaskerGatewayAuthenticator.verify(data, sig))
    }

    @Test
    fun `verify rejects invalid signature`() {
        val data = "hello world".toByteArray()
        assertFalse(TaskerGatewayAuthenticator.verify(data, "deadbeef"))
    }

    @Test
    fun `verify rejects empty signature`() {
        val data = "hello world".toByteArray()
        assertFalse(TaskerGatewayAuthenticator.verify(data, ""))
    }

    @Test
    fun `verify rejects tampered data`() {
        val data = "original".toByteArray()
        val sig = TaskerGatewayAuthenticator.sign(data)
        val tampered = "tampered".toByteArray()
        assertFalse(TaskerGatewayAuthenticator.verify(tampered, sig))
    }

    @Test
    fun `sha256 produces correct hash length`() {
        val hash = TaskerGatewayAuthenticator.sha256("test".toByteArray())
        assertEquals(64, hash.length)
        assertTrue(hash.all { it in '0'..'9' || it in 'a'..'f' })
    }

    @Test
    fun `sha256 is deterministic`() {
        val h1 = TaskerGatewayAuthenticator.sha256("data".toByteArray())
        val h2 = TaskerGatewayAuthenticator.sha256("data".toByteArray())
        assertEquals(h1, h2)
    }

    @Test
    fun `sha256 of known value`() {
        // SHA-256("hello") = 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
        val hash = TaskerGatewayAuthenticator.sha256("hello".toByteArray())
        assertEquals("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824", hash)
    }

    @Test
    fun `different keys produce different signatures`() {
        val data = "test".toByteArray()
        val sig1 = TaskerGatewayAuthenticator.sign(data)
        TaskerGatewayAuthenticator.configure("b3RoZXItc2VjcmV0LWtleS1mb3ItMjU2LWJpdHMhISEhIQ==")
        val sig2 = TaskerGatewayAuthenticator.sign(data)
        assertFalse(sig1 == sig2)
        // Restore
        TaskerGatewayAuthenticator.configure(testSecret)
    }

    @Test(expected = IllegalStateException::class)
    fun `sign throws before configure`() {
        // Reset secret
        val field = TaskerGatewayAuthenticator::class.java.getDeclaredField("secret")
        field.isAccessible = true
        field.set(TaskerGatewayAuthenticator, null)
        try {
            TaskerGatewayAuthenticator.sign("test".toByteArray())
        } finally {
            TaskerGatewayAuthenticator.configure(testSecret)
        }
    }

    @Test
    fun `canonicalJson produces deterministic output`() {
        data class TestObj(val b: Int, val a: String)
        val obj = TestObj(b = 2, a = "hello")
        val j1 = TaskerGatewayAuthenticator.canonicalJson(obj)
        val j2 = TaskerGatewayAuthenticator.canonicalJson(obj)
        assertEquals(String(j1), String(j2))
    }

    @Test
    fun `canonicalJson sorts keys`() {
        data class TestObj(val z: Int, val a: Int, val m: Int)
        val obj = TestObj(z = 3, a = 1, m = 2)
        val json = String(TaskerGatewayAuthenticator.canonicalJson(obj))
        assertTrue(json.indexOf("\"a\"") < json.indexOf("\"m\""))
        assertTrue(json.indexOf("\"m\"") < json.indexOf("\"z\""))
    }

    @Test
    fun `canonicalJson has no whitespace`() {
        data class TestObj(val x: Int, val y: String)
        val json = String(TaskerGatewayAuthenticator.canonicalJson(TestObj(x = 1, y = "test")))
        assertFalse(json.contains(" :"))
        assertFalse(json.contains(": "))
    }
}
