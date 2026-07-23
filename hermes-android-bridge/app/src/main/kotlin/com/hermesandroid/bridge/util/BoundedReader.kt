package com.hermesandroid.bridge.util

import java.io.InputStream

/**
 * Bounded stream reader that reads up to [maxBytes] from an [InputStream],
 * discarding any excess to prevent backpressure/blocking, and signals
 * whether truncation occurred.
 *
 * Designed for concurrent execution (one instance per stream) to avoid
 * deadlock when stdout and stderr are both consumed from the same process.
 */
object BoundedReader {

    data class Result(
        val text: String,
        val truncated: Boolean
    )

    /**
     * Read from [stream] until EOF, keeping the first [maxBytes] bytes.
     * Excess data is drained (read and discarded) so the producing process
     * does not block on a full pipe buffer.
     *
     * Multibyte UTF-8 characters that would be split at [maxBytes] are
     * discarded entirely to avoid replacement characters in the output.
     *
     * @param stream the input stream to read (closed by caller).
     * @param maxBytes maximum bytes to retain (default 1 MiB). Must be >= 0.
     * @return [Result] containing the bounded text and a truncation flag.
     * @throws IllegalArgumentException if maxBytes < 0.
     */
    fun read(stream: InputStream, maxBytes: Int = 1_048_576): Result {
        require(maxBytes >= 0) { "maxBytes must be >= 0, got $maxBytes" }
        if (maxBytes == 0) {
            // Retain nothing; drain and discard everything.
            var hadData = false
            while (stream.read(ByteArray(4096)) != -1) { hadData = true }
            return Result("", hadData)
        }

        val buffer = ByteArray(maxBytes)
        var totalRead = 0
        var truncated = false

        while (true) {
            val remaining = buffer.size - totalRead
            val bytesRead = if (remaining > 0) {
                val n = stream.read(buffer, totalRead, remaining)
                if (n == -1) break
                totalRead += n
                n
            } else {
                // We've already filled the buffer; drain the rest.
                val n = stream.read(ByteArray(4096))
                if (n == -1) break
                truncated = true
                n
            }
        }

        // Trim to last complete UTF-8 character boundary.
        val utfLen = lastCompleteUtf8Length(buffer, totalRead)
        val text = String(buffer, 0, utfLen, Charsets.UTF_8)
        return Result(text, truncated)
    }

    /**
     * Returns the longest prefix length of [buffer] up to [byteCount]
     * that ends on a complete UTF-8 character boundary.
     *
     * Scans backwards from the end to find the start byte of any multi-byte
     * character that may have been split, then verifies it has its full
     * complement of continuation bytes. If incomplete, the partial character
     * (start byte + any trailing continuation bytes) is discarded.
     */
    private fun lastCompleteUtf8Length(buffer: ByteArray, byteCount: Int): Int {
        val limit = byteCount.coerceAtMost(buffer.size)
        var i = limit - 1
        while (i >= 0) {
            val b = buffer[i].toInt() and 0xFF
            when {
                // ASCII byte (0xxxxxxx) — always a complete character.
                b and 0x80 == 0 -> return i + 1

                // Multi-byte start byte (11xxxxxx).
                b and 0xC0 == 0xC0 -> {
                    val expectedBytes = when {
                        b and 0xF0 == 0xF0 -> 4 // 11110xxx
                        b and 0xE0 == 0xE0 -> 3 // 1110xxxx
                        else -> 2                // 110xxxxx
                    }
                    val charEnd = i + expectedBytes
                    if (charEnd <= limit) {
                        // Verify that expected continuation bytes are valid (10xxxxxx).
                        for (j in (i + 1) until charEnd) {
                            val cb = buffer[j].toInt() and 0xFF
                            if (cb and 0xC0 != 0x80) {
                                // Invalid continuation byte — treat as incomplete character.
                                return i
                            }
                        }
                        // All continuation bytes present and valid.
                        return charEnd
                    }
                    // Incomplete multi-byte character at position [i..limit).
                    return i
                }

                // Continuation byte (10xxxxxx) — keep scanning backwards.
                else -> i--
            }
        }
        return limit
    }
}
