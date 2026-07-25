package com.hermesandroid.bridge.tasker

import android.content.Context
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Gateway configuration with secure provisioning.
 *
 * Secret is encrypted at rest using Android Keystore-backed EncryptedSharedPreferences.
 * Provisioning follows a challenge-response protocol:
 * 1. Bridge generates secret + challenge
 * 2. Bridge sends provisioning broadcast to Tasker
 * 3. Tasker stores secret, computes challenge_hmac = HMAC-SHA256(secret, challenge)
 * 4. Tasker sends back challenge_hmac
 * 5. Bridge verifies challenge_hmac before declaring pairing complete
 *
 * NEVER stored in Git, logs, or Tasker exports.
 * NEVER exposes a raw secret getter — only initAuthenticator() for internal use.
 */
object TaskerGatewayConfig {

    private const val TAG = "TaskerGatewayConfig"
    private const val PREFS_NAME = "tasker_gateway_encrypted"
    private const val KEY_SECRET_B64 = "gateway_hmac_secret_v2"
    private const val KEY_PAIRING_ID = "pairing_id"
    private const val KEY_PAIRING_STATE = "pairing_state"
    private const val KEY_ISSUED_AT_MS = "issued_at_ms"
    private const val KEY_DEADLINE_AT_MS = "deadline_at_ms"
    private const val KEY_TASKER_PACKAGE = "net.dinglisch.android.taskerm"

    /** Broadcast action: Bridge → Tasker (requests) */
    const val ACTION_REQUEST = "com.hermesandroid.bridge.TASKER_GATEWAY_REQUEST_V1"

    /** Broadcast action: Tasker → Bridge (responses) */
    const val ACTION_RESPONSE = "com.hermesandroid.bridge.TASKER_GATEWAY_RESPONSE_V1"

    /** Broadcast action: Bridge → Tasker (provisioning) */
    const val ACTION_PROVISION = "com.hermesandroid.bridge.TASKER_GATEWAY_PROVISION_V1"

    /** Broadcast action: Tasker → Bridge (provisioning response) */
    const val ACTION_PROVISION_RESPONSE = "com.hermesandroid.bridge.TASKER_GATEWAY_PROVISION_RESPONSE_V1"

    const val EXTRA_REQUEST_JSON = "request_json"
    const val EXTRA_RESPONSE_JSON = "response_json"
    const val EXTRA_PROVISION_JSON = "provision_json"

    /** Provisioning window: 5 minutes from issuance */
    const val PROVISION_WINDOW_MS = 5 * 60 * 1000L

    val taskerPackage: String get() = KEY_TASKER_PACKAGE

    /** Pairing states */
    enum class PairingState {
        UNPAIRED,
        PENDING,
        PAIRED
    }

    // ── Encrypted storage ──────────────────────────────────────────────

