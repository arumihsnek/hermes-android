package com.hermesandroid.bridge.auth

import android.util.Log
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * OkHttp Interceptor that handles automatic token attachment and 401 refresh-retry.
 *
 * Behaviour:
 * 1. Every outgoing request gets an Authorization header from BridgeTokenStorage.
 * 2. On a 401 response, the interceptor calls /auth/refresh with the stored refresh token.
 * 3. If refresh succeeds, new tokens are saved and the original request is retried once.
 * 4. Concurrent 401s are serialised via a Mutex so only one refresh call runs at a time.
 * 5. If refresh fails, [BridgeLogoutListener.onLogoutRequired] is invoked and the 401 is returned as-is.
 *
 * Usage:
 * ```
 * val authClient = BridgeAuthInterceptor.createClient(
 *     tokenStorage = BridgeTokenStorage.getInstance(context),
 *     baseUrl      = "http://localhost:8765",
 *     onLogout     = { /* navigate to login */ }
 * )
 * ```
 */
class BridgeAuthInterceptor private constructor(
    private val tokenStorage: BridgeTokenStorageInterface,
    private val baseUrl: String,
    private val onLogout: BridgeLogoutListener?
) : Interceptor {

    companion object {
        private const val TAG = "BridgeAuthInterceptor"
        private const val HEADER_AUTH="Authorization"
        private const val HEADER_BEARER = "Bearer "
        private const val CONNECT_TIMEOUT_SECONDS = 15L
        private const val READ_TIMEOUT_SECONDS = 30L
        private const val WRITE_TIMEOUT_SECONDS = 30L

        /**
         * Create an OkHttpClient pre-configured with [BridgeAuthInterceptor].
         */
        fun createClient(
            tokenStorage: BridgeTokenStorageInterface,
            baseUrl: String,
            onLogout: BridgeLogoutListener? = null,
            connectTimeout: Long = CONNECT_TIMEOUT_SECONDS,
            readTimeout: Long = READ_TIMEOUT_SECONDS,
            writeTimeout: Long = WRITE_TIMEOUT_SECONDS
        ): OkHttpClient {
            val interceptor = BridgeAuthInterceptor(tokenStorage, baseUrl, onLogout)
            return OkHttpClient.Builder()
                .addInterceptor(interceptor)
                .connectTimeout(connectTimeout, TimeUnit.SECONDS)
                .readTimeout(readTimeout, TimeUnit.SECONDS)
                .writeTimeout(writeTimeout, TimeUnit.SECONDS)
                .build()
        }
    }

    /** Serialises concurrent refresh attempts — only one 401 triggers a token refresh. */
    private val refreshMutex = Mutex()

    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()

        // Skip auth header for the refresh endpoint itself to avoid infinite loops
        if (originalRequest.url.encodedPath.endsWith("/auth/refresh")) {
            return chain.proceed(originalRequest)
        }

        // 1. Attach token
        val token = tokenStorage.getToken()
        val request = if (!token.isNullOrBlank()) {
            originalRequest.newBuilder()
                .header(HEADER_AUTH, "$HEADER_BEARER$token")
                .build()
        } else {
            originalRequest
        }

        // 2. Execute request
        val response = chain.proceed(request)

        // 3. On 401 — attempt refresh
        if (response.code == 401) {
            Log.w(TAG, "Got 401 on ${originalRequest.url.encodedPath} — attempting refresh")
            response.close()

            return runBlocking {
                val refreshed = attemptTokenRefresh()

                if (refreshed) {
                    // Retry original request with the new token
                    val newToken = tokenStorage.getToken()
                    val retryRequest = if (!newToken.isNullOrBlank()) {
                        originalRequest.newBuilder()
                            .header(HEADER_AUTH, "$HEADER_BEARER$newToken")
                            .build()
                    } else {
                        originalRequest
                    }
                    Log.i(TAG, "Token refreshed — retrying ${originalRequest.url.encodedPath}")
                    chain.proceed(retryRequest)
                } else {
                    // Refresh failed — notify logout
                    Log.e(TAG, "Token refresh failed — clearing tokens, notifying logout")
                    tokenStorage.clearToken()
                    onLogout?.onLogoutRequired()
                    // Return a synthetic 401 so the caller sees the failure
                    originalResponse(originalRequest, 401)
                }
            }
        }

        return response
    }

    /**
     * Serialised token refresh. Mutex ensures only one concurrent refresh runs.
     * Returns true if a new access token was obtained and saved.
     */
    private suspend fun attemptTokenRefresh(): Boolean = refreshMutex.withLock {
        val refreshToken = tokenStorage.getRefreshToken()
        if (refreshToken.isNullOrBlank()) {
            Log.w(TAG, "No refresh token available")
            return@withLock false
        }

        try {
            val refreshClient = OkHttpClient.Builder()
                .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .writeTimeout(WRITE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
                .build()

            val body = JSONObject().apply {
                put("refresh_token", refreshToken)
            }.toString()

            val refreshRequest = Request.Builder()
                .url("$baseUrl/auth/refresh")
                .post(body.toRequestBody("application/json".toMediaType()))
                .build()

            val refreshResponse = refreshClient.newCall(refreshRequest).execute()

            if (refreshResponse.isSuccessful) {
                val responseBody = refreshResponse.body?.string()
                if (responseBody != null) {
                    val json = JSONObject(responseBody)
                    val newAccessToken = json.optString("access_token", "")
                    val newRefreshToken = json.optString("refresh_token", "")
                    val expiresIn = json.optLong("expires_in", 0L)

                    if (newAccessToken.isNotBlank()) {
                        val expiryMillis = if (expiresIn > 0) {
                            System.currentTimeMillis() + (expiresIn * 1000)
                        } else {
                            null
                        }
                        tokenStorage.saveToken(
                            accessToken = newAccessToken,
                            refreshToken = if (newRefreshToken.isNotBlank()) newRefreshToken else refreshToken,
                            expiryMillis = expiryMillis
                        )
                        Log.i(TAG, "Token refreshed successfully (expires_in=${expiresIn}s)")
                        return@withLock true
                    }
                }
            }

            Log.e(TAG, "Refresh request failed: ${refreshResponse.code}")
            refreshResponse.close()
            return@withLock false

        } catch (e: IOException) {
            Log.e(TAG, "Network error during token refresh", e)
            return@withLock false
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error during token refresh", e)
            return@withLock false
        }
    }

    /**
     * Build a synthetic OkHttp Response for error paths where we need to return
     * a Response object but the original was already closed.
     */
    private fun originalResponse(request: Request, code: Int): Response {
        val emptyBody = ByteArray(0).toResponseBody(null)
        return Response.Builder()
            .request(request)
            .protocol(okhttp3.Protocol.HTTP_1_1)
            .code(code)
            .message("Unauthorized")
            .body(emptyBody)
            .build()
    }
}

/**
 * Callback interface for when a refresh failure requires the app to log the user out.
 */
fun interface BridgeLogoutListener {
    fun onLogoutRequired()
}