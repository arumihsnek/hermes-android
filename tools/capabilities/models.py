"""
Capability system models — versioned contracts for authorization, execution tiers,
action classification, verification outcomes, evidence references, and traces.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── Enums ────────────────────────────────────────────────────────────────────

class ExecutionTier(str, Enum):
    """Execution authorization tier."""
    CANDIDATE = "candidate"
    DOGFOOD = "dogfood"
    STABLE = "stable"


class ActionClassification(str, Enum):
    """Safety classification for actions."""
    ORDINARY_REVERSIBLE = "ordinary_reversible"
    CONFIRMATION_REQUIRED = "confirmation_required"
    PROHIBITED = "prohibited"


class VerificationOutcome(str, Enum):
    """Result of a verifier check."""
    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class ResultStatus(str, Enum):
    """Final status of a capability execution."""
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    REFUSED = "refused"


class FailureClass(str, Enum):
    """Stable failure classifications."""
    UNSUPPORTED_INTENT = "unsupported_intent"
    IGNORED_EXTRA = "ignored_extra"
    NON_EXPORTED_COMPONENT = "non_exported_component"
    MISSING_PERMISSION = "missing_permission"
    DEEPLINK_ONLY_OPENS_APP = "deeplink_only_opens_app"
    AMBIGUOUS_SELECTOR = "ambiguous_selector"
    ELEMENT_NO_ACCESSIBILITY = "element_no_accessibility"
    INSUFFICIENT_WAIT = "insufficient_wait"
    FALSE_POSITIVE_VERIFIER = "false_positive_verifier"
    VERSION_BLOCKED = "version_blocked"
    LANGUAGE_DEPENDENT = "language_dependent"
    SESSION_STATE_DEPENDENT = "session_state_dependent"
    CONFIRMATION_REQUIRED = "confirmation_required"
    PROHIBITED_ACTION = "prohibited_action"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    AUTHORIZATION_FINGERPRINT_MISMATCH = "authorization_fingerprint_mismatch"
    AUTHORIZATION_SCOPE_MISMATCH = "authorization_scope_mismatch"
    AUTHORIZATION_REPLAY = "authorization_replay"
    AUTHORIZATION_RECIPE_MISMATCH = "authorization_recipe_mismatch"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"
    VERIFICATION_UNAVAILABLE = "verification_unavailable"
    FLOW_TIMEOUT = "flow_timeout"
    FLOW_CANCELLED = "flow_cancelled"
    UNKNOWN_TOOL = "unknown_tool"
    HANDLER_RAISED = "handler_raised"
    DEVICE_UNAVAILABLE = "device_unavailable"


# ── Device Fingerprint ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeviceFingerprint:
    """Immutable device identifier for authorization binding."""
    device_id: str
    android_version: str
    sdk_int: int
    manufacturer: str = ""
    model: str = ""
    package_fingerprints: dict[str, str] = field(default_factory=dict)

    def digest(self) -> str:
        """Stable digest for authorization binding.

        Includes device_id, android_version, sdk_int, and sorted package
        fingerprints.  Package fingerprints encode versionName:versionCode
        so that any app update changes the digest deterministically.
        """
        raw = f"{self.device_id}:{self.android_version}:{self.sdk_int}"
        for pkg in sorted(self.package_fingerprints):
            raw += f":{pkg}={self.package_fingerprints[pkg]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    def from_bridge_response(cls, data: dict) -> "DeviceFingerprint":
        """Parse a /device/info bridge response into a DeviceFingerprint.

        Raises ValueError if required fields are missing or sdk_int is 0.
        """
        required = ("device_id", "android_version", "sdk_int")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing required field(s): {', '.join(missing)}")

        sdk_int = data["sdk_int"]
        if not isinstance(sdk_int, int) or sdk_int <= 0:
            raise ValueError(f"sdk_int must be a positive integer, got {sdk_int}")

        device_id = data["device_id"]
        if device_id == "unknown" or not device_id:
            raise ValueError("device_id must be a real device identifier, not 'unknown'")

        android_version = data["android_version"]
        if android_version == "unknown" or not android_version:
            raise ValueError("android_version must be a real version string")

        # Build package fingerprints: {package: "versionName:versionCode"}
        package_fingerprints: dict[str, str] = {}
        for pkg_name, pkg_data in data.get("packages", {}).items():
            vname = pkg_data.get("versionName", "")
            vcode = pkg_data.get("versionCode", 0)
            package_fingerprints[pkg_name] = f"{vname}:{vcode}"

        return cls(
            device_id=device_id,
            android_version=android_version,
            sdk_int=sdk_int,
            manufacturer=data.get("manufacturer", ""),
            model=data.get("model", ""),
            package_fingerprints=package_fingerprints,
        )


# ── Execution Authorization ──────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutionAuthorization:
    """
    Scoped, one-time authorization for candidate or dogfood execution.

    Neither tier bypasses confirmation-required or prohibited-action policy.
    """
    tier: ExecutionTier
    capability: str
    recipe_id: str
    recipe_revision: str
    device_fingerprint_digest: str
    allowed_actions: tuple[str, ...]
    nonce: str
    issued_at: float
    expires_at: float

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def validate(
        self,
        device: DeviceFingerprint,
        recipe_id: str,
        action: str,
        used_nonces: set[str],
        capability: Optional[str] = None,
        recipe_revision: Optional[str] = None,
    ) -> Optional[FailureClass]:
        """Validate authorization for a specific dispatch. Returns None on success."""
        if self.is_expired():
            return FailureClass.AUTHORIZATION_EXPIRED
        if self.nonce in used_nonces:
            return FailureClass.AUTHORIZATION_REPLAY
        if device.digest() != self.device_fingerprint_digest:
            return FailureClass.AUTHORIZATION_FINGERPRINT_MISMATCH
        if recipe_id != self.recipe_id:
            return FailureClass.AUTHORIZATION_RECIPE_MISMATCH
        if capability is not None and capability != self.capability:
            return FailureClass.AUTHORIZATION_SCOPE_MISMATCH
        if recipe_revision is not None and recipe_revision != self.recipe_revision:
            return FailureClass.AUTHORIZATION_RECIPE_MISMATCH
        if action not in self.allowed_actions:
            return FailureClass.AUTHORIZATION_SCOPE_MISMATCH
        return None


def create_authorization(
    tier: ExecutionTier,
    capability: str,
    recipe_id: str,
    recipe_revision: str,
    device: DeviceFingerprint,
    allowed_actions: tuple[str, ...],
    ttl_seconds: float = 300.0,
) -> ExecutionAuthorization:
    """Create a new authorization with generated nonce and timestamps."""
    now = time.time()
    return ExecutionAuthorization(
        tier=tier,
        capability=capability,
        recipe_id=recipe_id,
        recipe_revision=recipe_revision,
        device_fingerprint_digest=device.digest(),
        allowed_actions=tuple(allowed_actions),
        nonce=uuid.uuid4().hex[:16],
        issued_at=now,
        expires_at=now + ttl_seconds,
    )


# ── Evidence References ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvidenceReference:
    """
    Redacted reference to evidence. Never contains raw metadata.

    Traces store only these references, never raw evidence values.
    """
    evidence_id: str
    observer_type: str  # e.g. "media_session", "notification", "node_search", "hash"
    timestamp: float
    safe_summary: str  # bounded, non-sensitive summary

    @staticmethod
    def create(observer_type: str, safe_summary: str) -> EvidenceReference:
        return EvidenceReference(
            evidence_id=uuid.uuid4().hex[:12],
            observer_type=observer_type,
            timestamp=time.time(),
            safe_summary=safe_summary[:200],
        )


# ── Verification Outcome ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class VerificationResult:
    """Result of a verifier check."""
    outcome: VerificationOutcome
    verifier_type: str
    evidence_ref: Optional[EvidenceReference] = None
    failure_class: Optional[FailureClass] = None


# ── Trace Events ─────────────────────────────────────────────────────────────

@dataclass
class TraceEvent:
    """Single event in an execution trace."""
    event_type: str  # "classification", "authorization", "dispatch", "verifier", "evidence"
    timestamp: float
    detail: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[EvidenceReference] = field(default_factory=list)


@dataclass
class FlowTrace:
    """Ordered, redacted trace of a flow execution."""
    trace_id: str
    capability: str
    recipe_id: Optional[str]
    events: list[TraceEvent] = field(default_factory=list)

    def add_event(
        self,
        event_type: str,
        detail: dict[str, Any] | None = None,
        evidence_refs: list[EvidenceReference] | None = None,
    ) -> TraceEvent:
        evt = TraceEvent(
            event_type=event_type,
            timestamp=time.time(),
            detail=detail or {},
            evidence_refs=evidence_refs or [],
        )
        self.events.append(evt)
        return evt

    def to_dict(self) -> dict:
        """Serialize trace with redacted evidence references only."""
        return {
            "trace_id": self.trace_id,
            "capability": self.capability,
            "recipe_id": self.recipe_id,
            "events": [
                {
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "detail": e.detail,
                    "evidence_refs": [
                        {
                            "evidence_id": ref.evidence_id,
                            "observer_type": ref.observer_type,
                            "timestamp": ref.timestamp,
                            "safe_summary": ref.safe_summary,
                        }
                        for ref in e.evidence_refs
                    ],
                }
                for e in self.events
            ],
        }


# ── Capability Result ────────────────────────────────────────────────────────

@dataclass
class CapabilityResult:
    """
    Final result of a capability execution.

    Success requires a confirmed final verifier and at least one evidence reference.
    Traces contain only redacted evidence references, never raw values.
    """
    status: ResultStatus
    capability: str
    trace: FlowTrace
    failure_class: Optional[FailureClass] = None
    error_message: Optional[str] = None
    evidence_refs: list[EvidenceReference] = field(default_factory=list)
    final_verifier: Optional[VerificationResult] = None

    def to_dict(self) -> dict:
        result = {
            "status": self.status.value,
            "capability": self.capability,
            "trace_id": self.trace.trace_id,
            "failure_class": self.failure_class.value if self.failure_class else None,
            "error_message": self.error_message,
            "evidence_refs": [
                {
                    "evidence_id": ref.evidence_id,
                    "observer_type": ref.observer_type,
                    "timestamp": ref.timestamp,
                    "safe_summary": ref.safe_summary,
                }
                for ref in self.evidence_refs
            ],
            "final_verifier": {
                "outcome": self.final_verifier.outcome.value,
                "verifier_type": self.final_verifier.verifier_type,
            } if self.final_verifier else None,
        }
        return result

    def validate_success(self) -> Optional[str]:
        """
        Validate that a success result meets contract requirements.
        Returns error message if invalid, None if valid.
        """
        if self.status != ResultStatus.SUCCESS:
            return None  # Only validate success results
        if self.final_verifier is None:
            return "Success result must have a final_verifier"
        if self.final_verifier.outcome != VerificationOutcome.CONFIRMED:
            return f"Success result final_verifier must be confirmed, got {self.final_verifier.outcome.value}"
        if not self.evidence_refs:
            return "Success result must have at least one evidence reference"
        return None
