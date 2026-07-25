package com.hermesandroid.bridge.tasker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class TaskerGatewayRequestTest {

    @Before
    fun setup() {
        TaskerGatewayAuthenticator.configure("dGVzdC1zZWNyZXQta2V5LTI1Ni1iaXRzLW1pbmltdW0hIQ==")
    }

    @Test
    fun `create produces valid request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        assertEquals(1, req.version)
        assertEquals("device_owner.status.v1", req.adapter_id)
        assertTrue(req.command_id.isNotBlank())
        assertTrue(req.request_hash.isNotBlank())
        assertTrue(req.auth.signature.isNotBlank())
        assertTrue(req.deadline_at_ms > req.issued_at_ms)
        assertTrue(req.nonce.isNotBlank())
    }

    @Test
    fun `create with custom timeout`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1", timeoutMs = 5000)
        assertEquals(5000, req.deadline_at_ms - req.issued_at_ms)
    }

    @Test
    fun `create with params`() {
        val params = mapOf("key" to "value")
        val req = TaskerGatewayRequest.create("device_owner.status.v1", params = params)
        assertEquals(params, req.params)
    }

    @Test
    fun `validate accepts valid request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        assertNull(TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects version != 1`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(version = 2)
        assertEquals("INVALID_VERSION", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects empty adapter_id`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(adapter_id = "")
        assertEquals("MISSING_ADAPTER_ID", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects blank command_id`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(command_id = "")
        assertEquals("MISSING_COMMAND_ID", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects deadline before issued_at`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(
            issued_at_ms = 1000,
            deadline_at_ms = 500
        )
        assertEquals("INVALID_DEADLINE", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects empty request_hash`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(request_hash = "")
        assertEquals("MISSING_REQUEST_HASH", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `validate rejects empty signature`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1").copy(
            auth = TaskerGatewayRequest.Auth(signature = "")
        )
        assertEquals("MISSING_SIGNATURE", TaskerGatewayRequest.validate(req))
    }

    @Test
    fun `request_hash is SHA-256 of payload`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val payload = TaskerGatewayRequest.payloadForHashing(req)
        val expectedHash = TaskerGatewayAuthenticator.sha256(payload)
        assertEquals(expectedHash, req.request_hash)
    }

    @Test
    fun `no source code or file paths in request`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val json = String(TaskerGatewayAuthenticator.canonicalJson(req))
        assertFalse("No eval", json.contains("eval"))
        assertFalse("No /sdcard", json.contains("/sdcard"))
        assertFalse("No par1", json.contains("par1"))
        assertFalse("No source keyword", json.contains("source"))
    }

    @Test
    fun `canonical JSON is deterministic`() {
        val req = TaskerGatewayRequest.create("device_owner.status.v1")
        val j1 = String(TaskerGatewayAuthenticator.canonicalJson(req))
        val j2 = String(TaskerGatewayAuthenticator.canonicalJson(req))
        assertEquals(j1, j2)
    }
}
