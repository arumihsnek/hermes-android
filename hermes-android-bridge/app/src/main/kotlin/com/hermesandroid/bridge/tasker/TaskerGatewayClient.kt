package com.hermesandroid.bridge.tasker

import android.content.Context
import android.content.IntentFilter
import android.util.Log
import kotlinx.coroutines.withTimeout

/**
 * High-level client: send request → await response.
 *
 * Enforces:
 * - Deadline before sending
 * - Deduplication (identical replay / conflict)
 * - HMAC verification
 * - Adapter allowlist
 * - Timeout on response wait
 *
 * No shell, no polling, no file I/O.
 */
class TaskerGatewayClient(private val context: Context) {

    companion object {
        private const val TAG = "TaskerGatewayClient"
        private const val DEFAULT_TIMEOUT_MS = 10_000L
    }

    private val pendingRegistry = PendingCommandRegistry()
    private var receiverRegistered = false

    init {
        // Configure authenticator from on-device secret
        TaskerGatewayConfig.initAuthenticator(context)

        // Set registry on receiver for response correlation
        TaskerGatewayReceiver.registry = pendingRegistry

        // Register response receiver (if not already)
        if (!receiverRegistered) {
            val filter = IntentFilter(TaskerGatewayConfig.ACTION_RESPONSE)
            context.registerReceiver(
                TaskerGatewayReceiver(),
                filter,
                Context.RECEIVER_NOT_EXPORTED
            )
            receiverRegistered = true
        }
    }

    /**
     * Execute a command and await the response.
     * Enforces deadline, dedup, and timeout.
     */
    suspend fun execute(
        adapterId: String,
        params: Map<String, Any> = emptyMap(),
        timeoutMs: Long = DEFAULT_TIMEOUT_MS
    ): TaskerGatewayResponse {
        // 1. Validate adapter exists in allowlist
        val adapterError = AdapterRegistry.validateAdapter(adapterId)
        if (adapterError != null) {
            return TaskerGatewayResponse.error(
                commandId = "",
                adapterId = adapterId,
                requestHash = "",
                code = adapterError,
                message = "Adapter not allowed: $adapterId"
            )
        }

        // 2. Validate timeout
        if (timeoutMs <= 0) {
            return TaskerGatewayResponse.error(
                commandId = "",
                adapterId = adapterId,
                requestHash = "",
                code = "invalid_timeout",
                message = "Timeout must be positive"
            )
        }

        // 3. Create signed request
        val request = TaskerGatewayRequest.create(adapterId, params, timeoutMs)

        // 4. Register for dedup
        val outcome = pendingRegistry.register(request.command_id, request.request_hash)
        when (outcome.result) {
            PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL -> {
                Log.d(TAG, "Replay detected for ${request.command_id}, returning cached")
                return outcome.cachedResponse ?: TaskerGatewayResponse.error(
                    request.command_id, adapterId, request.request_hash,
                    "internal_error", "No cached response for identical replay"
                )
            }
            PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT -> {
                return TaskerGatewayResponse.error(
                    request.command_id, adapterId, request.request_hash,
                    "command_id_conflict",
                    "command_id reused with different request_hash"
                )
            }
            PendingCommandRegistry.RegistrationResult.NEW -> { /* proceed */ }
        }

        // 5. Check deadline right before sending
        if (System.currentTimeMillis() > request.deadline_at_ms) {
            val error = TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "deadline_exceeded", "Request expired before execution"
            )
            pendingRegistry.fail(request.command_id, error)
            return error
        }

        // 6. Send via native broadcast
        val sent = TaskerGatewayTransport.send(context, request)
        if (!sent) {
            val error = TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "transport_error", "Failed to send broadcast to Tasker"
            )
            pendingRegistry.fail(request.command_id, error)
            return error
        }

        // 7. Await response with timeout
        val deferred = pendingRegistry.getDeferred(request.command_id)
            ?: return TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "internal_error", "No deferred registered"
            )

        return try {
            withTimeout(timeoutMs) {
                deferred.await()
            }
        } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
            val error = TaskerGatewayResponse.error(
                request.command_id, adapterId, request.request_hash,
                "timeout", "Bridge timeout after ${timeoutMs}ms"
            )
            pendingRegistry.fail(request.command_id, error)
            error
        }
    }
}
