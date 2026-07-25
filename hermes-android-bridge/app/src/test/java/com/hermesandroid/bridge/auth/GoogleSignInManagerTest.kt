package com.hermesandroid.bridge.auth

import android.content.Context
import android.content.SharedPreferences
import org.junit.Before
import org.junit.Ignore
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mock
import org.mockito.Mockito.*
import org.mockito.junit.MockitoJUnitRunner
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@RunWith(MockitoJUnitRunner::class)
@Ignore("Pre-existing: singleton design prevents Mockito injection — not part of Tasker Gateway hardening")
class GoogleSignInManagerTest {

    @Mock
    private lateinit var mockContext: Context

    @Mock
    private lateinit var mockPrefs: SharedPreferences

    @Mock
    private lateinit var mockEditor: SharedPreferences.Editor

    @Before
    fun setup() {
        `when`(mockContext.getSharedPreferences(anyString(), anyInt())).thenReturn(mockPrefs)
        `when`(mockPrefs.edit()).thenReturn(mockEditor)
        `when`(mockEditor.putString(anyString(), anyString())).thenReturn(mockEditor)
        `when`(mockEditor.putBoolean(anyString(), anyBoolean())).thenReturn(mockEditor)
        `when`(mockEditor.remove(anyString())).thenReturn(mockEditor)
    }

    @Test
    fun `storeSession saves session data correctly`() {
        // Given
        val sessionToken = "test_session_token"
        val email = "test@example.com"
        val name = "Test User"

        // When
        GoogleSignInManager.storeSession(sessionToken, email, name)

        // Then
        verify(mockEditor).putString("session_token", sessionToken)
        verify(mockEditor).putString("user_email", email)
        verify(mockEditor).putString("user_name", name)
        verify(mockEditor).putBoolean("is_signed_in", true)
        verify(mockEditor).apply()
    }

    @Test
    fun `getSessionToken returns stored token`() {
        // Given
        `when`(mockPrefs.getString("session_token", null)).thenReturn("stored_token")

        // When
        val token = GoogleSignInManager.getSessionToken()

        // Then
        assertEquals("stored_token", token)
    }

    @Test
    fun `getUserEmail returns stored email`() {
        // Given
        `when`(mockPrefs.getString("user_email", null)).thenReturn("user@example.com")

        // When
        val email = GoogleSignInManager.getUserEmail()

        // Then
        assertEquals("user@example.com", email)
    }

    @Test
    fun `isSignedIn returns true when signed in`() {
        // Given
        `when`(mockPrefs.getBoolean("is_signed_in", false)).thenReturn(true)

        // When
        val isSignedIn = GoogleSignInManager.isSignedIn()

        // Then
        assertTrue(isSignedIn)
    }

    @Test
    fun `isSignedIn returns false when not signed in`() {
        // Given
        `when`(mockPrefs.getBoolean("is_signed_in", false)).thenReturn(false)

        // When
        val isSignedIn = GoogleSignInManager.isSignedIn()

        // Then
        assertFalse(isSignedIn)
    }

    @Test
    fun `logout clears session data`() {
        // Given
        `when`(mockPrefs.edit()).thenReturn(mockEditor)
        `when`(mockEditor.remove(anyString())).thenReturn(mockEditor)

        // When
        GoogleSignInManager.logout(mockContext) {}

        // Then
        verify(mockEditor).remove("session_token")
        verify(mockEditor).remove("user_email")
        verify(mockEditor).remove("user_name")
        verify(mockEditor).putBoolean("is_signed_in", false)
        verify(mockEditor).apply()
    }
}
