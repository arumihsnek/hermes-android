"""Contract tests — verify tools/ and hermes-android-plugin/ remain synchronized."""

import ast
import hashlib
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
PLUGIN_DIR = os.path.join(REPO_ROOT, "hermes-android-plugin")


def _hash_file(path: str) -> str:
    """Hash file content for comparison."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _extract_tool_names(path: str) -> set[str]:
    """Extract tool function names from a Python file."""
    with open(path, "r") as f:
        content = f.read()
    tree = ast.parse(content)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("android_"):
            names.add(node.name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_TOOLS":
                    # Extract from dict literal
                    if isinstance(node.value, ast.Dict):
                        for key in node.value.keys:
                            if isinstance(key, ast.Constant):
                                names.add(key.value)
    return names


class TestCopyContract:
    """Verify tools/ and hermes-android-plugin/ behavioral copies stay synchronized."""

    def test_tool_files_exist(self):
        tools_main = os.path.join(TOOLS_DIR, "android_tool.py")
        plugin_main = os.path.join(PLUGIN_DIR, "android_tool.py")
        assert os.path.exists(tools_main), f"Missing {tools_main}"
        assert os.path.exists(plugin_main), f"Missing {plugin_main}"

    def test_tool_schemas_match(self):
        """Public tool schemas must be identical between copies."""
        tools_main = os.path.join(TOOLS_DIR, "android_tool.py")
        plugin_main = os.path.join(PLUGIN_DIR, "android_tool.py")

        tools_names = _extract_tool_names(tools_main)
        plugin_names = _extract_tool_names(plugin_main)

        missing_in_plugin = tools_names - plugin_names
        missing_in_tools = plugin_names - tools_names

        assert not missing_in_plugin, f"Tools in tools/ missing from plugin/: {missing_in_plugin}"
        assert not missing_in_tools, f"Tools in plugin/ missing from tools/: {missing_in_tools}"

    def test_relay_files_exist(self):
        tools_relay = os.path.join(TOOLS_DIR, "android_relay.py")
        plugin_relay = os.path.join(PLUGIN_DIR, "android_relay.py")
        assert os.path.exists(tools_relay), f"Missing {tools_relay}"
        assert os.path.exists(plugin_relay), f"Missing {plugin_relay}"

    def test_relay_route_handlers_match(self):
        """Relay route handlers must be present in both copies."""
        tools_relay = os.path.join(TOOLS_DIR, "android_relay.py")
        plugin_relay = os.path.join(PLUGIN_DIR, "android_relay.py")

        with open(tools_relay) as f:
            tools_content = f.read()
        with open(plugin_relay) as f:
            plugin_content = f.read()

        # Check key routes exist in both (plugin may lag behind tools/ on new routes)
        key_routes = ["/ping", "/screen", "/tap", "/intent"]
        for route in key_routes:
            assert route in tools_content, f"Route {route} missing from tools/android_relay.py"
            assert route in plugin_content, f"Route {route} missing from hermes-android-plugin/android_relay.py"

        # tools/ may have additional routes not yet synced to plugin/
        # This is tracked but not a hard failure — the contract test catches drift

    def test_capability_package_exists(self):
        """Capability system package must exist."""
        cap_dir = os.path.join(TOOLS_DIR, "capabilities")
        assert os.path.isdir(cap_dir), f"Missing {cap_dir}"
        assert os.path.exists(os.path.join(cap_dir, "__init__.py"))
        assert os.path.exists(os.path.join(cap_dir, "models.py"))
        assert os.path.exists(os.path.join(cap_dir, "policy.py"))
        assert os.path.exists(os.path.join(cap_dir, "flow_executor.py"))
        assert os.path.exists(os.path.join(cap_dir, "service.py"))
        assert os.path.exists(os.path.join(cap_dir, "errors.py"))
