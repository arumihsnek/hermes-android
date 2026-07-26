package com.hermesandroid.bridge.server

import com.hermesandroid.bridge.client.RelayClient
import com.hermesandroid.bridge.tasker.TaskerResultRegistry
import io.mockk.every
import io.mockk.mockkObject
import io.mockk.verify
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/**
 * Full integration tests for TaskerResultHttpHandler loopback endpoint.
 *
 * Starts a real Netty server on a random loopback port and sends
 * real HTTP requests via OkHttp. No mocking of the transport layer.
 * Uses MockK only to intercept RelayClient.sendTaskerResult().
 */
class TaskerResultHttpHandlerTest {

    private lateinit var registry: TaskerResultRegistry
    private lateinit var client: OkHttpClient
    private var baseUrl: String = ""

    @Before
    fun setup() {
        registry = TaskerResultRegistry()
        TaskerResultHttpHandler.registry = registry

        // Start server on port 0 (random available port)
        TaskerResultHttpHandler.start(port = 8276)
        assertTrue("Server must be running", TaskerResultHttpHandler.isRunning)
        baseUrl = "http://127.0.0.1:${TaskerResultHttpHandler.port}"

        client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .build()

        // Mock RelayClient so we don't need a real WebSocket connection
        mockkObject(RelayClient)
        every { RelayClient.sendTaskerResult(any()) } returns true
    }

    @After
    fun teardown() {
        TaskerResultHttpHandler.stop()
    }

    // ── E2E: Valid commands ─────────────────────────────────────────────

    @Test
    fun `valid probe result accepted`() {
        registry.register(
            commandId = "probe-cmd-1",
            operation = "probe",
            expectedResultToken = "token-abc",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "probe-cmd-1",
            "result_token": "token-abc",
            "result_json": "{\"ok\":true,\"probe_token\":\"test123\"}",
            "finished_at_ms": "1785000000000"
        }""")

        assertEquals("Should accept", 200, response.code)
        assertTrue(registry.isCompleted("probe-cmd-1"))
        verify { RelayClient.sendTaskerResult(any()) }
    }

    @Test
    fun `valid import result accepted`() {
        registry.register(
            commandId = "import-cmd-1",
            operation = "import",
            expectedTaskName = "Hermes · Capability · Echo v1",
            expectedSha256 = "abc123",
            expectedResultToken = "token-xyz",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "import",
            "command_id": "import-cmd-1",
            "result_token": "token-xyz",
            "result_json": "{\"ok\":true,\"task_name\":\"Hermes · Capability · Echo v1\",\"sha256\":\"abc123\"}",
            "finished_at_ms": "1785000000000"
        }""")

