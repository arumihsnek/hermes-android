package com.hermesandroid.bridge.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.util.Log
import com.hermesandroid.bridge.media.ScreenRecorder

/**
 * Handles intent-based commands for the Hermes Bridge relay.
 *
 * Supported actions (defined in AndroidManifest.xml):
 * - START:      Start relay connection to server
 * - STOP:       Stop relay and release resources
 * - STATUS:     Return current state via ordered broadcast
 * - ENABLE_A11Y: Open accessibility settings
 * - ENABLE_SCREEN_RECORD: Request MediaProjection permission
 */
class RelayIntentReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "RelayIntentReceiver"

        const val ACTION_START = "com.hermesandroid.bridge.START"
        const val ACTION_STOP = "com.hermesandroid.bridge.STOP"
        const val ACTION_STATUS = "com.hermesandroid.bridge.STATUS"
        const val ACTION_ENABLE_A11Y = "com.hermesandroid.bridge.ENABLE_A11Y"
        const val ACTION_ENABLE_SCREEN_RECORD = "com.hermesandroid.bridge.ENABLE_SCREEN_RECORD"
        const val ACTION_START_SCREEN_RECORD = "com.hermesandroid.bridge.START_SCREEN_RECORD"
        const val ACTION_STOP_SCREEN_RECORD = "com.hermesandroid.bridge.STOP_SCREEN_RECORD"

        const val EXTRA_SERVER = "server"
        const val EXTRA_TOKEN = "token"
        const val ACTION_STATUS_RESULT = "com.hermesandroid.bridge.STATUS_RESULT"
        const val EXTRA_RELAY = "relay"
        const val EXTRA_A11Y = "a11y"
        const val EXTRA_SCREEN_RECORD = "screenRecord"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        try {
            Log.e(TAG, "onReceive: $action")  // Using ERROR level for visibility
            when (action) {
                ACTION_START -> handleStart(context, intent)
                ACTION_STOP -> handleStop(context)
                ACTION_STATUS -> handleStatus(context)
                ACTION_ENABLE_A11Y -> handleEnableA11y(context)
                ACTION_ENABLE_SCREEN_RECORD -> handleEnableScreenRecord(context)
                ACTION_START_SCREEN_RECORD -> handleStartScreenRecord()
                ACTION_STOP_SCREEN_RECORD -> handleStopScreenRecord()
                else -> Log.w(TAG, "Unknown action: $action")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling $action: ${e.message}", e)
        }
    }

    private fun handleStart(context: Context, intent: Intent) {
        val server = intent.getStringExtra(EXTRA_SERVER) ?: "82.70.86.174:18766"
        val token = intent.getStringExtra(EXTRA_TOKEN)
            ?: com.hermesandroid.bridge.auth.PairingManager.getCode()
        Log.d(TAG, "Starting relay, server=$server")
        RelayService.start(context, server, token)
    }

    private fun handleStop(context: Context) {
        Log.d(TAG, "Stopping relay")
        RelayService.stop(context)
    }

    private fun handleStatus(context: Context) {
        val service = RelayService.instance
        val status = service?.getStatus() ?: RelayService.RelayStatus()
        val resultIntent = Intent(ACTION_STATUS_RESULT).apply {
            putExtra(EXTRA_RELAY, status.relayConnected)
            putExtra(EXTRA_A11Y, status.accessibilityActive)
            putExtra(EXTRA_SCREEN_RECORD, status.screenRecordGranted)
        }
        context.sendBroadcast(resultIntent)
    }

    private fun handleEnableA11y(context: Context) {
        val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    private fun handleEnableScreenRecord(context: Context) {
        // ScreenRecordHelper.requestPermission(context) — TBD
        Log.d(TAG, "Screen record permission request not yet implemented via intent")
    }

    private fun handleStartScreenRecord() {
        val result = ScreenRecorder.startRecording()
        Log.d(TAG, "Screen record start: $result")
    }

    private fun handleStopScreenRecord() {
        val result = ScreenRecorder.stopRecording()
        Log.d(TAG, "Screen record stop: success=${result["success"]}")
    }
}
