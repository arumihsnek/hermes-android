---
# Implementation Plan: Hermes Android Capability System

## Overview

Build an additive capability layer above the existing `android_*` tools: semantic capabilities select fingerprint-aware app adapters and validated recipes, while `android_flow` executes verified, bounded flows with structured outcomes. Existing tools and `android_macro` remain backward compatible.

Deliver the system in vertical slices, beginning with typed intents and timers, then media, podcasts, messaging, navigation, saved locations, and update-pausing. Every external action requires evidence-based verification before it is reported complete.

## Prerequisites

- Python 3.11 with `pytest`, `responses`, and the project editable-installed.
- Android Studio/SDK, a connected Pixel 8, Shizuku where privileged capabilities are tested, and the bridge APK installed.
- Access to AntennaPod, WizeStream or NewPipe Material, WhatsApp, Waze, and OsmAnd test accounts/data.
- A non-production WhatsApp recipient or a route that stops before send.
- `codex-plan-relay` and `codex-review-relay` exposed to the implementation environment; they are required review gates.
- A controlled recipe-storage location with no user secrets, contact data, or screenshots committed.

## Tasks

### Task 1: Establish capability-system contracts and repository layout
- **Files**: `docs/capabilities/architecture.md` (create), `tools/capabilities/__init__.py` (create), `tools/capabilities/models.py` (create), `tools/capabilities/errors.py` (create), `tools/capabilities/registry.py` (create), `tests/capabilities/test_models.py` (create), `README.md` (modify)
- **Description**: Define versioned dataclasses/Pydantic-equivalent validation for `CapabilityRequest`, `CapabilityResult`, `DeviceFingerprint`, `AdapterDescriptor`, `Recipe`, `FlowTrace`, `Evidence`, and stable failure classes. Create the package boundaries for capability orchestration, adapters, recipes, observers, discovery, and policy; document that capability names are semantic and app-independent.
- **Tests**: Validate valid and invalid capability names, fingerprint serialization, required result status/evidence fields, maturity transitions, and unknown schema-version rejection.
- **Dependencies**: none

### Task 2: Define strict typed-intent wire schema
- **Files**: `tools/capabilities/intent_schema.py` (create), `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/model/TypedIntentExtra.kt` (create), `tests/capabilities/test_intent_schema.py` (create), `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/model/TypedIntentExtraTest.kt` (create)
- **Description**: Define a shared JSON representation for `string`, `integer`, `boolean`, `float`, `uri`, and intentionally limited homogeneous basic arrays. Reject unknown types, null values, mixed arrays, invalid URI values, integer overflow, and nested object extras. Specify that legacy `Map<String, String>` input remains accepted and is normalized to typed strings.
- **Tests**: Python and Kotlin tests must accept every supported type and reject identical malformed fixtures with the same stable error code.
- **Dependencies**: Task 1

### Task 3: Implement typed intents through Python, relay, WebSocket, and Kotlin
- **Files**: `tools/android_tool.py` (modify), `hermes-android-plugin/android_tool.py` (modify), `tools/android_relay.py` (modify if route validation is added), `hermes-android-plugin/android_relay.py` (modify if route validation is added), `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/server/BridgeRouter.kt` (modify), `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/executor/ActionExecutor.kt` (modify), `tests/test_android_tool.py` (modify), `tests/test_android_relay.py` (modify), `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/server/BridgeRouterIntentTest.kt` (create), `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/executor/ActionExecutorIntentTest.kt` (create)
- **Description**: Extend `android_send_intent` with typed extras while preserving its existing call shape. Deserialize and validate the schema at the bridge boundary, map each type to the corresponding Android `Intent.putExtra` overload, and return a structured result naming accepted/rejected extras without exposing sensitive values. Keep `tools/` and `hermes-android-plugin/` copies synchronized.
- **Tests**: Contract fixtures must prove Python payload → relay WebSocket body → Kotlin request → `Intent` extra type → structured response. Existing legacy string-extra tests must remain unchanged and pass.
- **Dependencies**: Task 2

