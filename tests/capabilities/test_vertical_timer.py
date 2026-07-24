"""Tests for Task 13: timer.set vertical — Android Clock adapter.

Uses standard android.provider.AlarmClock API:
  - android.intent.action.SET_TIMER with extras LENGTH, MESSAGE, SKIP_UI
  - Requires com.android.alarm.permission.SET_ALARM in bridge manifest

Verified on Shiba (Pixel 8):
  - /intent endpoint returns Permission Denial without SET_ALARM permission
  - /broadcast endpoint sends but Clock ignores broadcasts for SET_TIMER
  - Timer UI buttons don't respond to accessibility clicks (custom handler)
  - Intent-based approach is the only reliable method
"""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.clock_timer import ClockTimerAdapter
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
            evidence_ref=EvidenceReference.create(verifier, "timer set via intent"),
        )


class TestClockTimerAdapter:
    def test_adapter_creation(self):
        adapter = ClockTimerAdapter()
        assert adapter.name == "clock_timer"
        assert adapter.capability == "timer.set"
        assert adapter.package == "com.google.android.deskclock"
        assert adapter.recipe_id == "clock.timer.set.v1"

    def test_adapter_supports(self):
        adapter = ClockTimerAdapter()
        assert adapter.supports("timer.set")
        assert adapter.supports("timer.set", "com.google.android.deskclock")
        assert not adapter.supports("media.play")
        assert not adapter.supports("timer.set", "com.other.app")

    def test_intent_action(self):
        assert ClockTimerAdapter.intent_action() == "android.intent.action.SET_TIMER"

    def test_intent_extras(self):
        extras = ClockTimerAdapter.intent_extras(120, label="cooking", skip_ui=True)
        assert extras["android.intent.extra.alarm.LENGTH"] == 120
        assert extras["android.intent.extra.alarm.MESSAGE"] == "cooking"
        assert extras["android.intent.extra.alarm.SKIP_UI"] is True

    def test_intent_extras_default_label(self):
        extras = ClockTimerAdapter.intent_extras(60)
        assert extras["android.intent.extra.alarm.MESSAGE"] == "Timer 60s"

    def test_intent_extras_min_duration(self):
        extras = ClockTimerAdapter.intent_extras(0)
        assert extras["android.intent.extra.alarm.LENGTH"] == 1  # clamped to 1

    def test_build_flow_uses_intent(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=120)
        assert flow.capability == "timer.set"
        assert flow.recipe_id == "clock.timer.set.v1"
        # Primary step should be android_send_intent
        assert flow.steps[0].action == "android_send_intent"
        assert flow.steps[0].params["action"] == "android.intent.action.SET_TIMER"
        extras = flow.steps[0].params["extras"]
        assert extras["android.intent.extra.alarm.LENGTH"] == 120
        assert extras["android.intent.extra.alarm.SKIP_UI"] is True

    def test_build_flow_has_fallback(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60)
        step = flow.steps[0]
        assert step.fallback is not None
        assert step.fallback.action == "android_broadcast"
        assert step.fallback.params["action"] == "android.intent.action.SET_TIMER"

    def test_build_flow_default_duration(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow()
        extras = flow.steps[0].params["extras"]
        assert extras["android.intent.extra.alarm.LENGTH"] == 60  # default 1 minute

    def test_build_flow_with_label(self):
        adapter = ClockTimerAdapter()
        flow = build_flow_with_label(adapter, "pasta timer")
        extras = flow.steps[0].params["extras"]
        assert extras["android.intent.extra.alarm.MESSAGE"] == "pasta timer"

    def test_build_flow_skip_ui_false(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=30, skip_ui=False)
        extras = flow.steps[0].params["extras"]
        assert extras["android.intent.extra.alarm.SKIP_UI"] is False

    def test_flow_has_verifier(self):
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow()
        assert flow.steps[0].verifier == "timer_exists"


def build_flow_with_label(adapter, label):
    return adapter.build_flow(duration_seconds=60, label=label)


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

    def test_flow_calls_send_intent(self):
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=120)
        executor.execute(flow)
        assert len(handler.actions) == 1
        action, params = handler.actions[0]
        assert action == "android_send_intent"
        assert params["action"] == "android.intent.action.SET_TIMER"

    def test_flow_fallback_to_broadcast(self):
        handler = FakeHandler()
        # Make primary intent fail, broadcast succeed
        call_count = 0
        original_execute = handler.execute
        def failing_execute(action, params):
            nonlocal call_count
            call_count += 1
            if action == "android_send_intent":
                return {"success": False, "error": "Permission Denial"}
            return original_execute(action, params)
        handler.execute = failing_execute

        executor = FlowExecutor(handler)
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60)
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS
        # Should have fallen back to broadcast
        actions = [a[0] for a in handler.actions]
        assert "android_broadcast" in actions


class TestClockTimerRecipe:
    def test_recipe_loads(self):
        recipe = load_recipe_from_dict({
            "id": "clock.timer.set.v1",
            "capability": "timer.set",
            "package": "com.google.android.deskclock",
            "maturity": "candidate",
            "steps": [{
                "action": "android_send_intent",
                "params": {
                    "action": "android.intent.action.SET_TIMER",
                    "extras": {"android.intent.extra.alarm.LENGTH": 60},
                },
            }],
            "verifier": {"type": "timer_exists"},
        })
        assert recipe.id == "clock.timer.set.v1"
        assert recipe.capability == "timer.set"
        assert recipe.steps[0]["action"] == "android_send_intent"

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
