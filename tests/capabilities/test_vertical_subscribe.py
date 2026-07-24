"""Tests for Task 15: podcast.subscribe vertical — AntennaPod adapter."""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.antennapod_subscribe import AntennaPodSubscribeAdapter
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
            evidence_ref=EvidenceReference.create(verifier, "subscribed"),
        )


class TestAntennaPodSubscribeAdapter:
    def test_adapter_creation(self):
        adapter = AntennaPodSubscribeAdapter()
        assert adapter.name == "antennapod_subscribe"
        assert adapter.capability == "podcast.subscribe"
        assert adapter.package == "de.danoeh.antennapod"

    def test_adapter_supports(self):
        adapter = AntennaPodSubscribeAdapter()
        assert adapter.supports("podcast.subscribe", "de.danoeh.antennapod")
        assert not adapter.supports("media.play")

    def test_build_flow_with_name(self):
        adapter = AntennaPodSubscribeAdapter()
        flow = adapter.build_flow(podcast_name="Lex Fridman")
        assert flow.capability == "podcast.subscribe"
        # Should have search + type + subscribe steps
        assert len(flow.steps) >= 5
        # Last step should verify subscription
        assert flow.steps[-1].verifier == "node_predicate"

    def test_build_flow_without_name(self):
        adapter = AntennaPodSubscribeAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "podcast.subscribe"
        # Fewer steps without name
        assert len(flow.steps) >= 3

    def test_flow_executes(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = AntennaPodSubscribeAdapter()
        flow = adapter.build_flow(podcast_name="Test Show")
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_fallback_step_in_flow(self):
        adapter = AntennaPodSubscribeAdapter()
        flow = adapter.build_flow(podcast_name="Test")
        # First interactive step should have a fallback (Add Podcast → Search)
        first_tap = flow.steps[1]
        assert first_tap.fallback is not None

    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "antennapod.podcast.subscribe.v1",
            "capability": "podcast.subscribe",
            "package": "de.danoeh.antennapod",
            "maturity": "candidate",
            "steps": [{"action": "android_open_app", "params": {}}],
            "verifier": {"type": "node_predicate"},
        })
        assert recipe.id == "antennapod.podcast.subscribe.v1"
