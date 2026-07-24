"""Tests for Task 14: media.play vertical — AntennaPod adapter."""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.antennapod_media import AntennaPodMediaAdapter
from tools.capabilities.flow_executor import FlowExecutor, FlowHandler
from tools.capabilities.models import (
    DeviceFingerprint,
    EvidenceReference,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
)
from tools.capabilities.recipes import RecipeRegistry, load_recipe_from_dict


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
            evidence_ref=EvidenceReference.create(verifier, "media playing"),
        )


class TestAntennaPodMediaAdapter:
    def test_adapter_creation(self):
        adapter = AntennaPodMediaAdapter()
        assert adapter.name == "antennapod_media"
        assert adapter.capability == "media.play"
        assert adapter.package == "de.danoeh.antennapod"

    def test_adapter_supports(self):
        adapter = AntennaPodMediaAdapter()
        assert adapter.supports("media.play", "de.danoeh.antennapod")
        assert not adapter.supports("media.play", "com.other")
        assert not adapter.supports("timer.set")

    def test_build_flow_with_query(self):
        adapter = AntennaPodMediaAdapter()
        flow = adapter.build_flow(query="test podcast")
        assert flow.capability == "media.play"
        assert len(flow.steps) >= 5  # open, search, type, enter, select, play
        # Should have a search step
        actions = [s.action for s in flow.steps]
        assert "android_type_text" in actions
        # Should end with media_state verifier
        assert flow.steps[-1].verifier == "media_state"

    def test_build_flow_without_query(self):
        adapter = AntennaPodMediaAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "media.play"
        # Without query, fewer steps
        assert len(flow.steps) >= 2

    def test_flow_executes(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = AntennaPodMediaAdapter()
        flow = adapter.build_flow(query="test")
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(AntennaPodMediaAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("media.play", fp, package="de.danoeh.antennapod")
        assert selected is not None
        assert selected.name == "antennapod_media"

    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "antennapod.media.play.v1",
            "capability": "media.play",
            "package": "de.danoeh.antennapod",
            "maturity": "candidate",
            "steps": [{"action": "android_open_app", "params": {}}],
            "verifier": {"type": "media_state"},
        })
        assert recipe.id == "antennapod.media.play.v1"
