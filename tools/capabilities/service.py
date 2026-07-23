"""
Capability service — exposes android_flow and capability execution
through the guarded policy boundary.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from .errors import (
    AuthorizationRefused,
    FlowValidationError,
    PolicyViolation,
    RecipeNotFoundError,
    RecipeQuarantined,
)
from .flow_executor import FlowDefinition, FlowExecutor, FlowHandler, FlowStep
from .models import (
    CapabilityResult,
    DeviceFingerprint,
    EvidenceReference,
    ExecutionAuthorization,
    ExecutionTier,
    FailureClass,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
    create_authorization,
)
from .policy import PolicyGate


# ── Service ──────────────────────────────────────────────────────────────────

class CapabilityService:
    """
    Public entry point for android_flow and capability execution.

    All calls go through the policy gate before any Android handler dispatch.
    """

    def __init__(self, handler: FlowHandler):
        self.handler = handler
        self.policy = PolicyGate()
        self.executor = FlowExecutor(handler, self.policy)
        self._used_nonces: set[str] = set()

    def execute_flow(
        self,
        steps: list[dict[str, Any]],
        capability: str = "unknown",
        recipe_id: Optional[str] = None,
        recipe_revision: Optional[str] = None,
        timeout_ms: int = 60000,
        idempotency_key: Optional[str] = None,
        tier: Optional[str] = None,
        authorization: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Execute a flow with policy enforcement.

        Args:
            steps: List of step dicts with 'action', 'params', 'verifier', etc.
            capability: Semantic capability name
            recipe_id: Recipe identifier
            recipe_revision: Recipe revision digest
            timeout_ms: Global timeout
            idempotency_key: Optional idempotency key
            tier: Execution tier (candidate/dogfood/stable)
            authorization: Authorization envelope for candidate/dogfood

        Returns:
            JSON string with result status, trace, evidence, and failure info.
        """
        # Parse steps into FlowStep objects
        flow_steps = []
        for i, step_dict in enumerate(steps):
            fallback = None
            if "fallback" in step_dict:
                fb = step_dict["fallback"]
                fallback = FlowStep(
                    action=fb.get("action", ""),
                    params=fb.get("params", {}),
                    verifier=fb.get("verifier"),
                    verifier_params=fb.get("verifier_params", {}),
                    confirmation_token=fb.get("confirmation_token"),
                )

            flow_steps.append(FlowStep(
                action=step_dict.get("action", ""),
                params=step_dict.get("params", {}),
                verifier=step_dict.get("verifier"),
                verifier_params=step_dict.get("verifier_params", {}),
                timeout_ms=step_dict.get("timeout_ms", 10000),
                retries=step_dict.get("retries", 0),
                fallback=fallback,
                confirmation_token=step_dict.get("confirmation_token"),
            ))

        flow = FlowDefinition(
            capability=capability,
            steps=flow_steps,
            recipe_id=recipe_id,
            recipe_revision=recipe_revision,
            timeout_ms=timeout_ms,
            idempotency_key=idempotency_key,
        )

        # Parse authorization if provided
        auth_obj = None
        if tier in ("candidate", "dogfood"):
            if not authorization:
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_missing",
                    "error_message": f"Tier '{tier}' requires authorization envelope",
                })
            # Validate authorization fully before consuming nonce
            auth_obj = ExecutionAuthorization(
                tier=ExecutionTier(tier),
                capability=authorization.get("capability", capability),
                recipe_id=authorization.get("recipe_id", recipe_id or ""),
                recipe_revision=authorization.get("recipe_revision", recipe_revision or ""),
                device_fingerprint_digest=authorization.get("device_fingerprint_digest", ""),
                allowed_actions=tuple(authorization.get("allowed_actions", [])),
                nonce=authorization.get("nonce", ""),
                issued_at=authorization.get("issued_at", time.time()),
                expires_at=authorization.get("expires_at", time.time() + 300),
            )
            # Reject empty nonce
            if not auth_obj.nonce:
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_invalid",
                    "error_message": "Authorization envelope must include a nonce",
                })
            # Full validation before consuming (expiry, fingerprint, recipe)
            if auth_obj.is_expired():
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_expired",
                    "error_message": "Authorization has expired",
                })
            # Validate device fingerprint
            if not authorization.get("device_fingerprint_digest"):
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_invalid",
                    "error_message": "Authorization must include device_fingerprint_digest",
                })
            # Validate recipe binding
            if not authorization.get("recipe_id"):
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_invalid",
                    "error_message": "Authorization must include recipe_id",
                })
            # Validate allowed_actions is non-empty
            if not authorization.get("allowed_actions"):
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_invalid",
                    "error_message": "Authorization must include non-empty allowed_actions",
                })
            # Cross-validate envelope binding to flow arguments
            if auth_obj.capability and auth_obj.capability != capability:
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_scope_mismatch",
                    "error_message": f"Authorization capability '{auth_obj.capability}' doesn't match flow capability '{capability}'",
                })
            if auth_obj.recipe_id and recipe_id and auth_obj.recipe_id != recipe_id:
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_recipe_mismatch",
                    "error_message": f"Authorization recipe '{auth_obj.recipe_id}' doesn't match flow recipe '{recipe_id}'",
                })
            # Consume nonce only after full validation passes
            if auth_obj.nonce in self._used_nonces:
                return json.dumps({
                    "status": "refused",
                    "failure_class": "authorization_replay",
                    "error_message": "Authorization nonce already used",
                })
            self._used_nonces.add(auth_obj.nonce)

        # Execute through guarded executor
        try:
            result = self.executor.execute(flow, authorization=auth_obj)
        except (AuthorizationRefused, PolicyViolation) as e:
            return json.dumps({
                "status": "refused",
                "failure_class": getattr(e, "failure_class", FailureClass.PROHIBITED_ACTION).value
                    if hasattr(e, "failure_class") else "prohibited_action",
                "error_message": str(e),
            })

        return json.dumps(result.to_dict())

    def check_action(
        self,
        action: str,
        authorization: Optional[dict] = None,
        confirmation_token: Optional[str] = None,
    ) -> str:
        """
        Pre-check if an action is allowed without executing it.

        Returns JSON with classification and authorization status.
        """
        from .policy import classify_action

        classification = classify_action(action)

        auth_obj = None
        if authorization:
            tier = authorization.get("tier", "stable")
            try:
                auth_obj = ExecutionAuthorization(
                    tier=ExecutionTier(tier),
                    capability=authorization.get("capability", ""),
                    recipe_id=authorization.get("recipe_id", ""),
                    recipe_revision=authorization.get("recipe_revision", ""),
                    device_fingerprint_digest=authorization.get("device_fingerprint_digest", ""),
                    allowed_actions=tuple(authorization.get("allowed_actions", [])),
                    nonce=authorization.get("nonce", ""),
                    issued_at=authorization.get("issued_at", time.time()),
                    expires_at=authorization.get("expires_at", time.time() + 300),
                )
            except (ValueError, KeyError) as e:
                return json.dumps({
                    "allowed": False,
                    "failure_class": "authorization_invalid",
                    "error_message": str(e),
                })

        try:
            self.policy.check_action(action, auth_obj, confirmation_token)
            return json.dumps({
                "allowed": True,
                "classification": classification.value,
            })
        except AuthorizationRefused as e:
            return json.dumps({
                "allowed": False,
                "failure_class": e.failure_class.value,
                "error_message": e.message,
                "classification": classification.value,
            })
        except PolicyViolation as e:
            return json.dumps({
                "allowed": False,
                "failure_class": "prohibited_action",
                "error_message": e.message,
                "classification": classification.value,
            })

    def get_trace(self, trace_id: str) -> str:
        """Get a trace by ID (stub — requires trace store)."""
        return json.dumps({"error": "Trace store not implemented yet"})
