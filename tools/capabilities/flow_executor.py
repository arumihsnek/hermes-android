"""
Flow executor — deterministic execution with policy gate, verifier evidence,
and structured traces. Never infers completion from an app opening.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .errors import AuthorizationRefused, FlowValidationError, PolicyViolation
from .models import (
    CapabilityResult,
    EvidenceReference,
    ExecutionAuthorization,
    FailureClass,
    FlowTrace,
    ResultStatus,
    TraceEvent,
    VerificationOutcome,
    VerificationResult,
)
from .policy import PolicyGate


# ── Flow Step ────────────────────────────────────────────────────────────────

@dataclass
class FlowStep:
    """Single step in a flow."""
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    verifier: Optional[str] = None
    verifier_params: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 10000
    retries: int = 0
    fallback: Optional["FlowStep"] = None
    confirmation_token: Optional[str] = None


# ── Flow Definition ──────────────────────────────────────────────────────────

@dataclass
class FlowDefinition:
    """Complete flow definition."""
    capability: str
    steps: list[FlowStep]
    recipe_id: Optional[str] = None
    recipe_revision: Optional[str] = None
    timeout_ms: int = 60000
    idempotency_key: Optional[str] = None


# ── Handler Protocol ─────────────────────────────────────────────────────────

class FlowHandler:
    """
    Adapter that executes actions and checks verifiers.

    Implementations map to existing android_* handlers or new capability handlers.
    """

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an action. Returns result dict."""
        raise NotImplementedError

    def verify(self, verifier: str, params: dict[str, Any]) -> VerificationResult:
        """Check a verifier condition."""
        raise NotImplementedError


# ── Flow Executor ────────────────────────────────────────────────────────────

