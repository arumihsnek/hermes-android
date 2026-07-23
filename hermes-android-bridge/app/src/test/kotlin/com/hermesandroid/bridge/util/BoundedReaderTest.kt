package com.hermesandroid.bridge.util

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream

class BoundedReaderTest {

    @Test
    fun `reads text under limit`() {
        val input = "Hello, World!"
        val result = BoundedReader.read(input.byteInputStream(), maxBytes = 1024)
        assertEquals("Hello, World!", result.text)
        assertFalse(result.truncated)
    }

    @Test
    fun `truncates text exceeding limit`() {
        val input = "A".repeat(10_000)
        val result = BoundedReader.read(input.byteInputStream(), maxBytes = 100)
        assertEquals(100, result.text.length)
        assertTrue(result.truncated)
    }

    @Test
    fun `preserves multibyte UTF-8 at boundary`() {
        // 'é' is 2 bytes (0xC3 0xA9). If maxBytes=1, the byte is cut.
        val input = "é"
        val result = BoundedReader.read(input.byteInputStream(Charsets.UTF_8), maxBytes = 1)
        // UTF-8 start byte without continuation is discarded
        assertEquals("", result.text)
        assertTrue(result.truncated)
    }

    @Test
    fun `preserves multibyte UTF-8 within limit`() {
        val input = "héllo"
        val result = BoundedReader.read(input.byteInputStream(Charsets.UTF_8), maxBytes = 5)
        // 'h' (1 byte) + 'é' (2 bytes), but only 5 bytes available, so 'é' may be split
        assertFalse("Unexpected: $result.text", result.text.contains('\uFFFD'))
    }

    @Test
    fun `empty stream returns empty text`() {
        val input = ""
        val result = BoundedReader.read(input.byteInputStream(), maxBytes = 1024)
        assertEquals("", result.text)
        assertFalse(result.truncated)
    }

    @Test
    fun `zero maxBytes drains and truncates`() {
        val input = "some data"
        val result = BoundedReader.read(input.byteInputStream(), maxBytes = 0)
        assertEquals("", result.text)
        assertTrue(result.truncated)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `negative maxBytes throws`() {
        BoundedReader.read(ByteArrayInputStream(byteArrayOf()), maxBytes = -1)
    }

    @Test
    fun `large output does not cause OOM`() {
        // Simulate 2 MB of data
        val data = ByteArray(2_000_000) { 'A'.code.toByte() }
        val result = BoundedReader.read(ByteArrayInputStream(data), maxBytes = 1_048_576)
        assertTrue(result.text.length <= 1_048_576)
        assertTrue(result.truncated)
    }
}