### Task 4: Add bridge observers required for semantic verification
- **Files**: `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/observer/MediaSessionObserver.kt` (create), `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/observer/NotificationObserver.kt` (create), `hermes-android-bridge/app/src/main/kotlin/com/hermesandroid/bridge/server/BridgeRouter.kt` (modify), `tools/android_tool.py` (modify), `hermes-android-plugin/android_tool.py` (modify), `tests/test_android_tool.py` (modify), `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/observer/MediaSessionObserverTest.kt` (create), `hermes-android-bridge/app/src/test/kotlin/com/hermesandroid/bridge/observer/NotificationObserverTest.kt` (create)
- **Description**: Expose read-only media-session and notification queries, with package filtering and bounded metadata. Reuse existing event, selective-node, screen-hash, accessibility-tree, screenshot, and recording capabilities; do not add screenshot capture to successful flows.
- **Tests**: Verify each endpoint returns normalized success/failure data, honors package filters, bounds response size, and never returns screenshot/recording evidence unless explicitly requested for a failure diagnostic.
- **Dependencies**: Task 1

### Task 5: Create `android_flow` schema, validator, and compatibility boundary
- **Files**: `tools/capabilities/flow_schema.py` (create), `tools/capabilities/flow_validator.py` (create), `tools/android_tool.py` (modify), `hermes-android-plugin/android_tool.py` (modify), `tests/capabilities/test_flow_schema.py` (create), `tests/test_android_tool.py` (modify), `README.md` (modify)
- **Description**: Add `android_flow` without replacing `android_macro`. Define actions, typed parameters, variable references, result bindings, conditional branches, per-step/global timeout, cancellation token, bounded retry, explicit fallback, idempotence key, verifier declarations, and a single final `CapabilityResult`.
- **Tests**: Reject unknown actions, forward variable references, unbounded retry, sleep-only waits, recursive fallback, missing verifier, duplicate bindings, and invalid timeout values. Prove existing `android_macro` behavior is unchanged.
- **Dependencies**: Tasks 1, 3

### Task 6: Implement the deterministic flow executor and trace model
- **Files**: `tools/capabilities/flow_executor.py` (create), `tools/capabilities/trace.py` (create), `tools/capabilities/flow_actions.py` (create), `tests/capabilities/test_flow_executor.py` (create)
- **Description**: Execute validated flows against a narrow adapter over existing `android_*` handlers. Support variable interpolation, branch predicates, deadline propagation, cancellation, local retry limits, declared fallbacks, idempotence lookup, and ordered trace events. Return only `success`, `failure`, or `cancelled`; never infer completion from an app opening.
- **Tests**: Deterministic fake-handler tests must cover success, timeout, cancellation, retry exhaustion, fallback success, fallback exhaustion, idempotence replay, branch selection, and evidence-free success traces.
- **Dependencies**: Task 5

### Task 7: Implement observer selection and semantic verifiers
- **Files**: `tools/capabilities/observers.py` (create), `tools/capabilities/verifiers.py` (create), `tools/capabilities/evidence.py` (create), `tests/capabilities/test_observers.py` (create), `tests/capabilities/test_verifiers.py` (create)
- **Description**: Encode the minimum-sufficient observer order: direct query, event, media session, notification, node search, hash/diff, tree, screenshot, recording. Add reusable verifiers for timer existence, media state/metadata, notification pattern, node predicate, screen transition, contact/conversation, sent-message state, route destination/stop, and saved favorite.
- **Tests**: Prove the executor chooses the cheapest eligible observer, escalates only after a lower-cost verifier is unavailable/inconclusive, captures screenshot/recording only after failure, and rejects false-positive “app opened” results.
- **Dependencies**: Tasks 4, 6

