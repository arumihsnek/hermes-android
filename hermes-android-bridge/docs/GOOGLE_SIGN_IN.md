# Google Sign-In Implementation

## Overview

This document describes the Google Sign-In implementation for the Hermes Android Bridge app.

## Setup Instructions

### 1. Configure OAuth2 Client ID

Before using Google Sign-In, you need to:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sign-In API
4. Create OAuth2 credentials (Web application type)
5. Note down the Web Client ID

### 2. Update strings.xml

Edit `app/src/main/res/values/strings.xml` and replace `YOUR_WEB_CLIENT_ID.apps.googleusercontent.com` with your actual Web Client ID:

```xml
<string name="google_web_client_id">YOUR_ACTUAL_CLIENT_ID.apps.googleusercontent.com</string>
```

### 3. Configure google-services.json (Optional)

If you want to use other Google services, download `google-services.json` from the Google Cloud Console and place it in the `app/` directory.

### 4. Build and Run

Build the app normally:

```bash
cd hermes-android-bridge
./gradlew assembleDebug
```

## Features

### 1. Google Sign-In Button

- Located at the top of the main screen
- Shows "Sign in with Google" button
- Tapping opens Google account picker

### 2. Session Management

- Stores session token securely in SharedPreferences
- Remembers signed-in state across app restarts
- Shows user email when signed in

### 3. Backend Integration

- Calls `POST /auth/google` with Google ID token
- Backend validates token and returns session token
- Session token stored for subsequent API calls

### 4. Logout

- Clears stored session data
- Signs out from Google
- Returns to sign-in state

## API Integration

The app communicates with the backend at `http://localhost:8765` (default bridge server URL).

### POST /auth/google

**Request:**
```json
{
  "id_token": "google_id_token",
  "email": "user@example.com",
  "name": "User Name"
}
```

**Response:**
```json
{
  "session_token": "backend_session_token",
  "user_id": "user_id",
  "email": "user@example.com",
  "name": "User Name"
}
```

## File Structure

```
app/src/main/kotlin/com/hermesandroid/bridge/
├── auth/
│   ├── GoogleSignInManager.kt    # Google Sign-In flow management
│   ├── AuthApiClient.kt          # Backend API client
│   └── PairingManager.kt         # Existing pairing code manager
├── MainActivity.kt               # Main activity with Google Sign-In UI
└── ...
```

## Error Handling

### Google Sign-In Errors

- **Error 12501**: User cancelled sign-in
- **Other errors**: Shows generic error message

### Backend Errors

- Network errors: Shows "Authentication failed" message
- Invalid token: Shows error from backend
- Server errors: Shows generic error message

## Security Notes

1. **Token Storage**: Session tokens are stored in SharedPreferences. For production, consider using EncryptedSharedPreferences.

2. **Token Validation**: The backend should validate Google ID tokens using Google's token verification endpoint.

3. **HTTPS**: In production, ensure the backend uses HTTPS.

4. **Client ID Security**: The Web Client ID is safe to include in the app since it's not a secret.

## Testing

### Test Google Sign-In

1. Build and install the app
2. Tap "Sign in with Google"
3. Select a Google account
4. App should show email and "Signed in" status

### Test Logout

1. While signed in, tap "Logout"
2. App should clear session and show sign-in button

## Troubleshooting

### "Google Sign-In failed"

1. Verify Web Client ID in `strings.xml`
2. Check Google Cloud Console for correct OAuth2 credentials
3. Ensure Google Play Services is installed on device

### "Authentication failed"

1. Check backend server is running
2. Verify backend endpoint `POST /auth/google` exists
3. Check network connectivity

### Button not visible

1. Check if `googleSignInSection` is visible in layout
2. Verify layout XML changes are applied
