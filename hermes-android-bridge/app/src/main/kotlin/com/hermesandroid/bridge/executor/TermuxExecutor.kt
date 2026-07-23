package com.hermesandroid.bridge.executor

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import android.util.Log
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Executes commands inside the host's **Termux** environment using Termux's
 * `RUN_COMMAND` intent API, capturing the result via a result PendingIntent.
 *
 * Requirements on the device:
 *  - Termux installed (package `com.termux`)
 *  - `allow-external-apps = true` in `~/.termux/termux.properties`
 *  - The bridge app holds `com.termux.permission.RUN_COMMAND` (declared in the manifest)
 *
 * Running through Termux gives access to its package ecosystem (pkg/apt: python, git,
 * ssh, nmap, ffmpeg, …) which the app's own sandbox does not have.
 *
 * ## Timeout handling
 *
 * Termux does not expose a direct `Process` handle, so timeout cancellation
 * is done via a PID-capture wrapper:
 *
 *  1. The user command is wrapped in a shell snippet that captures the PID.
 *  2. The PID is stored to a known file keyed by a unique execution token.
 *  3. If the wait times out, a **second** `RUN_COMMAND` intent is sent which
 *     kills the stored PID and removes the marker file.
 */
object TermuxExecutor {

    private const val TAG = "TermuxExecutor"

    const val TERMUX_PACKAGE = "com.termux"
    private const val RUN_COMMAND_SERVICE = "com.termux.app.RunCommandService"
    private const val ACTION_RUN_COMMAND = "com.termux.RUN_COMMAND"

    private const val EXTRA_PATH = "com.termux.RUN_COMMAND_PATH"
    private const val EXTRA_ARGUMENTS = "com.termux.RUN_COMMAND_ARGUMENTS"
    private const val EXTRA_WORKDIR = "com.termux.RUN_COMMAND_WORKDIR"
    private const val EXTRA_BACKGROUND = "com.termux.RUN_COMMAND_BACKGROUND"
    private const val EXTRA_SESSION_ACTION = "com.termux.RUN_COMMAND_SESSION_ACTION"
    private const val EXTRA_PENDING_INTENT = "com.termux.RUN_COMMAND_PENDING_INTENT"

    // Keys inside the result bundle Termux returns.
    private const val RESULT_BUNDLE = "result"
    private const val RESULT_STDOUT = "stdout"
    private const val RESULT_STDERR = "stderr"
    private const val RESULT_EXIT_CODE = "exitCode"
    private const val RESULT_ERR = "err"
    private const val RESULT_ERRMSG = "errmsg"

    private const val BASH = "/data/data/com.termux/files/usr/bin/bash"
    private const val HOME = "/data/data/com.termux/files/home"
    private const val PID_DIR = "/data/data/com.termux/files/home/.termux_pids"

    /** Grace period after timeout for kill to take effect (ms). */
    private const val KILL_GRACE_MS = 2_000L

    /** Delay before issuing the kill-on-timeout cleanup (ms). */
    private const val KILL_SETTLE_MS = 500L

    /** Maximum bytes of stdout/stderr retained from Termux. */
    private const val TERMUX_OUTPUT_LIMIT = 1_048_576

    private val requestCounter = AtomicInteger(1000)
    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    fun isInstalled(): Boolean = runCatching {
        appContext.packageManager.getPackageInfo(TERMUX_PACKAGE, 0)
        true
    }.getOrDefault(false)

    data class TermuxResult(
        val stdout: String,
        val stderr: String,
        val exitCode: Int,
        val timedOut: Boolean,
        val error: String? = null
    )

