package com.hermesandroid.bridge.tasker

import android.content.Context
import android.util.Base64
import java.security.SecureRandom

/**
 * Gateway configuration. Secret is provisioned on-device.
 * NEVER stored in Git, logs, or Tasker exports.
 *
 * Provisioning flow:
 * 1. First run: auto-generates 256-bit random secret
 * 2. Stored in Android SharedPreferences
 * 3. Must be manually set as Tasker variable %gw_secret
 * 4. Rotation via rotateSecret() — old secret lost
 */
object TaskerGatewayConfig {

    private const val PREFS_NAME = "tasker_gateway_config"
    private const val KEY_SECRET = "gateway_hmac_secret"
    private const val KEY_TASKER_PACKAGE = "net.dinglisch.android.taskerm"

    /** Broadcast action: Bridge → Tasker */
    const val ACTION_REQUEST = "com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1"

    /** Broadcast action: Tasker → Bridge */
    const val ACTION_RESPONSE = "com.hermesandroid.bridge.TASKER_GATEWAY_RESPONSE_V1"

    const val EXTRA_REQUEST_JSON = "request_json"
    const val EXTRA_RESPONSE_JSON = "response_json"

    val taskerPackage: String get() = KEY_TASKER_PACKAGE

    /**
     * Get or generate the HMAC secret.
     * First call generates 256-bit random secret and stores it.
     * Subsequent calls read from SharedPreferences.
     */
    fun getOrCreateSecret(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val existing = prefs.getString(KEY_SECRET, null)
        if (existing != null) return existing

        // Generate 256-bit random secret
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val secret = Base64.encodeToString(bytes, Base64.NO_WRAP)
        prefs.edit().putString(KEY_SECRET, secret).commit()
        return secret
    }

    /**
     * Configure the authenticator with the on-device secret.
     * Must be called before any signing/verification.
     */
    fun initAuthenticator(context: Context) {
        val secret = getOrCreateSecret(context)
        TaskerGatewayAuthenticator.configure(secret)
    }

    /**
     * Rotate the secret. Old secret is lost.
     * Must re-provision on Tasker side after rotation.
     */
    fun rotateSecret(context: Context): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val newSecret = Base64.encodeToString(bytes, Base64.NO_WRAP)
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString(KEY_SECRET, newSecret).commit()
        TaskerGatewayAuthenticator.configure(newSecret)
        return newSecret
    }

    /**
     * Check if a secret has been provisioned.
     */
    fun isProvisioned(context: Context): Boolean {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .contains(KEY_SECRET)
    }
}
