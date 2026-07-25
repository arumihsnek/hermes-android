package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class TaskerGatewayClientTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `unknown adapter rejected immediately`() {
        val adapterError = AdapterRegistry.validateAdapter("raw_java")
        assertNotNull(adapterError)
        assertEquals("UNKNOWN_ADAPTER", adapterError)
    }

    @Test
    fun `valid adapter passes validation`() {
        assertNull(AdapterRegistry.validateAdapter("device_owner.status.v1"))
    }

    @Test
    fun `request contains no source code`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val json = String(TaskerGatewayAuthenticator.canonicalJson(req))
        assertFalse("No eval", json.contains("eval"))
        assertFalse("No par1", json.contains("par1"))
        assertFalse("No /sdcard", json.contains("/sdcard"))
        assertFalse("No source code", json.contains("source"))
    }

    @Test
    fun `deadline validation works`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1", timeoutMs = 5000)
        assertTrue(req.deadline_at_ms > req.issued_at_ms)
        assertEquals(5000, req.deadline_at_ms - req.issued_at_ms)
    }

    @Test
    fun `no shell in transport`() {
        val methods = TaskerGatewayTransport::class.java.methods.map { it.name }
        assertFalse("No sendShell method", methods.any { it.contains("shell") })
        assertFalse("No execCommand method", methods.any { it.contains("exec") })
    }

    @Test
    fun `transport actions are constants`() {
        assertEquals(
            "com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1",
            TaskerGatewayConfig.ACTION_REQUEST
        )
        assertEquals(
            "com.hermesandroid.bridge.TASKER_GATEWAY_RESPONSE_V1",
            TaskerGatewayConfig.ACTION_RESPONSE
        )
    }

    @Test
    fun `receiver validates HMAC`() {
        // Create a valid response
        val resp = TaskerGatewayResponse.success(
            commandId = "test-cmd",
            adapterId = "device_owner.status.v1",
            requestHash = "test-hash",
            result = mapOf("is_device_owner" to true),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 0, startedAt = 0, completedAt = 0
        )
        val signed = TaskerGatewayResponse.signResponse(resp)
        assertTrue(signed.auth.signature.isNotBlank())

        // Verify the signature is valid
        val payload = TaskerGatewayResponse.payloadForSigning(signed)
        assertTrue(TaskerGatewayAuthenticator.verify(payload, signed.auth.signature))
    }

    @Test
    fun `invalid HMAC fails verification`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "test-cmd",
            adapterId = "device_owner.status.v1",
            requestHash = "test-hash",
            result = emptyMap(),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 0, startedAt = 0, completedAt = 0
        )
        val payload = TaskerGatewayResponse.payloadForSigning(resp)
        assertFalse(TaskerGatewayAuthenticator.verify(payload, "invalid-signature"))
    }

    @Test
    fun `error responses for all rejection cases`() {
        val cases = mapOf(
            "deadline_exceeded" to "Request expired",
            "command_id_conflict" to "Reused command_id",
            "UNKNOWN_ADAPTER" to "Not in allowlist",
            "timeout" to "Bridge timeout",
            "transport_error" to "Broadcast failed",
            "NOT_PROVISIONED" to "Gateway not provisioned"
        )
        for ((code, msg) in cases) {
            val resp = TaskerGatewayResponse.error(
                "cmd", "adapter", "hash", code, msg
            )
            assertFalse("Error $code should be !ok", resp.ok)
            assertEquals(code, resp.error?.code)
        }
    }

    @Test
    fun `provisioning actions are defined`() {
        assertNotNull(TaskerGatewayConfig.ACTION_PROVISION)
        assertNotNull(TaskerGatewayConfig.ACTION_PROVISION_RESPONSE)
        assertTrue(TaskerGatewayConfig.ACTION_PROVISION.contains("PROVISION"))
        assertTrue(TaskerGatewayConfig.ACTION_PROVISION_RESPONSE.contains("PROVISION_RESPONSE"))
    }

    @Test
    fun `provision window is 5 minutes`() {
        assertEquals(5 * 60 * 1000L, TaskerGatewayConfig.PROVISION_WINDOW_MS)
    }
}
