package com.hermesandroid.bridge.executor

import android.content.Context
import com.hermesandroid.bridge.shizuku.ShizukuExecutor
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

    data class ShellResult(
        val stdout: String,
        val stderr: String,
        val exitCode: Int,
        val timedOut: Boolean = false,
        val backend: String = "app"
    )

    fun init(context: Context) {
        ShizukuExecutor.init(context)
        TermuxExecutor.init(context)
    }

    fun exec(command: String, timeoutMs: Long = 10_000, backend: String = "auto"): ShellResult {
        return when (resolveBackend(backend)) {
            "shizuku" -> runShizuku(command, timeoutMs)
            "termux" -> runTermux(command, timeoutMs)
            "root" -> runProcess(arrayOf("su", "-c", command), timeoutMs, "root")
            else -> runProcess(arrayOf("sh", "-c", command), timeoutMs, "app")
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

    private fun resolveBackend(requested: String): String = when (requested.lowercase()) {
        "auto", "" -> if (ShizukuExecutor.isAvailable()) "shizuku" else "app"
        else -> requested.lowercase()
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
            val process = ProcessBuilder(*cmd)
                .redirectErrorStream(false)
                .start()

            val pool = Executors.newFixedThreadPool(2)
            val outF = pool.submit<String> { process.inputStream.bufferedReader().readText() }
            val errF = pool.submit<String> { process.errorStream.bufferedReader().readText() }

            val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
            if (!finished) {
                process.destroyForcibly()
                val out = runCatching { outF.get(500, TimeUnit.MILLISECONDS) }.getOrDefault("")
                val err = runCatching { errF.get(500, TimeUnit.MILLISECONDS) }.getOrDefault("")
                pool.shutdownNow()
                return ShellResult(out, err, -1, timedOut = true, backend = backend)
            }

            val out = runCatching { outF.get(2, TimeUnit.SECONDS) }.getOrDefault("")
            val err = runCatching { errF.get(2, TimeUnit.SECONDS) }.getOrDefault("")
            pool.shutdownNow()
            ShellResult(out, err, process.exitValue(), backend = backend)
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
