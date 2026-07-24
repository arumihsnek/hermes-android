"""Tests for Task 13: timer.set vertical — Android Clock adapter."""

import pytest
from tools.capabilities.adapters import Adapter, AdapterRegistry
from tools.capabilities.adapters.clock_timer import ClockTimerAdapter
from tools.capabilities.flow_executor import FlowDefinition, FlowExecutor, FlowHandler, FlowStep
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
        self.verifiers = []

    def execute(self, action, params):
        self.actions.append((action, params))
        return {"success": True}

    def verify(self, verifier, params):
        self.verifiers.append((verifier, params))
        return VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type=verifier,
            evidence_ref=EvidenceReference.create(verifier, "timer set ok"),
        )


class TestClockTimerAdapter:
    def test_adapter_creation(self):
        adapter = ClockTimerAdapter()
        assert adapter.name == "clock_timer"
        assert adapter.capability == "timer.set"
        assert adapter.package == "com.google.android.deskclock"
        assert adapter.recipe_id == "clock.timer.set.v1"

    def test_adapter_supports_capability(self):
        adapter = ClockTimerAdapter()
        assert adapter.supports("timer.set")
        assert adapter.supports("timer.set", "com.google.android.deskclock")
        assert not adapter.supports("media.play")

    def test_adapter_rejects_wrong_package(self):
        adapter = ClockTimerAdapter()
        assert not adapter.supports("timer.set", "com.other.app")

    def test_build_flow_default(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow()
        assert flow.capability == "timer.set"
        assert flow.recipe_id == "clock.timer.set.v1"
        assert len(flow.steps) >= 3  # open, tap Timer, start
        # First step should be open_app
        assert flow.steps[0].action == "android_open_app"
        assert flow.steps[0].params["packageName"] == "com.google.android.deskclock"
        # Last step should have verifier
        assert flow.steps[-1].verifier == "timer_exists"

    def test_build_flow_with_duration(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=120)
        assert flow.capability == "timer.set"
        # Should have digit steps for "2" (2 minutes)
        actions = [s.action for s in flow.steps]
        assert "android_tap_text" in actions

    def test_build_flow_with_label(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60, label="cooking")
        assert flow.capability == "timer.set"

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(ClockTimerAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("timer.set", fp)
        assert selected is not None
        assert selected.name == "clock_timer"

    def test_adapter_registry_prefers_exact_package(self):
        registry = AdapterRegistry()
        registry.register(ClockTimerAdapter())
        registry.register(Adapter(
            name="generic_timer", capability="timer.set",
            package="com.any", min_sdk=21,
        ))
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("timer.set", fp, package="com.google.android.deskclock")
        assert selected.name == "clock_timer"


class TestClockTimerFlowExecution:
    def test_flow_executes_successfully(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60)

        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS
        assert result.final_verifier is not None
        assert result.final_verifier.outcome == VerificationOutcome.CONFIRMED
        assert len(result.evidence_refs) > 0
        # Verify steps were executed
        assert len(handler.actions) >= 3

    def test_flow_has_correct_steps(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60)

        result = executor.execute(flow)
        actions = [a[0] for a in handler.actions]
        assert "android_open_app" in actions
        assert "android_tap_text" in actions


class TestClockTimerRecipe:
    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "clock.timer.set.v1",
            "capability": "timer.set",
            "package": "com.google.android.deskclock",
            "maturity": "candidate",
            "steps": [
                {"action": "android_open_app", "params": {"packageName": "com.google.android.deskclock"}},
                {"action": "android_tap_text", "params": {"text": "Timer", "exact": False}},
                {"action": "android_tap_text", "params": {"text": "Start", "exact": True}},
            ],
            "verifier": {"type": "timer_exists"},
        })
        assert recipe.id == "clock.timer.set.v1"
        assert recipe.capability == "timer.set"
        assert recipe.maturity.value == "candidate"

    def test_recipe_registry(self):
        registry = RecipeRegistry()
        registry.register(load_recipe_from_dict({
            "id": "clock.timer.set.v1",
            "capability": "timer.set",
            "package": "com.google.android.deskclock",
            "maturity": "dogfood",
        }))
        results = registry.find_by_capability("timer.set")
        assert len(results) == 1
