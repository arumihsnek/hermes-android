"""
Canonical action contract — single source of truth for all actions in the
capability system. Every adapter, recipe, and handler must agree on these names.

Separation:
  - executable: actions that map to a bridge HTTP endpoint
  - semantic:   high-level actions that require transformation before dispatch
  - verifier:   verification-only actions (never dispatched)

Route priority (A > B > C):
  A (INTENT_API=10):    intent, API, provider, deep link, direct tool
  B (BRIDGE_NATIVE=20): bridge native, shell/Shizuku, accessibility
  C (UI_AUTOMATOR=30):  UI Automator (Plan C — requires incompatibility evidence)
"""
from __future__ import annotations

import enum
from typing import Any, Optional


# ── Route Priority ─────────────────────────────────────────────────────────

class RoutePriority(enum.IntEnum):
    """Route selection priority — lower = preferred."""
    INTENT_API = 10       # Plan A: intent, API, provider, deep link
    BRIDGE_NATIVE = 20    # Plan B: bridge native, shell, accessibility
    UI_AUTOMATOR = 30     # Plan C: UI Automator (requires incompatibility evidence)


# ── Action Catalog ─────────────────────────────────────────────────────────

ACTION_CATALOG: dict[str, dict[str, Any]] = {
    # ── Executable actions (Plan B: bridge native) ──────────────────────────
    "android_tap": {
        "bridge_endpoint": "/tap",
        "params": {"x": "int", "y": "int", "nodeId": "str?"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Tap at coordinates or node",
    },
    "android_tap_text": {
        "bridge_endpoint": "/tap_text",
        "params": {"text": "str", "exact": "bool"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Tap on element with matching text",
    },
    "android_tap_res_id": {
        "bridge_endpoint": "/tap_res_id",
        "params": {"resId": "str"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Tap on element by resource ID",
    },
    "android_type": {
        "bridge_endpoint": "/type",
        "params": {"text": "str", "clearFirst": "bool?"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": ["android_type_text"],
        "description": "Type text into focused field",
    },
    "android_type_text": {
        "bridge_endpoint": "/type",
        "params": {"text": "str", "clearFirst": "bool?"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Alias for android_type — type text into focused field",
    },
    "android_swipe": {
        "bridge_endpoint": "/swipe",
        "params": {"direction": "str", "distance": "str?"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Swipe in direction",
    },
    "android_open_app": {
        "bridge_endpoint": "/open_app",
        "params": {"packageName": "str"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Launch an app by package name",
    },
    "android_press_key": {
        "bridge_endpoint": "/press_key",
        "params": {"key": "str"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Press a key (home, back, recents, ENTER)",
    },
    "android_scroll": {
        "bridge_endpoint": "/scroll",
        "params": {"direction": "str", "nodeId": "str?"},
        "category": "executable",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Scroll in direction",
    },

    # ── Executable actions (Plan A: intent/API) ─────────────────────────────
    "android_send_intent": {
        "bridge_endpoint": "/intent",
        "params": {"action": "str", "extras": "dict?", "dataUri": "str?",
                   "packageOverride": "str?"},
        "category": "executable",
        "route_priority": RoutePriority.INTENT_API,
        "aliases": [],
        "description": "Send an Android intent",
    },
    "android_broadcast": {
        "bridge_endpoint": "/broadcast",
        "params": {"action": "str", "extras": "dict?"},
        "category": "executable",
        "route_priority": RoutePriority.INTENT_API,
        "aliases": [],
        "description": "Send a broadcast intent",
    },

    # ── Semantic actions (require transformation before dispatch) ────────────
    "message.send": {
        "bridge_endpoint": "",
        "params": {"contact": "str", "message": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Send a message — requires confirmation, resolved to UI steps",
    },
    "message.verify_sent": {
        "bridge_endpoint": "",
        "params": {"contact": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Verify a message was sent",
    },
    "navigate_driving": {
        "bridge_endpoint": "",
        "params": {"destination": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.INTENT_API,
        "aliases": [],
        "description": "Start driving navigation — confirmation required",
    },
    "media.play": {
        "bridge_endpoint": "",
        "params": {"query": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Play media content",
    },
    "timer.set": {
        "bridge_endpoint": "",
        "params": {"duration_seconds": "int", "label": "str?"},
        "category": "semantic",
        "route_priority": RoutePriority.INTENT_API,
        "aliases": [],
        "description": "Set a timer",
    },
    "podcast.subscribe": {
        "bridge_endpoint": "",
        "params": {"podcast_name": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Subscribe to a podcast",
    },
    "route.start": {
        "bridge_endpoint": "",
        "params": {"destination": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.INTENT_API,
        "aliases": [],
        "description": "Start navigation route",
    },
    "place.save": {
        "bridge_endpoint": "",
        "params": {"place_name": "str"},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Save a location as favorite",
    },
    "updates.pause": {
        "bridge_endpoint": "",
        "params": {},
        "category": "semantic",
        "route_priority": RoutePriority.BRIDGE_NATIVE,
        "aliases": [],
        "description": "Pause auto-updates in Play Store",
    },
}

# Build reverse alias map for fast lookup
_ALIAS_MAP: dict[str, str] = {}
for _name, _entry in ACTION_CATALOG.items():
    for _alias in _entry.get("aliases", []):
        _ALIAS_MAP[_alias] = _name


# ── Resolution Functions ───────────────────────────────────────────────────

def resolve_action(name: str) -> Optional[dict[str, Any]]:
    """Resolve an action name to its catalog entry.

    Returns the catalog entry if found (directly or via alias), None otherwise.
    """
    if name in ACTION_CATALOG:
        return ACTION_CATALOG[name]
    canonical = _ALIAS_MAP.get(name)
    if canonical and canonical in ACTION_CATALOG:
        return ACTION_CATALOG[canonical]
    return None


def validate_action(name: str) -> list[str]:
    """Validate that an action is in the catalog.

    Returns a list of error messages (empty if valid).
    """
    entry = resolve_action(name)
    if entry is None:
        return [f"Unknown action: '{name}' — not in canonical action catalog"]
    return []


def validate_flow_actions(flow) -> list[str]:
    """Validate all actions in a flow definition against the catalog.

    Returns a list of error messages (empty if all actions are valid).
    """
    errors = []
    for i, step in enumerate(flow.steps):
        step_errors = validate_action(step.action)
        for err in step_errors:
            errors.append(f"Step {i}: {err}")
        if step.fallback:
            fb_errors = validate_action(step.fallback.action)
            for err in fb_errors:
                errors.append(f"Step {i} fallback: {err}")
    return errors


def get_bridge_endpoint(action: str) -> Optional[str]:
    """Get the bridge endpoint for an executable action.

    Returns the endpoint path if the action is executable, None otherwise.
    """
    entry = resolve_action(action)
    if entry and entry["category"] == "executable":
        return entry["bridge_endpoint"]
    return None


def is_executable(action: str) -> bool:
    """Check if an action is directly executable on the bridge."""
    entry = resolve_action(action)
    return entry is not None and entry["category"] == "executable"


def is_semantic(action: str) -> bool:
    """Check if an action is a semantic capability action."""
    entry = resolve_action(action)
    return entry is not None and entry["category"] == "semantic"


def get_route_priority(action: str) -> Optional[int]:
    """Get the route priority for an action."""
    entry = resolve_action(action)
    if entry:
        return entry["route_priority"]
    return None
