"""Discovery — ordered protocol for discovering how to execute a capability."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DiscoveryStep:
    """A step in the discovery protocol."""
    name: str
    description: str
    priority: int


@dataclass
class DiscoveryResult:
    """Result of a discovery attempt."""
    capability: str
    candidate_recipe_id: Optional[str]
    steps_tried: list[str]
    success: bool
    failure_reason: str = ""
    candidate_recipe: Optional[dict[str, Any]] = None
    invalidation_conditions: list[str] = field(default_factory=list)


# ── Default Discovery Steps ──────────────────────────────────────────────────

_DEFAULT_STEPS = [
    DiscoveryStep("direct_tool_lookup", "Check if a direct android_* tool satisfies the capability", 10),
    DiscoveryStep("manifest_inspection", "Inspect app manifest for intents, shortcuts, services", 20),
    DiscoveryStep("package_fingerprint", "Check installed packages and versions", 30),
    DiscoveryStep("negative_learning_check", "Check if this route was previously incompatible", 40),
    DiscoveryStep("reversible_hypothesis", "Try reversible non-visual hypotheses", 50),
    DiscoveryStep("verifier_experiment", "Run verifier-backed experiments", 60),
    DiscoveryStep("selective_exploration", "Selective accessibility tree exploration", 70),
    DiscoveryStep("ui_exploration", "Full UI exploration (expensive, last resort)", 80),
]


class DiscoveryProtocol:
    """Ordered discovery protocol — tries cheaper methods first."""

    def __init__(self, steps: Optional[list[DiscoveryStep]] = None):
        self.steps = steps or list(_DEFAULT_STEPS)
        self.steps.sort(key=lambda s: s.priority)
        self.negative_learning: list[dict[str, Any]] = []

    def discover(
        self,
        capability: str,
        available_tools: list[str] | None = None,
        mock_manifest: dict[str, Any] | None = None,
        fingerprint_digest: str = "",
    ) -> DiscoveryResult:
        """Run the discovery protocol for a capability."""
        steps_tried: list[str] = []
        available_tools = available_tools or []
        mock_manifest = mock_manifest or {}

        for step in self.steps:
            steps_tried.append(step.name)

            if step.name == "direct_tool_lookup":
                # Check if any available tool can handle this capability
                intent_action = self._capability_to_intent(capability)
                if intent_action or any(self._capability_matches_tool(capability, t) for t in available_tools):
                    return DiscoveryResult(
                        capability=capability,
                        candidate_recipe_id=f"candidate_{capability.replace('.', '_')}",
                        steps_tried=steps_tried,
                        success=True,
                        candidate_recipe={
                            "steps": [{"action": "android_send_intent",
                                       "params": {"action": intent_action}}] if intent_action else [],
                        },
                    )

            elif step.name == "manifest_inspection":
                intents = mock_manifest.get("intents", [])
                if intents:
                    return DiscoveryResult(
                        capability=capability,
                        candidate_recipe_id=f"candidate_{capability.replace('.', '_')}_manifest",
                        steps_tried=steps_tried,
                        success=True,
                        candidate_recipe={
                            "steps": [{"action": "android_send_intent",
                                       "params": {"action": intents[0]}}],
                        },
                    )

            elif step.name == "negative_learning_check":
                for entry in self.negative_learning:
                    if (entry.get("capability") == capability
                            and entry.get("fingerprint") == fingerprint_digest):
                        # Skip this route
                        continue

        return DiscoveryResult(
            capability=capability,
            candidate_recipe_id=None,
            steps_tried=steps_tried,
            success=False,
            failure_reason=f"No discovery path found for capability '{capability}'",
        )

    def _capability_to_intent(self, capability: str) -> Optional[str]:
        """Map semantic capability to Android intent action."""
        intent_map = {
            "timer.set": "android.intent.action.SET_TIMER",
            "alarm.set": "android.intent.action.SET_ALARM",
            "media.play": "android.intent.action.VIEW",
            "call": "android.intent.action.CALL",
        }
        return intent_map.get(capability)

    def _capability_matches_tool(self, capability: str, tool: str) -> bool:
        """Check if a tool name matches a capability."""
        cap_parts = capability.split(".")
        return any(part in tool.lower() for part in cap_parts)


class DiscoveryStore:
    """Persistent store for discovery results."""

    def __init__(self):
        self._results: dict[str, DiscoveryResult] = {}

    def save(self, result: DiscoveryResult) -> None:
        self._results[result.capability] = result

    def get(self, capability: str) -> Optional[DiscoveryResult]:
        return self._results.get(capability)

    def list_capabilities(self) -> list[str]:
        return list(self._results.keys())

    def count(self) -> int:
        return len(self._results)