### Task 8: Add recipe registry, adapter registry, fingerprints, and maturity rules
- **Files**: `tools/capabilities/adapters/base.py` (create), `tools/capabilities/adapters/registry.py` (create), `tools/capabilities/recipes/loader.py` (create), `tools/capabilities/recipes/validator.py` (create), `recipes/schema.json` (create), `recipes/` (create), `tests/capabilities/test_recipe_registry.py` (create), `tests/capabilities/test_adapter_registry.py` (create)
- **Description**: Load YAML/JSON recipes, validate them against the schema, select adapters by supported capability/package/version/fingerprint, and enforce maturity states: `discovered`, `candidate`, `dogfood`, `stable`, `suspect`, `quarantined`, `deprecated`. Resolve only compatible stable/dogfood routes by default.
- **Tests**: Validate sample recipe parsing, invalid schema rejection, version/fingerprint mismatch exclusion, deterministic adapter precedence, and refusal to execute quarantined/deprecated recipes.
- **Dependencies**: Tasks 1, 5

### Task 9: Record metrics, negative learning, and recipe promotion evidence
- **Files**: `tools/capabilities/metrics.py` (create), `tools/capabilities/negative_learning.py` (create), `tools/capabilities/recipe_lifecycle.py` (create), `recipes/negative-learning.schema.json` (create), `tests/capabilities/test_recipe_lifecycle.py` (create), `docs/capabilities/recipe-lifecycle.md` (create)
- **Description**: Persist redacted traces, latency, response size, model-call count, observer choice, success/failure, false-positive assessment, context consumption, and fragility. Record incompatible routes by capability/app/fingerprint/method/failure/evidence/retest condition. Require a successful dogfood record before promotion and quarantine repeatedly failing routes.
- **Tests**: Verify incompatible routes are skipped for the same fingerprint, secret-like fields are redacted, promotion requires configured evidence, and failure classification is stable across serialization.
- **Dependencies**: Tasks 6, 8

### Task 10: Add safety and confirmation policy enforcement
- **Files**: `tools/capabilities/safety.py` (create), `tools/capabilities/policy.py` (create), `tests/capabilities/test_safety.py` (create), `docs/capabilities/safety.md` (create)
- **Description**: Classify each capability/action as ordinary reversible, confirmation-required, or prohibited. Require an explicit scoped authorization token for payments, purchases, public posts, mass sends, ambiguous recipients, deletions, irreversible modifications, security changes, lock actions, and privilege escalation. Require message-send verification before reporting success.
- **Tests**: Prove reversible, bounded actions proceed with an explicit user order; confirmation-required operations stop before dispatch without authorization; expired/mismatched authorization is rejected; WhatsApp send cannot return success without a sent-state verifier.
- **Dependencies**: Tasks 1, 6, 7

### Task 11: Implement discovery protocol and candidate-recipe generation
- **Files**: `tools/capabilities/discovery.py` (create), `tools/capabilities/manifest_inspector.py` (create), `tools/capabilities/discovery_store.py` (create), `tests/capabilities/test_discovery.py` (create), `docs/capabilities/discovery-protocol.md` (create)
- **Description**: Implement the ordered discovery protocol: capability decomposition, direct-tool lookup, package/fingerprint inspection, manifest/intents/shortcuts/services/permissions inspection, reversible nonvisual hypotheses, verifier-backed experiments, negative-learning checks, selective accessibility exploration, vision only when needed, and candidate-recipe output.
- **Tests**: Fake-device tests must prove direct integration is tried before UI, registered incompatibilities prevent retries, UI exploration is not entered before nonvisual routes fail, and discovery produces a candidate recipe plus invalidation conditions.
- **Dependencies**: Tasks 7, 8, 9, 10

### Task 12: Expose capability execution and discovery tools
- **Files**: `tools/android_tool.py` (modify), `hermes-android-plugin/android_tool.py` (modify), `tools/capabilities/service.py` (create), `tests/test_android_tool.py` (modify), `tests/capabilities/test_service.py` (create), `README.md` (modify), `skills/android/SKILL.md` (modify)
- **Description**: Register `android_execute_capability`, `android_discover_capability`, `android_flow`, and read-only recipe/status inspection tools. Each execution must return selected adapter/recipe, final verifier, trace ID, metrics, classification, and failure evidence when applicable; preserve all existing tool definitions.
- **Tests**: Tool-registration tests must verify schemas and handlers; an end-to-end mocked request must select an adapter, execute a flow, and return an unambiguous result. Existing 38-tool regression suite must pass.
- **Dependencies**: Tasks 6, 8, 10, 11

