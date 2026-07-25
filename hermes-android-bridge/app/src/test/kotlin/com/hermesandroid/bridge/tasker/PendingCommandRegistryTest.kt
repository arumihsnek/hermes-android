package com.hermesandroid.bridge.tasker

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class PendingCommandRegistryTest {

    private lateinit var registry: PendingCommandRegistry

    @Before
    fun setup() {
        registry = PendingCommandRegistry(ttlMs = 60_000)
    }

    private fun makeResponse(commandId: String, ok: Boolean = true): TaskerGatewayResponse {
        return TaskerGatewayResponse(
            command_id = commandId,
            adapter_id = "device_owner.status.v1",
            request_hash = "hash",
            ok = ok,
            status = if (ok) "completed" else "error"
        )
    }

    @Test
    fun `new command registers successfully`() {
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.NEW, outcome.result)
        assertNull(outcome.cachedResponse)
    }

    @Test
    fun `identical duplicate returns cached response`() {
        registry.register("cmd-1", "hash-a")
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL, outcome.result)
        assertNotNull(outcome.cachedResponse)
    }

    @Test
    fun `conflicting duplicate rejected`() {
        registry.register("cmd-1", "hash-a")
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        val outcome = registry.register("cmd-1", "hash-b")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT, outcome.result)
        assertNull(outcome.cachedResponse)  // No last-write-wins
    }

    @Test
    fun `pending identical duplicate detected`() {
        registry.register("cmd-1", "hash-a")
        val outcome = registry.register("cmd-1", "hash-a")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_IDENTICAL, outcome.result)
    }

    @Test
    fun `pending conflict detected`() {
        registry.register("cmd-1", "hash-a")
        val outcome = registry.register("cmd-1", "hash-b")
        assertEquals(PendingCommandRegistry.RegistrationResult.DUPLICATE_CONFLICT, outcome.result)
    }

    @Test
    fun `two different commands dont conflict`() {
        assertEquals(
            PendingCommandRegistry.RegistrationResult.NEW,
            registry.register("cmd-1", "hash-a").result
        )
        assertEquals(
            PendingCommandRegistry.RegistrationResult.NEW,
            registry.register("cmd-2", "hash-b").result
        )
    }

    @Test
    fun `deferred completes on complete call`() = runBlocking {
        registry.register("cmd-1", "hash-a")
        val deferred = registry.getDeferred("cmd-1")
        assertNotNull(deferred)
        val response = makeResponse("cmd-1")
        registry.complete("cmd-1", "hash-a", response)
        assertEquals(response, deferred!!.await())
    }

    @Test
    fun `pending count tracks correctly`() {
        assertEquals(0, registry.pendingCount())
        registry.register("cmd-1", "hash-a")
        assertEquals(1, registry.pendingCount())
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        assertEquals(0, registry.pendingCount())
        assertEquals(1, registry.completedCount())
    }

    @Test
    fun `fail completes deferred`() = runBlocking {
        registry.register("cmd-1", "hash-a")
        val deferred = registry.getDeferred("cmd-1")!!
        val error = TaskerGatewayResponse.error(
            "cmd-1", "device_owner.status.v1", "hash-a",
            "timeout", "timed out"
        )
        registry.fail("cmd-1", error)
        val result = deferred.await()
        assertEquals("timeout", result.error?.code)
    }

    @Test
    fun `isPending tracks correctly`() {
        assertTrue(!registry.isPending("cmd-1"))
        registry.register("cmd-1", "hash-a")
        assertTrue(registry.isPending("cmd-1"))
        registry.complete("cmd-1", "hash-a", makeResponse("cmd-1"))
        assertTrue(!registry.isPending("cmd-1"))
    }
}
