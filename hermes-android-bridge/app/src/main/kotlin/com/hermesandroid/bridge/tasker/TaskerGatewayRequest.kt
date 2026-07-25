package com.hermesandroid.bridge.tasker

import java.util.UUID

/**
 * Hardened request contract v1.
 *
 * No code, no file paths, no eval — only adapter_id selection.
 * All fields are part of the canonical payload that gets hashed and signed.
 */
data class TaskerGatewayRequest(
    val version: Int = 1,
    val command_id: String = UUID.randomUUID().toString(),
    val adapter_id: String,
    val params: Map<String, Any> = emptyMap(),
    val issued_at_ms: Long = System.currentTimeMillis(),
    val deadline_at_ms: Long = issued_at_ms + 10_000,
    val nonce: String = UUID.randomUUID().toString(),
    val request_hash: String = "",
    val auth: Auth = Auth()
) {
    data class Auth(
        val algorithm: String = "HMAC-SHA256",
        val signature: String = ""
    )

    companion object {
        const val MAX_REQUEST_SIZE = 65536  // 64 KB

        /**
         * Build the bytes that get hashed into request_hash.
         * Includes everything except request_hash and auth.
         */
        fun payloadForHashing(req: TaskerGatewayRequest): ByteArray {
            val payload = req.copy(request_hash = "", auth = Auth())
            return TaskerGatewayAuthenticator.canonicalJson(payload)
        }

        /**
         * Build a fully signed request.
         * Creates the request, computes request_hash, and signs it.
         */
        fun create(
            adapterId: String,
            params: Map<String, Any> = emptyMap(),
            timeoutMs: Long = 10_000
        ): TaskerGatewayRequest {
            val now = System.currentTimeMillis()
            val req = TaskerGatewayRequest(
                adapter_id = adapterId,
                params = params,
                issued_at_ms = now,
                deadline_at_ms = now + timeoutMs,
                nonce = UUID.randomUUID().toString()
            )
            val payloadBytes = payloadForHashing(req)
            val hash = TaskerGatewayAuthenticator.sha256(payloadBytes)
            val signature = TaskerGatewayAuthenticator.sign(payloadBytes)
            return req.copy(
                request_hash = hash,
                auth = Auth(signature = signature)
            )
        }

        /**
         * Validate request structure (before auth verification).
         * Returns null if valid, error code string if not.
         */
        fun validate(req: TaskerGatewayRequest): String? {
            if (req.version != 1) return "INVALID_VERSION"
            if (req.command_id.isBlank()) return "MISSING_COMMAND_ID"
            if (req.adapter_id.isBlank()) return "MISSING_ADAPTER_ID"
            if (req.deadline_at_ms <= req.issued_at_ms) return "INVALID_DEADLINE"
            if (req.request_hash.isBlank()) return "MISSING_REQUEST_HASH"
            if (req.auth.signature.isBlank()) return "MISSING_SIGNATURE"
            val size = TaskerGatewayAuthenticator.canonicalJson(req).size
            if (size > MAX_REQUEST_SIZE) return "REQUEST_TOO_LARGE"
            return null  // valid
        }
    }
}
