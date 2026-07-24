"""Tests for Task 17: route.start vertical — Waze adapter."""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.waze_route import WazeRouteAdapter
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
            evidence_ref=EvidenceReference.create(verifier, "route active"),
        )


class TestWazeRouteAdapter:
    def test_adapter_creation(self):
        adapter = WazeRouteAdapter()
        assert adapter.name == "waze_route"
        assert adapter.capability == "route.start"
        assert adapter.package == "com.waze"

    def test_adapter_supports(self):
        adapter = WazeRouteAdapter()
        assert adapter.supports("route.start", "com.waze")
        assert not adapter.supports("route.start", "com.google.android.apps.maps")
        assert not adapter.supports("timer.set")

    def test_build_flow_with_destination(self):
        adapter = WazeRouteAdapter()
        flow = adapter.build_flow(destination="Airport")
        assert flow.capability == "route.start"
        assert len(flow.steps) >= 4
        # Should have search, type, select, navigate
        actions = [s.action for s in flow.steps]
        assert "android_type_text" in actions
        # Last step should verify route
        assert flow.steps[-1].verifier == "route_active"

    def test_build_flow_without_destination(self):
        adapter = WazeRouteAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "route.start"
        assert len(flow.steps) >= 3

    def test_flow_executes(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = WazeRouteAdapter()
        flow = adapter.build_flow(destination="Home")
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_fallback_navigate(self):
        adapter = WazeRouteAdapter()
        flow = adapter.build_flow(destination="Work")
        # Last step should have fallback
        last_step = flow.steps[-1]
        assert last_step.fallback is not None
        assert last_step.fallback.action == "android_tap_text"
        assert last_step.fallback.params["text"] == "Navigate"

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(WazeRouteAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("route.start", fp, package="com.waze")
        assert selected is not None
        assert selected.name == "waze_route"

    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "waze.route.start.v1",
            "capability": "route.start",
            "package": "com.waze",
            "maturity": "candidate",
            "steps": [{"action": "android_open_app", "params": {}}],
            "verifier": {"type": "route_active"},
        })
        assert recipe.id == "waze.route.start.v1"
