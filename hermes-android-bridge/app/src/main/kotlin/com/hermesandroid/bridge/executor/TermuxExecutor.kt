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
        val resultAction = "com.hermesandroid.bridge.TERMUX_RESULT.$requestCode"
        val latch = CountDownLatch(1)
        var result = TermuxResult("", "No response from Termux.", -1, true, "no_response")

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
                putExtra(EXTRA_ARGUMENTS, arrayOf("-c", command))
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

            val completed = latch.await(timeoutMs + 2000, TimeUnit.MILLISECONDS)
            if (!completed) {
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
        val stdout = bundle.getString(RESULT_STDOUT, "") ?: ""
        val stderr = bundle.getString(RESULT_STDERR, "") ?: ""
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