### Task 13: Deliver Vertical 1 — standard Android timers
- **Files**: `tools/capabilities/adapters/android_clock.py` (create), `recipes/android-clock.timer.set.v1.yaml` (create), `tests/capabilities/test_android_clock_timer.py` (create), `docs/capabilities/dogfood/timers.md` (create)
- **Description**: Implement `timer.set` with typed standard Android timer extras, a direct timer-state/notification verifier, idempotence by requested label/duration, and a fallback that does not claim success merely because the Clock app opened.
- **Tests**: Contract tests must prove integer and string timer extras cross every layer. Pixel 8 dogfood must create a timer, capture the verifier’s timer evidence, record latency/response size/model calls, and add a signed-off dogfood recipe record.
- **Dependencies**: Tasks 3, 7, 8, 9, 12

### Task 14: Deliver Vertical 2 — media search, playback, and verification
- **Files**: `tools/capabilities/adapters/media_common.py` (create), `tools/capabilities/adapters/antennapod.py` (create), `tools/capabilities/adapters/wizestream.py` (create), `tools/capabilities/adapters/newpipe_material.py` (create), `recipes/media.*.yaml` (create), `tests/capabilities/test_media_adapters.py` (create), `docs/capabilities/dogfood/media.md` (create)
- **Description**: Implement `catalog.search`, `content.resolve`, `content.rank`, `media.play`, and `media.verify_playback`; prioritize media intents/deep links and verify via MediaSession state and metadata, then notification/UI fallback.
- **Tests**: Adapter tests must show app-specific selection from one semantic request. Pixel 8 dogfood for AntennaPod and one WizeStream/NewPipe variant must prove requested media title and playback state, not only a launched app.
- **Dependencies**: Tasks 4, 7, 8, 9, 12

### Task 15: Deliver Vertical 3 — podcast resolution and subscription
- **Files**: `tools/capabilities/adapters/podcast_common.py` (create), `tools/capabilities/adapters/antennapod.py` (modify), `recipes/antennapod.podcast.*.yaml` (create), `tests/capabilities/test_podcast_adapters.py` (create), `docs/capabilities/dogfood/podcast-subscription.md` (create)
- **Description**: Implement `podcast.search`, `podcast.episode.resolve`, and `podcast.subscribe` with external/internal search, feed resolution, explicit selection, subscription verification, and candidate fallbacks. Keep content ranking/classification separate from subscription logic.
- **Tests**: Verify one podcast and a small selected list against fixture feeds; Pixel 8 dogfood must show each intended feed in AntennaPod’s subscribed state and record failures as negative learning.
- **Dependencies**: Tasks 8, 9, 12, 14

### Task 16: Deliver Vertical 4 — WhatsApp messaging with send controls
- **Files**: `tools/capabilities/adapters/whatsapp.py` (create), `recipes/whatsapp.message.compose.v1.yaml` (create), `recipes/whatsapp.message.send.v1.yaml` (create), `tests/capabilities/test_whatsapp_adapter.py` (create), `docs/capabilities/dogfood/whatsapp.md` (create)
- **Description**: Implement `contact.resolve`, `message.compose`, `message.send`, and `message.verify_sent` as separate steps. Resolve recipient ambiguity before composition; allow dogfood to stop at the composed conversation unless explicit content and recipient authorization is supplied.
- **Tests**: Tests must reject ambiguous contacts, unapproved send, and absent sent evidence. Controlled dogfood must either stop before send with a documented pending confirmation or verify a deliberately authorized safe test message.
- **Dependencies**: Tasks 7, 8, 9, 10, 12