    /**
     * Get or create EncryptedSharedPreferences backed by Android Keystore.
     * Returns null if Keystore is unavailable (unit tests, old devices).
     */
    private fun getEncryptedPrefs(context: Context): android.content.SharedPreferences? {
        return try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context,
                PREFS_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create encrypted prefs: ${e.message}", e)
            // Fallback to plain SharedPreferences for development
            context.getSharedPreferences("${PREFS_NAME}_fallback", Context.MODE_PRIVATE)
        }
    }

    // ── Secret management ──────────────────────────────────────────────

    /**
     * Get or generate the HMAC secret.
     * First call generates 256-bit random secret and stores it encrypted.
     * Subsequent calls read from encrypted storage.
     *
     * This is the ONLY way to access the secret. There is no raw getter.
     */
    fun getOrCreateSecret(context: Context): String {
        val prefs = getEncryptedPrefs(context)
        val existing = prefs?.getString(KEY_SECRET_B64, null)
        if (existing != null) return existing

        // Generate 256-bit random secret
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val secret = Base64.getEncoder().encodeToString(bytes)
        prefs?.edit()?.putString(KEY_SECRET_B64, secret)?.commit()
        return secret
    }

    /**
     * Configure the authenticator with the on-device secret.
     * Must be called before any signing/verification.
     */
    fun initAuthenticator(context: Context) {
        val secret = getOrCreateSecret(context)
        TaskerGatewayAuthenticator.configure(secret)
        Log.d(TAG, "Authenticator initialized (secret loaded from encrypted storage)")
    }

    // ── Provisioning ───────────────────────────────────────────────────

    /**
     * Start provisioning: generate challenge, open temporal window.
     * Returns the provisioning request to send to Tasker.
     * Provisioning is disabled by default and requires explicit local action.
     */
    fun startProvisioning(context: Context): ProvisionRequest? {
        val prefs = getEncryptedPrefs(context) ?: return null

        // Check if already paired — reject silent reprovisioning
        val currentState = getPairingState(prefs)
        if (currentState == PairingState.PAIRED) {
            Log.w(TAG, "Already paired — use rotateSecret() to re-provision")
            return null
        }

        // Generate secret (if first time) or use existing
        val secretB64 = getOrCreateSecret(context)

        // Generate challenge
        val challengeBytes = ByteArray(32)
        SecureRandom().nextBytes(challengeBytes)
        val challenge = Base64.getEncoder().encodeToString(challengeBytes)

        // Generate pairing_id
        val pairingId = java.util.UUID.randomUUID().toString()

        val now = System.currentTimeMillis()
        val deadline = now + PROVISION_WINDOW_MS

        // Store pending state
        prefs.edit()
            .putString(KEY_PAIRING_ID, pairingId)
            .putString(KEY_PAIRING_STATE, PairingState.PENDING.name)
            .putLong(KEY_ISSUED_AT_MS, now)
            .putLong(KEY_DEADLINE_AT_MS, deadline)
            .commit()

        Log.d(TAG, "Provisioning started: pairing_id=$pairingId, deadline=$deadline")

        return ProvisionRequest(
            version = 1,
            pairingId = pairingId,
            challenge = challenge,
            secretB64 = secretB64,
            issuedAtMs = now,
            deadlineAtMs = deadline
        )
    }

    /**
     * Complete provisioning: verify challenge_hmac from Tasker.
     * Returns true if Tasker proved it stores the correct secret.
     *
     * This is the verification step — Bridge computes expected HMAC
     * and compares with what Tasker returned.
     */
    fun completeProvisioning(context: Context, response: ProvisionResponse): Boolean {
        val prefs = getEncryptedPrefs(context) ?: return false

        // Check pairing state
        val state = getPairingState(prefs)
        if (state != PairingState.PENDING) {
            Log.w(TAG, "Provisioning not in PENDING state: $state")
            return false
        }

        // Check deadline
        val deadline = prefs.getLong(KEY_DEADLINE_AT_MS, 0)
        if (System.currentTimeMillis() > deadline) {
            Log.w(TAG, "Provisioning window expired")
            prefs.edit().putString(KEY_PAIRING_STATE, PairingState.UNPAIRED.name).commit()
            return false
        }

        // Check pairing_id matches
        val expectedPairingId = prefs.getString(KEY_PAIRING_ID, null)
        if (response.pairingId != expectedPairingId) {
            Log.w(TAG, "Pairing ID mismatch: expected=$expectedPairingId, got=${response.pairingId}")
            return false
        }

        // Verify challenge_hmac: compute expected and compare
        val secret = getOrCreateSecret(context)
        val secretBytes = Base64.getDecoder().decode(secret)
        val challengeBytes = Base64.getDecoder().decode(
            prefs.getString("pending_challenge", null) ?: return false
        )
        val expectedHmac = computeHmac(secretBytes, challengeBytes)

        if (!constantTimeEquals(expectedHmac, response.challengeHmac)) {
            Log.w(TAG, "Challenge HMAC verification failed — Tasker has wrong secret")
            prefs.edit().putString(KEY_PAIRING_STATE, PairingState.UNPAIRED.name).commit()
            return false
        }

        // Provisioning complete
        prefs.edit()
            .putString(KEY_PAIRING_STATE, PairingState.PAIRED.name)
            .remove("pending_challenge")
            .commit()

        Log.d(TAG, "Provisioning complete: pairing_id=${response.pairingId}")
        return true
    }

    /**
     * Rotate the secret. Generates a new secret and opens provisioning window.
     * Old secret is invalidated after Tasker re-provisions with new one.
     */
    fun rotateSecret(context: Context): ProvisionRequest? {
        val prefs = getEncryptedPrefs(context) ?: return null

        // Generate new secret
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val newSecret = Base64.getEncoder().encodeToString(bytes)
        prefs.edit().putString(KEY_SECRET_B64, newSecret).commit()

        // Reset pairing state to trigger re-provisioning
        prefs.edit()
            .putString(KEY_PAIRING_STATE, PairingState.UNPAIRED.name)
            .commit()

        Log.d(TAG, "Secret rotated — must re-provision Tasker")

        // Start new provisioning
        return startProvisioning(context)
    }

    /**
     * Check if a secret has been provisioned and paired.
     */
    fun isProvisioned(context: Context): Boolean {
        return getPairingState(context) == PairingState.PAIRED
    }

    /**
     * Get current pairing state.
     */
    fun getPairingState(context: Context): PairingState {
        val prefs = getEncryptedPrefs(context) ?: return PairingState.UNPAIRED
        return getPairingState(prefs)
    }

    private fun getPairingState(prefs: android.content.SharedPreferences): PairingState {
        val stateStr = prefs.getString(KEY_PAIRING_STATE, PairingState.UNPAIRED.name)
        return try {
            PairingState.valueOf(stateStr!!)
        } catch (_: Exception) {
            PairingState.UNPAIRED
        }
    }

    // ── HMAC helpers ───────────────────────────────────────────────────

    /**
     * Compute HMAC-SHA256 over raw bytes.
     */
    fun computeHmac(key: ByteArray, data: ByteArray): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return Base64.getEncoder().encodeToString(mac.doFinal(data))
    }

    /**
     * Constant-time string comparison.
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        return result == 0
    }

    // ── Data classes ───────────────────────────────────────────────────

    /**
     * Provisioning request sent from Bridge to Tasker.
     * Contains the secret (encrypted transport, local only).
     */
    data class ProvisionRequest(
        val version: Int = 1,
        val pairingId: String,
        val challenge: String,
        val secretB64: String,
        val issuedAtMs: Long,
        val deadlineAtMs: Long
    )

    /**
     * Provisioning response from Tasker to Bridge.
     * Tasker proves it stored the secret by computing HMAC(secret, challenge).
     */
    data class ProvisionResponse(
        val version: Int = 1,
        val pairingId: String,
        val challengeHmac: String,
        val stored: Boolean
    )
}
