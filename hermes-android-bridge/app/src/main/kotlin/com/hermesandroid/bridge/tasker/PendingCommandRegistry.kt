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
                recordRegistration(RegistrationResult.DUPLICATE_IDENTICAL)
                RegistrationOutcome(RegistrationResult.DUPLICATE_IDENTICAL)
            } else {
                recordRegistration(RegistrationResult.DUPLICATE_CONFLICT)
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // Check completed (replay)
        completed[commandId]?.let { entry ->
            return if (entry.requestHash == requestHash) {
                recordRegistration(RegistrationResult.DUPLICATE_IDENTICAL)
                RegistrationOutcome(
                    RegistrationResult.DUPLICATE_IDENTICAL,
                    cachedResponse = entry.response
                )
            } else {
                recordRegistration(RegistrationResult.DUPLICATE_CONFLICT)
                RegistrationOutcome(RegistrationResult.DUPLICATE_CONFLICT)
            }
        }

        // New command — register
        pending[commandId] = PendingEntry(
            deferred = CompletableDeferred(),
            requestHash = requestHash
        )
        recordRegistration(RegistrationResult.NEW)
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
        recordCompletion()
    }

    /**
     * Fail a pending command (e.g., timeout).
     */
    fun fail(commandId: String, error: TaskerGatewayResponse) {
        val entry = pending.remove(commandId) ?: return
        entry.deferred.complete(error)
        recordFailure()
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

    // ── Diagnostic execution counters (Phase 7) ────────────────────────
    // Temporary counters for live dogfood evidence.
    // Remove or deactivate after Phase 6 verification is complete.

    data class ExecutionCounters(
        val registeredNew: Long = 0,
        val duplicateIdentical: Long = 0,
        val duplicateConflict: Long = 0,
        val completedSuccess: Long = 0,
        val failedTimeout: Long = 0,
        val deadlineExceeded: Long = 0,
        val dpmExecutions: Long = 0  // Track actual DPM executions from Tasker side
    ) {
        fun toMap(): Map<String, Any> = mapOf(
            "registered_new" to registeredNew,
            "duplicate_identical" to duplicateIdentical,
            "duplicate_conflict" to duplicateConflict,
            "completed_success" to completedSuccess,
            "failed_timeout" to failedTimeout,
            "deadline_exceeded" to deadlineExceeded,
            "dpm_executions" to dpmExecutions
        )
    }

    @Volatile
    private var counters = ExecutionCounters()

    /** Record a registration event. Called from register(). */
    fun recordRegistration(result: RegistrationResult) {
        counters = when (result) {
            RegistrationResult.NEW -> counters.copy(registeredNew = counters.registeredNew + 1)
            RegistrationResult.DUPLICATE_IDENTICAL -> counters.copy(duplicateIdentical = counters.duplicateIdentical + 1)
            RegistrationResult.DUPLICATE_CONFLICT -> counters.copy(duplicateConflict = counters.duplicateConflict + 1)
        }
    }

    /** Record a completion event. Called from complete(). */
    fun recordCompletion() {
        counters = counters.copy(completedSuccess = counters.completedSuccess + 1)
    }

    /** Record a failure event. Called from fail(). */
    fun recordFailure() {
        counters = counters.copy(failedTimeout = counters.failedTimeout + 1)
    }

    /** Record a deadline exceeded event. */
    fun recordDeadlineExceeded() {
        counters = counters.copy(deadlineExceeded = counters.deadlineExceeded + 1)
    }

    /** Record a DPM execution (reported by Tasker in response). */
    fun recordDpmExecution() {
        counters = counters.copy(dpmExecutions = counters.dpmExecutions + 1)
    }

    /** Get current counters snapshot. */
    fun getExecutionCounters(): ExecutionCounters = counters

    /** Reset all counters (for testing). */
    fun resetCounters() {
        counters = ExecutionCounters()
    }
}
