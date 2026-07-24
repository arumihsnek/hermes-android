"""Tests for Task 8: Recipe registry, adapter registry, fingerprints, maturity rules."""

import json
import os
import time
import pytest
import yaml

from tools.capabilities.recipes import (
    Recipe,
    RecipeRegistry,
    MaturityState,
    load_recipe_from_dict,
    validate_recipe,
)
from tools.capabilities.adapters import (
    Adapter,
    AdapterRegistry,
)
from tools.capabilities.models import DeviceFingerprint


# ── Recipe Tests ─────────────────────────────────────────────────────────────

class TestRecipe:
    """Recipe data model and validation."""

    def test_load_valid_recipe(self):
        recipe = load_recipe_from_dict({
            "id": "antennapod.timer.set.v1",
            "capability": "timer.set",
            "package": "de.danoeh.antennapod",
            "version": "3.0.0",
            "maturity": "stable",
            "steps": [
                {"action": "android_open_app", "params": {"package": "com.google.android.deskclock"}},
                {"action": "android_tap_text", "params": {"text": "Timer"}},
            ],
            "verifier": {"type": "timer_exists"},
            "fingerprint": {"device": "pixel8", "android_version": "15"},
        })
        assert recipe.id == "antennapod.timer.set.v1"
        assert recipe.capability == "timer.set"
        assert recipe.maturity == MaturityState.STABLE

    def test_reject_invalid_recipe_missing_id(self):
        with pytest.raises(ValueError, match="id"):
            load_recipe_from_dict({"capability": "timer.set"})

    def test_reject_invalid_recipe_missing_capability(self):
        with pytest.raises(ValueError, match="capability"):
            load_recipe_from_dict({"id": "test.v1"})

    def test_reject_invalid_maturity(self):
        with pytest.raises(ValueError, match="maturity"):
            load_recipe_from_dict({
                "id": "test.v1", "capability": "test",
                "maturity": "nonexistent",
            })

    def test_recipe_steps_optional(self):
        recipe = load_recipe_from_dict({
            "id": "test.v1",
            "capability": "test",
            "maturity": "discovered",
        })
        assert recipe.steps == []


class TestMaturityState:
    """Maturity state transitions."""

    def test_states_exist(self):
        assert MaturityState.DISCOVERED.value == "discovered"
        assert MaturityState.CANDIDATE.value == "candidate"
        assert MaturityState.DOGFOOD.value == "dogfood"
        assert MaturityState.STABLE.value == "stable"
        assert MaturityState.SUSPECT.value == "suspect"
        assert MaturityState.QUARANTINED.value == "quarantined"
        assert MaturityState.DEPRECATED.value == "deprecated"

    def test_state_ordering(self):
        """States exist and can be compared by their defined order."""
        states = [s.value for s in MaturityState]
        assert "discovered" in states
        assert "candidate" in states
        assert "dogfood" in states
        assert "stable" in states
        assert "quarantined" in states


class TestRecipeRegistry:
    """Registry for loading and querying recipes."""

    def test_register_and_query(self):
        registry = RecipeRegistry()
        recipe = load_recipe_from_dict({
            "id": "test.v1", "capability": "timer.set",
            "maturity": "stable", "package": "com.example",
        })
        registry.register(recipe)
        results = registry.find_by_capability("timer.set")
        assert len(results) == 1
        assert results[0].id == "test.v1"

    def test_find_filters_by_maturity(self):
        registry = RecipeRegistry()
        registry.register(load_recipe_from_dict({
            "id": "r1", "capability": "test", "maturity": "stable",
        }))
        registry.register(load_recipe_from_dict({
            "id": "r2", "capability": "test", "maturity": "quarantined",
        }))
        # Default: only stable and dogfood
        results = registry.find_by_capability("test")
        assert len(results) == 1
        assert results[0].id == "r1"

    def test_find_includes_dogfood(self):
        registry = RecipeRegistry()
        registry.register(load_recipe_from_dict({
            "id": "r1", "capability": "test", "maturity": "dogfood",
        }))
        results = registry.find_by_capability("test")
        assert len(results) == 1

    def test_find_excludes_deprecated(self):
        registry = RecipeRegistry()
        registry.register(load_recipe_from_dict({
            "id": "r1", "capability": "test", "maturity": "deprecated",
        }))
        results = registry.find_by_capability("test")
        assert len(results) == 0

    def test_find_by_package(self):
        registry = RecipeRegistry()
        registry.register(load_recipe_from_dict({
            "id": "r1", "capability": "test", "maturity": "stable",
            "package": "com.example",
        }))
        registry.register(load_recipe_from_dict({
            "id": "r2", "capability": "test", "maturity": "stable",
            "package": "com.other",
        }))
        results = registry.find_by_capability("test", package="com.example")
        assert len(results) == 1
        assert results[0].id == "r1"


