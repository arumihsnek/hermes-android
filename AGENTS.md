# hermes-android

## Overview
This extension adds Android device control to hermes-agent via the `android` toolset.
It communicates with a bridge app running on an Android device over HTTP/WebSocket.

## Architecture (fork v0.4.0-fork)
```
Phone ──WebSocket──▶ Relay (systemd:8766) ──HTTP──▶ Agent
                           │
                    on-demand (BroadcastReceiver)
                    no ADB/Tailscale required
                    auto-connect via preference
                    unlock via Shizuku (wm dismiss-keyguard)
```

## Setup
1. Install the bridge APK on the Android device
2. Grant permissions (auto-granted via Shizuku if available):
   - Accessibility Service
   - System Alert Window (Overlay)
   - Screen Recording (MediaProjection)
3. Enable Auto-connect Relay toggle in app
4. Start relay on server: `setup-hermes-relay --start`
5. Verify: `hermes-phone status`

## Intent-Based Control
The app responds to broadcast intents (no UI interaction required):
```bash
# Start relay
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.START --es server <HOST:PORT>

# Stop relay
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.STOP

# Check status
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.STATUS

# Enable accessibility
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.ENABLE_A11Y

# Start screen recording
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.START_SCREEN_RECORD

# Stop screen recording
adb shell am broadcast -n com.hermesandroid.bridge/.service.RelayIntentReceiver \
  -a com.hermesandroid.bridge.STOP_SCREEN_RECORD
```

## HTTP Bridge Endpoints (direct or via relay)
```
POST /unlock    — wake + dismiss keyguard
POST /shell     — run shell command
POST /tap       — tap coordinates
POST /type      — type text
POST /swipe     — swipe direction
GET  /ping      — check connection
GET  /screen    — accessibility tree
GET  /screenshot — capture screen
GET  /apps      — list installed apps
POST /intent    — send Android intent
POST /broadcast — send broadcast intent
```

## Shell Backends
| Backend | Privilege | Requirements |
|---------|-----------|-------------|
| `app` | App sandbox | None (always available) |
| `shizuku` | shell/ADB (UID 2000) | Shizuku installed + permission |
| `termux` | Termux user | Termux + allow-external-apps |
| `root` | root | Rooted device |

## Permissions
| Permission | How to Grant | Required For |
|------------|-------------|--------------|
| Accessibility | App button → Settings > Accessibility | All tools |
| Overlay | App button → Settings > Draw over apps | Status overlay |
| Screen Recording | App button → approve dialog | Screen recording |
| Location | Settings > Permissions > Location | Location |
| Contacts | Settings > Permissions > Contacts | Search contacts |
| SMS | Settings > Permissions > SMS | Send SMS |
| Phone | Settings > Permissions > Phone | Make calls |
| Notification Listener | Settings > Special access > Notification access | Read notifications |

## Tool usage patterns

### Read before act
ALWAYS call android_read_screen before tapping. Never guess coordinates.

### Prefer text over coordinates
Use android_tap_text("Continue") over android_tap(x=540, y=1200).

### Wait after navigation
After opening an app or tapping a button that triggers loading,
always call android_wait with expected text before next action.

### Use unlock before interaction
```bash
POST /unlock  # wake screen + dismiss keyguard first
POST /shell   # then interact
```
