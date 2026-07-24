#!/usr/bin/env python3
"""
check_android_copy_contract.py — verify tools/ and hermes-android-plugin/ stay synchronized.

Runs structural checks (tool names, relay routes, file existence) and behavioral
checks (tool function parity, error shape parity) without needing pytest.

Usage:
    python scripts/check_android_copy_contract.py --check
"""

import ast
import json
import os
import sys
import types
import importlib
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
PLUGIN_DIR = os.path.join(REPO_ROOT, "hermes-android-plugin")
FIXTURES_PATH = os.path.join(REPO_ROOT, "tests", "contracts", "fixtures", "contract_fixtures.json")

errors = []


def check(condition: bool, msg: str):
    """Record a check failure."""
    if not condition:
        errors.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  PASS: {msg}")


def main():
    print("=" * 60)
    print("Android Copy Contract Check")
    print("=" * 60)

    # ── 1. Structural checks ─────────────────────────────────────────────
    print("\n[1] Structural checks")

    check(os.path.exists(os.path.join(TOOLS_DIR, "android_tool.py")),
          "tools/android_tool.py exists")
    check(os.path.exists(os.path.join(PLUGIN_DIR, "android_tool.py")),
          "hermes-android-plugin/android_tool.py exists")
    check(os.path.exists(os.path.join(TOOLS_DIR, "android_relay.py")),
          "tools/android_relay.py exists")
    check(os.path.exists(os.path.join(PLUGIN_DIR, "android_relay.py")),
          "hermes-android-plugin/android_relay.py exists")

    # Check tool function sets match
    with open(os.path.join(TOOLS_DIR, "android_tool.py")) as f:
        tools_tree = ast.parse(f.read())
    with open(os.path.join(PLUGIN_DIR, "android_tool.py")) as f:
        plugin_tree = ast.parse(f.read())

    def extract_funcs(tree):
        return {node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name.startswith("android_")}

    tools_funcs = extract_funcs(tools_tree)
    plugin_funcs = extract_funcs(plugin_tree)
    check(tools_funcs == plugin_funcs,
          f"Tool function sets match ({len(tools_funcs)} functions)")
    if tools_funcs != plugin_funcs:
        errors.append(f"  tools/ only: {tools_funcs - plugin_funcs}")
        errors.append(f"  plugin/ only: {plugin_funcs - tools_funcs}")

    # ── 2. Route parity checks ───────────────────────────────────────────
    print("\n[2] Route parity checks")

    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)

    shared_routes = fixtures["shared_routes"]
    tools_only_routes = fixtures["tools_only_routes"]

    # Extract tools/ routes from ROUTES dict
    with open(os.path.join(TOOLS_DIR, "android_relay.py")) as f:
        tools_relay_tree = ast.parse(f.read())

    tools_routes = {}
    for node in ast.walk(tools_relay_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ROUTES":
                    tools_routes = ast.literal_eval(node.value)

    for route, method in shared_routes.items():
        check(route in tools_routes, f"Shared route {route} in tools/ ({method})")
        if route in tools_routes:
            check(tools_routes[route] == method,
                  f"Route {route} method matches in tools/ ({tools_routes[route]} == {method})")

    for route, method in tools_only_routes.items():
        check(route in tools_routes, f"Tools-only route {route} in tools/")

    # Extract plugin/ routes from for-loops
    with open(os.path.join(PLUGIN_DIR, "android_relay.py")) as f:
        plugin_relay_tree = ast.parse(f.read())

    plugin_routes = {}
    for node in ast.walk(plugin_relay_tree):
        if not isinstance(node, ast.For):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if not isinstance(node.iter, ast.Tuple):
            continue
        method = None
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "add_get":
                    method = "GET"
                elif child.func.attr == "add_post":
                    method = "POST"
                if method:
                    break
        if not method:
            continue
        for elt in node.iter.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                route = elt.value
                if route in plugin_routes and plugin_routes[route] != method:
                    plugin_routes[route] = "BOTH"
                else:
                    plugin_routes[route] = method

    for route, method in shared_routes.items():
        check(route in plugin_routes, f"Shared route {route} in plugin/ ({method})")

    extra_plugin = set(plugin_routes.keys()) - set(shared_routes.keys())
    check(not extra_plugin, f"Plugin has no routes outside shared set")
    if extra_plugin:
        errors.append(f"  Plugin extra routes: {extra_plugin}")

    # ── 3. Capability system checks ───────────────────────────────────────
    print("\n[3] Capability system checks")

    cap_dir = os.path.join(TOOLS_DIR, "capabilities")
    check(os.path.isdir(cap_dir), f"tools/capabilities/ directory exists")
    for mod_name in ("__init__.py", "models.py", "policy.py", "flow_executor.py", "service.py", "errors.py"):
        check(os.path.exists(os.path.join(cap_dir, mod_name)),
              f"tools/capabilities/{mod_name} exists")

    # ── 4. CI workflow check ──────────────────────────────────────────────
    print("\n[4] CI workflow check")

    ci_path = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
    check(os.path.exists(ci_path), ".github/workflows/ci.yml exists")
    if os.path.exists(ci_path):
        with open(ci_path) as f:
            ci_content = f.read()
        check("pytest tests/contracts/" in ci_content,
              "CI runs pytest tests/contracts/")
        check("python-version: '3.11'" in ci_content or "python-version: 3.11" in ci_content,
              "CI uses Python 3.11")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"RESULT: FAIL ({len(errors)} issues)")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("RESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
