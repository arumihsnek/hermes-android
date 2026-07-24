"""
Observers — cheapest-first escalation for verifying capability outcomes.

Observer order (from cheapest to most expensive):
1. Direct query (timer state, media session metadata)
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
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


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


@dataclass
class ObserverResult:
    """Result from an observer query."""
    observer_type: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class Observer:
    """Base class for observers."""
    priority: ObserverPriority
    name: str

    def execute(self, **kwargs) -> ObserverResult:
        raise NotImplementedError


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
            )
        return ObserverResult(
            observer_type=self.name,
            success=False,
            error=f"No mock data for query '{query}'",
        )


class EventObserver(Observer):
    """Listens for broadcast/intent events."""
    priority = ObserverPriority.EVENT
    name = "event"

    def execute(self, event_type: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is not None:
            return ObserverResult(observer_type=self.name, success=True, data=mock_data)
        return ObserverResult(observer_type=self.name, success=False, error="No event data")


class MediaSessionObserver(Observer):
    """Queries active media sessions for playback state and metadata."""
    priority = ObserverPriority.MEDIA_SESSION
    name = "media_session"

    def execute(self, package: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is None:
            return ObserverResult(observer_type=self.name, success=False, error="No media data")
        # Filter by package if specified
        if package and mock_data.get("package") and mock_data["package"] != package:
            return ObserverResult(observer_type=self.name, success=False,
                                  error=f"Media session package mismatch: {mock_data.get('package')} != {package}")
        return ObserverResult(observer_type=self.name, success=True, data=mock_data)


class NotificationObserver(Observer):
    """Reads notification content with package filtering."""
    priority = ObserverPriority.NOTIFICATION
    name = "notification"

    def execute(self, package: str = "",
                mock_data: Optional[dict] = None, **kwargs) -> ObserverResult:
        if mock_data is None:
            return ObserverResult(observer_type=self.name, success=False, error="No notification data")
        if package and mock_data.get("package") and mock_data["package"] != package:
            return ObserverResult(observer_type=self.name, success=False,
                                  error=f"Notification package mismatch")
        return ObserverResult(observer_type=self.name, success=True, data=mock_data)


class NodeSearchObserver(Observer):
    """Searches accessibility tree for nodes matching text/class criteria."""
    priority = ObserverPriority.NODE_SEARCH
    name = "node_search"

    def execute(self, text: str = "", class_name: str = "",
                mock_nodes: Optional[list] = None, **kwargs) -> ObserverResult:
        if mock_nodes is None:
            return ObserverResult(observer_type=self.name, success=False, error="No node data")
        for node in mock_nodes:
            if text and node.get("text") == text:
                return ObserverResult(observer_type=self.name, success=True, data=node)
            if class_name and node.get("className") == class_name:
                return ObserverResult(observer_type=self.name, success=True, data=node)
        return ObserverResult(observer_type=self.name, success=False,
                              error=f"No node matching text='{text}' class='{class_name}'")


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
        )


class TreeObserver(Observer):
    """Full accessibility tree traversal — expensive."""
    priority = ObserverPriority.TREE
    name = "tree"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False, error="Not implemented")


class ScreenshotObserver(Observer):
    """Screen capture — failure diagnostic only."""
    priority = ObserverPriority.SCREENSHOT
    name = "screenshot"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False, error="Not implemented in contract test")


class RecordingObserver(Observer):
    """Screen recording — failure diagnostic only."""
    priority = ObserverPriority.RECORDING
    name = "recording"

    def execute(self, **kwargs) -> ObserverResult:
        return ObserverResult(observer_type=self.name, success=False, error="Not implemented in contract test")


# ── Observer Registry ────────────────────────────────────────────────────────

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