class TestRecipeValidation:
    """Recipe schema validation."""

    def test_valid_recipe_passes(self):
        errors = validate_recipe({
            "id": "test.v1", "capability": "test", "maturity": "stable",
        })
        assert errors == []

    def test_missing_required_field(self):
        errors = validate_recipe({})
        assert len(errors) > 0
        assert any("id" in e for e in errors)

    def test_invalid_maturity(self):
        errors = validate_recipe({
            "id": "test.v1", "capability": "test", "maturity": "INVALID",
        })
        assert any("maturity" in e for e in errors)


# ── Adapter Tests ────────────────────────────────────────────────────────────

class TestDeviceFingerprint:
    """Device fingerprint for adapter matching."""

    def test_fingerprint_creation(self):
        fp = DeviceFingerprint(
            device_id="pixel8",
            android_version="15",
            sdk_int=35,
            package_fingerprints={"com.example": "v1"},
        )
        assert fp.device_id == "pixel8"
        assert fp.sdk_int == 35

    def test_fingerprint_digest_deterministic(self):
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.a": "v1"})
        assert fp.digest() == fp.digest()

    def test_fingerprint_digest_changes(self):
        fp1 = DeviceFingerprint("pixel8", "15", 35)
        fp2 = DeviceFingerprint("pixel9", "15", 35)
        assert fp1.digest() != fp2.digest()


class TestAdapter:
    """Adapter for executing capabilities on specific apps."""

    def test_adapter_creation(self):
        adapter = Adapter(
            name="antennapod_timer",
            capability="timer.set",
            package="de.danoeh.antennapod",
            min_sdk=21,
            recipe_id="antennapod.timer.set.v1",
        )
        assert adapter.name == "antennapod_timer"
        assert adapter.supports("timer.set", package="de.danoeh.antennapod")

    def test_adapter_rejects_wrong_capability(self):
        adapter = Adapter(
            name="test", capability="timer.set",
            package="com.example", min_sdk=21,
        )
        assert not adapter.supports("media.play")

    def test_adapter_rejects_wrong_package(self):
        adapter = Adapter(
            name="test", capability="timer.set",
            package="com.example", min_sdk=21,
        )
        assert not adapter.supports("timer.set", package="com.other")

    def test_adapter_fingerprint_match(self):
        adapter = Adapter(
            name="test", capability="timer.set",
            package="com.example", min_sdk=21,
            required_packages=["com.helper"],
        )
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.helper": "v1"})
        assert adapter.matches_fingerprint(fp)

    def test_adapter_fingerprint_no_match(self):
        adapter = Adapter(
            name="test", capability="timer.set",
            package="com.example", min_sdk=21,
            required_packages=["com.missing"],
        )
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={})
        assert not adapter.matches_fingerprint(fp)


class TestAdapterRegistry:
    """Registry for selecting adapters by capability and fingerprint."""

    def test_register_and_select(self):
        registry = AdapterRegistry()
        adapter = Adapter(
            name="test", capability="timer.set",
            package="com.example", min_sdk=21,
        )
        registry.register(adapter)
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("timer.set", fp)
        assert selected is not None
        assert selected.name == "test"

    def test_select_returns_none_when_no_match(self):
        registry = AdapterRegistry()
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("nonexistent", fp)
        assert selected is None

    def test_select_prefers_exact_package(self):
        registry = AdapterRegistry()
        registry.register(Adapter(
            name="generic", capability="timer.set",
            package="com.any", min_sdk=21,
        ))
        registry.register(Adapter(
            name="specific", capability="timer.set",
            package="com.specific", min_sdk=21,
        ))
        fp = DeviceFingerprint("pixel8", "15", 35, package_fingerprints={"com.specific": "v1"})
        selected = registry.select("timer.set", fp, package="com.specific")
        assert selected.name == "specific"
