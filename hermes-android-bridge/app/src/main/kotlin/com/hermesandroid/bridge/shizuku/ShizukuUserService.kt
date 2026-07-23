package com.hermesandroid.bridge.shizuku

import android.util.Log
import com.hermesandroid.bridge.util.BoundedReader
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Runs inside the process Shizuku spawns with `shell` (UID 2000 / ADB) privileges.
 * Commands executed here inherit those privileges — equivalent to `adb shell`.
 *
 * Must expose a no-arg constructor for Shizuku's UserService loader.
 */
class ShizukuUserService : IUserService.Stub {

    companion object {
        private const val TAG = "ShizukuUserService"
        private const val MAX_OUTPUT_BYTES = 1_048_576
    }

    @Suppress("unused")
    constructor()

    override fun destroy() {
        Log.i(TAG, "UserService destroy()")
        System.exit(0)
    }

    override fun exec(command: String, timeoutMs: Long): String {
        return try {
            val process = ProcessBuilder("sh", "-c", command)
                .redirectErrorStream(false)
                .start()

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
                    // Attempt to kill child processes via PID.
                    // ProcessHandle isn't reliably available on Android, so use reflection.
                    runCatching {
                        val pidMethod = process.javaClass.getMethod("pid")
                        val pid = pidMethod.invoke(process) as Int
                        if (pid > 0) {
                            Runtime.getRuntime().exec(arrayOf("kill", "-TERM", "--", "-$pid"))
                                .waitFor(2, TimeUnit.SECONDS)
                        }
                    }
                    process.destroyForcibly()
                    process.waitFor(1, TimeUnit.SECONDS)
                }

                val outResult = runCatching { outF.get(2, TimeUnit.SECONDS) }
                    .getOrDefault(BoundedReader.Result("", false))
                val errResult = runCatching { errF.get(2, TimeUnit.SECONDS) }
                    .getOrDefault(BoundedReader.Result("", false))

                result(
                    stdout = outResult.text,
                    stderr = errResult.text,
                    exitCode = if (finished) process.exitValue() else -1,
                    timedOut = !finished,
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
            result("", e.message ?: "unknown error", -1, false)
        }
    }

    private fun result(
        stdout: String,
        stderr: String,
        exitCode: Int,
        timedOut: Boolean,
        stdoutTruncated: Boolean = false,
        stderrTruncated: Boolean = false
    ): String = JSONObject()
        .put("stdout", stdout)
        .put("stderr", stderr)
        .put("exitCode", exitCode)
        .put("timedOut", timedOut)
        .put("stdoutTruncated", stdoutTruncated)
        .put("stderrTruncated", stderrTruncated)
        .toString()
}
