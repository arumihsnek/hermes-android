"""
Persistence — SQLite-backed storage for traces, metrics, nonces,
negative learning, discoveries, and lifecycle state.

Path: ~/.hermes/android-capabilities/state.db
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

from .metrics import ExecutionMetric
from .models import FlowTrace, TraceEvent, EvidenceReference


# ── Schema ─────────────────────────────────────────────────────────────────

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    recipe_id TEXT,
    created_at REAL NOT NULL,
    events_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    recipe_id TEXT NOT NULL,
    success INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    response_size INTEGER NOT NULL,
    model_calls INTEGER NOT NULL,
    observer_choice TEXT NOT NULL,
    false_positive INTEGER NOT NULL,
    context_tokens INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    failure_class TEXT,
    fragility REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS nonces (
    nonce TEXT PRIMARY KEY,
    recorded_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS incompatible_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    package TEXT NOT NULL,
    fingerprint_digest TEXT NOT NULL,
    method TEXT NOT NULL,
    failure_reason TEXT NOT NULL,
    recorded_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    package TEXT NOT NULL,
    recipe_id TEXT,
    success INTEGER NOT NULL,
    recorded_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_lifecycle (
    recipe_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    failure_count INTEGER DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_capability ON traces(capability);
CREATE INDEX IF NOT EXISTS idx_traces_created ON traces(created_at);
CREATE INDEX IF NOT EXISTS idx_metrics_capability ON metrics(capability);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_incomp_routes_fp ON incompatible_routes(fingerprint_digest, capability, method);
CREATE INDEX IF NOT EXISTS idx_discoveries_cap ON discoveries(capability);
"""


# ── Store ──────────────────────────────────────────────────────────────────

