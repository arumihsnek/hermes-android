package com.hermesandroid.bridge.auth

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class AuthApiClientTest {

    private lateinit var mockServer: MockWebServer

    @Before
    fun setup() {
        mockServer = MockWebServer()
        mockServer.start()
        // Point AuthApiClient to the mock server
        AuthApiClient.setBaseUrl(mockServer.url("/").toString())
    }

    @After
    fun tearDown() {
        mockServer.shutdown()
        // Reset to default for other tests
        AuthApiClient.resetBaseUrl()
    }

    @Test
    fun `authenticateWithGoogle returns success on valid response`() = runBlocking {
        // Given
        val responseBody = """
            {
                "session_token": "test_session_token",
                "user_id": "user123",
                "email": "test@example.com",
                "name": "Test User"
            }
        """.trimIndent()
        
        mockServer.enqueue(MockResponse()
            .setBody(responseBody)
            .setHeader("Content-Type", "application/json"))

        // When
        val result = AuthApiClient.authenticateWithGoogle(
            idToken = "google_id_token",
            email = "test@example.com",
            name = "Test User"
        )

        // Then
        assertTrue(result.isSuccess)
        val authResponse = result.getOrNull()
        assertNotNull(authResponse)
        assertEquals("test_session_token", authResponse?.sessionToken)
        assertEquals("user123", authResponse?.userId)
        assertEquals("test@example.com", authResponse?.email)
        assertEquals("Test User", authResponse?.name)
    }

    @Test
    fun `authenticateWithGoogle returns failure on error response`() = runBlocking {
        // Given
        mockServer.enqueue(MockResponse()
            .setResponseCode(400)
            .setBody("""{"error": "Invalid token"}"""))

        // When
        val result = AuthApiClient.authenticateWithGoogle(
            idToken = "invalid_token",
            email = "test@example.com",
            name = "Test User"
        )

        // Then
        assertTrue(result.isFailure)
    }

    @Test
    fun `authenticateWithGoogle returns failure on network error`() = runBlocking {
        // Given
        mockServer.shutdown() // Shutdown server to simulate network error

        // When
        val result = AuthApiClient.authenticateWithGoogle(
            idToken = "google_id_token",
            email = "test@example.com",
            name = "Test User"
        )

        // Then
        assertTrue(result.isFailure)
    }
}
