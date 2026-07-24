"""Tests for Task 18: updates.pause vertical — Play Store adapter."""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.playstore_updates import PlayStoreUpdatesAdapter
from tools.capabilities.flow_executor import FlowExecutor, FlowHandler
from tools.capabilities.models import (
    DeviceFingerprint,
    EvidenceReference,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
)
from tools.capabilities.recipes import load_recipe_from_dict


class FakeHandler(FlowHandler):
    def __init__(self):
        self.actions = []
    def execute(self, action, params):
        self.actions.append((action, params))
        return {"success": True}
    def verify(self, verifier, params):
        return VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type=verifier,
            evidence_ref=EvidenceReference.create(verifier, "updates paused"),
        )


class TestPlayStoreUpdatesAdapter:
    def test_adapter_creation(self):
        adapter = PlayStoreUpdatesAdapter()
        assert adapter.name == "playstore_updates"
        assert adapter.capability == "updates.pause"
        assert adapter.package == "com.android.vending"

    def test_adapter_supports(self):
        adapter = PlayStoreUpdatesAdapter()
        assert adapter.supports("updates.pause", "com.android.vending")
        assert not adapter.supports("updates.pause", "com.other")
        assert not adapter.supports("timer.set")

    def test_build_flow(self):
        adapter = PlayStoreUpdatesAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "updates.pause"
        assert len(flow.steps) >= 4
        # Should navigate through settings
        texts = [s.params.get("text", "") for s in flow.steps]
        assert "Settings" in texts
        assert "Network preferences" in texts
        assert "Auto-update apps" in texts
        # Last step should verify
        assert flow.steps[-1].verifier == "node_predicate"

    def test_flow_executes(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = PlayStoreUpdatesAdapter()
        flow = adapter.build_flow()
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_fallback_dont_autoupdate(self):
        adapter = PlayStoreUpdatesAdapter()
        flow = adapter.build_flow()
        last_step = flow.steps[-1]
        assert last_step.fallback is not None
        assert "Don't auto-update" in last_step.fallback.params["text"]

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(PlayStoreUpdatesAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("updates.pause", fp, package="com.android.vending")
        assert selected is not None
        assert selected.name == "playstore_updates"

    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "playstore.updates.pause.v1",
            "capability": "updates.pause",
            "package": "com.android.vending",
            "maturity": "candidate",
            "steps": [{"action": "android_open_app", "params": {}}],
            "verifier": {"type": "node_predicate"},
        })
        assert recipe.id == "playstore.updates.pause.v1"
