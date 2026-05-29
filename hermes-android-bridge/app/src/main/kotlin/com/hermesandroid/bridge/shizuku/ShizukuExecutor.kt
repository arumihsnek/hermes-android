package com.hermesandroid.bridge.shizuku

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import android.util.Log
import com.hermesandroid.bridge.BuildConfig
import rikka.shizuku.Shizuku
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Bridges shell execution to a Shizuku-managed process running with `shell` (UID 2000)
 * privileges — the same level `adb shell` has, without root.
 *
 * Lifecycle: the user service is bound lazily on first use and kept alive (daemon) for reuse.
 */
object ShizukuExecutor {

    private const val TAG = "ShizukuExecutor"
    const val PERMISSION_REQUEST_CODE = 4242

    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"
    private const val SUI_PACKAGE = "com.android.shell" // Sui rides inside shell; pingBinder is the real test

    @Volatile private var userService: IUserService? = null
    @Volatile private var binding = false
    private var bindLatch: CountDownLatch? = null

    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            userService = if (binder != null && binder.pingBinder()) {
                IUserService.Stub.asInterface(binder)
            } else null
            binding = false
            bindLatch?.countDown()
            Log.i(TAG, "UserService connected: ${userService != null}")
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            userService = null
            binding = false
            Log.i(TAG, "UserService disconnected")
        }
    }

    private val userServiceArgs by lazy {
        Shizuku.UserServiceArgs(ComponentName(appContext, ShizukuUserService::class.java))
            .daemon(true)
            .processNameSuffix("shell")
            .debuggable(BuildConfig.DEBUG)
            .version(BuildConfig.VERSION_CODE)
    }

    /** Shizuku/Sui service is running and reachable. */
    fun isRunning(): Boolean = runCatching { Shizuku.pingBinder() }.getOrDefault(false)

    /** Shizuku app is installed (may or may not be running). */
    fun isInstalled(): Boolean = runCatching {
        appContext.packageManager.getPackageInfo(SHIZUKU_PACKAGE, 0)
        true
    }.getOrDefault(false) || isRunning()

    fun hasPermission(): Boolean {
        if (!isRunning()) return false
        // checkSelfPermission throws on pre-v11 Shizuku; runCatching makes that a safe "false".
        return runCatching {
            Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
        }.getOrDefault(false)
    }

    fun shouldShowRationale(): Boolean = runCatching {
        Shizuku.shouldShowRequestPermissionRationale()
    }.getOrDefault(false)

    /** Trigger Shizuku's permission dialog. Result arrives via the listener registered in [init]/Application. */
    fun requestPermission() {
        if (isRunning()) {
            runCatching { Shizuku.requestPermission(PERMISSION_REQUEST_CODE) }
        }
    }

    fun isAvailable(): Boolean = isRunning() && hasPermission()

    /**
     * Run `sh -c command` with shell privileges. Returns the raw JSON produced by
     * [ShizukuUserService.exec], or a JSON error object if Shizuku is unavailable.
     */
    fun exec(command: String, timeoutMs: Long): String {
        if (!isRunning()) {
            return errorJson("Shizuku service is not running. Install/start Shizuku and pair it via ADB.")
        }
        if (!hasPermission()) {
            requestPermission()
            return errorJson("Shizuku permission not granted. Approve the Hermes Bridge request in Shizuku, then retry.")
        }

        val svc = ensureBound()
            ?: return errorJson("Could not bind the Shizuku user service (timed out).")

        return try {
            svc.exec(command, timeoutMs)
        } catch (e: Exception) {
            // Binder may have died — drop the cache so the next call rebinds.
            userService = null
            errorJson("Shizuku exec failed: ${e.message}")
        }
    }

    @Synchronized
    private fun ensureBound(): IUserService? {
        userService?.let { return it }
        if (binding) {
            bindLatch?.await(8, TimeUnit.SECONDS)
            return userService
        }
        binding = true
        val latch = CountDownLatch(1)
        bindLatch = latch
        try {
            Shizuku.bindUserService(userServiceArgs, connection)
        } catch (e: Exception) {
            binding = false
            Log.e(TAG, "bindUserService failed", e)
            return null
        }
        latch.await(8, TimeUnit.SECONDS)
        return userService
    }

    private fun errorJson(message: String): String =
        org.json.JSONObject()
            .put("stdout", "")
            .put("stderr", message)
            .put("exitCode", -1)
            .put("timedOut", false)
            .put("error", message)
            .toString()
}
