package com.hermesandroid.bridge.auth

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.util.Log
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.tasks.Task
import com.hermesandroid.bridge.R

/**
 * Manages Google Sign-In authentication flow.
 *
 * Handles:
 * - Configuring GoogleSignInClient with web client ID
 * - Launching sign-in intent
 * - Processing sign-in results
 * - Storing session tokens
 * - Logout functionality
 */
object GoogleSignInManager {
    private const val TAG = "GoogleSignInManager"
    private const val PREFS_NAME = "hermes_bridge_prefs"
    private const val KEY_SESSION_TOKEN = "session_token"
    private const val KEY_USER_EMAIL = "user_email"
    private const val KEY_USER_NAME = "user_name"
    private const val KEY_IS_SIGNED_IN = "is_signed_in"

    @Volatile
    private var googleSignInClient: GoogleSignInClient? = null
    
    @Volatile
    private var prefs: SharedPreferences? = null

    /**
     * Initialize the Google Sign-In manager.
     * Must be called before using any other methods.
     */
    fun init(context: Context) {
        prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        
        val webClientId = context.getString(R.string.google_web_client_id)
        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(webClientId)
            .requestEmail()
            .build()
        
        googleSignInClient = GoogleSignIn.getClient(context, gso)
    }

    /**
     * Get the sign-in intent to launch.
     */
    fun getSignInIntent(): Intent? {
        return googleSignInClient?.signInIntent
    }

    /**
     * Process the sign-in result from onActivityResult.
     * Returns the GoogleSignInAccount if successful, null otherwise.
     */
    fun handleSignInResult(data: Intent?): GoogleSignInAccount? {
        val task = GoogleSignIn.getSignedInAccountFromIntent(data)
        return try {
            val account = task.getResult(ApiException::class.java)
            Log.d(TAG, "Google Sign-In successful: ${account.email}")
            account
        } catch (e: ApiException) {
            Log.w(TAG, "Google Sign-In failed: ${e.statusCode}", e)
            null
        }
    }

    /**
     * Store session data after successful backend authentication.
     */
    fun storeSession(sessionToken: String, email: String, name: String?) {
        prefs?.edit()?.apply {
            putString(KEY_SESSION_TOKEN, sessionToken)
            putString(KEY_USER_EMAIL, email)
            putString(KEY_USER_NAME, name ?: "")
            putBoolean(KEY_IS_SIGNED_IN, true)
            apply()
        }
    }

    /**
     * Get the stored session token.
     */
    fun getSessionToken(): String? {
        return prefs?.getString(KEY_SESSION_TOKEN, null)
    }

    /**
     * Get the stored user email.
     */
    fun getUserEmail(): String? {
        return prefs?.getString(KEY_USER_EMAIL, null)
    }

    /**
     * Get the stored user name.
     */
    fun getUserName(): String? {
        return prefs?.getString(KEY_USER_NAME, null)
    }

    /**
     * Check if user is currently signed in.
     */
    fun isSignedIn(): Boolean {
        return prefs?.getBoolean(KEY_IS_SIGNED_IN, false) ?: false
    }

    /**
     * Logout and clear stored session data.
     */
    fun logout(context: Context, onComplete: () -> Unit = {}) {
        googleSignInClient?.signOut()?.addOnCompleteListener {
            prefs?.edit()?.apply {
                remove(KEY_SESSION_TOKEN)
                remove(KEY_USER_EMAIL)
                remove(KEY_USER_NAME)
                putBoolean(KEY_IS_SIGNED_IN, false)
                apply()
            }
            Log.d(TAG, "User logged out")
            onComplete()
        }
    }

    /**
     * Revoke access and clear stored session data.
     * This is more thorough than signOut - it revokes the token.
     */
    fun revokeAccess(context: Context, onComplete: () -> Unit = {}) {
        googleSignInClient?.revokeAccess()?.addOnCompleteListener {
            prefs?.edit()?.apply {
                remove(KEY_SESSION_TOKEN)
                remove(KEY_USER_EMAIL)
                remove(KEY_USER_NAME)
                putBoolean(KEY_IS_SIGNED_IN, false)
                apply()
            }
            Log.d(TAG, "Google access revoked")
            onComplete()
        }
    }

    /**
     * Silent sign-in check - attempts to sign in without user interaction.
     * Returns the last signed-in account if available.
     */
    fun silentSignIn(context: Context, callback: (GoogleSignInAccount?) -> Unit) {
        val lastAccount = GoogleSignIn.getLastSignedInAccount(context)
        if (lastAccount != null && !GoogleSignIn.hasPermissions(lastAccount)) {
            // Token might be expired, try silent sign-in
            googleSignInClient?.silentSignIn()?.addOnCompleteListener { task ->
                try {
                    val account = task.getResult(ApiException::class.java)
                    callback(account)
                } catch (e: ApiException) {
                    Log.w(TAG, "Silent sign-in failed: ${e.statusCode}", e)
                    callback(null)
                }
            }
        } else {
            callback(lastAccount)
        }
    }
}
