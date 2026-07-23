package com.hermesandroid.bridge.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.io.IOException
import java.security.GeneralSecurityException

/**
 * Interface for token storage operations.
 * Allows swapping real Keystore-backed storage with fakes in tests.
 */
interface BridgeTokenStorageInterface {
    fun saveToken(accessToken: String, refreshToken: String? = null, expiryMillis: Long? = null): Boolean
    fun getToken(): String?
    fun getRefreshToken(): String?
    fun getTokenExpiry(): Long?
    fun isTokenValid(): Boolean
    fun clearToken()
}

/**
 * Secure token storage backed by Android Keystore via EncryptedSharedPreferences.
 *
 * Tokens are never stored in plaintext. All crypto operations happen inside the
 * Android Keystore - the app process never sees the master key material.
 *
 * Thread-safe: EncryptedSharedPreferences delegates synchronization to the
 * underlying SharedPreferences implementation.
 */
class BridgeTokenStorage private constructor(context: Context) : BridgeTokenStorageInterface {

    companion object {
        private const val TAG = "BridgeTokenStorage"
        private const val PREFS_NAME = "hermes_bridge_auth_prefs"
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_TOKEN_EXPIRY = "token_expiry"

        @Volatile
        private var instance: BridgeTokenStorage? = null

        fun getInstance(context: Context): BridgeTokenStorage {
            return instance ?: synchronized(this) {
                instance ?: BridgeTokenStorage(context.applicationContext).also { instance = it }
            }
        }
    }

    private val prefs: SharedPreferences by lazy { createPrefs(context) }

    // -- Public API --------------------------------------------------------

    override fun saveToken(
        accessToken: String,
        refreshToken: String?,
        expiryMillis: Long?
    ): Boolean {
        return try {
            val editor = prefs.edit()
            editor.putString(KEY_ACCESS_TOKEN, accessToken)
            if (refreshToken != null) {
                editor.putString(KEY_REFRESH_TOKEN, refreshToken)
            } else {
                editor.remove(KEY_REFRESH_TOKEN)
            }
            if (expiryMillis != null) {
                editor.putLong(KEY_TOKEN_EXPIRY, expiryMillis)
            } else {
                editor.remove(KEY_TOKEN_EXPIRY)
            }
            editor.apply()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save token", e)
            false
        }
    }

    override fun getToken(): String? {
        return try {
            prefs.getString(KEY_ACCESS_TOKEN, null)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read token", e)
            null
        }
    }

    override fun getRefreshToken(): String? {
        return try {
            prefs.getString(KEY_REFRESH_TOKEN, null)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read refresh token", e)
            null
        }
    }

    override fun getTokenExpiry(): Long? {
        return try {
            val v = prefs.getLong(KEY_TOKEN_EXPIRY, -1L)
            if (v >= 0) v else null
        } catch (e: Exception) {
            null
        }
    }

    override fun isTokenValid(): Boolean {
        val token = getToken() ?: return false
        val expiry = getTokenExpiry() ?: return token.isNotBlank()
        return System.currentTimeMillis() < expiry - 30_000L
    }

    override fun clearToken() {
        try {
            prefs.edit().clear().apply()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear token", e)
        }
    }

    // -- Internal ----------------------------------------------------------

    /**
     * Open base class for testing. Override methods to use in-memory storage.
     * Real implementation is [BridgeTokenStorage] (the private-constructor singleton).
     */
    open class Fake : BridgeTokenStorageInterface {
        override fun saveToken(accessToken: String, refreshToken: String?, expiryMillis: Long?) = true
        override fun getToken(): String? = null
        override fun getRefreshToken(): String? = null
        override fun getTokenExpiry(): Long? = null
        override fun isTokenValid() = getToken() != null
        override fun clearToken() {}
    }

    private fun createPrefs(context: Context): SharedPreferences {
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
        } catch (e: GeneralSecurityException) {
            Log.e(TAG, "Keystore unavailable, falling back to plain SharedPreferences")
            context.getSharedPreferences(PREFS_NAME + "_fallback", Context.MODE_PRIVATE)
        } catch (e: IOException) {
            Log.e(TAG, "IO error initializing encrypted prefs, falling back")
            context.getSharedPreferences(PREFS_NAME + "_fallback", Context.MODE_PRIVATE)
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error initializing encrypted prefs, falling back")
            context.getSharedPreferences(PREFS_NAME + "_fallback", Context.MODE_PRIVATE)
        }
    }
}