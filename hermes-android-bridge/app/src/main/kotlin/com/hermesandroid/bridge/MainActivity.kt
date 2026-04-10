package com.hermesandroid.bridge

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import com.hermesandroid.bridge.auth.PairingManager
import com.hermesandroid.bridge.client.RelayClient
import com.hermesandroid.bridge.media.ScreenRecorder
import com.hermesandroid.bridge.overlay.StatusOverlay
import com.hermesandroid.bridge.service.BridgeAccessibilityService
import java.net.NetworkInterface

class MainActivity : Activity() {

    companion object {
        private const val REQUEST_CODE_SCREEN_RECORD = 1001
    }

    // FIGlet "HERMES BRIDGE" in ANSI Shadow style (fits mobile width)
    private val ASCII_TITLE = """
 ██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗
 ██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝
 ███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗
 ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║
 ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║
 ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝
 ██████╗ ██████╗ ██╗██████╗  ██████╗ ███████╗
 ██╔══██╗██╔══██╗██║██╔══██╗██╔════╝ ██╔════╝
 ██████╔╝██████╔╝██║██║  ██║██║  ███╗█████╗
 ██╔══██╗██╔══██╗██║██║  ██║██║   ██║██╔══╝
 ██████╔╝██║  ██║██║██████╔╝╚██████╔╝███████╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝╚═════╝  ╚═════╝ ╚══════╝""".trimIndent()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Set ASCII title
        findViewById<TextView>(R.id.tvAsciiTitle).text = ASCII_TITLE

        // Pairing code
        updatePairingCode()

        findViewById<Button>(R.id.btnRegenerate).setOnClickListener {
            PairingManager.regenerateCode()
            updatePairingCode()
            Toast.makeText(this, "New pairing code generated", Toast.LENGTH_SHORT).show()
        }

        // Tap pairing code to copy
        findViewById<TextView>(R.id.tvPairingCode).setOnClickListener {
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("Hermes pairing code", PairingManager.getCode()))
            Toast.makeText(this, "Pairing code copied", Toast.LENGTH_SHORT).show()
        }

        // Permissions
        findViewById<Button>(R.id.btnAccessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        findViewById<Button>(R.id.btnOverlay).setOnClickListener {
            if (!Settings.canDrawOverlays(this)) {
                startActivity(Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                ))
            } else {
                StatusOverlay.show(this)
            }
        }

        findViewById<Button>(R.id.btnScreenRecord).setOnClickListener {
            val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            startActivityForResult(mpm.createScreenCaptureIntent(), REQUEST_CODE_SCREEN_RECORD)
        }

        updateScreenRecordStatus()

        // Relay server connection
        setupRelayConnection()

        updateConnectionInfo()
        updateStatus()
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
        updateRelayButton()
        updateScreenRecordStatus()
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_SCREEN_RECORD) {
            if (resultCode == RESULT_OK && data != null) {
                val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                val projection = mpm.getMediaProjection(resultCode, data)
                if (projection != null) {
                    ScreenRecorder.setProjection(projection)
                    Toast.makeText(this, "Screen recording permission granted", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "Screen recording permission denied", Toast.LENGTH_SHORT).show()
            }
            updateScreenRecordStatus()
        }
    }

    private fun updateScreenRecordStatus() {
        val btn = findViewById<Button>(R.id.btnScreenRecord)
        val tv = findViewById<TextView>(R.id.tvScreenRecordStatus)
        if (ScreenRecorder.hasPermission()) {
            btn.text = "> Screen Recording: Granted"
            tv.text = "[*] screen record: permission granted"
        } else {
            btn.text = "> Grant Screen Recording"
            tv.text = ""
        }
    }

    private fun setupRelayConnection() {
        val etServerUrl = findViewById<EditText>(R.id.etServerUrl)
        val btnConnect = findViewById<Button>(R.id.btnConnect)
        val tvRelayStatus = findViewById<TextView>(R.id.tvRelayStatus)

        // Load saved server URL
        val savedUrl = RelayClient.serverUrl
        if (!savedUrl.isNullOrBlank()) {
            etServerUrl.setText(savedUrl)
        }

        // Status callback
        RelayClient.onStatusChanged = { connected, message ->
            tvRelayStatus.text = if (connected) "[*] $message" else "[ ] $message"
            tvRelayStatus.setTextColor(
                if (connected) 0xFF4CAF50.toInt() else 0xFF888888.toInt()
            )
            btnConnect.text = if (connected || RelayClient.isConnected)
                "> DISCONNECT" else "> CONNECT"
            btnConnect.setBackgroundColor(
                if (connected || RelayClient.isConnected) 0xFFFF5722.toInt() else 0xFF4CAF50.toInt()
            )
            updateStatus()
        }

        // Update button state based on current connection
        updateRelayButton()

        btnConnect.setOnClickListener {
            if (RelayClient.isConnected) {
                RelayClient.disconnect()
                btnConnect.text = "Connect to Server"
                tvRelayStatus.text = "Disconnected"
                tvRelayStatus.setTextColor(0xFF888888.toInt())
            } else {
                val url = etServerUrl.text.toString().trim()
                if (url.isBlank()) {
                    Toast.makeText(this, "Enter a server URL", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                val code = PairingManager.getCode()
                RelayClient.connect(url, code)
            }
            updateStatus()
        }
    }

    private fun updateRelayButton() {
        val btnConnect = findViewById<Button>(R.id.btnConnect)
        val tvRelayStatus = findViewById<TextView>(R.id.tvRelayStatus)
        if (RelayClient.isConnected) {
            btnConnect.text = "> DISCONNECT"
            btnConnect.setBackgroundColor(0xFFFF5722.toInt())
            tvRelayStatus.text = "[*] Connected to ${RelayClient.serverUrl}"
            tvRelayStatus.setTextColor(0xFF4CAF50.toInt())
        } else {
            btnConnect.text = "> CONNECT"
            btnConnect.setBackgroundColor(0xFF4CAF50.toInt())
        }
    }

    private fun updatePairingCode() {
        findViewById<TextView>(R.id.tvPairingCode).text = PairingManager.getCode()
    }

    private fun updateConnectionInfo() {
        val ip = getLocalIpAddress()
        findViewById<TextView>(R.id.tvAddress).text =
            "Local: http://$ip:8765 (USB/LAN only)"
    }

    private fun updateStatus() {
        val serviceRunning = BridgeAccessibilityService.instance != null
        val relayConnected = RelayClient.isConnected
        val tvStatus = findViewById<TextView>(R.id.tvStatus)
        tvStatus.text = buildString {
            if (serviceRunning) append("[*] a11y: active")
            else append("[ ] a11y: inactive")
            append("\n[*] server: :8765")
            if (relayConnected) {
                append("\n[*] relay: ${RelayClient.serverUrl}")
            } else if (!RelayClient.serverUrl.isNullOrBlank()) {
                append("\n[ ] relay: disconnected")
            }
            append("\n[*] auth: ${PairingManager.getCode()}")
        }
        tvStatus.setTextColor(
            if (serviceRunning && relayConnected) 0xFF4CAF50.toInt() else 0xFFFF9800.toInt()
        )
    }

    private fun getLocalIpAddress(): String {
        return NetworkInterface.getNetworkInterfaces()?.toList()
            ?.flatMap { it.inetAddresses.toList() }
            ?.firstOrNull { !it.isLoopbackAddress && it.hostAddress?.contains(':') == false }
            ?.hostAddress ?: "localhost"
    }
}