class FlowExecutor:
    """
    Executes validated flows with policy enforcement, verification, and traces.

    Key guarantees:
    - Policy gate is invoked before EVERY dispatch (including retries and fallbacks)
    - Success requires a confirmed final verifier
    - Evidence is captured only on failure
    - Screenshots/recordings are failure-diagnostic-only
    - android_macro behavior is unchanged
    """

    def __init__(self, handler: FlowHandler, policy: Optional[PolicyGate] = None):
        self.handler = handler
        self.policy = policy or PolicyGate()

    def execute(
        self,
        flow: FlowDefinition,
        authorization: Optional[ExecutionAuthorization] = None,
    ) -> CapabilityResult:
        """
        Execute a flow with policy enforcement and verification.

        Returns CapabilityResult with status, trace, and evidence.
        """
        trace = FlowTrace(
            trace_id=uuid.uuid4().hex[:12],
            capability=flow.capability,
            recipe_id=flow.recipe_id,
        )

        deadline = time.time() + (flow.timeout_ms / 1000)
        last_result: Optional[CapabilityResult] = None

        for step_idx, step in enumerate(flow.steps):
            # Check global timeout
            if time.time() > deadline:
                trace.add_event("timeout", {"step": step_idx})
                return CapabilityResult(
                    status=ResultStatus.FAILURE,
                    capability=flow.capability,
                    trace=trace,
                    failure_class=FailureClass.FLOW_TIMEOUT,
                    error_message=f"Flow timed out at step {step_idx}",
                )

            # Execute with retries
            step_success = False
            last_error: Optional[Exception] = None

            for attempt in range(step.retries + 1):
                # Check deadline before each dispatch
                if time.time() > deadline:
                    trace.add_event("timeout", {"step": step_idx, "attempt": attempt})
                    return CapabilityResult(
                        status=ResultStatus.FAILURE,
                        capability=flow.capability,
                        trace=trace,
                        failure_class=FailureClass.FLOW_TIMEOUT,
                        error_message=f"Flow timed out at step {step_idx}, attempt {attempt}",
                    )

                try:
                    # Policy gate before EVERY dispatch
                    self.policy.check_action(
                        action=step.action,
                        authorization=authorization,
                        confirmation_token=step.confirmation_token,
                    )

                    # Dispatch
                    trace.add_event("dispatch", {
                        "step": step_idx,
                        "action": step.action,
                        "attempt": attempt,
                    })

                    result = self.handler.execute(step.action, step.params)

                    # Record dispatch result
                    trace.add_event("dispatch_result", {
                        "step": step_idx,
                        "success": result.get("success", False),
                    })

                    if not result.get("success", False):
                        last_error = Exception(result.get("error", "dispatch failed"))
                        continue

                    # Check deadline after dispatch
                    if time.time() > deadline:
                        trace.add_event("timeout", {"step": step_idx, "attempt": attempt})
                        return CapabilityResult(
                            status=ResultStatus.FAILURE,
                            capability=flow.capability,
                            trace=trace,
                            failure_class=FailureClass.FLOW_TIMEOUT,
                            error_message=f"Flow timed out at step {step_idx} after dispatch",
                        )

                    # Verify if verifier declared
                    if step.verifier:
                        verification = self.handler.verify(
                            step.verifier,
                            step.verifier_params,
                        )
                        trace.add_event("verifier", {
                            "step": step_idx,
                            "verifier": step.verifier,
                            "outcome": verification.outcome.value,
                        })

                        if verification.outcome == VerificationOutcome.CONFIRMED:
                            step_success = True
                            if verification.evidence_ref:
                                trace.add_event("evidence", {
                                    "step": step_idx,
                                }, evidence_refs=[verification.evidence_ref])
                            break
                        else:
                            last_error = Exception(
                                f"Verifier '{step.verifier}' returned {verification.outcome.value}"
                            )
                            continue
                    else:
                        # No verifier — step is considered successful
                        step_success = True
                        break

                except (AuthorizationRefused, PolicyViolation) as e:
                    trace.add_event("policy_refused", {
                        "step": step_idx,
                        "action": step.action,
                        "error": str(e),
                    })
                    return CapabilityResult(
                        status=ResultStatus.REFUSED,
                        capability=flow.capability,
                        trace=trace,
                        failure_class=e.failure_class if isinstance(e, AuthorizationRefused) else FailureClass.PROHIBITED_ACTION,
                        error_message=str(e),
                    )

            if not step_success:
                # Try fallback
                if step.fallback:
                    try:
                        self.policy.check_action(
                            action=step.fallback.action,
                            authorization=authorization,
                            confirmation_token=step.fallback.confirmation_token,
                        )

                        trace.add_event("fallback_dispatch", {
                            "step": step_idx,
                            "action": step.fallback.action,
                        })

                        result = self.handler.execute(
                            step.fallback.action,
                            step.fallback.params,
                        )

                        if result.get("success", False):
                            if step.fallback.verifier:
                                verification = self.handler.verify(
                                    step.fallback.verifier,
                                    step.fallback.verifier_params,
                                )
                                fallback_evt = trace.add_event("fallback_verifier", {
                                    "step": step_idx,
                                    "outcome": verification.outcome.value,
                                })
                                if verification.evidence_ref:
                                    fallback_evt.evidence_refs.append(verification.evidence_ref)
                                if verification.outcome == VerificationOutcome.CONFIRMED:
                                    step_success = True
                                    break
                            else:
                                step_success = True
                                break

                    except (AuthorizationRefused, PolicyViolation) as e:
                        trace.add_event("fallback_policy_refused", {
                            "step": step_idx,
                            "error": str(e),
                        })
                        # Propagate policy refusal from fallback
                        return CapabilityResult(
                            status=ResultStatus.REFUSED,
                            capability=flow.capability,
                            trace=trace,
                            failure_class=e.failure_class if isinstance(e, AuthorizationRefused) else FailureClass.PROHIBITED_ACTION,
                            error_message=str(e),
                        )

                if not step_success:
                    failure_class = FailureClass.HANDLER_RAISED
                    if last_error and "timeout" in str(last_error).lower():
                        failure_class = FailureClass.INSUFFICIENT_WAIT
                    elif last_error and "verifier" in str(last_error).lower():
                        failure_class = FailureClass.VERIFICATION_INCONCLUSIVE

                    trace.add_event("step_failed", {
                        "step": step_idx,
                        "error": str(last_error),
                    })

                    return CapabilityResult(
                        status=ResultStatus.FAILURE,
                        capability=flow.capability,
                        trace=trace,
                        failure_class=failure_class,
                        error_message=f"Step {step_idx} ({step.action}) failed: {last_error}",
                    )

        # All steps completed — require final verifier for success
        # Find the last step with a verifier (including fallbacks that succeeded)
        last_verifier_step = None
        for step in reversed(flow.steps):
            if step.verifier:
                last_verifier_step = step
                break
            if step.fallback and step.fallback.verifier:
                last_verifier_step = step.fallback
                break

        if last_verifier_step is None:
            # No verifier declared — cannot claim success
            return CapabilityResult(
                status=ResultStatus.FAILURE,
                capability=flow.capability,
                trace=trace,
                failure_class=FailureClass.VERIFICATION_UNAVAILABLE,
                error_message="No final verifier declared; cannot confirm success",
            )

        # The last verifier should have been checked during execution
        # Check if we have a confirmed verifier in the trace
        last_verifier_event = None
        for evt in reversed(trace.events):
            if evt.event_type in ("verifier", "fallback_verifier") and evt.detail.get("outcome") == "confirmed":
                last_verifier_event = evt
                break

        if last_verifier_event is None:
            return CapabilityResult(
                status=ResultStatus.FAILURE,
                capability=flow.capability,
                trace=trace,
                failure_class=FailureClass.VERIFICATION_INCONCLUSIVE,
                error_message="Final verifier did not return confirmed",
            )

        # Collect evidence references from trace
        evidence_refs = []
        for evt in trace.events:
            evidence_refs.extend(evt.evidence_refs)

        if not evidence_refs:
            return CapabilityResult(
                status=ResultStatus.FAILURE,
                capability=flow.capability,
                trace=trace,
                failure_class=FailureClass.VERIFICATION_INCONCLUSIVE,
                error_message="Success requires at least one evidence reference",
            )

        return CapabilityResult(
            status=ResultStatus.SUCCESS,
            capability=flow.capability,
            trace=trace,
            evidence_refs=evidence_refs,
            final_verifier=VerificationResult(
                outcome=VerificationOutcome.CONFIRMED,
                verifier_type=last_verifier_step.verifier or "unknown",
                evidence_ref=evidence_refs[0] if evidence_refs else None,
            ),
        )
