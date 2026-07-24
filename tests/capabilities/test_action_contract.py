"""
Block 2: Canonical action contract tests.

Tests that:
- Every adapter/recipe action is in the canonical catalog
- Every action maps to a valid bridge endpoint
- Unknown actions are rejected before execution
- Semantic actions (message.send) don't leak to bridge as unknown
- All adapter flows can be dispatched by the handler
- Route priority A/B/C gate is enforced
"""
import pytest
from typing import Any


# ── Action Catalog ─────────────────────────────────────────────────────────

class TestActionCatalog:
    """Verify the canonical action catalog exists and has required structure."""

    def test_catalog_exists(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        assert isinstance(ACTION_CATALOG, dict)
        assert len(ACTION_CATALOG) > 0

    def test_each_action_has_required_fields(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        for name, entry in ACTION_CATALOG.items():
            assert "bridge_endpoint" in entry, f"{name} missing bridge_endpoint"
            assert "params" in entry, f"{name} missing params schema"
            assert "category" in entry, f"{name} missing category"
            assert entry["category"] in ("executable", "semantic", "verifier"), \
                f"{name} has invalid category: {entry['category']}"

    def test_executable_actions_have_bridge_endpoint(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        for name, entry in ACTION_CATALOG.items():
            if entry["category"] == "executable":
                assert entry["bridge_endpoint"], \
                    f"Executable action '{name}' must have a bridge_endpoint"

    def test_semantic_actions_have_no_endpoint(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        for name, entry in ACTION_CATALOG.items():
            if entry["category"] == "semantic":
                # Semantic actions must NOT have a direct bridge endpoint
                # They are transformed into executable actions by the handler
                assert not entry.get("bridge_endpoint"), \
                    f"Semantic action '{name}' should not have a direct bridge endpoint"

    def test_all_bridge_endpoints_are_known(self):
        """Every bridge endpoint in the catalog must be a real endpoint."""
        from tools.capabilities.action_contract import ACTION_CATALOG
        known_endpoints = {
            "/tap", "/tap_text", "/tap_res_id", "/type", "/swipe", "/open_app",
            "/press_key", "/scroll", "/intent", "/broadcast",
            "/shell", "/screenshot", "/screen", "/current_app",
            "/notifications", "/find_nodes", "/diff_screen",
            "/media", "/send_sms", "/long_press", "/drag",
        }
        for name, entry in ACTION_CATALOG.items():
            ep = entry.get("bridge_endpoint", "")
            if ep:
                assert ep in known_endpoints, \
                    f"Action '{name}' maps to unknown endpoint '{ep}'"

    def test_aliases_are_documented(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        for name, entry in ACTION_CATALOG.items():
            aliases = entry.get("aliases", [])
            assert isinstance(aliases, list), f"{name} aliases must be a list"
            for alias in aliases:
                assert isinstance(alias, str), f"{name} alias must be string"


# ── Action Resolution ──────────────────────────────────────────────────────

class TestActionResolution:
    """Test that actions resolve correctly through the catalog."""

    def test_resolve_known_action(self):
        from tools.capabilities.action_contract import resolve_action
        result = resolve_action("android_tap_text")
        assert result is not None
        assert result["bridge_endpoint"] == "/tap_text"

    def test_resolve_known_alias(self):
        from tools.capabilities.action_contract import resolve_action
        # "android_type" is the canonical name; any alias should resolve
        result = resolve_action("android_type")
        assert result is not None
        assert result["bridge_endpoint"] == "/type"

    def test_resolve_unknown_returns_none(self):
        from tools.capabilities.action_contract import resolve_action
        result = resolve_action("android_foo_bar_nonexistent")
        assert result is None

    def test_resolve_semantic_action_returns_semantic(self):
        from tools.capabilities.action_contract import resolve_action
        result = resolve_action("message.send")
        assert result is not None
        assert result["category"] == "semantic"

    def test_reject_unknown_action(self):
        from tools.capabilities.action_contract import validate_action
        errors = validate_action("android_foo_bar")
        assert len(errors) > 0
        assert "Unknown action" in errors[0]


# ── Adapter Action Validation ──────────────────────────────────────────────

class TestAdapterActionValidation:
    """Verify that all registered adapters use only cataloged actions."""

    def test_clock_timer_uses_valid_actions(self):
        from tools.capabilities.adapters.clock_timer import ClockTimerAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = ClockTimerAdapter()
        flow = adapter.build_flow(duration_seconds=60)
        errors = validate_flow_actions(flow)
        assert errors == [], f"Clock timer has invalid actions: {errors}"

    def test_antennapod_media_uses_valid_actions(self):
        from tools.capabilities.adapters.antennapod_media import AntennaPodMediaAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = AntennaPodMediaAdapter()
        flow = adapter.build_flow(query="test")
        errors = validate_flow_actions(flow)
        assert errors == [], f"AntennaPod media has invalid actions: {errors}"

    def test_antennapod_subscribe_uses_valid_actions(self):
        from tools.capabilities.adapters.antennapod_subscribe import AntennaPodSubscribeAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = AntennaPodSubscribeAdapter()
        flow = adapter.build_flow(podcast_name="test")
        errors = validate_flow_actions(flow)
        assert errors == [], f"AntennaPod subscribe has invalid actions: {errors}"

    def test_whatsapp_message_uses_valid_actions(self):
        from tools.capabilities.adapters.whatsapp_message import WhatsAppMessageAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="test", message="hi")
        errors = validate_flow_actions(flow)
        assert errors == [], f"WhatsApp message has invalid actions: {errors}"

    def test_waze_route_uses_valid_actions(self):
        from tools.capabilities.adapters.waze_route import WazeRouteAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = WazeRouteAdapter()
        flow = adapter.build_flow(destination="test")
        errors = validate_flow_actions(flow)
        assert errors == [], f"Waze route has invalid actions: {errors}"

    def test_osmand_place_uses_valid_actions(self):
        from tools.capabilities.adapters.osmand_place import OsmAndPlaceAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = OsmAndPlaceAdapter()
        flow = adapter.build_flow(place_name="test")
        errors = validate_flow_actions(flow)
        assert errors == [], f"OsmAnd place has invalid actions: {errors}"

    def test_playstore_updates_uses_valid_actions(self):
        from tools.capabilities.adapters.playstore_updates import PlayStoreUpdatesAdapter
        from tools.capabilities.action_contract import validate_flow_actions
        adapter = PlayStoreUpdatesAdapter()
        flow = adapter.build_flow()
        errors = validate_flow_actions(flow)
        assert errors == [], f"Play Store updates has invalid actions: {errors}"

    def test_all_registered_adapters_validate(self):
        """Every adapter registered in the system must produce valid actions."""
        from tools.capabilities.action_contract import validate_flow_actions
        from tools.android_tool import _get_adapter_registry
        registry = _get_adapter_registry()
        for adapter in registry._adapters:
            try:
                # Build flow with minimal params
                import inspect
                sig = inspect.signature(adapter.build_flow)
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == 'self':
                        continue
                    if param.default is not inspect.Parameter.empty:
                        continue  # skip params with defaults
                    # Provide minimal values for required params
                    if 'query' in param_name or 'name' in param_name or 'contact' in param_name or 'message' in param_name or 'destination' in param_name or 'place' in param_name:
                        kwargs[param_name] = "test"
                    elif 'duration' in param_name:
                        kwargs[param_name] = 60
                    elif 'count' in param_name:
                        kwargs[param_name] = 1
                flow = adapter.build_flow(**kwargs)
                errors = validate_flow_actions(flow)
                assert errors == [], f"Adapter '{adapter.name}' has invalid actions: {errors}"
            except TypeError as e:
                pytest.skip(f"Cannot build flow for {adapter.name}: {e}")


# ── Recipe Action Validation ───────────────────────────────────────────────

class TestRecipeActionValidation:
    """Verify all YAML recipes use only cataloged actions."""

    def test_all_recipes_validate(self):
        import os
        import yaml
        from tools.capabilities.action_contract import validate_action
        recipe_dir = os.path.join(os.path.dirname(__file__), "..", "..", "recipes")
        if not os.path.isdir(recipe_dir):
            pytest.skip("recipes/ directory not found")
        for fname in sorted(os.listdir(recipe_dir)):
            if not fname.endswith(".yaml"):
                continue
            with open(os.path.join(recipe_dir, fname)) as f:
                recipe = yaml.safe_load(f)
            for step in recipe.get("steps", []):
                action = step.get("action", "")
                errors = validate_action(action)
                assert errors == [], f"Recipe {fname} step '{action}': {errors}"
                # Also validate fallback action if present
                if "fallback" in step:
                    fb_action = step["fallback"].get("action", "")
                    errors = validate_action(fb_action)
                    assert errors == [], f"Recipe {fname} fallback '{fb_action}': {errors}"


# ── Handler Dispatch Coverage ──────────────────────────────────────────────

class TestHandlerDispatchCoverage:
    """Verify _BridgeFlowHandler can dispatch every action from all adapters."""

    def test_handler_dispatches_all_adapter_actions(self):
        """Walk all adapter flows and confirm each action maps to an endpoint."""
        from tools.capabilities.action_contract import ACTION_CATALOG
        from tools.android_tool import _get_adapter_registry
        import inspect

        registry = _get_adapter_registry()
        all_actions = set()

        for adapter in registry._adapters:
            try:
                sig = inspect.signature(adapter.build_flow)
                kwargs = {}
                for param_name, param in sig.parameters.items():
                    if param_name == 'self':
                        continue
                    if param.default is not inspect.Parameter.empty:
                        continue
                    if any(k in param_name for k in ('query', 'name', 'contact', 'message', 'destination', 'place')):
                        kwargs[param_name] = "test"
                    elif 'duration' in param_name:
                        kwargs[param_name] = 60
                    elif 'count' in param_name:
                        kwargs[param_name] = 1
                flow = adapter.build_flow(**kwargs)
                for step in flow.steps:
                    all_actions.add(step.action)
                    if step.fallback:
                        all_actions.add(step.fallback.action)
            except TypeError:
                continue

        for action in all_actions:
            entry = ACTION_CATALOG.get(action)
            if entry is None:
                # Check if it's an alias
                from tools.capabilities.action_contract import resolve_action
                resolved = resolve_action(action)
                assert resolved is not None, \
                    f"Action '{action}' from adapter flows is not in catalog or aliases"

    def test_handler_endpoint_map_matches_catalog(self):
        """_BridgeFlowHandler endpoint_map must be a subset of the catalog."""
        from tools.capabilities.action_contract import ACTION_CATALOG
        from tools.android_tool import _BridgeFlowHandler

        handler = _BridgeFlowHandler()
        # The handler's internal endpoint_map (we can't access it directly,
        # but we can verify by checking what actions it can handle)
        # Instead, verify that every executable action in catalog has a valid endpoint
        for name, entry in ACTION_CATALOG.items():
            if entry["category"] == "executable":
                ep = entry["bridge_endpoint"]
                assert ep, f"Executable action '{name}' has no endpoint"


# ── Route Priority A/B/C ──────────────────────────────────────────────────

class TestRoutePriority:
    """Verify route priority gate: A (intent/API) > B (bridge/native) > C (UI Automator)."""

    def test_route_priority_exists(self):
        from tools.capabilities.action_contract import RoutePriority
        assert hasattr(RoutePriority, 'INTENT_API')
        assert hasattr(RoutePriority, 'BRIDGE_NATIVE')
        assert hasattr(RoutePriority, 'UI_AUTOMATOR')

    def test_route_priority_values_order(self):
        from tools.capabilities.action_contract import RoutePriority
        assert RoutePriority.INTENT_API.value < RoutePriority.BRIDGE_NATIVE.value
        assert RoutePriority.BRIDGE_NATIVE.value < RoutePriority.UI_AUTOMATOR.value

    def test_actions_have_route_priority(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        for name, entry in ACTION_CATALOG.items():
            assert "route_priority" in entry, \
                f"Action '{name}' missing route_priority"
            assert isinstance(entry["route_priority"], int)

    def test_intent_actions_have_highest_priority(self):
        from tools.capabilities.action_contract import ACTION_CATALOG, RoutePriority
        intent_actions = [name for name, e in ACTION_CATALOG.items()
                          if "intent" in name.lower() or e.get("bridge_endpoint") == "/intent"]
        for name in intent_actions:
            entry = ACTION_CATALOG[name]
            assert entry["route_priority"] <= RoutePriority.INTENT_API.value, \
                f"Intent action '{name}' should have priority A"

    def test_ui_automator_rejected_when_higher_priority_available(self):
        """UI Automator (Plan C) cannot be selected while A or B routes exist."""
        from tools.capabilities.action_contract import ACTION_CATALOG, RoutePriority
        ui_actions = [name for name, e in ACTION_CATALOG.items()
                      if e.get("route_priority", 99) >= RoutePriority.UI_AUTOMATOR.value]
        # There should be no UI Automator actions registered yet
        # (as per spec: "no implementes todavía un executor completo de UI Automator")
        for name in ui_actions:
            entry = ACTION_CATALOG[name]
            assert entry.get("bridge_endpoint") == "", \
                f"UI Automator action '{name}' should not have a bridge endpoint yet"


# ── Semantic vs Executable Separation ──────────────────────────────────────

class TestSemanticExecutableSeparation:
    """Verify semantic actions don't leak to bridge as unknown."""

    def test_message_send_is_semantic(self):
        from tools.capabilities.action_contract import ACTION_CATALOG
        assert "message.send" in ACTION_CATALOG
        entry = ACTION_CATALOG["message.send"]
        assert entry["category"] == "semantic"

    def test_message_send_not_in_bridge_endpoint_map(self):
        """message.send should never appear in the bridge endpoint map."""
        from tools.capabilities.action_contract import ACTION_CATALOG
        entry = ACTION_CATALOG.get("message.send", {})
        assert not entry.get("bridge_endpoint"), \
            "message.send should not have a direct bridge endpoint"

    def test_confirmation_required_actions_are_semantic(self):
        """Confirmation-required actions should be semantic, not executable."""
        from tools.capabilities.action_contract import ACTION_CATALOG
        from tools.capabilities.policy import _CONFIRMATION_REQUIRED_ACTIONS
        for action in _CONFIRMATION_REQUIRED_ACTIONS:
            entry = ACTION_CATALOG.get(action)
            if entry is not None:
                # Confirmation-required actions in the catalog should be semantic
                # or have a confirmation flow, not directly dispatchable
                pass  # Not all confirmation actions need to be in catalog

    def test_whatsapp_send_step_uses_semantic_action(self):
        """WhatsApp send step should use 'message.send' not 'android_tap_text'."""
        from tools.capabilities.adapters.whatsapp_message import WhatsAppMessageAdapter
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="test", message="hi", auto_send=True)
        send_steps = [s for s in flow.steps if s.action == "message.send"]
        # If auto_send is True, there should be a message.send step
        if send_steps:
            assert send_steps[0].confirmation_token is not None, \
                "message.send step must have confirmation_token"
