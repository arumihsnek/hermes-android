package com.hermesandroid.bridge

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import com.hermesandroid.bridge.auth.AuthApiClient
import com.hermesandroid.bridge.auth.GoogleSignInManager
import com.hermesandroid.bridge.auth.PairingManager
import com.hermesandroid.bridge.client.RelayClient
import com.hermesandroid.bridge.media.ScreenRecorder
import com.hermesandroid.bridge.overlay.StatusOverlay
import com.hermesandroid.bridge.service.BridgeAccessibilityService
import com.hermesandroid.bridge.service.RelayService
import com.hermesandroid.bridge.shizuku.ShizukuExecutor
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.launch
import java.net.NetworkInterface

class MainActivity : Activity() {

    companion object {
        private const val REQUEST_CODE_SCREEN_RECORD = 1001
        private const val REQUEST_CODE_GOOGLE_SIGN_IN = 1002
    }

    // Ask for Shizuku permission at most once per app session.
    private var shizukuPermissionRequested = false
    private val scope = MainScope()

    private lateinit var tvA11yStatus: TextView
    private lateinit var tvServerStatus: TextView
    private lateinit var tvRelayAddr: TextView
    private lateinit var tvAuthCode: TextView
    private lateinit var indicatorA11y: View
    private lateinit var indicatorServer: View
    private lateinit var indicatorRelay: View
    private lateinit var indicatorAuth: View
    private lateinit var switchAccessibility: Switch
    private lateinit var switchOverlay: Switch
    private lateinit var switchScreenRecord: Switch
    private lateinit var switchAutoConnectRelay: Switch
    private lateinit var tvPairingCode: TextView
    private lateinit var btnRegenerate: Button
    private lateinit var etServerUrl: EditText
    private lateinit var tvRelayStatus: TextView
    private lateinit var btnConnect: Button
    private lateinit var btnDisconnect: Button
    private lateinit var tvAddress: TextView
    
    // Google Sign-In views
    private lateinit var googleSignInSection: LinearLayout
    private lateinit var tvUserEmail: TextView
    private lateinit var btnGoogleSignIn: Button
    private lateinit var btnLogout: Button
    private lateinit var tvAuthStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvA11yStatus = findViewById(R.id.tvA11yStatus)
        tvServerStatus = findViewById(R.id.tvServerStatus)
        tvRelayAddr = findViewById(R.id.tvRelayAddr)
        tvAuthCode = findViewById(R.id.tvAuthCode)
        indicatorA11y = findViewById(R.id.indicatorA11y)
        indicatorServer = findViewById(R.id.indicatorServer)
        indicatorRelay = findViewById(R.id.indicatorRelay)
        indicatorAuth = findViewById(R.id.indicatorAuth)
        switchAccessibility = findViewById(R.id.switchAccessibility)
        switchOverlay = findViewById(R.id.switchOverlay)
        switchScreenRecord = findViewById(R.id.switchScreenRecord)
        switchAutoConnectRelay = findViewById(R.id.switchAutoConnectRelay)
        tvPairingCode = findViewById(R.id.tvPairingCode)
        btnRegenerate = findViewById(R.id.btnRegenerate)
        etServerUrl = findViewById(R.id.etServerUrl)
        tvRelayStatus = findViewById(R.id.tvRelayStatus)
        btnConnect = findViewById(R.id.btnConnect)
        btnDisconnect = findViewById(R.id.btnDisconnect)
        tvAddress = findViewById(R.id.tvAddress)
        
        // Google Sign-In removed — backend /auth/google not implemented
        // googleSignInSection = findViewById(R.id.googleSignInSection)
        // tvUserEmail = findViewById(R.id.tvUserEmail)
        // btnGoogleSignIn = findViewById(R.id.btnGoogleSignIn)
        // btnLogout = findViewById(R.id.btnLogout)
        // tvAuthStatus = findViewById(R.id.tvAuthStatus)

        setupPairingCode()
        setupPermissions()
        setupRelayConnection()
        // setupGoogleSignIn()