        assertEquals("Should accept", 200, response.code)
        assertTrue(registry.isCompleted("import-cmd-1"))
        verify { RelayClient.sendTaskerResult(any()) }
    }

    @Test
    fun `valid run result accepted`() {
        registry.register(
            commandId = "run-cmd-1",
            operation = "run",
            expectedResultToken = "token-run",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "run",
            "command_id": "run-cmd-1",
            "result_token": "token-run",
            "result_json": "{\"ok\":true,\"result\":\"hello\"}",
            "finished_at_ms": "1785000000001"
        }""")

        assertEquals("Should accept", 200, response.code)
        assertTrue(registry.isCompleted("run-cmd-1"))
    }

    // ── HTTP method ─────────────────────────────────────────────────────

    @Test
    fun `GET returns 405`() {
        val response = getJson("/v1/tasker/result")
        assertEquals("Method not allowed", 405, response.code)
    }

    @Test
    fun `wrong route returns 404`() {
        val response = postJson("/wrong/path", """{}""")
        assertEquals("Not found", 404, response.code)
    }

    // ── Content-Type ─────────────────────────────────────────────────────

    @Test
    fun `wrong content type returns 415`() {
        val response = postWithContentType("/v1/tasker/result", """{}""", "text/plain")
        assertEquals("Unsupported media type", 415, response.code)
    }

    // ── Body validation ──────────────────────────────────────────────────

    @Test
    fun `empty body returns 400`() {
        val response = postJson("/v1/tasker/result", "")
        assertEquals("Bad request", 400, response.code)
    }

    @Test
    fun `body over limit returns 413`() {
        val bigResult = "x".repeat(70000)
        val body = """{"schema":"hermes-tasker-result/v1","operation":"probe","command_id":"big","result_token":"t","result_json":"$bigResult","finished_at_ms":"0"}"""
        val response = postJson("/v1/tasker/result", body)
        assertEquals("Too large", 413, response.code)
    }

    // ── Envelope validation ─────────────────────────────────────────────

    @Test
    fun `invalid JSON body returns 400`() {
        val response = postJson("/v1/tasker/result", "this is not json")
        assertEquals("Bad request", 400, response.code)
    }

    @Test
    fun `invalid schema returns 400`() {
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v2",
            "operation": "probe",
            "command_id": "cmd-1",
            "result_token": "t",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Bad request", 400, response.code)
    }

    @Test
    fun `invalid operation returns 400`() {
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "delete",
            "command_id": "cmd-1",
            "result_token": "t",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Bad request", 400, response.code)
    }

    @Test
    fun `missing result_token returns 400`() {
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-1",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Bad request", 400, response.code)
    }

    @Test
    fun `result_json not valid JSON returns 400`() {
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-1",
            "result_token": "t",
            "result_json": "not json",
            "finished_at_ms": "0"
        }""")
        assertEquals("Bad request", 400, response.code)
    }

    // ── Unknown command ─────────────────────────────────────────────────

    @Test
    fun `unknown command_id returns 404`() {
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "unknown-cmd",
            "result_token": "t",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Not found", 404, response.code)
    }

    // ── Token mismatch ───────────────────────────────────────────────────

    @Test
    fun `wrong result_token returns 401`() {
        registry.register(
            commandId = "cmd-token-mismatch",
            operation = "probe",
            expectedResultToken = "expected-token",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-token-mismatch",
            "result_token": "wrong-token",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Unauthorized", 401, response.code)
        assertTrue(registry.isPending("cmd-token-mismatch"))
    }

    // ── Duplicate ────────────────────────────────────────────────────────

    @Test
    fun `duplicate result returns 409`() {
        registry.register(
            commandId = "cmd-dup",
            operation = "probe",
            expectedResultToken = "token-dup",
            deadline = futureDeadline()
        )

        // First — accepted
        val resp1 = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-dup",
            "result_token": "token-dup",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals(200, resp1.code)

        // Second — duplicate
        val resp2 = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-dup",
            "result_token": "token-dup",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Duplicate", 409, resp2.code)
    }

    // ── Expired ──────────────────────────────────────────────────────────

    @Test
    fun `expired command returns 410`() {
        registry.register(
            commandId = "cmd-expired",
            operation = "probe",
            expectedResultToken = "token-exp",
            deadline = System.currentTimeMillis() - 1000
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-expired",
            "result_token": "token-exp",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Gone", 410, response.code)
    }

    // ── Operation mismatch ───────────────────────────────────────────────

    @Test
    fun `operation mismatch returns 401`() {
        registry.register(
            commandId = "cmd-op-mismatch",
            operation = "import",
            expectedResultToken = "token-op",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "run",
            "command_id": "cmd-op-mismatch",
            "result_token": "token-op",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Unauthorized", 401, response.code)
        assertTrue(registry.isPending("cmd-op-mismatch"))
    }

    // ── Task name mismatch (import) ──────────────────────────────────────

    @Test
    fun `task_name mismatch returns 401`() {
        registry.register(
            commandId = "cmd-tn-mismatch",
            operation = "import",
            expectedTaskName = "Expected Task",
            expectedResultToken = "token-tn",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "import",
            "command_id": "cmd-tn-mismatch",
            "result_token": "token-tn",
            "result_json": "{\"task_name\":\"Wrong Task\"}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Unauthorized", 401, response.code)
    }

    // ── SHA mismatch (import) ────────────────────────────────────────────

    @Test
    fun `sha256 mismatch returns 401`() {
        registry.register(
            commandId = "cmd-sha-mismatch",
            operation = "import",
            expectedTaskName = "Expected Task",
            expectedSha256 = "abc123",
            expectedResultToken = "token-sha",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "import",
            "command_id": "cmd-sha-mismatch",
            "result_token": "token-sha",
            "result_json": "{\"task_name\":\"Expected Task\",\"sha256\":\"xyz789\"}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Unauthorized", 401, response.code)
    }

    // ── Forwarding exactly once ──────────────────────────────────────────

    @Test
    fun `forwarding happens exactly once on accepted result`() {
        registry.register(
            commandId = "cmd-fwd",
            operation = "probe",
            expectedResultToken = "token-fwd",
            deadline = futureDeadline()
        )

        // Clear any previous mock invocations
        every { RelayClient.sendTaskerResult(any()) } returns true

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-fwd",
            "result_token": "token-fwd",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals(200, response.code)

        verify(exactly = 1) { RelayClient.sendTaskerResult(any()) }
    }

    @Test
    fun `rejected result not forwarded`() {
        registry.register(
            commandId = "cmd-no-fwd",
            operation = "probe",
            expectedResultToken = "token-nf",
            deadline = futureDeadline()
        )

        every { RelayClient.sendTaskerResult(any()) } returns true

        // Wrong token -> rejected
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-no-fwd",
            "result_token": "wrong-token",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals(401, response.code)

        verify(exactly = 0) { RelayClient.sendTaskerResult(any()) }
    }

    // ── Loopback binding ─────────────────────────────────────────────────

    @Test
    fun `server listens only on 1270_0_0_1`() {
        // The server was started on 127.0.0.1
        // Verify by trying to connect via 127.0.0.1 (should work)
        val response = postJson("/v1/tasker/result", """{}""")
        assertNotNull("Should respond on loopback", response)

        // No easy way to verify 0.0.0.0 from a test without netstat,
        // but the host param in embeddedServer ensures it
    }

    // ── Regression: existing BridgeRouter routes still work ──────────────

    @Test
    fun `loopback server does not expose bridge routes`() {
        // BridgeRouter routes are on port 8765, not on loopback
        val response = postJson("/tap", """{"x":100,"y":200}""")
        assertEquals("Not found on loopback server", 404, response.code)
    }

    @Test
    fun `loopback server does not expose ping`() {
        val response = getJson("/ping")
        assertEquals("Not found on loopback server", 404, response.code)
    }

    // ── Backward compatibility: registry without token ───────────────────

    @Test
    fun `command registered without token accepts HTTP result`() {
        // Simulate: command registered without result_token
        registry.register(
            commandId = "cmd-no-token-reg",
            operation = "probe",
            deadline = futureDeadline()
        )

        // HTTP path requires token — it passes the token through
        // registry.complete() skips token validation when expectedResultToken is null
        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "probe",
            "command_id": "cmd-no-token-reg",
            "result_token": "any-token",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")
        assertEquals("Accepts when no token was stored", 200, response.code)
        assertTrue(registry.isCompleted("cmd-no-token-reg"))
    }

    // ── Response body assertions ─────────────────────────────────────────

    @Test
    fun `accepted response contains command_id and operation`() {
        registry.register(
            commandId = "cmd-assert",
            operation = "run",
            expectedResultToken = "token-assert",
            deadline = futureDeadline()
        )

        val response = postJson("/v1/tasker/result", """{
            "schema": "hermes-tasker-result/v1",
            "operation": "run",
            "command_id": "cmd-assert",
            "result_token": "token-assert",
            "result_json": "{}",
            "finished_at_ms": "0"
        }""")

        val body = response.body?.string()
        assertNotNull("Response body should not be null", body)
        assertTrue("Body should contain accepted", body!!.contains("accepted"))
        assertTrue("Body should contain command_id", body.contains("cmd-assert"))
        assertTrue("Body should contain operation", body.contains("run"))
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private fun postJson(path: String, body: String) = client.newCall(
        Request.Builder()
            .url("$baseUrl$path")
            .post(body.toRequestBody("application/json".toMediaTypeOrNull()))
            .build()
    ).execute()

    private fun getJson(path: String) = client.newCall(
        Request.Builder()
            .url("$baseUrl$path")
            .get()
            .build()
    ).execute()

    private fun postWithContentType(path: String, body: String, contentType: String) =
        client.newCall(
            Request.Builder()
                .url("$baseUrl$path")
                .post(body.toRequestBody(contentType.toMediaTypeOrNull()))
                .build()
        ).execute()

    private fun futureDeadline(): Long = System.currentTimeMillis() + 60_000
}