    fun exec(command: String, timeoutMs: Long, workdir: String = HOME): TermuxResult {
        if (!isInstalled()) {
            return TermuxResult("", "Termux is not installed (package com.termux).", -1, false,
                "termux_not_installed")
        }

        val requestCode = requestCounter.incrementAndGet()
        val token = "hmx_${requestCode}_${System.nanoTime()}"
        val pidFile = "$PID_DIR/pid_$token"
        val resultAction = "com.hermesandroid.bridge.TERMUX_RESULT.$requestCode"
        val latch = CountDownLatch(1)
        var result = TermuxResult("", "No response from Termux.", -1, true, "no_response")

        // Wrap the command so its PID is captured and its process group can be killed.
        // Structure:
        //   1. Ensure PID dir exists.
        //   2. Launch the command via setsid (creates a new process group).
        //   3. Store the PID (also PGID) so the whole group can be killed on timeout.
        //   4. When the command finishes, remove the PID file.
        val escapedCommand = command
            .replace("'", "'\\''")
        val wrappedCommand =
            "mkdir -p $PID_DIR; " +
            "setsid bash -c '" + escapedCommand + "' & " +
            "CMD_PID=\$!; " +
            "echo \$CMD_PID > $pidFile; " +
            "wait \$CMD_PID; " +
            "EXIT=\$?; " +
            "rm -f $pidFile; " +
            "exit \$EXIT"

        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                val bundle = intent?.getBundleExtra(RESULT_BUNDLE)
                result = parseResult(bundle)
                latch.countDown()
            }
        }

        val filter = IntentFilter(resultAction)
        registerReceiverCompat(receiver, filter)

        try {
            val resultIntent = Intent(resultAction).setPackage(appContext.packageName)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0)
            val pendingIntent = PendingIntent.getBroadcast(appContext, requestCode, resultIntent, flags)

            val intent = Intent(ACTION_RUN_COMMAND).apply {
                component = ComponentName(TERMUX_PACKAGE, RUN_COMMAND_SERVICE)
                putExtra(EXTRA_PATH, BASH)
                putExtra(EXTRA_ARGUMENTS, arrayOf("-c", wrappedCommand))
                putExtra(EXTRA_WORKDIR, workdir)
                putExtra(EXTRA_BACKGROUND, true)
                putExtra(EXTRA_SESSION_ACTION, "0")
                putExtra(EXTRA_PENDING_INTENT, pendingIntent)
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                appContext.startForegroundService(intent)
            } else {
                appContext.startService(intent)
            }

            val completed = latch.await(timeoutMs, TimeUnit.MILLISECONDS)
            if (!completed) {
                // Timed out — give Termux a brief moment to write the PID file,
                // then kill the process group and wait a bit more for late results.
                runCatching {
                    Thread.sleep(KILL_SETTLE_MS)
                    val killIntent = Intent(ACTION_RUN_COMMAND).apply {
                        component = ComponentName(TERMUX_PACKAGE, RUN_COMMAND_SERVICE)
                        putExtra(EXTRA_PATH, BASH)
                        putExtra(EXTRA_ARGUMENTS, arrayOf(
                            "-c",
                            "if [ -f $pidFile ]; then " +
                            "PID=\$(cat $pidFile); " +
                            "kill -TERM -- -\"\$PID\" 2>/dev/null; " +
                            "kill -TERM \"\$PID\" 2>/dev/null; " +
                            "rm -f $pidFile; fi"
                        ))
                        putExtra(EXTRA_WORKDIR, workdir)
                        putExtra(EXTRA_BACKGROUND, true)
                        putExtra(EXTRA_SESSION_ACTION, "0")
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        appContext.startForegroundService(killIntent)
                    } else {
                        appContext.startService(killIntent)
                    }
                    // Wait briefly for any late result after the kill
                    if (latch.await(KILL_GRACE_MS, TimeUnit.MILLISECONDS)) {
                        // The result was received after kill — use it
                        return@runCatching
                    }
                }
                result = TermuxResult("", "Termux command timed out after ${timeoutMs}ms.", -1, true, "timeout")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Termux exec failed", e)
            result = TermuxResult("", e.message ?: "unknown error", -1, false, "exception")
        } finally {
            runCatching { appContext.unregisterReceiver(receiver) }
        }

        return result
    }

    private fun parseResult(bundle: Bundle?): TermuxResult {
        if (bundle == null) {
            return TermuxResult("", "Empty result from Termux. Is 'allow-external-apps=true' set?", -1, false,
                "empty_result")
        }
        val rawStdout = bundle.getString(RESULT_STDOUT, "") ?: ""
        val rawStderr = bundle.getString(RESULT_STDERR, "") ?: ""
        val stdout = if (rawStdout.length <= TERMUX_OUTPUT_LIMIT) {
            rawStdout
        } else {
            rawStdout.take(TERMUX_OUTPUT_LIMIT) + "\n[truncated ${rawStdout.length - TERMUX_OUTPUT_LIMIT} bytes]"
        }
        val stderr = if (rawStderr.length <= TERMUX_OUTPUT_LIMIT) {
            rawStderr
        } else {
            rawStderr.take(TERMUX_OUTPUT_LIMIT) + "\n[truncated ${rawStderr.length - TERMUX_OUTPUT_LIMIT} bytes]"
        }
        val exitCode = bundle.getInt(RESULT_EXIT_CODE, -1)
        val err = bundle.getInt(RESULT_ERR, 0)
        val errmsg = bundle.getString(RESULT_ERRMSG, "") ?: ""
        val error = if (err != 0 && errmsg.isNotBlank()) errmsg else null
        val mergedStderr = if (error != null) (stderr + "\n" + errmsg).trim() else stderr
        return TermuxResult(stdout, mergedStderr, exitCode, false, error)
    }

    private fun registerReceiverCompat(receiver: BroadcastReceiver, filter: IntentFilter) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            appContext.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            appContext.registerReceiver(receiver, filter)
        }
    }
}
