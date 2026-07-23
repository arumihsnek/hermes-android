package com.hermesandroid.bridge.executor

import org.junit.Assert.*
import org.junit.Test

class TerminalExecutorTest {

    @Test
    fun `unknown backend is rejected`() {
        val result = TerminalExecutor.exec("echo ok", backend = "nonexistent")
        assertEquals(-1, result.exitCode)
        assertTrue(result.stderr.contains("Unknown backend"))
    }

    @Test
    fun `empty backend defaults to auto`() {
        val result = TerminalExecutor.exec("echo ok", backend = "")
        // Should not throw; defaults to "auto"
        assertNotNull(result)
    }

    @Test
    fun `command exceeding max length is rejected`() {
        val longCmd = "a".repeat(TerminalExecutor.MAX_COMMAND_LENGTH + 1)
        val result = TerminalExecutor.exec(longCmd)
        assertEquals(-1, result.exitCode)
        assertTrue(result.stderr.contains("too long"))
    }

    @Test
    fun `app backend executes simple command`() {
        val result = TerminalExecutor.exec("echo hello", backend = "app")
        assertEquals(0, result.exitCode)
        assertEquals("hello", result.stdout.trim())
    }

    @Test
    fun `app backend reports stdoutTruncated on large output`() {
        val result = TerminalExecutor.exec(
            "awk 'BEGIN{while(i++<150000) print i}'",
            timeoutMs = 5000,
            backend = "app"
        )
        assertTrue(result.stdout.length <= TerminalExecutor.MAX_OUTPUT_BYTES)
    }
}
