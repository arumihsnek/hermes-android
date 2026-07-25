package com.hermesandroid.bridge.tasker

import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Native broadcast transport to Tasker.
 *
 * NO /shell, NO am command, NO file I/O, NO ADB, NO Shizuku.
 * Sends HMAC-signed request as JSON extra via Android broadcast.
 *
 * The intent is directed at Tasker's package explicitly.
 * Proves that setPackage() triggers Tasker's profile.
 */
object TaskerGatewayTransport {

    private const val TAG = "TaskerGatewayTransport"

    /**
     * Send request to Tasker via native broadcast.
     * Returns true if broadcast was sent successfully.
     */
    fun send(context: Context, request: TaskerGatewayRequest): Boolean {
        return try {
            val gson = com.google.gson.Gson()
            val requestJson = gson.toJson(request)

            val intent = Intent(TaskerGatewayConfig.ACTION_REQUEST).apply {
                setPackage(TaskerGatewayConfig.taskerPackage)
                putExtra(TaskerGatewayConfig.EXTRA_REQUEST_JSON, requestJson)
                addFlags(Intent.FLAG_RECEIVER_EXPORTED)
            }

            context.sendBroadcast(intent)
            Log.d(TAG, "Sent request ${request.command_id} for adapter ${request.adapter_id}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send request: ${e.message}", e)
            false
        }
    }

    /**
     * Check if Tasker is installed on the device.
     */
    fun isTaskerInstalled(context: Context): Boolean {
        return try {
            context.packageManager.getPackageInfo(TaskerGatewayConfig.taskerPackage, 0)
            true
        } catch (_: android.content.pm.PackageManager.NameNotFoundException) {
            false
        }
    }
}