class CapabilityStateStore:
    """SQLite-backed persistence for the capability system.

    Default path: ~/.hermes/android-capabilities/state.db
    Use ":memory:" for tests.
    """

    def __init__(
        self,
        db_path: str = "",
        max_traces: int = 1000,
        max_metrics: int = 5000,
    ):
        if not db_path:
            home = os.path.expanduser("~")
            db_dir = os.path.join(home, ".hermes", "android-capabilities")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "state.db")

        self._db_path = db_path
        self._max_traces = max_traces
        self._max_metrics = max_metrics
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        """Run schema migration (idempotent)."""
        self._conn.executescript(_SCHEMA_SQL)
        # Set schema version
        self._conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("schema_version", str(_SCHEMA_VERSION)),
        )
        self._conn.commit()

    def schema_version(self) -> int:
        """Get current schema version."""
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()

    # ── Traces ─────────────────────────────────────────────────────────────

    def save_trace(self, trace: FlowTrace) -> None:
        """Save a flow trace to the database."""
        events_data = []
        for evt in trace.events:
            events_data.append({
                "event_type": evt.event_type,
                "timestamp": evt.timestamp,
                "detail": evt.detail,
                "evidence_refs": [
                    {
                        "evidence_id": ref.evidence_id,
                        "observer_type": ref.observer_type,
                        "timestamp": ref.timestamp,
                        "safe_summary": ref.safe_summary,
                    }
                    for ref in evt.evidence_refs
                ],
            })
        self._conn.execute(
            "INSERT OR REPLACE INTO traces (trace_id, capability, recipe_id, created_at, events_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (trace.trace_id, trace.capability, trace.recipe_id,
             time.time(), json.dumps(events_data)),
        )
        self._conn.commit()

    def get_trace(self, trace_id: str) -> Optional[FlowTrace]:
        """Retrieve a trace by ID."""
        row = self._conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if not row:
            return None
        trace = FlowTrace(
            trace_id=row["trace_id"],
            capability=row["capability"],
            recipe_id=row["recipe_id"],
        )
        events_data = json.loads(row["events_json"])
        for evt_dict in events_data:
            refs = [
                EvidenceReference(
                    evidence_id=r["evidence_id"],
                    observer_type=r["observer_type"],
                    timestamp=r["timestamp"],
                    safe_summary=r["safe_summary"],
                )
                for r in evt_dict.get("evidence_refs", [])
            ]
            trace.events.append(TraceEvent(
                event_type=evt_dict["event_type"],
                timestamp=evt_dict["timestamp"],
                detail=evt_dict.get("detail", {}),
                evidence_refs=refs,
            ))
        return trace

    def cleanup(self) -> None:
        """Remove old traces exceeding the limit."""
        self._conn.execute(
            "DELETE FROM traces WHERE trace_id NOT IN "
            "(SELECT trace_id FROM traces ORDER BY created_at DESC LIMIT ?)",
            (self._max_traces,),
        )
        self._conn.commit()

    # ── Metrics ────────────────────────────────────────────────────────────

    def save_metric(self, metric: ExecutionMetric) -> None:
        """Save an execution metric."""
        self._conn.execute(
            "INSERT INTO metrics (capability, recipe_id, success, latency_ms, "
            "response_size, model_calls, observer_choice, false_positive, "
            "context_tokens, timestamp, failure_class, fragility) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (metric.capability, metric.recipe_id, int(metric.success),
             metric.latency_ms, metric.response_size, metric.model_calls,
             metric.observer_choice, int(metric.false_positive),
             metric.context_tokens, metric.timestamp or time.time(),
             metric.failure_class, metric.fragility),
        )
        self._conn.commit()

    def get_metrics(self, capability: str) -> list[ExecutionMetric]:
        """Retrieve metrics for a capability."""
        rows = self._conn.execute(
            "SELECT * FROM metrics WHERE capability = ? ORDER BY timestamp DESC",
            (capability,),
        ).fetchall()
        return [
            ExecutionMetric(
                capability=r["capability"],
                recipe_id=r["recipe_id"],
                success=bool(r["success"]),
                latency_ms=r["latency_ms"],
                response_size=r["response_size"],
                model_calls=r["model_calls"],
                observer_choice=r["observer_choice"],
                false_positive=bool(r["false_positive"]),
                context_tokens=r["context_tokens"],
                timestamp=r["timestamp"],
                failure_class=r["failure_class"],
                fragility=r["fragility"],
            )
            for r in rows
        ]

    # ── Nonces ─────────────────────────────────────────────────────────────

    def record_nonce(self, nonce: str) -> None:
        """Record a used nonce for replay protection."""
        self._conn.execute(
            "INSERT OR IGNORE INTO nonces (nonce, recorded_at) VALUES (?, ?)",
            (nonce, time.time()),
        )
        self._conn.commit()

    def is_nonce_used(self, nonce: str) -> bool:
        """Check if a nonce has been used."""
        row = self._conn.execute(
            "SELECT 1 FROM nonces WHERE nonce = ?", (nonce,)
        ).fetchone()
        return row is not None

    # ── Negative Learning ──────────────────────────────────────────────────

    def record_incompatible_route(
        self,
        capability: str,
        package: str,
        fingerprint_digest: str,
        method: str,
        failure_reason: str,
    ) -> None:
        """Record an incompatible route to avoid in future."""
        self._conn.execute(
            "INSERT INTO incompatible_routes "
            "(capability, package, fingerprint_digest, method, failure_reason, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (capability, package, fingerprint_digest, method, failure_reason, time.time()),
        )
        self._conn.commit()

    def is_route_incompatible(
        self, fingerprint_digest: str, capability: str, method: str
    ) -> bool:
        """Check if a route should be skipped based on negative learning."""
        row = self._conn.execute(
            "SELECT 1 FROM incompatible_routes "
            "WHERE fingerprint_digest = ? AND capability = ? AND method = ?",
            (fingerprint_digest, capability, method),
        ).fetchone()
        return row is not None

    # ── Discovery ──────────────────────────────────────────────────────────

    def save_discovery(
        self,
        capability: str,
        package: str,
        recipe_id: str,
        success: bool,
    ) -> None:
        """Save a discovery result."""
        self._conn.execute(
            "INSERT INTO discoveries (capability, package, recipe_id, success, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (capability, package, recipe_id, int(success), time.time()),
        )
        self._conn.commit()

    def get_discoveries(self, capability: str) -> list[dict[str, Any]]:
        """Retrieve discovery results for a capability."""
        rows = self._conn.execute(
            "SELECT * FROM discoveries WHERE capability = ? ORDER BY recorded_at DESC",
            (capability,),
        ).fetchall()
        return [
            {
                "capability": r["capability"],
                "package": r["package"],
                "recipe_id": r["recipe_id"],
                "success": bool(r["success"]),
                "recorded_at": r["recorded_at"],
            }
            for r in rows
        ]

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def set_recipe_state(self, recipe_id: str, state: str) -> None:
        """Set recipe lifecycle state."""
        self._conn.execute(
            "INSERT OR REPLACE INTO recipe_lifecycle (recipe_id, state, failure_count, updated_at) "
            "VALUES (?, ?, COALESCE((SELECT failure_count FROM recipe_lifecycle WHERE recipe_id = ?), 0), ?)",
            (recipe_id, state, recipe_id, time.time()),
        )
        self._conn.commit()

    def get_recipe_state(self, recipe_id: str) -> Optional[str]:
        """Get recipe lifecycle state."""
        row = self._conn.execute(
            "SELECT state FROM recipe_lifecycle WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
        return row["state"] if row else None

    def record_failure(self, recipe_id: str, reason: str) -> None:
        """Record a failure for a recipe (increments failure count)."""
        self._conn.execute(
            "INSERT INTO recipe_lifecycle (recipe_id, state, failure_count, updated_at) "
            "VALUES (?, 'active', 1, ?) "
            "ON CONFLICT(recipe_id) DO UPDATE SET "
            "failure_count = failure_count + 1, updated_at = ?",
            (recipe_id, time.time(), time.time()),
        )
        self._conn.commit()

    def failure_count(self, recipe_id: str) -> int:
        """Get failure count for a recipe."""
        row = self._conn.execute(
            "SELECT failure_count FROM recipe_lifecycle WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
        return row["failure_count"] if row else 0