### Task 17: Deliver Verticals 5 and 6 — Waze navigation and OsmAnd favorites
- **Files**: `tools/capabilities/adapters/waze.py` (create), `tools/capabilities/adapters/osmand.py` (create), `recipes/waze.route.*.yaml` (create), `recipes/osmand.place.save.v1.yaml` (create), `tests/capabilities/test_waze_adapter.py` (create), `tests/capabilities/test_osmand_adapter.py` (create), `docs/capabilities/dogfood/navigation.md` (create), `docs/capabilities/dogfood/saved-location.md` (create)
- **Description**: Implement destination resolution, route planning/launch/verification, then two-segment or stop-in-route navigation. Implement current-location retrieval and favorite creation with direct integration preferred over minimal UI fallback; evaluate GPX import only if measured more robust.
- **Tests**: Dogfood must prove destination and stop/second segment before claiming navigation started. OsmAnd dogfood must prove the saved favorite exists after the operation. Record observer metrics and any version-specific failures.
- **Dependencies**: Tasks 7, 8, 9, 10, 11, 12

### Task 18: Deliver Vertical 7 — explicitly limited update pausing
- **Files**: `tools/capabilities/adapters/updates.py` (create), `tests/capabilities/test_updates_adapter.py` (create), `docs/capabilities/updates-limitations.md` (create), `README.md` (modify)
- **Description**: Define separate capabilities for Play Store, system updates, and scheduled-job pausing. Detect available bridge/Device Owner/Dhizuku/Shizuku/shell authority before action; return explicit unsupported or confirmation-required results rather than simulated success.
- **Tests**: Matrix tests must show every unavailable authority produces a verifiable limitation, every destructive/security-changing route requests confirmation, and no route reports “paused” without a subsystem-specific state verifier.
- **Dependencies**: Tasks 4, 7, 9, 10, 12

### Task 19: Benchmark, review, and release the capability system
- **Files**: `tools/capabilities/benchmark.py` (create), `tests/capabilities/test_benchmark.py` (create), `docs/capabilities/pixel-8-benchmark.md` (create), `docs/capabilities/release-checklist.md` (create), `README.md` (modify)
- **Description**: Run the observer-policy benchmark on Pixel 8 for each completed vertical, measuring latency, response size, model calls, success rate, false positives, context consumption, and fragility. Run `codex-plan-relay` before implementation and `codex-review-relay` after the full test/dogfood evidence is assembled; address review findings before promotion to stable.
- **Tests**: Benchmark tests must produce machine-readable records with every required metric. Release review must verify schema compatibility, existing-tool regressions, recipe promotion evidence, negative-learning coverage, and no successful external action lacking a verifier.
- **Dependencies**: Tasks 13, 14, 15, 16, 17, 18

## Verification

- [ ] `pytest` passes, including capability schema, flow, adapter, safety, discovery, relay, and existing tool regressions.
- [ ] `./gradlew test` passes in `hermes-android-bridge`, including typed-intent and observer tests.
- [ ] Python → relay/WebSocket → Kotlin typed-extra contract fixtures pass for every supported type and malformed case.
- [ ] Existing `android_macro` and all prior `android_*` tool contracts remain compatible.
- [ ] Pixel 8 dogfood evidence exists for timers, media playback, podcast subscription, authorized-or-stopped messaging, navigation, and saved locations.
- [ ] Every promoted recipe has fingerprint constraints, verifier evidence, metrics, invalidation conditions, and no unredacted sensitive data.
- [ ] `codex-review-relay` reports no unresolved correctness, safety, or backward-compatibility finding.

## Risks

- Cross-stack schema drift: generate shared JSON fixtures and require Python/Kotlin contract tests in CI.
- App UI/API changes and OEM differences: fingerprint recipes, prefer nonvisual integrations, quarantine failures, and retain verified fallbacks.
- Android cannot reliably expose every target state: return `unsupported` or `inconclusive` rather than claiming completion.
- WhatsApp and update controls are safety-sensitive: require explicit scoped confirmation and preserve a stop-before-send route.
- Recipe YAML may accumulate sensitive user data: redact evidence, prohibit secrets/contact payloads in committed recipes, and retain only bounded diagnostics.
- “Pause updates” is ambiguous across Play Store, system, and scheduled jobs: define and verify each subsystem separately before exposing a capability.
- `codex-plan-relay` and `codex-review-relay` are required by the specification but are not exposed in the current session: make their availability a release prerequisite rather than silently skipping those gates.
---