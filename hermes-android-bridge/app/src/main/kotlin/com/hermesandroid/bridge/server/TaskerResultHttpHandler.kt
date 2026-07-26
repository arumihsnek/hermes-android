package com.hermesandroid.bridge.server

import android.util.Log
import com.hermesandroid.bridge.BuildConfig
import com.google.gson.Gson
import com.google.gson.JsonParser
import com.hermesandroid.bridge.client.RelayClient
import com.hermesandroid.bridge.tasker.TaskerResultEnvelope
import com.hermesandroid.bridge.tasker.TaskerResultReceiver
import com.hermesandroid.bridge.tasker.TaskerResultRegistry
import io.ktor.http.*
import io.ktor.serialization.gson.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*

/**
 * Loopback-only HTTP endpoint for Tasker to submit results via
 * POST http://127.0.0.1:8767/v1/tasker/result
 *
 * This server binds exclusively to 127.0.0.1 (loopback) so no external
 * interface can reach it. No auth token required — local loopback is trusted.
 *
 * Architecture: HTTP handler → TaskerResultEnvelope parser →
 *   TaskerResultRegistry → RelayClient. No broadcast involved.
 *
 * Security constraints enforced:
 * - POST only (405 for other methods)
 * - Content-Type: application/json (415 for others)
 * - Body ≤ 65536 bytes; Content-Length pre-check before reading (413 for oversized)
 * - Full envelope validation before registry interaction
 * - result_token match for commands registered with a token
 * - Atomic completion (single terminal result per command_id)
 * - No sensitive data in error responses
 */
object TaskerResultHttpHandler {

    private const val TAG = "TaskerResultHttp"
    private const val TASKER_PORT = 8767
    private const val TASKER_HOST = "127.0.0.1"
    private const val MAX_BODY_BYTES = 65536
    private const val ROUTE = "/v1/tasker/result"

    private val gson = Gson()
    private var server: ApplicationEngine? = null
    private var actualPort: Int = TASKER_PORT

    /** Shared reference to the TaskerResultRegistry. Set during startup. */
    var registry: TaskerResultRegistry? = null

    /**
     * Start the loopback HTTP server for Tasker results.
     * Idempotent — safe to call multiple times.
     */
    fun start(port: Int = TASKER_PORT) {
        if (server != null) {
            Log.i(TAG, "Loopback server already running on $TASKER_HOST:$TASKER_PORT")
            return
        }
        actualPort = port
        server = embeddedServer(Netty, port = port, host = TASKER_HOST) {
            install(ContentNegotiation) {
                gson {
                    setPrettyPrinting()
                    serializeNulls()
                }
            }
            routing {
                route(ROUTE) {
                    handle {
                        handleRequest(call)
                    }
                }

                // Debug-only endpoint for registering a probe command
                // Only compiled when BuildConfig.DEBUG is true
                if (BuildConfig.DEBUG) {
                    post("/v1/tasker/debug/register") {
                        val reg = registry
                        if (reg == null) {
                            call.respond(HttpStatusCode.InternalServerError, mapOf("error" to "Registry not initialized"))
                            return@post
                        }
                        try {
                            val bodyText = call.receive<String>()
                            val json = com.google.gson.JsonParser.parseString(bodyText).asJsonObject
                            val commandId = json.get("command_id")?.asString ?: run {
                                call.respond(HttpStatusCode.BadRequest, mapOf("error" to "Missing command_id"))
                                return@post
                            }
                            val operation = json.get("operation")?.asString ?: "probe"
                            val resultToken = json.get("result_token")?.asString
                            val deadlineMs = json.get("deadline_ms")?.asLong
                                ?: (System.currentTimeMillis() + 60_000)
                            val result = reg.register(
                                commandId = commandId,
                                operation = operation,
                                expectedResultToken = resultToken,
                                deadline = deadlineMs
                            )
                            when (result) {
                                TaskerResultRegistry.RegistrationResult.OK ->
                                    call.respond(HttpStatusCode.OK, mapOf("ok" to true, "command_id" to commandId))
                                TaskerResultRegistry.RegistrationResult.DUPLICATE ->
                                    call.respond(HttpStatusCode.Conflict, mapOf("error" to "Duplicate command_id", "command_id" to commandId))
                            }
                        } catch (e: Exception) {
                            val msg: String = e.message ?: "Invalid request"
                            call.respond(HttpStatusCode.BadRequest, mapOf<String, Any>("error" to msg))
                        }
                    }
                }

                // Catch-all for unknown routes
                handle {
                    val method = call.request.httpMethod.value
                    val path = call.request.path()
                    Log.w(TAG, "Unhandled $method $path")
                    call.respond(HttpStatusCode.NotFound, mapOf(
                        "error" to "Not found",
                        "path" to path
                    ))
                }
            }
        }.also {
            it.start(wait = false)
            Log.i(TAG, "Loopback server started on $TASKER_HOST:$TASKER_PORT")
        }
    }

