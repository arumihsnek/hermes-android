# Requirements: Hermes Android Capability System

## Context
The hermes-android bridge (v0.4.0-fork) currently has 38 tools that directly control an Android phone via HTTP/WebSocket. The current `android_macro` tool runs a simple sequential list of steps with no verification, no branching, no typed extras, and no learning from failures.

This specification designs a **general capability system** so Hermes can execute natural-language Android requests, discover how to perform unknown tasks autonomously, verify completion, and retain learned routes for reuse.

## Core Architecture

### 1. Capability System (Semantic, not phrase-based)
Capabilities are the fundamental unit. A request composes capabilities. Examples:
- `podcast.search`, `podcast.episode.resolve`, `podcast.subscribe`, `media.play`, `media.verify_playback`
- `contact.resolve`, `message.compose`, `message.send`, `message.verify_sent`
- `timer.set`, `alarm.set`, `location.current`, `place.resolve`, `place.save`
- `route.plan`, `route.launch`, `route.with_stop`
- `updates.pause`, `updates.resume`
- `catalog.search`, `content.resolve`, `content.rank`

A capability is NOT tied to an app name or button text. It's an abstract operation that can be implemented by multiple adapters.

### 2. Adapter System (per-application)
Each app (AntennaPod, Waze, WhatsApp, OsmAnd, etc.) has an adapter that maps capabilities to concrete implementations:
- intents, deep links, broadcasts, content providers, MediaSession, notifications, accessibility, shell
- Each adapter declares supported capabilities, required permissions, package name, version constraints
- Adapters are versioned and fingerprint-aware

### 3. Recipe Registry (YAML/JSON validated)
Recipes are learned, verified routes for specific capability+adapter combinations. Format:
```yaml
id: "antennapod.podcast.subscribe.v1"
capability: podcast.subscribe
adapter: antennapod
package: de.danoeh.antennapod
android_version: ">=12"
device_class: pixel
preconditions:
  - antennapod_installed: true
permissions:
  - INTERNET
method: deeplink
steps:
  - action: intent
    params:
      action: android.intent.action.VIEW
      dataUri: "https://antennapod.org/deeplink/subscribe?url={feed_url}"
  - action: verify
    params:
      method: notification
      pattern: "Subscribed to {podcast_name}"
fallbacks:
  - method: ui_automation
    steps: [...]
maturity: stable  # discovered | candidate | dogfood | stable | suspect | quarantined | deprecated
metrics:
  success_count: 15
  failure_count: 1
  avg_latency_ms: 2300
  last_validated: "2026-07-23"
  model_calls: 0
  screenshot_required: false
```

### 4. android_flow (evolution of android_macro)
New tool that replaces/extends android_macro. Must support:
- Typed extras (string, integer, boolean, float, URI, basic arrays)
- Variables and results reusable between steps
- Conditions and branches
- Event/predicate-based waits (not fixed sleeps)
- Per-step and global timeouts
- Semantic verifiers
- Limited local retries
- Explicit fallbacks
- Cancellation
- Idempotence
- Evidence capture only on failure
- Structured error classification
- Traces and metrics
- Unambiguous final result

A single call must express: execute action → wait for transition → verify result → apply limited fallback → return success/failure with evidence.

### 5. Observer Policy (minimum sufficient observation)
For each step, choose the cheapest observer:
1. Direct state query (if available)
2. Events/listeners for async transitions
3. MediaSession for playback
4. Notifications for app-exposed state
5. Selective node search (android_find_nodes)
6. Screen hash/diff for change detection
7. Full accessibility tree (when structure unknown)
8. Screenshot (when accessibility doesn't represent content)
9. Screen recording (diagnostic only)

Must measure on Pixel 8: latency, response size, model calls, success rate, false positives, context consumption, fragility.

### 6. Negative Learning
Record methods that don't work:
- Unsupported intent, ignored extra, non-exported component
- Missing permission, dee link only opens app
- Ambiguous selector, element without accessibility
- Insufficient wait, false positive verifier
- Version-blocked action, language-dependent behavior
- Session/state-dependent flow, confirmation-required route

Each entry: capability, app, fingerprint, method tried, evidence, failure class, date, re-test condition.

### 7. Typed Intent Extras
Extend android_send_intent to support:
- string, integer, boolean, float, URI
- Basic arrays only when real case exists
- Strict validation between Python, WebSocket, and Kotlin
- First dogfood: Android timer via standard intent

### 8. Discovery Protocol (for unknown routes)
1. Identify capability/composition
2. Check direct tools available
3. Identify installed package
4. Inspect manifest, exported components, intent filters, shortcuts, services, permissions
5. Check docs/source when relevant
6. Try non-visual, reversible routes first
7. Verify each hypothesis
8. Don't retry routes registered as incompatible for same fingerprint
9. If no direct integration, explore UI with selective accessibility
10. Use vision only when accessibility lacks info
11. When route found, create candidate recipe
12. Run dogfood before promotion
13. Record why it works, how to verify, when to invalidate

### 9. Safety and Confirmations
- User's explicit order authorizes ordinary, reversible, clearly bounded actions
- Require confirmation for: payment, purchase, public posting, mass send, ambiguous recipient, deletion, irreversible modification, security changes, device-locking actions, privilege escalation
- WhatsApp: resolve contact → compose → open conversation → send → verify sent (never claim sent without evidence)

## Verticals (Implementation Order)

### Vertical 1: Timers
- Typed intents
- Required permissions
- Action + verification in single call
- Unit and contract tests
- Real dogfood on Pixel 8
- Timer creation evidence

### Vertical 2: Media Search & Playback
- General search, playback, verification capabilities
- Test: AntennaPod, WizeStream/NewPipe Material
- Explore: multimedia intents, MEDIA_PLAY_FROM_SEARCH, deep links, MediaSession, notification controls
- Verify via media state and metadata, not just visible UI

### Vertical 3: Podcast Subscription & Resolution
- External/internal search, feed resolution, podcast selection
- Subscription opening, confirmation, verification
- Test single subscription and small list
- Content classification is a separate capability (not hardcoded list)

### Vertical 4: Messaging (WhatsApp)
- Contact resolution, composition, conversation opening, send, verification
- Controlled dogfood, no unauthorized test messages
- Safe test route or stop before send without explicit content authorization

### Vertical 5: Composite Navigation (Waze)
- Destination resolution, route estimation, stop search
- Two segments or app's stop function
- Navigation start, destination and stop verification
- Simple route first, then composite variant

### Vertical 6: Save Location (OsmAnd)
- Get current location, open/represent point
- Use direct integration if available
- Minimal UI recipe as fallback
- Verify favorite created
- Consider GPX import only if more robust

### Vertical 7: Pause Updates
- Define what pausing means per subsystem (Play Store, system updates, scheduled jobs)
- Detect actual capabilities (bridge, Device Owner, Dhizuku, Shizuku, shell)
- Return explicit, verifiable limitations

## Constraints
- Backward compatible with existing 38 android_* tools
- Don't replace functional routes with theoretically better abstractions without comparative tests
- Don't declare external actions complete just because an app opened
- Use codex-plan-relay for plan generation, codex-review-relay for review
- TDD for deterministic components (schemas, validators, parsers, serialization)
- Contract tests: Python→WebSocket, WebSocket→Kotlin, Kotlin→response
- Real dogfood for app-dependent behavior (mocks don't substitute real app intents, playback, messaging, navigation, favorites, permissions, accessibility behavior)
