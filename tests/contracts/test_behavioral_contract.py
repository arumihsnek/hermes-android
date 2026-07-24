"""Behavioral contract tests — verify tool function parity between tools/ and plugin/."""

import importlib
import importlib.util
import json
import os
import sys
import types
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES_PATH = os.path.join(REPO_ROOT, "tests", "contracts", "fixtures", "contract_fixtures.json")

with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)


# ── Plugin loader ────────────────────────────────────────────────────────────

_PLUGIN_LOADED = False
_PLUGIN_MOD = None


def _load_plugin():
    """Load hermes-android-plugin as a synthetic Python package (once)."""
    global _PLUGIN_LOADED, _PLUGIN_MOD
    if _PLUGIN_LOADED and _PLUGIN_MOD is not None:
        return _PLUGIN_MOD

    plugin_dir = os.path.join(REPO_ROOT, "hermes-android-plugin")
    pkg_name = "hermes_android_plugin_contract"

    # Create synthetic package
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [plugin_dir]
    pkg.__package__ = pkg_name
    sys.modules[pkg_name] = pkg

    # Load android_relay first (android_tool imports it)
    relay_path = os.path.join(plugin_dir, "android_relay.py")
    relay_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.android_relay", relay_path,
        submodule_search_locations=[]
    )
    assert relay_spec is not None and relay_spec.loader is not None
    relay_mod = importlib.util.module_from_spec(relay_spec)
    relay_mod.__package__ = pkg_name
    sys.modules[f"{pkg_name}.android_relay"] = relay_mod
    relay_spec.loader.exec_module(relay_mod)

    # Load android_tool
    tool_path = os.path.join(plugin_dir, "android_tool.py")
    tool_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.android_tool", tool_path,
        submodule_search_locations=[]
    )
    assert tool_spec is not None and tool_spec.loader is not None
    tool_mod = importlib.util.module_from_spec(tool_spec)
    tool_mod.__package__ = pkg_name
    sys.modules[f"{pkg_name}.android_tool"] = tool_mod
    tool_spec.loader.exec_module(tool_mod)

    _PLUGIN_LOADED = True
    _PLUGIN_MOD = tool_mod
    return tool_mod


# ── Import tools/ module ─────────────────────────────────────────────────────

from tools import android_tool as tools_module


# ── Tool parity tests ────────────────────────────────────────────────────────

class TestToolParity:
    """Verify tool functions produce identical result shapes in both copies."""

    @pytest.mark.parametrize(
        "fixture",
        FIXTURES["tool_parity_fixtures"],
        ids=[f["name"] for f in FIXTURES["tool_parity_fixtures"]],
    )
    def test_tool_parity(self, fixture):
        func_name = fixture["function"]
        args = fixture.get("args", {})
        # _get/_post return dicts (already extracted by _extract_response)
        mock_data = fixture["mock_response"].get("json", {})
        expected_keys = fixture["expected_keys"]
        expected_values = fixture.get("expected_values", {})
        plugin_mod = _load_plugin()

        # Test tools/ copy
        with patch("tools.android_tool._post", return_value=mock_data), \
             patch("tools.android_tool._get", return_value=mock_data):
            tools_func = getattr(tools_module, func_name)
            tools_result = json.loads(tools_func(**args))

        # Verify expected keys present
        for key in expected_keys:
            assert key in tools_result, (
                f"tools/: missing key '{key}' in {func_name} result: {tools_result}"
            )

        # Verify expected values
        for key, val in expected_values.items():
            assert tools_result.get(key) == val, (
                f"tools/: {func_name}.{key} = {tools_result.get(key)}, expected {val}"
            )

        # Test plugin/ copy
        with patch(f"{plugin_mod.__name__}._post", return_value=mock_data), \
             patch(f"{plugin_mod.__name__}._get", return_value=mock_data):
            plugin_func = getattr(plugin_mod, func_name)
            plugin_result = json.loads(plugin_func(**args))

        # Verify same keys present in plugin
        for key in expected_keys:
            assert key in plugin_result, (
                f"plugin/: missing key '{key}' in {func_name} result: {plugin_result}"
            )

        # Compare deterministic values
        for key, val in expected_values.items():
            assert plugin_result.get(key) == val, (
                f"plugin/: {func_name}.{key} = {plugin_result.get(key)}, expected {val}"
            )

        # Compare key sets between copies (structural parity)
        tools_keys = set(tools_result.keys())
        plugin_keys = set(plugin_result.keys())
        assert tools_keys == plugin_keys, (
            f"DRIFT: {func_name} result keys differ.\n"
            f"  tools/ only: {tools_keys - plugin_keys}\n"
            f"  plugin/ only: {plugin_keys - tools_keys}"
        )


