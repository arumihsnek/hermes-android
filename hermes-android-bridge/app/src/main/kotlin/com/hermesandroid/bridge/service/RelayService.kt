package com.hermesandroid.bridge.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.hermesandroid.bridge.client.RelayClient

/**
 * Foreground service managing the relay connection lifecycle.
 *
 * Started via [RelayIntentReceiver.ACTION_START] broadcast.
 * Wraps [RelayClient.connect] / [RelayClient.disconnect].
 * Runs as foreground service (persistent notification) so the system
 * doesn't kill it. Notification updates on connect/disconnect events.
 */
class RelayService : Service() {

    data class RelayStatus(
        val relayConnected: Boolean = false,
        val accessibilityActive: Boolean = false,
        val screenRecordGranted: Boolean = false
    )

    companion object {
        private const val TAG = "RelayService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "bridge-relay"

        @Volatile
        var instance: RelayService? = null
            private set

        fun start(context: Context, server: String, token: String = "") {
            val intent = Intent(context, RelayService::class.java).apply {
                putExtra("server", server)
                putExtra("token", token)
            }
            context.startService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, RelayService::class.java))
        }
    }

    private var serverAddress: String = ""
    private var relayToken: String = ""

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        Log.d(TAG, "RelayService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val server = intent?.getStringExtra("server") ?: serverAddress
        val token = intent?.getStringExtra("token") ?: relayToken
        if (server.isNotBlank()) {
            val needReconnect = server != serverAddress || token != relayToken
            serverAddress = server
            relayToken = token
            if (needReconnect) {
                RelayClient.disconnect()
                connectRelay()
            }
        }
        val notification = buildNotification("Connecting to $serverAddress...")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            @Suppress("DEPRECATION")
            startForeground(NOTIFICATION_ID, notification)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        Log.d(TAG, "RelayService destroyed")
        RelayClient.disconnect()
        instance = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    fun getStatus(): RelayStatus {
        return RelayStatus(
            relayConnected = RelayClient.isConnected,
            accessibilityActive = BridgeAccessibilityService.instance != null,
            screenRecordGranted = false
        )
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Relay Connection",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Hermes Bridge relay status" }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Hermes Bridge")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_share)
            .setOngoing(true)
            .build()

    private fun connectRelay() {
        RelayClient.init(this)
        // Chain: preserve existing callback (UI) and add notification update
        val existingCallback = RelayClient.onStatusChanged
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        RelayClient.onStatusChanged = { connected, msg ->
            existingCallback?.invoke(connected, msg)
            handler.post {
                val text = if (connected) "Connected to $serverAddress" else msg
                val notif = buildNotification(text)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(NOTIFICATION_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
                } else {
                    @Suppress("DEPRECATION")
                    startForeground(NOTIFICATION_ID, notif)
                }
            }
        }
        RelayClient.connect(serverAddress, relayToken)
    }
}
