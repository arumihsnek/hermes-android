"""Metrics — execution metrics collection and summarization."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExecutionMetric:
    """Record of a single capability execution."""
    capability: str
    recipe_id: str
    success: bool
    latency_ms: float
    response_size: int
    model_calls: int
    observer_choice: str
    false_positive: bool
    context_tokens: int
    timestamp: float = field(default_factory=time.time)
    failure_class: Optional[str] = None
    fragility: float = 0.0  # 0=stable, 1=fragile

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "recipe_id": self.recipe_id,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "response_size": self.response_size,
            "model_calls": self.model_calls,
            "observer_choice": self.observer_choice,
            "false_positive": self.false_positive,
            "context_tokens": self.context_tokens,
            "timestamp": self.timestamp,
            "failure_class": self.failure_class,
            "fragility": self.fragility,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionMetric:
        return cls(
            capability=data["capability"],
            recipe_id=data["recipe_id"],
            success=data["success"],
            latency_ms=data["latency_ms"],
            response_size=data["response_size"],
            model_calls=data["model_calls"],
            observer_choice=data["observer_choice"],
            false_positive=data["false_positive"],
            context_tokens=data["context_tokens"],
            timestamp=data.get("timestamp", 0),
            failure_class=data.get("failure_class"),
            fragility=data.get("fragility", 0.0),
        )


@dataclass
class MetricSummary:
    """Summary statistics for a capability."""
    capability: str
    total: int
    successes: int
    failures: int
    avg_latency_ms: float
    false_positives: int

    @property
    def success_rate(self) -> float:
        return self.successes / self.total if self.total > 0 else 0.0

    @property
    def false_positive_rate(self) -> float:
        return self.false_positives / self.total if self.total > 0 else 0.0


class MetricsCollector:
    """Collects execution metrics and computes summaries."""

    def __init__(self):
        self._metrics: list[ExecutionMetric] = []

    def record(self, metric: ExecutionMetric) -> None:
        self._metrics.append(metric)

    def count(self) -> int:
        return len(self._metrics)

    def summary(self, capability: str) -> MetricSummary:
        """Compute summary for a specific capability."""
        relevant = [m for m in self._metrics if m.capability == capability]
        if not relevant:
            return MetricSummary(
                capability=capability, total=0, successes=0, failures=0,
                avg_latency_ms=0.0, false_positives=0,
            )
        successes = sum(1 for m in relevant if m.success)
        failures = len(relevant) - successes
        avg_latency = sum(m.latency_ms for m in relevant) / len(relevant)
        fp = sum(1 for m in relevant if m.false_positive)
        return MetricSummary(
            capability=capability,
            total=len(relevant),
            successes=successes,
            failures=failures,
            avg_latency_ms=avg_latency,
            false_positives=fp,
        )

    def all_for_capability(self, capability: str) -> list[ExecutionMetric]:
        return [m for m in self._metrics if m.capability == capability]
