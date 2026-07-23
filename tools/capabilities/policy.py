"""
Safety policy — classifies actions and enforces authorization before dispatch.
"""

from __future__ import annotations

from typing import Optional

from .errors import AuthorizationRefused, PolicyViolation
from .models import (
    ActionClassification,
    ExecutionAuthorization,
    ExecutionTier,
    FailureClass,
)


# ── Action Classification Registry ───────────────────────────────────────────

# Actions that require explicit confirmation before execution.
# These are mapped by (capability, action) or just action name.
_CONFIRMATION_REQUIRED_ACTIONS: set[str] = {
    # Messaging
    "send_sms", "send_whatsapp", "send_message", "message.send",
    "message.verify_sent",
    # Payments / purchases
    "payment", "purchase", "buy", "checkout",
    # Public posting
    "post_public", "publish", "share_public",
    # Mass operations
    "mass_send", "broadcast_send",
    # Deletions
    "delete", "delete_all", "remove_permanently",
    # Security / lock
    "lock_device", "change_password", "change_pin", "enable_vpn",
    "disable_security", "factory_reset", "wipe_data",
    # Privilege escalation
    "grant_permission", "enable_admin", "install_package",
    "root_action", "shizuku_action",
    # Navigation that could be dangerous
    "navigate_driving",
}

# Actions that are always prohibited.
_PROHIBITED_ACTIONS: set[str] = {
    "factory_reset", "wipe_data", "erase_all",
    "install_root", "disable_selinux",
}


def classify_action(action: str) -> ActionClassification:
    """Classify an action by its safety level."""
    if action in _PROHIBITED_ACTIONS:
        return ActionClassification.PROHIBITED
    if action in _CONFIRMATION_REQUIRED_ACTIONS:
        return ActionClassification.CONFIRMATION_REQUIRED
    return ActionClassification.ORDINARY_REVERSIBLE


def is_confirmation_required(action: str) -> bool:
    return classify_action(action) == ActionClassification.CONFIRMATION_REQUIRED


def is_prohibited(action: str) -> bool:
    return classify_action(action) == ActionClassification.PROHIBITED


# ── Policy Gate ───────────────────────────────────────────────────────────────

class PolicyGate:
    """
    Validates authorization and classifies actions before dispatch.

    Called by the flow executor before every handler dispatch, including
    retries and fallbacks.
    """

    def __init__(self):
        self.used_nonces: set[str] = set()

    def check_action(
        self,
        action: str,
        authorization: Optional[ExecutionAuthorization] = None,
        confirmation_token: Optional[str] = None,
    ) -> None:
        """
        Validate that an action is allowed.

        Raises AuthorizationRefused or PolicyViolation if blocked.
        """
        classification = classify_action(action)

        # Prohibited actions always fail
        if classification == ActionClassification.PROHIBITED:
            raise PolicyViolation(
                ActionClassification.PROHIBITED.value,
                f"Action '{action}' is prohibited",
            )

        # Authorization is required for candidate/dogfood tiers
        if authorization is not None:
            if authorization.tier in (ExecutionTier.CANDIDATE, ExecutionTier.DOGFOOD):
                # Validate the authorization first
                if authorization.is_expired():
                    raise AuthorizationRefused(
                        FailureClass.AUTHORIZATION_EXPIRED,
                        "Authorization has expired",
                    )
                if authorization.nonce in self.used_nonces:
                    raise AuthorizationRefused(
                        FailureClass.AUTHORIZATION_REPLAY,
                        "Authorization nonce already used",
                    )
                if action not in authorization.allowed_actions:
                    raise AuthorizationRefused(
                        FailureClass.AUTHORIZATION_SCOPE_MISMATCH,
                        f"Action '{action}' not in authorization scope",
                    )

                # Candidate tier: only ordinary reversible actions
                if authorization.tier == ExecutionTier.CANDIDATE:
                    if classification != ActionClassification.ORDINARY_REVERSIBLE:
                        raise AuthorizationRefused(
                            FailureClass.AUTHORIZATION_SCOPE_MISMATCH,
                            f"Candidate tier cannot execute '{action}' (classified as {classification.value})",
                        )

        # Confirmation-required actions need a confirmation token
        if classification == ActionClassification.CONFIRMATION_REQUIRED:
            if not confirmation_token:
                raise AuthorizationRefused(
                    FailureClass.CONFIRMATION_REQUIRED,
                    f"Action '{action}' requires confirmation",
                )

    def validate_authorization(
        self,
        authorization: ExecutionAuthorization,
        device_digest: str,
        recipe_id: str,
    ) -> Optional[FailureClass]:
        """
        Full validation of an authorization object.
        Returns None on success, FailureClass on failure.
        """
        if authorization.is_expired():
            return FailureClass.AUTHORIZATION_EXPIRED
        if authorization.nonce in self.used_nonces:
            return FailureClass.AUTHORIZATION_REPLAY
        if device_digest != authorization.device_fingerprint_digest:
            return FailureClass.AUTHORIZATION_FINGERPRINT_MISMATCH
        if recipe_id != authorization.recipe_id:
            return FailureClass.AUTHORIZATION_RECIPE_MISMATCH
        return None
