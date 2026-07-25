package com.hermesandroid.bridge.tasker

/**
 * Hardened response contract v1.
 *
 * Signed by Tasker after execution. Verified by Bridge before processing.
 * Auth field is excluded from the signing payload.
 */
data class TaskerGatewayResponse(
    val version: Int = 1,
    val command_id: String,
    val adapter_id: String,
    val request_hash: String,
    val ok: Boolean,
    val status: String,
    val received_at_ms: Long = 0,
    val started_at_ms: Long = 0,
    val completed_at_ms: Long = 0,
    val duration_ms: Long = 0,
    val result: Map<String, Any>? = null,
    val executor: ExecutorInfo? = null,
    val error: ErrorInfo? = null,
    val auth: Auth = Auth()
) {
    data class Auth(
        val algorithm: String = "HMAC-SHA256",
        val signature: String = ""
    )

    data class ExecutorInfo(
        val type: String = "tasker",
        val package_name: String = "net.dinglisch.android.taskerm",
        val process_uid: Int = 0,
        val process_pid: Int = 0,
        val task_name: String = ""
    )

    data class ErrorInfo(
        val code: String,
        val message: String
    )

    companion object {
        const val MAX_RESPONSE_SIZE = 262144  // 256 KB

        /**
         * Build a successful response.
         */
        fun success(
            commandId: String,
            adapterId: String,
            requestHash: String,
            result: Map<String, Any>,
            executor: ExecutorInfo,
            receivedAt: Long,
            startedAt: Long,
            completedAt: Long
        ): TaskerGatewayResponse {
            return TaskerGatewayResponse(
                command_id = commandId,
                adapter_id = adapterId,
                request_hash = requestHash,
                ok = true,
                status = "completed",
                received_at_ms = receivedAt,
                started_at_ms = startedAt,
                completed_at_ms = completedAt,
                duration_ms = completedAt - startedAt,
                result = result,
                executor = executor
            )
        }

        /**
         * Build an error response.
         */
        fun error(
            commandId: String,
            adapterId: String,
            requestHash: String,
            code: String,
            message: String
        ): TaskerGatewayResponse {
            return TaskerGatewayResponse(
                command_id = commandId,
                adapter_id = adapterId,
                request_hash = requestHash,
                ok = false,
                status = "rejected",
                error = ErrorInfo(code, message)
            )
        }

        /**
         * Build bytes for signing: everything except auth.
         */
        fun payloadForSigning(resp: TaskerGatewayResponse): ByteArray {
            val unsigned = resp.copy(auth = Auth())
            return TaskerGatewayAuthenticator.canonicalJson(unsigned)
        }

        /**
         * Sign a response.
         */
        fun signResponse(resp: TaskerGatewayResponse): TaskerGatewayResponse {
            val payload = payloadForSigning(resp)
            val signature = TaskerGatewayAuthenticator.sign(payload)
            return resp.copy(auth = Auth(signature = signature))
        }
    }
}
