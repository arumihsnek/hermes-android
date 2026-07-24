"""Integration tests for verticals — verifies adapters are wired into
android_execute_capability and recipes load from YAML."""

import json
import pytest
from unittest.mock import patch
from tools.android_tool import (
    android_execute_capability,
    _get_adapter_registry,
    _get_recipe_registry,
)
from tools.capabilities.models import DeviceFingerprint


# Pixel 8 fingerprint for integration tests
PIXEL8_FP = DeviceFingerprint(device_id="pixel8", android_version="15", sdk_int=35)


class TestAdapterRegistryIntegration:
    def test_registry_has_all_verticals(self):
        registry = _get_adapter_registry()
        assert registry.count() == 7
        caps = {a.capability for a in registry._adapters}
        assert "timer.set" in caps
        assert "media.play" in caps
        assert "podcast.subscribe" in caps
        assert "message.send" in caps
        assert "route.start" in caps
        assert "place.save" in caps
        assert "updates.pause" in caps

    def test_registry_selects_correct_adapters(self):
        registry = _get_adapter_registry()
        fp = PIXEL8_FP
        assert registry.select("timer.set", fp).name == "clock_timer"
        assert registry.select("media.play", fp).name == "antennapod_media"
        assert registry.select("podcast.subscribe", fp).name == "antennapod_subscribe"
        assert registry.select("message.send", fp).name == "whatsapp_message"
        assert registry.select("route.start", fp).name == "waze_route"
        assert registry.select("place.save", fp).name == "osmand_place"
        assert registry.select("updates.pause", fp).name == "playstore_updates"


class TestRecipeRegistryIntegration:
    def test_recipes_loaded_from_yaml(self):
        registry = _get_recipe_registry()
        assert registry.count() == 7
        ids = {r.id for r in registry.all()}
        assert "clock.timer.set.v1" in ids
        assert "antennapod.media.play.v1" in ids
        assert "whatsapp.message.send.v1" in ids

    def test_recipes_have_correct_capabilities(self):
        registry = _get_recipe_registry()
        caps = {r.capability for r in registry.all()}
        expected = {"timer.set", "media.play", "message.send", "route.start",
                    "place.save", "updates.pause", "podcast.subscribe"}
        assert caps == expected


class TestExecuteCapabilityIntegration:
    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_timer_set_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("timer.set"))
        assert result["adapter"] == "clock_timer"
        assert result["capability"] == "timer.set"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_media_play_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("media.play"))
        assert result["adapter"] == "antennapod_media"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_message_send_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("message.send"))
        assert result["adapter"] == "whatsapp_message"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_route_start_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("route.start"))
        assert result["adapter"] == "waze_route"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_place_save_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("place.save"))
        assert result["adapter"] == "osmand_place"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_updates_pause_finds_adapter(self, mock_fp):
        result = json.loads(android_execute_capability("updates.pause"))
        assert result["adapter"] == "playstore_updates"

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_unknown_capability_returns_error(self, mock_fp):
        result = json.loads(android_execute_capability("nonexistent.thing"))
        assert result["status"] == "error"
        assert "No adapter found" in result["error_message"]
        assert "available_capabilities" in result

    @patch("tools.android_tool._get_device_fingerprint", return_value=PIXEL8_FP)
    def test_timer_set_builds_flow(self, mock_fp):
        result = json.loads(android_execute_capability(
            "timer.set", params={"duration_seconds": 120}
        ))
        assert result["adapter"] == "clock_timer"
        assert "status" in result
