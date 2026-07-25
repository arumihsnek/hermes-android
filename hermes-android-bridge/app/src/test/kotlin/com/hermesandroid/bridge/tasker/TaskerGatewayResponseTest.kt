package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class TaskerGatewayResponseTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `success response has correct structure`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc123",
            result = mapOf("is_device_owner" to true),
            executor = TaskerGatewayResponse.ExecutorInfo(task_name = "test"),
            receivedAt = 100,
            startedAt = 150,
            completedAt = 200
        )
        assertTrue(resp.ok)
        assertEquals("completed", resp.status)
        assertEquals(50, resp.duration_ms)
        assertNotNull(resp.result)
        assertNull(resp.error)
        assertEquals("cmd-1", resp.command_id)
    }

    @Test
    fun `error response has correct structure`() {
        val resp = TaskerGatewayResponse.error(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            code = "deadline_exceeded",
            message = "Request expired"
        )
        assertFalse(resp.ok)
        assertEquals("rejected", resp.status)
        assertEquals("deadline_exceeded", resp.error?.code)
        assertEquals("Request expired", resp.error?.message)
        assertNull(resp.result)
    }

    @Test
    fun `response payload excludes auth for signing`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            result = emptyMap(),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 0, startedAt = 0, completedAt = 0
        )
        val payload = String(TaskerGatewayResponse.payloadForSigning(resp))
        assertFalse(payload.contains("auth"))
        assertFalse(payload.contains("signature"))
    }

    @Test
    fun `signResponse adds valid signature`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            result = mapOf("key" to "value"),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 100, startedAt = 150, completedAt = 200
        )
        val signed = TaskerGatewayResponse.signResponse(resp)
        assertTrue(signed.auth.signature.isNotBlank())
        assertEquals("HMAC-SHA256", signed.auth.algorithm)

        // Verify signature
        val payload = TaskerGatewayResponse.payloadForSigning(signed)
        assertTrue(TaskerGatewayAuthenticator.verify(payload, signed.auth.signature))
    }

    @Test
    fun `error codes for common cases`() {
        val cases = listOf(
            "deadline_exceeded" to "Request expired before execution",
            "command_id_conflict" to "command_id reused with different request_hash",
            "UNKNOWN_ADAPTER" to "Adapter not allowed",
            "timeout" to "Bridge timeout",
            "transport_error" to "Failed to send broadcast"
        )
        for ((code, message) in cases) {
            val resp = TaskerGatewayResponse.error(
                commandId = "test", adapterId = "test",
                requestHash = "test", code = code, message = message
            )
            assertEquals(code, resp.error?.code)
            assertFalse(resp.ok)
        }
    }

    @Test
    fun `response is canonical`() {
        val resp = TaskerGatewayResponse.success(
            commandId = "cmd-1",
            adapterId = "device_owner.status.v1",
            requestHash = "abc",
            result = mapOf("z" to 1, "a" to 2),
            executor = TaskerGatewayResponse.ExecutorInfo(),
            receivedAt = 0, startedAt = 0, completedAt = 0
        )
        val j1 = String(TaskerGatewayResponse.payloadForSigning(resp))
        val j2 = String(TaskerGatewayResponse.payloadForSigning(resp))
        assertEquals(j1, j2)
    }
}