        updateConnectionInfo()
        updateStatus()
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
        updatePermissionSwitches()
        maybeRequestShizukuPermission()
        autoGrantPermissionsFromPrefs()
    }

    /** Try to auto-grant permissions that the user has toggled ON. */
    private fun autoGrantPermissionsFromPrefs() {
        val prefs = getSharedPreferences("hermes_bridge_prefs", MODE_PRIVATE)

        // Auto-grant overlay if toggle ON but not granted
        if (prefs.getBoolean("overlay_enabled", false) && !Settings.canDrawOverlays(this)) {
            try {
                ShizukuExecutor.exec("pm grant $packageName android.permission.SYSTEM_ALERT_WINDOW", 5000)
            } catch (_: Exception) {}
        }

        // Auto-grant screen record if toggle ON but not granted
        if (prefs.getBoolean("screen_record_enabled", false) && !ScreenRecorder.hasPermission()) {
            try {
                ShizukuExecutor.exec("appops set $packageName PROJECT_MEDIA allow", 5000)
            } catch (_: Exception) {}
        }

        // Auto-enable accessibility if toggle ON but not active
        if (prefs.getBoolean("accessibility_enabled", false) && BridgeAccessibilityService.instance == null) {
            try {
                val svc = "$packageName/${BridgeAccessibilityService::class.java.canonicalName}"
                ShizukuExecutor.exec("settings put secure enabled_accessibility_services $svc", 5000)
                ShizukuExecutor.exec("settings put secure accessibility_enabled 1", 5000)
            } catch (_: Exception) {}
        }

        updatePermissionSwitches()
    }

    private fun setupPermissions() {
        switchAccessibility.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && BridgeAccessibilityService.instance == null) {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }

        switchOverlay.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (!Settings.canDrawOverlays(this)) {
                    startActivity(Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")
                    ))
                } else {
                    StatusOverlay.show(this)
                }
            } else {
                StatusOverlay.hide(this)
            }
        }

        switchScreenRecord.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked && !ScreenRecorder.hasPermission()) {
                val service = BridgeAccessibilityService.instance
                if (service == null) {
                    Toast.makeText(this, "Enable Accessibility Service before screen recording", Toast.LENGTH_LONG).show()
                    updatePermissionSwitches()
                } else {
                    val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                    startActivityForResult(mpm.createScreenCaptureIntent(), REQUEST_CODE_SCREEN_RECORD)
                }
            }
        }
    }

    /** Request Shizuku permission if available and not yet granted. */
    private fun maybeRequestShizukuPermission() {
        if (shizukuPermissionRequested) return
        if (ShizukuExecutor.isRunning() && !ShizukuExecutor.hasPermission()) {
            shizukuPermissionRequested = true
            ShizukuExecutor.requestPermission()
            Toast.makeText(
                this,
                "Approve Shizuku access to enable privileged terminal (android_shell backend=shizuku)",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_SCREEN_RECORD) {
            if (resultCode == RESULT_OK && data != null) {
                val service = BridgeAccessibilityService.instance
                if (service == null) {
                    Toast.makeText(this, "Enable Accessibility Service before screen recording", Toast.LENGTH_LONG).show()
                } else {
                    ScreenRecorder.setProjectionPermission(resultCode, data)
                    Toast.makeText(this, "Screen recording permission granted", Toast.LENGTH_SHORT).show()
                }
            } else {
                Toast.makeText(this, "Screen recording permission denied", Toast.LENGTH_SHORT).show()
            }
            updatePermissionSwitches()
        } else if (requestCode == REQUEST_CODE_GOOGLE_SIGN_IN) {
            // handleGoogleSignInResult(data) — Google Sign-In removed
        }
    }

    private fun setupPairingCode() {
        tvPairingCode.text = PairingManager.getCode()

        btnRegenerate.setOnClickListener {
            PairingManager.regenerateCode()
            tvPairingCode.text = PairingManager.getCode()
            updateStatus()
            Toast.makeText(this, "New pairing code generated", Toast.LENGTH_SHORT).show()
        }

        tvPairingCode.setOnClickListener {
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("Hermes pairing code", PairingManager.getCode()))
            Toast.makeText(this, "Pairing code copied", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updatePermissionSwitches() {
        switchAccessibility.setOnCheckedChangeListener(null)
        switchOverlay.setOnCheckedChangeListener(null)
        switchScreenRecord.setOnCheckedChangeListener(null)

        switchAccessibility.isChecked = BridgeAccessibilityService.instance != null
        switchOverlay.isChecked = Settings.canDrawOverlays(this)
        switchScreenRecord.isChecked = ScreenRecorder.hasPermission()

        setupPermissions()
    }

    private fun setupRelayConnection() {
        val prefs = getSharedPreferences("hermes_bridge_prefs", MODE_PRIVATE)
        val autoConnect = prefs.getBoolean("auto_connect_relay", false)
        val savedUrl = RelayClient.serverUrl
        
        // Initialize auto-connect switch
        switchAutoConnectRelay.isChecked = autoConnect
        switchAutoConnectRelay.setOnCheckedChangeListener { _, isChecked ->
            prefs.edit().putBoolean("auto_connect_relay", isChecked).apply()
        }
        
        // Auto-fill server URL if saved
        if (!savedUrl.isNullOrBlank()) {
            etServerUrl.setText(savedUrl)
        } else {
            // Default to relay on Eddy
            etServerUrl.setText("82.70.86.174:18766")
        }
        
        // Auto-connect if preference enabled
        if (autoConnect && savedUrl.isNullOrBlank().not() && !RelayClient.isConnected) {
            val code = PairingManager.getCode()
            RelayService.start(this, savedUrl ?: "82.70.86.174:18766", code)
        }
        
        RelayClient.onStatusChanged = { connected, message ->
            tvRelayStatus.text = message
            tvRelayStatus.setTextColor(
                if (connected) 0xFF4CAF50.toInt() else 0xFF888888.toInt()
            )
            btnDisconnect.visibility = if (connected || RelayClient.isConnected) View.VISIBLE else View.GONE
            btnConnect.text = if (RelayClient.isConnected) "CONNECTED" else "CONNECT"
            btnConnect.background = getDrawable(
                if (RelayClient.isConnected) R.drawable.bg_input_dark else R.drawable.bg_button_orange
            )
            btnConnect.setTextColor(
                if (RelayClient.isConnected) 0xFF4CAF50.toInt() else 0xFF1A1A1A.toInt()
            )
            updateStatus()
        }

        btnConnect.setOnClickListener {
            if (RelayClient.isConnected) return@setOnClickListener
            val url = etServerUrl.text.toString().trim()
            if (url.isBlank()) {
                Toast.makeText(this, "Enter a server URL", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            val code = PairingManager.getCode()
            // Save URL for auto-connect
            RelayClient.serverUrl = url
            RelayService.start(this, url, code)
        }

        btnDisconnect.setOnClickListener {
            RelayService.stop(this)
            updateRelayButton()
        }

        updateRelayButton()
    }

    private fun updateRelayButton() {
        if (RelayClient.isConnected) {
            btnDisconnect.visibility = View.VISIBLE
            btnConnect.text = "CONNECTED"
            btnConnect.background = getDrawable(R.drawable.bg_input_dark)
            btnConnect.setTextColor(0xFF4CAF50.toInt())
            tvRelayStatus.text = "Connected to ${RelayClient.serverUrl}"
            tvRelayStatus.setTextColor(0xFF4CAF50.toInt())
        } else {
            btnDisconnect.visibility = View.GONE
            btnConnect.text = "CONNECT"
            btnConnect.background = getDrawable(R.drawable.bg_button_orange)
            btnConnect.setTextColor(0xFF1A1A1A.toInt())
        }
    }

    private fun updateConnectionInfo() {
        val ip = getLocalIpAddress()
        if (BuildConfig.DEBUG) {
            tvAddress.text = "http://$ip:8765 (debug)"
        } else {
            tvAddress.text = "relay: ${RelayClient.serverUrl ?: "not connected"}"
        }
    }

    private fun updateStatus() {
        val serviceRunning = BridgeAccessibilityService.instance != null
        val relayConnected = RelayClient.isConnected

        tvA11yStatus.text = if (serviceRunning) "active" else "inactive"
        tvA11yStatus.setTextColor(if (serviceRunning) 0xFF4CAF50.toInt() else 0xFF888888.toInt())
        indicatorA11y.setBackgroundResource(
            if (serviceRunning) R.drawable.bg_status_dot_green else R.drawable.bg_status_dot_grey
        )

        tvServerStatus.text = "8765"
        tvServerStatus.setTextColor(0xFF4CAF50.toInt())

        if (relayConnected) {
            tvRelayAddr.text = RelayClient.serverUrl
            tvRelayAddr.setTextColor(0xFF4CAF50.toInt())
            indicatorRelay.setBackgroundResource(R.drawable.bg_status_dot_green)
        } else if (!RelayClient.serverUrl.isNullOrBlank()) {
            tvRelayAddr.text = "disconnected"
            tvRelayAddr.setTextColor(0xFF888888.toInt())
            indicatorRelay.setBackgroundResource(R.drawable.bg_status_dot_red)
        } else {
            tvRelayAddr.text = "—"
            tvRelayAddr.setTextColor(0xFF555555.toInt())
            indicatorRelay.setBackgroundResource(R.drawable.bg_status_dot_grey)
        }

        tvAuthCode.text = PairingManager.getCode()
        tvAuthCode.setTextColor(0xFF4CAF50.toInt())
    }

    private fun getLocalIpAddress(): String {
        return NetworkInterface.getNetworkInterfaces()?.toList()
            ?.flatMap { it.inetAddresses.toList() }
            ?.firstOrNull { !it.isLoopbackAddress && it.hostAddress?.contains(':') == false }
            ?.hostAddress ?: "localhost"
    }

    /**
     * Setup Google Sign-In button and logout button.
     */
    private fun setupGoogleSignIn() {
        // Initialize Google Sign-In manager
        GoogleSignInManager.init(this)

        // Show the Google Sign-In section
        googleSignInSection.visibility = View.VISIBLE

        // Check if user is already signed in
        if (GoogleSignInManager.isSignedIn()) {
            showSignedInState()
        } else {
            showSignedOutState()
        }

        // Setup sign-in button click
        btnGoogleSignIn.setOnClickListener {
            startGoogleSignIn()
        }

        // Setup logout button click
        btnLogout.setOnClickListener {
            logout()
        }
    }

    /**
     * Start the Google Sign-In flow.
     */
    private fun startGoogleSignIn() {
        val signInIntent = GoogleSignInManager.getSignInIntent()
        if (signInIntent != null) {
            startActivityForResult(signInIntent, REQUEST_CODE_GOOGLE_SIGN_IN)
        } else {
            Toast.makeText(this, getString(R.string.google_sign_in_error), Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Handle the Google Sign-In result.
     */
    private fun handleGoogleSignInResult(data: Intent?) {
        val account = GoogleSignInManager.handleSignInResult(data)
        
        if (account != null && account.idToken != null) {
            // Successfully signed in with Google
            showLoadingState(true)
            
            // Call backend with Google token
            scope.launch {
                val result = AuthApiClient.authenticateWithGoogle(
                    idToken = account.idToken!!,
                    email = account.email ?: "",
                    name = account.displayName
                )
                
                result.onSuccess { authResponse ->
                    // Store session data
                    GoogleSignInManager.storeSession(
                        sessionToken = authResponse.sessionToken,
                        email = authResponse.email,
                        name = authResponse.name
                    )
                    
                    showLoadingState(false)
                    showSignedInState()
                    
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.auth_success),
                        Toast.LENGTH_SHORT
                    ).show()
                }
                
                result.onFailure { error ->
                    showLoadingState(false)
                    showSignedOutState()
                    
                    Toast.makeText(
                        this@MainActivity,
                        getString(R.string.auth_error),
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        } else {
            // Sign-in failed or was cancelled - error already logged by GoogleSignInManager
            Toast.makeText(
                this,
                getString(R.string.google_sign_in_error),
                Toast.LENGTH_LONG
            ).show()
        }
    }

    /**
     * Show loading state during authentication.
     */
    private fun showLoadingState(loading: Boolean) {
        btnGoogleSignIn.isEnabled = !loading
        btnGoogleSignIn.text = if (loading) {
            getString(R.string.google_sign_in_loading)
        } else {
            getString(R.string.google_sign_in_button_text)
        }
        tvAuthStatus.visibility = if (loading) View.VISIBLE else View.GONE
        tvAuthStatus.text = if (loading) "Authenticating..." else ""
    }

    /**
     * Show signed-in state.
     */
    private fun showSignedInState() {
        btnGoogleSignIn.visibility = View.GONE
        btnLogout.visibility = View.VISIBLE
        tvUserEmail.visibility = View.VISIBLE
        tvUserEmail.text = GoogleSignInManager.getUserEmail() ?: ""
        tvAuthStatus.visibility = View.VISIBLE
        tvAuthStatus.text = "Signed in as ${GoogleSignInManager.getUserName() ?: GoogleSignInManager.getUserEmail()}"
        tvAuthStatus.setTextColor(0xFF4CAF50.toInt())
    }

    /**
     * Show signed-out state.
     */
    private fun showSignedOutState() {
        btnGoogleSignIn.visibility = View.VISIBLE
        btnLogout.visibility = View.GONE
        tvUserEmail.visibility = View.GONE
        tvAuthStatus.visibility = View.GONE
    }

    /**
     * Logout and clear session.
     */
    private fun logout() {
        GoogleSignInManager.logout(this) {
            showSignedOutState()
            Toast.makeText(this, "Logged out", Toast.LENGTH_SHORT).show()
        }
    }
}
