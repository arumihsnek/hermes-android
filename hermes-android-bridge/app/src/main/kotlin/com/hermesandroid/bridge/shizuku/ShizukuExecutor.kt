package com.hermesandroid.bridge.shizuku

import android.content.ComponentName
import android.content.Context
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import android.os.RemoteException
import android.util.Log
import com.hermesandroid.bridge.BuildConfig
import rikka.shizuku.Shizuku
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Bridges shell execution to a Shizuku-managed process running with `shell` (UID 2000)
 * privileges — the same level `adb shell` has, without root.
 *
 * Lifecycle: the user service is bound lazily on first use and kept alive (daemon) for reuse.
 * If the binder dies, a death recipient clears the cached service, and the next call
 * triggers a fresh bind.
 */
object ShizukuExecutor {

    private const val TAG = "ShizukuExecutor"
    const val PERMISSION_REQUEST_CODE = 4242

    private const val SHIZUKU_PACKAGE = "moe.shizuku.privileged.api"

    private enum class BindingState { UNBOUND, BINDING, BOUND }

    @Volatile private var userService: IUserService? = null
    @Volatile private var bindingState = BindingState.UNBOUND
    @Volatile private var shuttingDown = false

    private var bindLatch: CountDownLatch? = null

    private lateinit var appContext: Context

    fun init(context: Context) {
        appContext = context.applicationContext
        // Register death recipient to detect service crashes.
        Shizuku.addBinderDeadListener {
            Log.w(TAG, "Shizuku binder died — resetting service")
            userService = null
            bindingState = BindingState.UNBOUND
        }
    }

    fun shutdown() {
        shuttingDown = true
        userService?.let {
            try { it.destroy() } catch (_: RemoteException) { }
        }
        userService = null
        bindingState = BindingState.UNBOUND
    }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
            if (binder != null && binder.pingBinder()) {
                userService = IUserService.Stub.asInterface(binder)
                bindingState = BindingState.BOUND
            } else {
                userService = null
                bindingState = BindingState.UNBOUND
            }
            bindLatch?.countDown()
            Log.i(TAG, "UserService connected: ${userService != null}")
        }

        override fun onServiceDisconnected(name: ComponentName?) {
            userService = null
            bindingState = BindingState.UNBOUND
            Log.i(TAG, "UserService disconnected")
        }

        override fun onBindingDied(name: ComponentName?) {
            userService = null
            bindingState = BindingState.UNBOUND
            Log.w(TAG, "UserService binding died")
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
        return runCatching {
            Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
        }.getOrDefault(false)
    }

    fun shouldShowRationale(): Boolean = runCatching {
        Shizuku.shouldShowRequestPermissionRationale()
    }.getOrDefault(false)

    /** Trigger Shizuku's permission dialog. */
    fun requestPermission() {
        if (isRunning()) {
            runCatching { Shizuku.requestPermission(PERMISSION_REQUEST_CODE) }
        }
    }

    fun isAvailable(): Boolean = isRunning() && hasPermission()

    /**
     * Run `sh -c command` with shell privileges. Returns the raw JSON produced by
     * [ShizukuUserService.exec], or a JSON error object if Shizuku is unavailable.
     *
     * Thread-safe: concurrent calls are serialized on binding state and each
     * uses its own AIDL transaction.
     */
    fun exec(command: String, timeoutMs: Long): String {
        if (shuttingDown) {
            return errorJson("ShizukuExecutor is shut down.")
        }
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
        } catch (e: RemoteException) {
            // Binder died — clear cache for next call.
            userService = null
            bindingState = BindingState.UNBOUND
            errorJson("Shizuku exec failed (binder died): ${e.message}")
        } catch (e: Exception) {
            userService = null
            bindingState = BindingState.UNBOUND
            errorJson("Shizuku exec failed: ${e.message}")
        }
    }

    /**
     * Ensures the Shizuku user service is bound.
     * Serializes concurrent bind attempts: the first caller binds,
     * subsequent callers wait for the latch.
     */
    @Synchronized
    private fun ensureBound(): IUserService? {
        // Fast path — already bound.
        userService?.let {
            if (runCatching { it.asBinder().pingBinder() }.getOrDefault(false)) {
                return it
            }
            // Stale reference — clear and rebind.
            userService = null
            bindingState = BindingState.UNBOUND
        }

        if (bindingState == BindingState.BINDING && bindLatch != null) {
            // Another thread is binding — wait for it.
            bindLatch!!.await(8, TimeUnit.SECONDS)
            return userService
        }

        bindingState = BindingState.BINDING
        val latch = CountDownLatch(1)
        bindLatch = latch
        try {
            Shizuku.bindUserService(userServiceArgs, connection)
        } catch (e: Exception) {
            bindingState = BindingState.UNBOUND
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
