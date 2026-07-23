package com.hermesandroid.bridge.executor

import android.content.Context
import com.hermesandroid.bridge.shizuku.ShizukuExecutor
import com.hermesandroid.bridge.util.BoundedReader
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Dispatches shell command execution to one of several backends:
 *
 *  - `app`     — runs as the bridge app's own UID (unprivileged sandbox). Always available.
 *  - `root`    — runs via `su -c` (requires a rooted device).
 *  - `shizuku` — runs with `shell` (UID 2000 / ADB) privileges via Shizuku, no root needed.
 *  - `termux`  — runs inside the host's Termux environment (pkg/apt ecosystem).
 *  - `auto`    — picks the best privileged backend available: shizuku → app.
 */
object TerminalExecutor {

    /** Maximum bytes retained per stdout/stderr stream (1 MiB). */
    const val MAX_OUTPUT_BYTES: Int = 1_048_576

    /** Maximum command length (4 KiB). */
    const val MAX_COMMAND_LENGTH: Int = 4096

    data class ShellResult(
        val stdout: String,
        val stderr: String,
        val exitCode: Int,
        val timedOut: Boolean = false,
        val backend: String = "app",
        val stdoutTruncated: Boolean = false,
        val stderrTruncated: Boolean = false
    )

    fun init(context: Context) {
        ShizukuExecutor.init(context)
        TermuxExecutor.init(context)
    }

    fun exec(command: String, timeoutMs: Long = 10_000, backend: String = "auto"): ShellResult {
        if (command.length > MAX_COMMAND_LENGTH) {
            return ShellResult(
                "", "Command too long: ${command.length} chars (max $MAX_COMMAND_LENGTH)",
                -1, backend = resolveBackend(backend)
            )
        }
        return try {
            when (resolveBackend(backend)) {
                "shizuku" -> runShizuku(command, timeoutMs)
                "termux" -> runTermux(command, timeoutMs)
                "root" -> runProcess(arrayOf("su", "-c", command), timeoutMs, "root")
                else -> runProcess(arrayOf("sh", "-c", command), timeoutMs, "app")
            }
        } catch (e: Exception) {
            ShellResult("", "${e::class.simpleName}: ${e.message ?: "Unknown"}", -1, backend = resolveBackend(backend))
        }
    }

    /** Report which backends are usable right now. */
    fun status(): Map<String, Any> = mapOf(
        "app" to mapOf("available" to true),
        "root" to mapOf("available" to isRootAvailable()),
        "shizuku" to mapOf(
            "installed" to ShizukuExecutor.isInstalled(),
            "running" to ShizukuExecutor.isRunning(),
            "permission" to ShizukuExecutor.hasPermission(),
            "available" to ShizukuExecutor.isAvailable()
        ),
        "termux" to mapOf(
            "installed" to TermuxExecutor.isInstalled(),
            "available" to TermuxExecutor.isInstalled()
        ),
        "default" to resolveBackend("auto")
    )

    private fun resolveBackend(requested: String): String {
        val known = setOf("auto", "app", "shizuku", "termux", "root")
        val lower = requested.lowercase()
        if (lower == "" || lower == "auto") {
            return if (ShizukuExecutor.isAvailable()) "shizuku" else "app"
        }
        require(lower in known) { "Unknown backend: $requested. Known: ${known.joinToString()}" }
        return lower
    }

    private fun runShizuku(command: String, timeoutMs: Long): ShellResult {
        val json = ShizukuExecutor.exec(command, timeoutMs)
        return try {
            val o = JSONObject(json)
            ShellResult(
                stdout = o.optString("stdout", ""),
                stderr = o.optString("stderr", ""),
                exitCode = o.optInt("exitCode", -1),
                timedOut = o.optBoolean("timedOut", false),
                backend = "shizuku"
            )
        } catch (e: Exception) {
            ShellResult("", "Failed to parse Shizuku result: ${e.message}", -1, backend = "shizuku")
        }
    }

    private fun runTermux(command: String, timeoutMs: Long): ShellResult {
        val r = TermuxExecutor.exec(command, timeoutMs)
        return ShellResult(r.stdout, r.stderr, r.exitCode, r.timedOut, "termux")
    }

    private fun runProcess(cmd: Array<String>, timeoutMs: Long, backend: String): ShellResult {
        return try {
            val process = try {
                ProcessBuilder(*cmd)
                    .redirectErrorStream(false)
                    .start()
            } catch (e: Exception) {
                return ShellResult("", "Process creation failed: ${e.message}", -1, backend = backend)
            }

            val pool = Executors.newFixedThreadPool(2)
            try {
                val outF = pool.submit<BoundedReader.Result> {
                    BoundedReader.read(process.inputStream, MAX_OUTPUT_BYTES)
                }
                val errF = pool.submit<BoundedReader.Result> {
                    BoundedReader.read(process.errorStream, MAX_OUTPUT_BYTES)
                }

                val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
                if (!finished) {
                    process.destroyForcibly()
                    process.waitFor(1, TimeUnit.SECONDS)
                }

                val outResult = runCatching { outF.get(2, TimeUnit.SECONDS) }
                    .getOrDefault(BoundedReader.Result("", false))
                val errResult = runCatching { errF.get(2, TimeUnit.SECONDS) }
                    .getOrDefault(BoundedReader.Result("", false))

                ShellResult(
                    stdout = outResult.text,
                    stderr = errResult.text,
                    exitCode = if (finished) process.exitValue() else -1,
                    timedOut = !finished,
                    backend = backend,
                    stdoutTruncated = outResult.truncated,
                    stderrTruncated = errResult.truncated
                )
            } finally {
                pool.shutdownNow()
                if (process.isAlive()) {
                    process.destroyForcibly()
                    process.waitFor(1, TimeUnit.SECONDS)
                }
            }
        } catch (e: Exception) {
            ShellResult("", e.message ?: "Unknown error", -1, backend = backend)
        }
    }

    private fun isRootAvailable(): Boolean = try {
        val p = ProcessBuilder("sh", "-c", "command -v su").start()
        val out = p.inputStream.bufferedReader().readText().trim()
        p.waitFor(2, TimeUnit.SECONDS)
        out.isNotEmpty()
    } catch (e: Exception) {
        false
    }
}
