"""Relay contract tests — verify route maps and auth constants are synchronized."""

import ast
import json
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES_PATH = os.path.join(REPO_ROOT, "tests", "contracts", "fixtures", "contract_fixtures.json")

with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)

SHARED_ROUTES = FIXTURES["shared_routes"]
TOOLS_ONLY_ROUTES = FIXTURES["tools_only_routes"]


# ── Route extraction ─────────────────────────────────────────────────────────

def _extract_tools_routes() -> dict[str, str]:
    """Extract ROUTES dict from tools/android_relay.py via AST."""
    path = os.path.join(REPO_ROOT, "tools", "android_relay.py")
    with open(path) as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ROUTES":
                    return ast.literal_eval(node.value)

    raise AssertionError("ROUTES dict not found in tools/android_relay.py")


def _extract_plugin_routes() -> dict[str, str]:
    """Extract routes from hermes-android-plugin/android_relay.py via AST.

    Plugin registers routes in for-loops over tuple literals:
        for path in ("/ping", "/screen", ...):
            app.router.add_get(path, ...)
        for path in ("/tap", ...):
            app.router.add_post(path, ...)

    Returns dict mapping route path -> method ("GET", "POST", or "BOTH").
    """
    path = os.path.join(REPO_ROOT, "hermes-android-plugin", "android_relay.py")
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source)

    routes: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue

        # Check: for <target> in (<tuple of constants>):
        if not isinstance(node.target, ast.Name):
            continue
        if not isinstance(node.iter, ast.Tuple):
            continue

        # Determine method from the loop body's add_get/add_post call
        method = None
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    if func.attr == "add_get":
                        method = "GET"
                    elif func.attr == "add_post":
                        method = "POST"
                if method:
                    break

        if not method:
            continue

        # Extract route paths from the tuple
        for elt in node.iter.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                route = elt.value
                if route in routes:
                    # Already seen with different method -> BOTH
                    if routes[route] != method:
                        routes[route] = "BOTH"
                else:
                    routes[route] = method

    return routes


# ── Route parity tests ──────────────────────────────────────────────────────

class TestRouteParity:
    """Verify relay route maps match the explicit shared set."""

    def test_tools_routes_match_shared_set(self):
        """tools/ relay must contain all shared routes with correct methods."""
        tools_routes = _extract_tools_routes()

        for route, expected_method in SHARED_ROUTES.items():
            assert route in tools_routes, (
                f"Shared route {route} missing from tools/android_relay.py"
            )
            actual = tools_routes[route]
            # BOTH in fixture means the route accepts GET and POST
            if expected_method == "BOTH":
                assert actual in ("GET", "POST", "BOTH"), (
                    f"Route {route}: expected GET/POST/BOTH, got {actual}"
                )
            else:
                assert actual == expected_method, (
                    f"Route {route}: expected {expected_method}, got {actual}"
                )

    def test_plugin_routes_match_shared_set(self):
        """Plugin relay must contain all shared routes with correct methods."""
        plugin_routes = _extract_plugin_routes()

        for route, expected_method in SHARED_ROUTES.items():
            assert route in plugin_routes, (
                f"Shared route {route} missing from hermes-android-plugin/android_relay.py"
            )
            actual = plugin_routes[route]
            if expected_method == "BOTH":
                assert actual in ("GET", "POST", "BOTH"), (
                    f"Route {route}: expected GET/POST/BOTH, got {actual}"
                )
            else:
                assert actual == expected_method, (
                    f"Route {route}: expected {expected_method}, got {actual}"
                )

    def test_plugin_has_no_extra_routes(self):
        """Plugin must not have routes outside the shared set."""
        plugin_routes = _extract_plugin_routes()
        shared_set = set(SHARED_ROUTES.keys())
        extra = set(plugin_routes.keys()) - shared_set
        assert not extra, (
            f"Plugin has routes not in shared set: {extra}"
        )

    def test_tools_has_expected_extra_routes(self):
        """tools/ should have /shell and /unlock as documented extras."""
        tools_routes = _extract_tools_routes()
        for route, method in TOOLS_ONLY_ROUTES.items():
            assert route in tools_routes, (
                f"Expected tools-only route {route} missing from tools/android_relay.py"
            )
            assert tools_routes[route] == method, (
                f"Route {route}: expected {method}, got {tools_routes[route]}"
            )

    def test_route_count_consistency(self):
        """tools/ must have shared + tools_only routes, no more."""
        tools_routes = _extract_tools_routes()
        expected_count = len(SHARED_ROUTES) + len(TOOLS_ONLY_ROUTES)
        assert len(tools_routes) == expected_count, (
            f"tools/ has {len(tools_routes)} routes, expected {expected_count} "
            f"({len(SHARED_ROUTES)} shared + {len(TOOLS_ONLY_ROUTES)} tools-only)"
        )


# ── Auth constants tests ────────────────────────────────────────────────────

class TestAuthConstants:
    """Verify rate-limit constants are identical in both relay copies."""

    def _extract_rate_limit_constants(self, filepath: str) -> dict:
        """Extract rate-limit constants from a relay file."""
        with open(filepath) as f:
            source = f.read()

        result = {}
        # Look for numeric constants in the auth/rate-limit context
        # patterns: MAX_ATTEMPTS = 5, WINDOW = 60, BLOCK_DURATION = 300
        for line in source.split("\n"):
            stripped = line.strip()
            for varname in ("max_attempts", "MAX_ATTEMPTS", "window", "WINDOW",
                            "block_duration", "BLOCK_DURATION", "BLOCK_SECONDS"):
                if varname in stripped and "=" in stripped:
                    try:
                        val = int(stripped.split("=")[-1].strip().rstrip(","))
                        result[varname] = val
                    except (ValueError, IndexError):
                        pass
        return result

    def test_rate_limit_constants_match(self):
        """Both relay copies must define the same rate-limit values."""
        tools_path = os.path.join(REPO_ROOT, "tools", "android_relay.py")
        plugin_path = os.path.join(REPO_ROOT, "hermes-android-plugin", "android_relay.py")

        tools_consts = self._extract_rate_limit_constants(tools_path)
        plugin_consts = self._extract_rate_limit_constants(plugin_path)

        # Normalize keys for comparison
        # Expected: 5 attempts, 60s window, 300s block
        for key in tools_consts:
            if key in plugin_consts:
                assert tools_consts[key] == plugin_consts[key], (
                    f"Auth constant {key} differs: tools/{tools_consts[key]} vs plugin/{plugin_consts[key]}"
                )
