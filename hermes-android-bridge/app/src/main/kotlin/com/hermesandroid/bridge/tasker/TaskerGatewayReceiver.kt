package com.hermesandroid.bridge.tasker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.gson.Gson

/**
 * Receives responses from Tasker Gateway.
 *
 * Validates HMAC before processing.
 * Only accepts responses directed to our package.
 * No file polling — responses arrive via broadcast.
 */
class TaskerGatewayReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "TaskerGatewayReceiver"

        /**
         * Registry reference — set by TaskerGatewayClient during initialization.
         * Responses complete the Deferred associated with the command_id.
         */
        var registry: PendingCommandRegistry? = null
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TaskerGatewayConfig.ACTION_RESPONSE) {
            Log.w(TAG, "Unexpected action: ${intent.action}")
            return
        }

        val responseJson = intent.getStringExtra(TaskerGatewayConfig.EXTRA_RESPONSE_JSON)
        if (responseJson == null) {
            Log.w(TAG, "No response JSON in intent")
            return
        }

        try {
            val gson = Gson()
            val response = gson.fromJson(responseJson, TaskerGatewayResponse::class.java)

            // Validate HMAC — reject if invalid
            val payloadBytes = TaskerGatewayResponse.payloadForSigning(response)
            if (!TaskerGatewayAuthenticator.verify(payloadBytes, response.auth.signature)) {
                Log.w(TAG, "HMAC verification failed for command ${response.command_id}")
                return
            }

            // Complete the pending command
            val pendingRegistry = registry
            if (pendingRegistry != null) {
                pendingRegistry.complete(
                    response.command_id,
                    response.request_hash,
                    response
                )
                Log.d(TAG, "Completed command ${response.command_id}")
            } else {
                Log.w(TAG, "No registry set — discarding response")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to process response: ${e.message}", e)
        }
    }
}
