"""
Observers — bridge-backed, cheapest-first escalation for verifying capability outcomes.

Observer order (from cheapest to most expensive):
1. Direct query (timer state, alarm, media session metadata)
2. Event (pending intent, broadcast result)
3. Media session (active playback metadata)
4. Notification (notification content pattern)
5. Node search (accessibility tree text/class)
6. Screen hash/diff (visual change detection)
7. Tree (full accessibility tree traversal)
8. Screenshot (image capture — failure diagnostic only)
9. Recording (screen recording — failure diagnostic only)
"""
from __future__ import annotations

import enum
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Bridge HTTP helper ─────────────────────────────────────────────────────

def _get_bridge_json(endpoint: str, params: Optional[dict] = None) -> dict:
    """Fetch JSON from the bridge HTTP API."""
    import requests
    bridge_url = os.environ.get("ANDROID_BRIDGE_URL", "http://localhost:18766")
    token = os.environ.get("ANDROID_BRIDGE_TOKEN", "")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{bridge_url}{endpoint}"
    resp = requests.get(url, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()


# ── Priority ───────────────────────────────────────────────────────────────

class ObserverPriority(enum.IntEnum):
    """Cost-based priority — lower = cheaper."""
    DIRECT_QUERY = 10
    EVENT = 20
    MEDIA_SESSION = 30
    NOTIFICATION = 40
    NODE_SEARCH = 50
    SCREEN_HASH = 60
    TREE = 70
    SCREENSHOT = 80
    RECORDING = 90


# ── Observer Result ────────────────────────────────────────────────────────

@dataclass
class ObserverResult:
    """Result from an observer query."""
    observer_type: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    available: bool = True
    timestamp: float = field(default_factory=time.time)
    cost: int = 0
    safe_summary: str = ""


# ── Base Observer ──────────────────────────────────────────────────────────

class Observer:
    """Base class for observers."""
    priority: ObserverPriority
    name: str

    def execute(self, **kwargs) -> ObserverResult:
        raise NotImplementedError


# ── Legacy Observers (kept for backward compat) ────────────────────────────

class DirectQueryObserver(Observer):
    """Queries device state directly (timer, alarm, media session)."""
    priority = ObserverPriority.DIRECT_QUERY
    name = "direct_query"

    def execute(self, package: str = "", query: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is not None:
            return ObserverResult(
                observer_type=self.name,
                success=True,
                data=mock_data,
                cost=self.priority.value,
            )
        # Try bridge direct query
        try:
            data = _get_bridge_json("/current_app")
            return ObserverResult(
                observer_type=self.name,
                success=True,
                data=data,
                cost=self.priority.value,
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


class EventObserver(Observer):
    """Listens for broadcast/intent events."""
    priority = ObserverPriority.EVENT
    name = "event"

    def execute(self, event_type: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is not None:
            return ObserverResult(observer_type=self.name, success=True, data=mock_data,
                                  cost=self.priority.value)
        return ObserverResult(observer_type=self.name, success=False,
                              available=False, error="No event data",
                              cost=self.priority.value)


class MediaSessionObserver(Observer):
    """Queries active media sessions for playback state and metadata (legacy)."""
    priority = ObserverPriority.MEDIA_SESSION
    name = "media_session"

    def execute(self, package: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is None:
            return ObserverResult(observer_type=self.name, success=False,
                                  available=False, error="No media data",
                                  cost=self.priority.value)
        if package and mock_data.get("package") and mock_data["package"] != package:
            return ObserverResult(observer_type=self.name, success=False,
                                  error=f"Media session package mismatch: {mock_data.get('package')} != {package}",
                                  cost=self.priority.value)
        return ObserverResult(observer_type=self.name, success=True, data=mock_data,
                              cost=self.priority.value)


class NotificationObserver(Observer):
    """Reads notification content with package filtering (legacy)."""
    priority = ObserverPriority.NOTIFICATION
    name = "notification"

    def execute(self, package: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is None:
            return ObserverResult(observer_type=self.name, success=False,
                                  available=False, error="No notification data",
                                  cost=self.priority.value)
        if package and mock_data.get("package") and mock_data["package"] != package:
            return ObserverResult(observer_type=self.name, success=False,
                                  error=f"Notification package mismatch",
                                  cost=self.priority.value)
        return ObserverResult(observer_type=self.name, success=True, data=mock_data,
                              cost=self.priority.value)


class NodeSearchObserver(Observer):
    """Searches accessibility tree for nodes matching text/class criteria."""
    priority = ObserverPriority.NODE_SEARCH
    name = "node_search"

    def execute(self, text: str = "", class_name: str = "",
                mock_nodes: Optional[list] = None, **kwargs) -> ObserverResult:
        if mock_nodes is None:
            return ObserverResult(observer_type=self.name, success=False,
                                  available=False, error="No node data",
                                  cost=self.priority.value)
        for node in mock_nodes:
            if text and node.get("text") == text:
                return ObserverResult(observer_type=self.name, success=True, data=node,
                                      cost=self.priority.value)
            if class_name and node.get("className") == class_name:
                return ObserverResult(observer_type=self.name, success=True, data=node,
                                      cost=self.priority.value)
        return ObserverResult(observer_type=self.name, success=False,
                              error=f"No node matching text='{text}' class='{class_name}'",
                              cost=self.priority.value)


class ScreenHashObserver(Observer):
    """Detects visual changes via screen hash comparison."""
    priority = ObserverPriority.SCREEN_HASH
    name = "screen_hash"

    def execute(self, previous_hash: str = "",
                mock_current_hash: str = "", **kwargs) -> ObserverResult:
        changed = previous_hash != mock_current_hash if mock_current_hash else False
        return ObserverResult(
            observer_type=self.name,
            success=True,
            data={"changed": changed, "current_hash": mock_current_hash},
            cost=self.priority.value,
        )


class TreeObserver(Observer):
    """Full accessibility tree traversal — expensive."""
    priority = ObserverPriority.TREE
    name = "tree"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False,
                              available=False, error="Not implemented",
                              cost=self.priority.value)


class ScreenshotObserver(Observer):
    """Screen capture — failure diagnostic only."""
    priority = ObserverPriority.SCREENSHOT
    name = "screenshot"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False,
                              available=False, error="Not implemented",
                              cost=self.priority.value)


class RecordingObserver(Observer):
    """Screen recording — failure diagnostic only."""
    priority = ObserverPriority.RECORDING
    name = "recording"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False,
                              available=False, error="Not implemented",
                              cost=self.priority.value)


# ── Bridge-backed Observers (real endpoints) ───────────────────────────────

class CurrentAppObserver(Observer):
    """Queries current foreground app via /current_app endpoint."""
    priority = ObserverPriority.DIRECT_QUERY
    name = "current_app"

    def execute(self, **kwargs) -> ObserverResult:
        try:
            data = _get_bridge_json("/current_app")
            return ObserverResult(
                observer_type=self.name,
                success=True,
                data=data,
                cost=self.priority.value,
                safe_summary=f"App: {data.get('package', 'unknown')}",
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


class MediaSessionBridgeObserver(Observer):
    """Queries media session via bridge media endpoint."""
    priority = ObserverPriority.MEDIA_SESSION
    name = "media_session"

    def execute(self, package: str = "", **kwargs) -> ObserverResult:
        try:
            # Try /screen for media info (the bridge reports media state in tree)
            # In a real implementation, this would use a dedicated /media_session endpoint
            data = _get_bridge_json("/current_app")
            # The current_app endpoint tells us what's in foreground
            # For media, we also check if the media app is in foreground
            is_media = data.get("package", "") == package if package else False
            result_data = {
                "package": data.get("package", ""),
                "className": data.get("className", ""),
                "playing": is_media,  # If media package is foreground, assume playing
            }
            return ObserverResult(
                observer_type=self.name,
                success=True,
                data=result_data,
                cost=self.priority.value,
                safe_summary=f"Media: {result_data['package']}",
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


class NotificationBridgeObserver(Observer):
    """Queries notifications via /notifications endpoint."""
    priority = ObserverPriority.NOTIFICATION
    name = "notification"

    def execute(self, package: str = "", limit: int = 50, **kwargs) -> ObserverResult:
        try:
            data = _get_bridge_json("/notifications", {"limit": limit})
            notifications = data.get("notifications", [])
            # Filter by package if specified
            if package:
                notifications = [n for n in notifications
                                 if n.get("package") == package]
            result_data = {
                "notifications": notifications,
                "count": len(notifications),
                "package": package,
            }
            return ObserverResult(
                observer_type=self.name,
                success=len(notifications) > 0,
                data=result_data,
                cost=self.priority.value,
                safe_summary=f"Notifications: {len(notifications)} from {package or 'any'}",
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


class NodeSearchBridgeObserver(Observer):
    """Searches accessibility tree via /find_nodes endpoint."""
    priority = ObserverPriority.NODE_SEARCH
    name = "node_search"

    def execute(self, text: str = "", class_name: str = "", **kwargs) -> ObserverResult:
        try:
            params = {}
            if text:
                params["text"] = text
            if class_name:
                params["className"] = class_name
            data = _get_bridge_json("/find_nodes", params)
            nodes = data.get("nodes", [])
            return ObserverResult(
                observer_type=self.name,
                success=len(nodes) > 0,
                data={"nodes": nodes, "count": len(nodes)},
                cost=self.priority.value,
                safe_summary=f"Nodes: {len(nodes)} matching '{text or class_name}'",
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


class ScreenHashBridgeObserver(Observer):
    """Detects visual changes via /diff_screen endpoint."""
    priority = ObserverPriority.SCREEN_HASH
    name = "screen_hash"

    def execute(self, previous_hash: str = "", **kwargs) -> ObserverResult:
        try:
            data = _get_bridge_json("/screen_hash")
            current_hash = data.get("hash", "")
            changed = current_hash != previous_hash if previous_hash else False
            return ObserverResult(
                observer_type=self.name,
                success=True,
                data={"changed": changed, "current_hash": current_hash},
                cost=self.priority.value,
                safe_summary=f"Screen hash: {'changed' if changed else 'unchanged'}",
            )
        except Exception as e:
            return ObserverResult(
                observer_type=self.name,
                success=False,
                available=False,
                error=str(e),
                cost=self.priority.value,
            )


# ── Observer Registry ──────────────────────────────────────────────────────

_OBSERVERS: dict[str, type[Observer]] = {
    "direct_query": DirectQueryObserver,
    "event": EventObserver,
    "media_session": MediaSessionObserver,
    "notification": NotificationObserver,
    "node_search": NodeSearchObserver,
    "screen_hash": ScreenHashObserver,
    "tree": TreeObserver,
    "screenshot": ScreenshotObserver,
    "recording": RecordingObserver,
    # Bridge-backed observers (prefer these over legacy mock-based ones)
    "current_app": CurrentAppObserver,
    "media_session_bridge": MediaSessionBridgeObserver,
    "notification_bridge": NotificationBridgeObserver,
    "node_search_bridge": NodeSearchBridgeObserver,
    "screen_hash_bridge": ScreenHashBridgeObserver,
}


def select_observers(names: list[str]) -> list[Observer]:
    """Return observers by name, ordered by priority (cheapest first).

    If names is empty, return all observers.
    """
    if not names:
        instances = [cls() for cls in _OBSERVERS.values()]
    else:
        instances = []
        for name in names:
            cls = _OBSERVERS.get(name)
            if cls:
                instances.append(cls())
    return sorted(instances, key=lambda o: o.priority.value)


# ── Verifier-Observer Mapping ──────────────────────────────────────────────

_VERIFIER_OBSERVER_MAP: dict[str, str] = {
    "timer_exists": "direct_query",
    "media_state": "media_session",
    "notification_pattern": "notification",
    "node_predicate": "node_search",
    "screen_transition": "screen_hash",
    "screen_changed": "screen_hash",
    "route_active": "current_app",
    "favorite_saved": "current_app",
}


def select_observer_for_verifier(verifier_name: str) -> Observer:
    """Select the cheapest observer capable of verifying a condition."""
    obs_name = _VERIFIER_OBSERVER_MAP.get(verifier_name, "direct_query")
    cls = _OBSERVERS.get(obs_name, DirectQueryObserver)
    return cls()


# ── Escalation Verification ───────────────────────────────────────────────

def verify_with_escalation(
    verifier,
    observers: list[Callable[[], ObserverResult]],
) -> "VerificationResult":
    """Try each observer (cheapest first) until verifier confirms.

    Returns the first confirmed result, or INCONCLUSIVE if none confirm.
    """
    from .models import VerificationOutcome, VerificationResult

    for obs_fn in observers:
        try:
            result = obs_fn()
        except Exception:
            continue

        if not result.success or not result.data:
            continue

        vresult = verifier.verify(result.data)
        if vresult.outcome == VerificationOutcome.CONFIRMED:
            return vresult

    return VerificationResult(
        outcome=VerificationOutcome.INCONCLUSIVE,
        verifier_type=verifier.name if hasattr(verifier, 'name') else "unknown",
    )
