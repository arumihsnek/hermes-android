"""Tests for Task 17b: place.save vertical — OsmAnd adapter."""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.osmand_place import OsmAndPlaceAdapter
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
            evidence_ref=EvidenceReference.create(verifier, "place saved"),
        )


class TestOsmAndPlaceAdapter:
    def test_adapter_creation(self):
        adapter = OsmAndPlaceAdapter()
        assert adapter.name == "osmand_place"
        assert adapter.capability == "place.save"
        assert adapter.package == "net.osmand.plus"

    def test_adapter_supports(self):
        adapter = OsmAndPlaceAdapter()
        assert adapter.supports("place.save", "net.osmand.plus")
        assert not adapter.supports("place.save", "com.google.android.apps.maps")
        assert not adapter.supports("timer.set")

    def test_build_flow_with_place_name(self):
        adapter = OsmAndPlaceAdapter()
        flow = adapter.build_flow(place_name="Cafe Central")
        assert flow.capability == "place.save"
        assert len(flow.steps) >= 4
        # Should have search, type, enter, select, save
        actions = [s.action for s in flow.steps]
        assert "android_type_text" in actions
        # Last step should verify save
        assert flow.steps[-1].verifier == "favorite_saved"

    def test_build_flow_without_place_name(self):
        adapter = OsmAndPlaceAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "place.save"
        assert len(flow.steps) >= 2

    def test_flow_executes(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = OsmAndPlaceAdapter()
        flow = adapter.build_flow(place_name="Home")
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_fallback_save_button(self):
        adapter = OsmAndPlaceAdapter()
        flow = adapter.build_flow(place_name="Office")
        last_step = flow.steps[-1]
        assert last_step.fallback is not None
        assert last_step.fallback.params["text"] == "Save"

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(OsmAndPlaceAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("place.save", fp, package="net.osmand.plus")
        assert selected is not None
        assert selected.name == "osmand_place"

    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "osmand.place.save.v1",
            "capability": "place.save",
            "package": "net.osmand.plus",
            "maturity": "candidate",
            "steps": [{"action": "android_open_app", "params": {}}],
            "verifier": {"type": "favorite_saved"},
        })
        assert recipe.id == "osmand.place.save.v1"