    /**
     * Stop the loopback server. Idempotent.
     */
    fun stop() {
        server?.stop(1000, 2000)
        server = null
        Log.i(TAG, "Loopback server stopped")
    }

    val isRunning: Boolean get() = server != null
    val port: Int get() = actualPort

    private suspend fun handleRequest(call: ApplicationCall) {
        val startTime = System.currentTimeMillis()
        val path = call.request.path()

        // ── 1. Method check ──────────────────────────────────────────────
        if (call.request.httpMethod != HttpMethod.Post) {
            Log.w(TAG, "Rejected method=${call.request.httpMethod.value} path=$path")
            call.respond(HttpStatusCode.MethodNotAllowed, mapOf(
                "error" to "Method not allowed. Use POST.",
                "allowed" to listOf("POST")
            ))
            return
        }

        // ── 2. Content-Type check ────────────────────────────────────────
        val contentType = call.request.contentType()
        if (!contentType.match(ContentType.Application.Json)) {
            Log.w(TAG, "Rejected content-type=$contentType")
            call.respond(HttpStatusCode.UnsupportedMediaType, mapOf(
                "error" to "Content-Type must be application/json"
            ))
            return
        }

        // ── 3. Body size check (pre-check via Content-Length) ──────────
        val contentLength = call.request.contentLength()
        if (contentLength != null && contentLength > MAX_BODY_BYTES) {
            Log.w(TAG, "Content-Length too large: $contentLength (max $MAX_BODY_BYTES)")
            call.respond(HttpStatusCode(413, "Payload Too Large"), mapOf(
                "error" to "Body exceeds maximum size of $MAX_BODY_BYTES bytes",
                "max" to MAX_BODY_BYTES
            ))
            return
        }

        // Read body
        val bodyText = try {
            call.receive<String>()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to read body: ${e.message}")
            call.respond(HttpStatusCode.BadRequest, mapOf(
                "error" to "Failed to read request body"
            ))
            return
        }

        // Post-read size check (catches chunked requests without Content-Length)
        val bodyBytes = bodyText.toByteArray(Charsets.UTF_8)
        if (bodyBytes.size > MAX_BODY_BYTES) {
            Log.w(TAG, "Body too large: ${bodyBytes.size} bytes (max $MAX_BODY_BYTES)")
            call.respond(HttpStatusCode(413, "Payload Too Large"), mapOf(
                "error" to "Body exceeds maximum size of $MAX_BODY_BYTES bytes",
                "size" to bodyBytes.size,
                "max" to MAX_BODY_BYTES
            ))
            return
        }

        // ── 4. Parse envelope ──────────────────────────────────────────
        val envelope = TaskerResultEnvelope.parse(bodyText)

        if (envelope == null) {
            Log.w(TAG, "Invalid envelope: size=${bodyText.length}")
            call.respond(HttpStatusCode.BadRequest, mapOf(
                "error" to "Invalid result envelope. Check schema, operation, command_id, result_json."
            ))
            return
        }

        // ── 5. result_token required for HTTP ───────────────────────────
        if (envelope.resultToken.isNullOrBlank()) {
            Log.w(TAG, "Missing result_token for ${truncate(envelope.commandId)}")
            call.respond(HttpStatusCode.BadRequest, mapOf(
                "error" to "result_token is required"
            ))
            return
        }

        // ── 6. Validate body JSON (result_json must be valid JSON) ────
        try {
            JsonParser.parseString(envelope.resultJson)
        } catch (e: Exception) {
            Log.w(TAG, "result_json is not valid JSON for ${truncate(envelope.commandId)}: ${e.message}")
            call.respond(HttpStatusCode.BadRequest, mapOf(
                "error" to "result_json must be valid JSON"
            ))
            return
        }

        // ── 7. Registry check ──────────────────────────────────────────
        val reg = registry ?: run {
            Log.e(TAG, "Registry not initialized")
            call.respond(HttpStatusCode.InternalServerError, mapOf(
                "error" to "Internal error"
            ))
            return
        }

        // ── 8. Command existence check (before token) ──────────────────
        if (!reg.isPending(envelope.commandId)) {
            val state = reg.getState(envelope.commandId)
            val statusCode = when (state) {
                TaskerResultRegistry.CommandState.COMPLETED -> HttpStatusCode.Conflict
                TaskerResultRegistry.CommandState.EXPIRED -> HttpStatusCode.Gone
                TaskerResultRegistry.CommandState.FAILED -> HttpStatusCode.Conflict
                else -> HttpStatusCode.NotFound
            }
            Log.w(TAG, "Command ${truncate(envelope.commandId)} not pending: state=$state")
            val errorMsg = when (statusCode) {
                HttpStatusCode.Conflict -> "Command already completed or failed"
                HttpStatusCode.Gone -> "Command deadline expired"
                else -> "Command not found"
            }
            call.respond(statusCode, mapOf("error" to errorMsg))
            return
        }

        // ── 9. Attempt atomic completion ───────────────────────────────
        val accepted = reg.complete(
            commandId = envelope.commandId,
            operation = envelope.operation,
            resultJson = envelope.resultJson,
            resultToken = envelope.resultToken
        )

        if (!accepted) {
            val state = reg.getState(envelope.commandId)
            val (code, msg) = when (state) {
                TaskerResultRegistry.CommandState.COMPLETED -> {
                    Log.i(TAG, "Duplicate result for ${truncate(envelope.commandId)}")
                    HttpStatusCode.Conflict to "Duplicate result: command already completed"
                }
                TaskerResultRegistry.CommandState.EXPIRED -> {
                    Log.i(TAG, "Expired result for ${truncate(envelope.commandId)}")
                    HttpStatusCode.Gone to "Command deadline expired"
                }
                TaskerResultRegistry.CommandState.FAILED -> {
                    Log.i(TAG, "Result for failed command ${truncate(envelope.commandId)}")
                    HttpStatusCode.Conflict to "Command already failed"
                }
                else -> {
                    if (state == TaskerResultRegistry.CommandState.PENDING) {
                        Log.w(TAG, "Token mismatch for ${truncate(envelope.commandId)}")
                        HttpStatusCode.Unauthorized to "Invalid result_token"
                    } else {
                        Log.w(TAG, "Result rejected for ${truncate(envelope.commandId)}: state=$state")
                        HttpStatusCode.Conflict to "Result rejected"
                    }
                }
            }
            call.respond(code, mapOf("error" to msg))
            return
        }

        // ── 10. Forward to relay ────────────────────────────────────────
        val relayMsg = TaskerResultReceiver.buildRelayMessage(envelope)
        try {
            val sent = RelayClient.sendTaskerResult(relayMsg)
            if (!sent) {
                Log.w(TAG, "Tasker result queued (relay disconnected) for ${truncate(envelope.commandId)}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error forwarding result to relay: ${e.message}", e)
            // Result is already accepted and completed — do NOT reject it
        }

        val elapsed = System.currentTimeMillis() - startTime
        Log.i(TAG, "Accepted op=${envelope.operation} cmd=${truncate(envelope.commandId)} size=${bodyText.length} latency=${elapsed}ms")

        call.respond(HttpStatusCode.OK, mapOf(
            "accepted" to true,
            "command_id" to envelope.commandId,
            "operation" to envelope.operation
        ))
    }

    private fun truncate(s: String): String =
        if (s.length > 12) s.take(12) + "…" else s
}
