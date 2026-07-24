"""Tests for Task 9: Metrics, negative learning, and recipe lifecycle."""

import json
import time
import pytest

from tools.capabilities.metrics import (
    ExecutionMetric,
    MetricsCollector,
    MetricSummary,
)
from tools.capabilities.negative_learning import (
    IncompatibleRoute,
    NegativeLearningStore,
)
from tools.capabilities.recipe_lifecycle import (
    RecipeLifecycle,
    PromotionEvidence,
    can_promote,
)


# ── Metrics Tests ────────────────────────────────────────────────────────────

class TestExecutionMetric:
    """Individual execution metric record."""

    def test_create_metric(self):
        m = ExecutionMetric(
            capability="timer.set",
            recipe_id="r1",
            success=True,
            latency_ms=150,
            response_size=2048,
            model_calls=1,
            observer_choice="direct_query",
            false_positive=False,
            context_tokens=500,
        )
        assert m.capability == "timer.set"
        assert m.success is True

    def test_to_dict_roundtrip(self):
        m = ExecutionMetric(
            capability="test", recipe_id="r1", success=True,
            latency_ms=100, response_size=512, model_calls=0,
            observer_choice="direct_query", false_positive=False,
            context_tokens=0,
        )
        d = m.to_dict()
        m2 = ExecutionMetric.from_dict(d)
        assert m2.capability == m.capability
        assert m2.success == m.success


class TestMetricsCollector:
    """Collects and summarizes execution metrics."""

    def test_record_and_query(self):
        collector = MetricsCollector()
        collector.record(ExecutionMetric(
            capability="timer.set", recipe_id="r1", success=True,
            latency_ms=100, response_size=512, model_calls=1,
            observer_choice="direct_query", false_positive=False,
            context_tokens=0,
        ))
        assert collector.count() == 1

    def test_summary計算(self):
        collector = MetricsCollector()
        for i in range(5):
            collector.record(ExecutionMetric(
                capability="timer.set", recipe_id="r1", success=i < 4,
                latency_ms=100 + i * 10, response_size=512, model_calls=1,
                observer_choice="direct_query", false_positive=False,
                context_tokens=0,
            ))
        summary = collector.summary("timer.set")
        assert summary.total == 5
        assert summary.successes == 4
        assert summary.failures == 1
        assert summary.success_rate == 0.8

    def test_summary_empty(self):
        collector = MetricsCollector()
        summary = collector.summary("nonexistent")
        assert summary.total == 0


class TestMetricSummary:
    """Summary statistics for a capability."""

    def test_properties(self):
        s = MetricSummary(
            capability="test", total=10, successes=8, failures=2,
            avg_latency_ms=120.0, false_positives=1,
        )
        assert s.success_rate == 0.8
        assert s.false_positive_rate == 0.1


# ── Negative Learning Tests ─────────────────────────────────────────────────

class TestIncompatibleRoute:
    """Record of an incompatible route for a specific fingerprint."""

    def test_create_route(self):
        route = IncompatibleRoute(
            capability="timer.set",
            package="com.example",
            fingerprint_digest="abc123",
            method="ui_automation",
            failure_reason="Timer UI not found",
            evidence="screenshot showing no timer",
            retest_after="app_update",
        )
        assert route.capability == "timer.set"
        assert route.is_retestable("app_update")

    def test_not_retestable(self):
        route = IncompatibleRoute(
            capability="test", package="com.example",
            fingerprint_digest="abc", method="ui",
            failure_reason="error", evidence="",
        )
        assert not route.is_retestable("version_bump")


class TestNegativeLearningStore:
    """Store of incompatible routes for a fingerprint."""

    def test_record_and_query(self):
        store = NegativeLearningStore()
        route = IncompatibleRoute(
            capability="timer.set", package="com.example",
            fingerprint_digest="abc123", method="ui",
            failure_reason="not found", evidence="",
        )
        store.record(route)
        incompatible = store.get_incompatible("abc123", capability="timer.set")
        assert len(incompatible) == 1

    def test_skip_incompatible_route(self):
        store = NegativeLearningStore()
        store.record(IncompatibleRoute(
            capability="timer.set", package="com.example",
            fingerprint_digest="abc123", method="ui",
            failure_reason="not found", evidence="",
        ))
        assert store.should_skip("abc123", "timer.set", "ui") is True
        assert store.should_skip("abc123", "timer.set", "direct") is False

    def test_different_fingerprint_not_affected(self):
        store = NegativeLearningStore()
        store.record(IncompatibleRoute(
            capability="test", package="com.example",
            fingerprint_digest="abc", method="ui",
            failure_reason="err", evidence="",
        ))
        assert store.should_skip("xyz", "test", "ui") is False


# ── Recipe Lifecycle Tests ───────────────────────────────────────────────────

class TestRecipeLifecycle:
    """Recipe promotion and quarantine lifecycle."""

    def test_can_promote_with_evidence(self):
        evidence = PromotionEvidence(
            successful_runs=5,
            false_positives=0,
            last_success_time=time.time(),
        )
        assert can_promote(evidence, from_state="candidate", to_state="dogfood") is True

    def test_cannot_promote_without_evidence(self):
        evidence = PromotionEvidence(
            successful_runs=0,
            false_positives=0,
            last_success_time=0,
        )
        assert can_promote(evidence, from_state="candidate", to_state="dogfood") is False

    def test_cannot_promote_with_false_positives(self):
        evidence = PromotionEvidence(
            successful_runs=5,
            false_positives=2,
            last_success_time=time.time(),
        )
        assert can_promote(evidence, from_state="dogfood", to_state="stable") is False

    def test_quarantine_on_repeated_failure(self):
        lifecycle = RecipeLifecycle()
        lifecycle.record_failure("r1", "timer not found")
        lifecycle.record_failure("r1", "timer not found")
        lifecycle.record_failure("r1", "timer not found")
        assert lifecycle.should_quarantine("r1") is True
