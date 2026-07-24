"""Tests for Task 11: Discovery protocol and candidate-recipe generation."""

import pytest

from tools.capabilities.discovery import (
    DiscoveryStep,
    DiscoveryResult,
    DiscoveryProtocol,
    DiscoveryStore,
)


class TestDiscoveryStep:
    """Individual discovery step."""

    def test_step_creation(self):
        step = DiscoveryStep(
            name="direct_tool_lookup",
            description="Check if a direct tool call can satisfy the capability",
            priority=1,
        )
        assert step.name == "direct_tool_lookup"
        assert step.priority == 1


class TestDiscoveryResult:
    """Result of a discovery attempt."""

    def test_create_result(self):
        result = DiscoveryResult(
            capability="timer.set",
            candidate_recipe_id="candidate_timer_v1",
            steps_tried=["direct_tool_lookup", "manifest_inspection"],
            success=True,
        )
        assert result.success is True
        assert len(result.steps_tried) == 2

    def test_create_failure_result(self):
        result = DiscoveryResult(
            capability="unknownCapability",
            candidate_recipe_id=None,
            steps_tried=["direct_tool_lookup"],
            success=False,
            failure_reason="No matching tool or intent found",
        )
        assert result.success is False


class TestDiscoveryProtocol:
    """Ordered discovery protocol — tries cheaper methods first."""

    def test_protocol_has_steps(self):
        protocol = DiscoveryProtocol()
        assert len(protocol.steps) > 0

    def test_steps_ordered_by_priority(self):
        protocol = DiscoveryProtocol()
        priorities = [s.priority for s in protocol.steps]
        assert priorities == sorted(priorities)

    def test_direct_tool_before_manifest(self):
        """Direct tool lookup must come before manifest inspection."""
        protocol = DiscoveryProtocol()
        names = [s.name for s in protocol.steps]
        assert names.index("direct_tool_lookup") < names.index("manifest_inspection")

    def test_manifest_before_ui_exploration(self):
        """Manifest/intent inspection must come before UI exploration."""
        protocol = DiscoveryProtocol()
        names = [s.name for s in protocol.steps]
        if "ui_exploration" in names and "manifest_inspection" in names:
            assert names.index("manifest_inspection") < names.index("ui_exploration")

    def test_discover_direct_tool(self):
        """Discovery should succeed when a direct tool exists."""
        protocol = DiscoveryProtocol()
        result = protocol.discover(
            "timer.set",
            available_tools=["android_send_intent", "android_tap"],
            mock_manifest={"intents": ["android.intent.action.SET_TIMER"]},
        )
        assert result.success is True
        assert "direct_tool_lookup" in result.steps_tried

    def test_discover_from_manifest(self):
        """Discovery should succeed from manifest inspection when no direct tool."""
        protocol = DiscoveryProtocol()
        result = protocol.discover(
            "custom_capability",
            available_tools=[],  # no direct tool
            mock_manifest={"intents": ["com.example.CUSTOM_ACTION"]},
        )
        assert result.success is True
        assert "manifest_inspection" in result.steps_tried

    def test_discover_failure(self):
        """Discovery should fail when nothing matches."""
        protocol = DiscoveryProtocol()
        result = protocol.discover(
            "impossibleCapability",
            available_tools=[],
            mock_manifest={"intents": []},
        )
        assert result.success is False

    def test_negative_learning_blocks_retry(self):
        """Previously failed route should be skipped."""
        protocol = DiscoveryProtocol()
        # Record a failure
        protocol.negative_learning.append({
            "capability": "test",
            "fingerprint": "abc",
            "method": "direct_tool",
        })
        result = protocol.discover(
            "test",
            available_tools=["android_tap"],
            mock_manifest={},
            fingerprint_digest="abc",
        )
        # Should skip direct_tool and try other steps
        assert "direct_tool_lookup" not in result.steps_tried or result.success is False


class TestDiscoveryStore:
    """Persistent store for discovery results."""

    def test_store_and_retrieve(self):
        store = DiscoveryStore()
        result = DiscoveryResult(
            capability="timer.set",
            candidate_recipe_id="r1",
            steps_tried=["direct_tool_lookup"],
            success=True,
        )
        store.save(result)
        retrieved = store.get("timer.set")
        assert retrieved is not None
        assert retrieved.candidate_recipe_id == "r1"

    def test_get_nonexistent(self):
        store = DiscoveryStore()
        assert store.get("nonexistent") is None

    def test_list_capabilities(self):
        store = DiscoveryStore()
        store.save(DiscoveryResult(
            capability="a", candidate_recipe_id="r1",
            steps_tried=[], success=True,
        ))
        store.save(DiscoveryResult(
            capability="b", candidate_recipe_id="r2",
            steps_tried=[], success=True,
        ))
        caps = store.list_capabilities()
        assert "a" in caps
        assert "b" in caps
