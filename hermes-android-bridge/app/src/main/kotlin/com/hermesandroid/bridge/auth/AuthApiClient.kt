package com.hermesandroid.bridge.auth

import android.util.Log
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Backend authentication API client.
 * Handles communication with the Hermes backend for Google Sign-In.
 */
object AuthApiClient {
    private const val TAG = "AuthApiClient"
    private const val DEFAULT_BASE_URL = "http://localhost:8765" // Default bridge server URL
    
    private var baseUrl: String = DEFAULT_BASE_URL
    
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    
    private val gson = Gson()

    /**
     * Set the base URL for API requests.
     * Useful for testing with MockWebServer or custom server URLs.
     */
    fun setBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    /**
     * Get the current base URL.
     */
    fun getBaseUrl(): String = baseUrl

    /**
     * Reset to default base URL.
     */
    fun resetBaseUrl() {
        baseUrl = DEFAULT_BASE_URL
    }
    
    /**
     * Request body for POST /auth/google
     */
    data class GoogleAuthRequest(
        @SerializedName("id_token") val idToken: String,
        @SerializedName("email") val email: String,
        @SerializedName("name") val name: String?
    )
    
    /**
     * Response from POST /auth/google
     */
    data class GoogleAuthResponse(
        @SerializedName("session_token") val sessionToken: String,
        @SerializedName("user_id") val userId: String,
        @SerializedName("email") val email: String,
        @SerializedName("name") val name: String?
    )
    
    /**
     * Error response from backend
     */
    data class ErrorResponse(
        @SerializedName("error") val error: String,
        @SerializedName("message") val message: String?
    )
    
    /**
     * Authenticate with backend using Google ID token.
     * 
     * @param idToken Google ID token from GoogleSignInAccount
     * @param email User's email
     * @param name User's display name
     * @return Result with session token or error
     */
    suspend fun authenticateWithGoogle(
        idToken: String,
        email: String,
        name: String?
    ): Result<GoogleAuthResponse> = withContext(Dispatchers.IO) {
        try {
            val request = GoogleAuthRequest(
                idToken = idToken,
                email = email,
                name = name
            )
            
            val jsonBody = gson.toJson(request)
            val requestBody = jsonBody.toRequestBody("application/json".toMediaType())
            
            val httpRequest = Request.Builder()
                .url("$baseUrl/auth/google")
                .post(requestBody)
                .build()
            
            val response = client.newCall(httpRequest).execute()
            val responseBody = response.body?.string()
            
            if (response.isSuccessful && responseBody != null) {
                val authResponse = gson.fromJson(responseBody, GoogleAuthResponse::class.java)
                Log.d(TAG, "Authentication successful for user: ${authResponse.email}")
                Result.success(authResponse)
            } else {
                val errorBody = responseBody ?: "Unknown error"
                Log.e(TAG, "Authentication failed: $errorBody")
                Result.failure(Exception("Authentication failed: ${response.code}"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Network error during authentication", e)
            Result.failure(e)
        }
    }
    
    /**
     * Validate an existing session token with the backend.
     */
    suspend fun validateSession(sessionToken: String): Result<Boolean> = withContext(Dispatchers.IO) {
        try {
            val httpRequest = Request.Builder()
                .url("$baseUrl/auth/validate")
                .addHeader("Authorization", "Bearer $sessionToken")
                .get()
                .build()
            
            val response = client.newCall(httpRequest).execute()
            Result.success(response.isSuccessful)
        } catch (e: Exception) {
            Log.e(TAG, "Session validation failed", e)
            Result.failure(e)
        }
    }
}