class TestErrorParity:
    """Verify error handling produces same shape in both copies."""

    @pytest.mark.parametrize(
        "fixture",
        FIXTURES["error_fixtures"],
        ids=[f["name"] for f in FIXTURES["error_fixtures"]],
    )
    def test_error_shape_parity(self, fixture):
        func_name = fixture["function"]
        args = fixture.get("args", {})
        plugin_mod = _load_plugin()

        # Both copies: _get/_post raise HTTPError for errors
        from requests.exceptions import HTTPError
        error_body = fixture.get("mock_response", {}).get("json", {"error": "mocked"})
        error_msg = json.dumps(error_body)

        def _raise_error(*a, **kw):
            raise HTTPError(error_msg)

        # Test tools/ copy
        with patch("tools.android_tool._post", side_effect=_raise_error), \
             patch("tools.android_tool._get", side_effect=_raise_error):
            tools_result = json.loads(getattr(tools_module, func_name)(**args))

        # Both copies wrap errors — check that a result dict is produced
        assert isinstance(tools_result, dict), f"tools/: {func_name} did not return dict"

        # Test plugin/ copy
        with patch(f"{plugin_mod.__name__}._post", side_effect=_raise_error), \
             patch(f"{plugin_mod.__name__}._get", side_effect=_raise_error):
            plugin_result = json.loads(getattr(plugin_mod, func_name)(**args))

        assert isinstance(plugin_result, dict), f"plugin/: {func_name} did not return dict"

        # Compare structural keys (both should handle errors similarly)
        assert set(tools_result.keys()) == set(plugin_result.keys()), (
            f"DRIFT: {func_name} error keys differ: tools/{set(tools_result.keys())} vs plugin/{set(plugin_result.keys())}"
        )


class TestCapabilityFlow:
    """Verify CapabilityService produces correct result shapes (tools-only)."""

    def test_flow_simple_success(self):
        """Simple flow with confirmed verifier returns success with trace."""
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.models import VerificationResult, VerificationOutcome

        from tools.capabilities.models import EvidenceReference

        class FakeHandler:
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                return VerificationResult(
                    outcome=VerificationOutcome.CONFIRMED,
                    verifier_type="screen_hash",
                    evidence_ref=EvidenceReference(
                        evidence_id="ev_test_001",
                        observer_type="hash",
                        timestamp=1784853566.535857,
                        safe_summary="screen hash matched",
                    ),
                )

        service = CapabilityService(FakeHandler())
        steps = [{"action": "android_tap", "params": {"x": 100, "y": 200}, "verifier": "screen_changed"}]
        result = json.loads(service.execute_flow(steps, capability="tap"))

        assert result["status"] == "success"
        assert "trace_id" in result
        assert len(result["evidence_refs"]) > 0

    def test_flow_verification_failed(self):
        """Flow with inconclusive verifier returns failure."""
        from tools.capabilities.service import CapabilityService
        from tools.capabilities.models import VerificationResult, VerificationOutcome

        class FakeHandler:
            def execute(self, action, params):
                return {"success": True}
            def verify(self, verifier, params):
                return VerificationResult(
                    outcome=VerificationOutcome.INCONCLUSIVE,
                    verifier_type="screen_hash",
                )

        service = CapabilityService(FakeHandler())
        steps = [{"action": "android_tap", "params": {"x": 100, "y": 200}, "verifier": "screen_changed"}]
        result = json.loads(service.execute_flow(steps, capability="tap"))

        assert result["status"] == "failure"
        assert "failure_class" in result


class TestPolicyClassification:
    """Verify PolicyGate classifies actions correctly."""

    def test_reversible_action(self):
        from tools.capabilities.policy import classify_action
        from tools.capabilities.models import ActionClassification
        result = classify_action("android_tap")
        assert result == ActionClassification.ORDINARY_REVERSIBLE

    def test_confirmation_required_action(self):
        from tools.capabilities.policy import classify_action
        from tools.capabilities.models import ActionClassification
        result = classify_action("message.send")
        assert result == ActionClassification.CONFIRMATION_REQUIRED

    def test_prohibited_action(self):
        from tools.capabilities.policy import classify_action
        from tools.capabilities.models import ActionClassification
        result = classify_action("factory_reset")
        assert result == ActionClassification.PROHIBITED


class TestToolFunctionParity:
    """Verify both copies expose identical tool function sets."""

    def test_function_names_match(self):
        """Both copies must define the same android_* functions."""
        tools_funcs = {n for n in dir(tools_module) if n.startswith("android_") and callable(getattr(tools_module, n))}
        plugin_mod = _load_plugin()
        plugin_funcs = {n for n in dir(plugin_mod) if n.startswith("android_") and callable(getattr(plugin_mod, n))}

        assert tools_funcs == plugin_funcs, (
            f"DRIFT: function sets differ.\n"
            f"  tools/ only: {tools_funcs - plugin_funcs}\n"
            f"  plugin/ only: {plugin_funcs - tools_funcs}"
        )

    def test_function_signatures_match(self):
        """Key functions must have identical signatures."""
        import inspect
        plugin_mod = _load_plugin()

        key_functions = [
            "android_ping", "android_read_screen", "android_tap", "android_tap_text",
            "android_type", "android_swipe", "android_open_app", "android_screenshot",
            "android_send_intent", "android_broadcast",
        ]

        for func_name in key_functions:
            tools_sig = inspect.signature(getattr(tools_module, func_name))
            plugin_sig = inspect.signature(getattr(plugin_mod, func_name))
            assert str(tools_sig) == str(plugin_sig), (
                f"DRIFT: {func_name} signature differs: tools/{tools_sig} vs plugin/{plugin_sig}"
            )
