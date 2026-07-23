---
# Implementation Plan: Hermes Android Capability System — Safety, Authorization, and Copy-Contract Corrections

## Overview
Amend the capability plan so execution policy is enforced inside the flow executor before any `android_flow` is publicly registered. Candidate and dogfood runs receive explicit, device- and recipe-bound authorization, while confirmation-required actions remain blocked unless separately authorized.

Make successful outcomes evidence-backed by contract: a success result must reference a confirmed final verifier, while traces retain redacted evidence references rather than raw sensitive values. Add CI contract checks proving `tools/` and `hermes-android-plugin/` remain behaviorally synchronized.

## Prerequisites
- Python 3.11 with `pytest` and the project editable-installed.
- Existing CI access capable of running Python contract tests.
- A defined recipe fingerprint format and controlled test-device identity for candidate/dogfood authorization.

## Tasks

### Task 1: Define execution authorization and evidence-backed trace contracts
- **Files**: `tools/capabilities/models.py` (modify), `tools/capabilities/errors.py` (modify), `tools/capabilities/flow_schema.py` (modify), `docs/capabilities/architecture.md` (modify), `tests/capabilities/test_models.py` (modify), `tests/capabilities/test_flow_schema.py` (modify)
- **Description**: Add versioned models for `ExecutionAuthorization`, `ExecutionTier` (`candidate`, `dogfood`, `stable`), `ActionClassification`, `VerificationOutcome`, and redacted `EvidenceReference`. Bind candidate and dogfood authorization to capability, recipe ID and revision digest, device fingerprint digest, allowed action scope, one-time nonce, issuance time, and expiry. Define candidate runs as test-device, candidate-safe execution only; define dogfood runs as explicitly authorized, fingerprint-bound recipe evaluation. Neither tier bypasses confirmation-required or prohibited-action policy. Require a successful `CapabilityResult` to contain a confirmed final-verifier outcome and at least one success-evidence reference; traces may contain redacted references only and must never make an evidence-free success appear valid.
- **Tests**: Reject missing/expired/reused/non-matching candidate and dogfood authorization; reject a success result with no final verifier or no evidence reference; accept failure and cancellation traces with no success evidence; verify trace serialization excludes raw evidence values and preserves ordered evidence IDs.
- **Dependencies**: none

### Task 2: Implement policy classification and authorization validation before dispatch
- **Files**: `tools/capabilities/safety.py` (create), `tools/capabilities/policy.py` (create), `tools/capabilities/authorization.py` (create), `tests/capabilities/test_safety.py` (create), `tests/capabilities/test_authorization.py` (create), `docs/capabilities/safety.md` (create)
- **Description**: Implement a policy gate that classifies every primary, retry, branch, and fallback action as ordinary reversible, confirmation-required, or prohibited. Validate execution-tier authorization and any separate scoped confirmation token before an action reaches an Android handler. Candidate authorization permits only declared candidate-safe, ordinary reversible actions on its bound test device. Dogfood authorization permits only the bound recipe/action scope and still requires scoped confirmation for sends, payments, public posts, deletions, lock/security changes, privilege escalation, or other confirmation-required actions.
- **Tests**: Using a fake Android handler, prove blocked actions produce zero dispatches; prove expired, replayed, fingerprint-mismatched, recipe-mismatched, and scope-mismatched authorization is rejected; prove a valid dogfood authorization does not bypass message-send confirmation; prove prohibited actions fail before fallback or retry dispatch.
- **Dependencies**: Task 1

