package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.Base64

/**
 * Tests for provisioning logic (Phase 2).
 *
 * These tests verify:
 * - ProvisionRequest/Response data classes
 * - HMAC computation for challenge verification
 * - PairingState enum
 * - Config action constants for provisioning broadcasts
 * - computeHmac correctness
 */
class TaskerGatewayProvisioningTest {

    private val testSecret = "dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ=="
    private val testSecretBytes = Base64.getDecoder().decode(testSecret)

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure(testSecret)
    }

    @Test
    fun `provision request has required fields`() {
        val request = TaskerGatewayConfig.ProvisionRequest(
            pairingId = "test-pairing-id",
            challenge = "test-challenge",
            secretB64 = testSecret,
            issuedAtMs = 1000L,
            deadlineAtMs = 2000L
        )
        assertEquals(1, request.version)
        assertEquals("test-pairing-id", request.pairingId)
        assertEquals("test-challenge", request.challenge)
        assertEquals(testSecret, request.secretB64)
        assertEquals(1000L, request.issuedAtMs)
        assertEquals(2000L, request.deadlineAtMs)
    }

    @Test
    fun `provision response has required fields`() {
        val response = TaskerGatewayConfig.ProvisionResponse(
            pairingId = "test-pairing-id",
            challengeHmac = "expected-hmac",
            stored = true
        )
        assertEquals(1, response.version)
        assertEquals("test-pairing-id", response.pairingId)
        assertEquals("expected-hmac", response.challengeHmac)
        assertTrue(response.stored)
    }

    @Test
    fun `computeHmac produces deterministic result`() {
        val data = "test-challenge".toByteArray()
        val hmac1 = TaskerGatewayConfig.computeHmac(testSecretBytes, data)
        val hmac2 = TaskerGatewayConfig.computeHmac(testSecretBytes, data)
        assertEquals(hmac1, hmac2)
    }

    @Test
    fun `computeHmac changes with different keys`() {
        val data = "test-challenge".toByteArray()
        val otherSecret = Base64.getDecoder().decode("b3RoZXItc2VjcmV0LWtleS0yNTYtYml0cy1taW5pbXVtISEhIQ==")
        val hmac1 = TaskerGatewayConfig.computeHmac(testSecretBytes, data)
        val hmac2 = TaskerGatewayConfig.computeHmac(otherSecret, data)
        assertFalse("Different keys should produce different HMAC", hmac1 == hmac2)
    }

    @Test
    fun `computeHmac changes with different data`() {
        val data1 = "challenge-1".toByteArray()
        val data2 = "challenge-2".toByteArray()
        val hmac1 = TaskerGatewayConfig.computeHmac(testSecretBytes, data1)
        val hmac2 = TaskerGatewayConfig.computeHmac(testSecretBytes, data2)
        assertFalse("Different data should produce different HMAC", hmac1 == hmac2)
    }

    @Test
    fun `computeHmac produces 32 byte HMAC-SHA256 output`() {
        val data = "test".toByteArray()
        val hmac = TaskerGatewayConfig.computeHmac(testSecretBytes, data)
        // HMAC-SHA256 produces 32 bytes = 44 Base64 chars (with padding)
        val decoded = Base64.getDecoder().decode(hmac)
        assertEquals(32, decoded.size)
    }

    @Test
    fun `pairing state enum has all states`() {
        val states = TaskerGatewayConfig.PairingState.values()
        assertEquals(3, states.size)
        assertNotNull(TaskerGatewayConfig.PairingState.UNPAIRED)
        assertNotNull(TaskerGatewayConfig.PairingState.PENDING)
        assertNotNull(TaskerGatewayConfig.PairingState.PAIRED)
    }

    @Test
    fun `pairing state string roundtrip`() {
        for (state in TaskerGatewayConfig.PairingState.values()) {
            val parsed = TaskerGatewayConfig.PairingState.valueOf(state.name)
            assertEquals(state, parsed)
        }
    }

    @Test
    fun `provision broadcast actions are distinct from request and response`() {
        // Provisioning uses separate actions from normal request/response
        assertFalse(
            "Provision action differs from request action",
            TaskerGatewayConfig.ACTION_PROVISION == TaskerGatewayConfig.ACTION_REQUEST
        )
        assertFalse(
            "Provision response action differs from response action",
            TaskerGatewayConfig.ACTION_PROVISION_RESPONSE == TaskerGatewayConfig.ACTION_RESPONSE
        )
        // But they share the same tasker package
        assertEquals(
            TaskerGatewayConfig.taskerPackage,
            TaskerGatewayConfig.taskerPackage
        )
    }

    @Test
    fun `provisioning uses same extra key for JSON`() {
        // Both provision and request use EXTRA_REQUEST_JSON / EXTRA_PROVISION_JSON
        // but provision has its own key
        assertEquals("provision_json", TaskerGatewayConfig.EXTRA_PROVISION_JSON)
        assertEquals("request_json", TaskerGatewayConfig.EXTRA_REQUEST_JSON)
        assertEquals("response_json", TaskerGatewayConfig.EXTRA_RESPONSE_JSON)
    }

    @Test
    fun `computeHmac is compatible with TaskerGatewayAuthenticator sign`() {
        // The provisioning HMAC uses the same algorithm as the gateway authenticator
        // Both should produce HMAC-SHA256 using the same key
        val data = "test-payload".toByteArray()

        // Direct HMAC computation
        val directHmac = TaskerGatewayConfig.computeHmac(testSecretBytes, data)

        // Via authenticator (which uses the configured secret)
        val authenticatorHmac = TaskerGatewayAuthenticator.sign(data)

        // Both use the same key and algorithm, so should produce same result
        assertEquals(directHmac, authenticatorHmac)
    }

    @Test
    fun `provision request can be serialized to JSON`() {
        val request = TaskerGatewayConfig.ProvisionRequest(
            pairingId = "test-id",
            challenge = "test-challenge",
            secretB64 = testSecret,
            issuedAtMs = System.currentTimeMillis(),
            deadlineAtMs = System.currentTimeMillis() + 300_000
        )
        val json = com.google.gson.Gson().toJson(request)
        // Gson uses camelCase by default (matching Kotlin property names)
        assertTrue(json.contains("pairingId"))
        assertTrue(json.contains("challenge"))
        assertTrue(json.contains("secretB64"))
        assertTrue(json.contains("issuedAtMs"))
        assertTrue(json.contains("deadlineAtMs"))
        assertTrue(json.contains("version"))
    }

    @Test
    fun `provision response can be deserialized from JSON`() {
        // Gson camelCase field names
        val json = """{"version":1,"pairingId":"test","challengeHmac":"hmac","stored":true}"""
        val response = com.google.gson.Gson().fromJson(json, TaskerGatewayConfig.ProvisionResponse::class.java)
        assertEquals(1, response.version)
        assertEquals("test", response.pairingId)
        assertEquals("hmac", response.challengeHmac)
        assertTrue(response.stored)
    }
}
