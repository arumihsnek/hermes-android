package com.hermesandroid.bridge.shizuku

import android.util.Log
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
            val outF = pool.submit<String> { process.inputStream.bufferedReader().readText() }
            val errF = pool.submit<String> { process.errorStream.bufferedReader().readText() }

            val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
            if (!finished) {
                process.destroyForcibly()
                val out = runCatching { outF.get(500, TimeUnit.MILLISECONDS) }.getOrDefault("")
                val err = runCatching { errF.get(500, TimeUnit.MILLISECONDS) }.getOrDefault("")
                pool.shutdownNow()
                return result(out, err + "\n[shizuku] timed out after ${timeoutMs}ms", -1, true)
            }

            val out = runCatching { outF.get(2, TimeUnit.SECONDS) }.getOrDefault("")
            val err = runCatching { errF.get(2, TimeUnit.SECONDS) }.getOrDefault("")
            pool.shutdownNow()
            result(out, err, process.exitValue(), false)
        } catch (e: Exception) {
            result("", e.message ?: "unknown error", -1, false)
        }
    }

    private fun result(stdout: String, stderr: String, exitCode: Int, timedOut: Boolean): String =
        JSONObject()
            .put("stdout", stdout)
            .put("stderr", stderr)
            .put("exitCode", exitCode)
            .put("timedOut", timedOut)
            .toString()

    companion object {
        private const val TAG = "ShizukuUserService"
    }
}