### Task 3: Integrate policy and verifier evidence into the deterministic flow executor
- **Files**: `tools/capabilities/flow_executor.py` (create), `tools/capabilities/flow_actions.py` (create), `tools/capabilities/trace.py` (create), `tools/capabilities/evidence.py` (create), `tools/capabilities/verifiers.py` (modify), `tests/capabilities/test_flow_executor.py` (create), `tests/capabilities/test_verifiers.py` (modify)
- **Description**: Make `FlowExecutor` invoke the policy and authorization gate before every dispatch, including fallbacks. Record a redacted ordered trace with classification decision, authorization decision, dispatch attempt, verifier attempt, verifier outcome, and evidence references. Permit `success` only after the declared final verifier returns `confirmed`; convert unavailable or inconclusive verification into a non-success terminal result with a stable failure classification. Keep screenshots and recordings failure-diagnostic-only, and preserve `android_macro` behavior unchanged.
- **Tests**: Prove confirmation-required and prohibited actions are blocked by the executor even when callers bypass public tools; prove candidate and dogfood flows obey their distinct authorization limits; prove retry/fallback cannot evade policy; prove a launched app plus inconclusive verification is not success; prove every successful result has a matching terminal trace verifier event and evidence reference.
- **Dependencies**: Tasks 1, 2

### Task 4: Expose `android_flow` only through the guarded capability boundary
- **Files**: `tools/capabilities/service.py` (create), `tools/android_tool.py` (modify), `hermes-android-plugin/android_tool.py` (modify), `tests/capabilities/test_service.py` (create), `tests/test_android_tool.py` (modify), `README.md` (modify), `skills/android/SKILL.md` (modify)
- **Description**: Register `android_flow` and capability execution only after constructing the guarded executor from Task 3. Require execution tier and authorization inputs for candidate/dogfood routes; return a structured refusal before dispatch when authorization or policy validation fails. Expose selected recipe/adapter, classification, trace ID, final verifier outcome, and redacted evidence references. Preserve every legacy `android_*` definition and `android_macro` contract.
- **Tests**: Verify tool schemas require the appropriate authorization envelope for candidate/dogfood execution; verify a mocked public `android_flow` request cannot reach a handler without policy approval; verify a successful public result contains final-verifier evidence; verify legacy tools and `android_macro` retain their existing schemas and behavior.
- **Dependencies**: Task 3

### Task 5: Add synchronized-copy contract tests and CI enforcement
- **Files**: `tests/contracts/test_android_tool_copy_contract.py` (create), `tests/contracts/test_android_relay_copy_contract.py` (create), `tests/contracts/fixtures/capability_flow_contracts.json` (create), `scripts/check_android_copy_contract.py` (create), `.github/workflows/ci.yml` (modify or create)
- **Description**: Define shared typed-intent, authorization-refusal, guarded-flow, and successful-evidence fixtures. Execute each fixture against both `tools/` and `hermes-android-plugin/` implementations and compare public tool schemas, serialized relay payloads, refusal codes, result status, final-verifier fields, and redacted trace shape. Add a CI job that runs the focused copy-contract tests and `scripts/check_android_copy_contract.py --check` before the broader Python suite.
- **Tests**: Intentionally alter one mirrored tool schema, relay payload field, or refusal code in a temporary test fixture and prove the contract check fails; prove both copies accept identical typed-intent inputs, reject identical malformed authorization inputs, and produce identical guarded-flow result shapes.
- **Dependencies**: Task 4

## Verification
- [ ] The executor blocks confirmation-required and prohibited actions before any Android handler dispatch, including retry and fallback paths.
- [ ] Candidate and dogfood authorizations are recipe-, revision-, fingerprint-, scope-, expiry-, and nonce-bound, and neither bypasses scoped confirmation.
- [ ] Every `success` result has a confirmed final-verifier event and redacted success-evidence reference in its trace.
- [ ] `android_flow` is registered only through the guarded executor, while legacy `android_macro` and existing tools remain compatible.
- [ ] CI runs contract fixtures against both `tools/` and `hermes-android-plugin/` copies and fails on behavioral drift.

## Risks
- Candidate versus dogfood scope may be interpreted differently by product owners: keep both tiers explicitly restrictive and require an approved policy decision before broadening either tier.
- Evidence references can become too permissive if they contain raw metadata: enforce redaction at creation and serialize only bounded identifiers, observer type, timestamp, and safe summary fields.
- Mirrored implementations can still drift internally while matching current fixtures: expand shared fixtures whenever a public tool schema, relay payload, authorization rule, or result field changes.
---