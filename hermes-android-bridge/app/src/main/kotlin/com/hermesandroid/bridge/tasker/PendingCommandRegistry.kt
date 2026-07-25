package com.hermesandroid.bridge.tasker

import kotlinx.coroutines.CompletableDeferred
import java.util.concurrent.ConcurrentHashMap

/**
 * Manages pending commands with deduplication.
 *
 * Dedup semantics (NO last-write-wins):
 * - Same command_id + same request_hash → return cached (replay)
 * - Same command_id + different request_hash → reject (conflict)
 * - New command_id → execute once
 *
 * Uses CompletableDeferred for async response correlation.
 * No blocking, no polling, no file I/O.
 */
class PendingCommandRegistry(private val ttlMs: Long = 300_000) {

    data class PendingEntry(
        val deferred: CompletableDeferred<TaskerGatewayResponse>,
        val requestHash: String,
        val createdAt: Long = System.currentTimeMillis()
    )

    data class CompletedEntry(
        val requestHash: String,
        val response: TaskerGatewayResponse,
        val completedAt: Long = System.currentTimeMillis()
    )

    enum class RegistrationResult {
        NEW,
        DUPLICATE_IDENTICAL,
        DUPLICATE_CONFLICT
    }

    data class RegistrationOutcome(
        val result: RegistrationResult,
        val cachedResponse: TaskerGatewayResponse? = null
    )

    private val pending = ConcurrentHashMap<String, PendingEntry>()
    private val completed = ConcurrentHashMap<String, CompletedEntry>()

    /**
     * Register a command for execution.
     * Returns outcome:
     * - NEW: command registered, caller should execute
     * - DUPLICATE_IDENTICAL: same command_id + same hash → replay
     * - DUPLICATE_CONFLICT: same command_id + different hash → reject
     */
    fun register(commandId: String, requestHash: String): RegistrationOutcome {
        // Check pending first
        pending[commandId]?.let { entry ->
            return if (entry.requestHash == requestHash) {
                RegistrationOutcome(RegistrationResult.DUPLICATE_IDENTICAL)
            } else {
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // Check completed (replay)
        completed[commandId]?.let { entry ->
            return if (entry.requestHash == requestHash) {
                RegistrationOutcome(
                    RegistrationResult.DUPLICATE_IDENTICAL,
                    cachedResponse = entry.response
                )
            } else {
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // New command — register
        pending[commandId] = PendingEntry(
            deferred = CompletableDeferred(),
            requestHash = requestHash
        )
        return RegistrationOutcome(RegistrationResult.NEW)
    }

    /**
     * Get the deferred for a pending command.
     */
    fun getDeferred(commandId: String): CompletableDeferred<TaskerGatewayResponse>? {
        return pending[commandId]?.deferred
    }

    /**
     * Complete a pending command with its response.
     */
    fun complete(commandId: String, requestHash: String, response: TaskerGatewayResponse) {
        val entry = pending.remove(commandId) ?: return
        if (entry.requestHash != requestHash) {
            // Hash mismatch — put back (shouldn't happen in normal flow)
            pending[commandId] = entry
            throw IllegalArgumentException("Request hash mismatch on complete")
        }
        entry.deferred.complete(response)
        completed[commandId] = CompletedEntry(
            requestHash = requestHash,
            response = response
        )
    }

    /**
     * Fail a pending command (e.g., timeout).
     */
    fun fail(commandId: String, error: TaskerGatewayResponse) {
        val entry = pending.remove(commandId) ?: return
        entry.deferred.complete(error)
    }

    /**
     * Cleanup expired completed entries.
     */
    fun cleanup() {
        val now = System.currentTimeMillis()
        completed.entries.removeIf { (_, entry) ->
            (now - entry.completedAt) > ttlMs
        }
    }

    fun pendingCount(): Int = pending.size
    fun completedCount(): Int = completed.size
    fun isPending(commandId: String): Boolean = pending.containsKey(commandId)
}
