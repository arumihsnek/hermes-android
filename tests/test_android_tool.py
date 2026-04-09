import json
import os
import responses
import pytest

# Import tool functions directly (not via registry)
from tools.android_tool import (
    android_ping,
    android_read_screen,
    android_tap,
    android_tap_text,
    android_type,
    android_swipe,
    android_open_app,
    android_press_key,
    android_screenshot,
    android_scroll,
    android_wait,
    android_get_apps,
    android_current_app,
    android_setup,
    android_clipboard_read,
    android_clipboard_write,
    android_notifications,
    android_long_press,
    android_drag,
    android_describe_node,
    android_screen_hash,
    android_macro,
    android_location,
    android_send_sms,
    android_call,
    _SCHEMAS,
    _HANDLERS,
)


class TestSchemas:
    def test_all_25_tools_have_schemas(self):
        assert len(_SCHEMAS) == 25

    def test_all_25_tools_have_handlers(self):
        assert len(_HANDLERS) == 25

    def test_schema_names_match_handler_names(self):
        assert set(_SCHEMAS.keys()) == set(_HANDLERS.keys())

    def test_all_schemas_have_required_fields(self):
        for name, schema in _SCHEMAS.items():
            assert "name" in schema, f"{name} missing 'name'"
            assert "description" in schema, f"{name} missing 'description'"
            assert "parameters" in schema, f"{name} missing 'parameters'"


class TestPing:
    @responses.activate
    def test_ping_success(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/ping",
            json={"status": "ok", "accessibilityService": True, "version": "0.1.0"},
        )
        result = json.loads(android_ping())
        assert result["status"] == "ok"
        assert result["bridge"]["accessibilityService"] is True

    @responses.activate
    def test_ping_failure(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/ping",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_ping())
        assert result["status"] == "error"


class TestReadScreen:
    @responses.activate
    def test_read_screen(self, bridge_url):
        tree = [{"nodeId": "n1", "text": "Hello", "clickable": True}]
        responses.add(
            responses.GET,
            f"{bridge_url}/screen",
            json={"tree": tree, "count": 1},
        )
        result = json.loads(android_read_screen())
        assert result["tree"][0]["text"] == "Hello"

    @responses.activate
    def test_read_screen_with_bounds(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/screen",
            json={"tree": [], "count": 0},
        )
        result = json.loads(android_read_screen(include_bounds=True))
        assert "tree" in result


class TestTap:
    @responses.activate
    def test_tap_by_coordinates(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/tap",
            json={"success": True, "message": "Tapped (100, 200)"},
        )
        result = json.loads(android_tap(x=100, y=200))
        assert result["success"] is True

    @responses.activate
    def test_tap_by_node_id(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/tap",
            json={"success": True, "message": "Tapped node n1"},
        )
        result = json.loads(android_tap(node_id="n1"))
        assert result["success"] is True

    def test_tap_no_args(self):
        result = json.loads(android_tap())
        assert "error" in result


class TestTapText:
    @responses.activate
    def test_tap_text(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/tap_text",
            json={"success": True, "message": "Tapped 'Continue'"},
        )
        result = json.loads(android_tap_text("Continue"))
        assert result["success"] is True

    @responses.activate
    def test_tap_text_exact(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/tap_text",
            json={"success": True},
        )
        result = json.loads(android_tap_text("OK", exact=True))
        assert result["success"] is True


class TestType:
    @responses.activate
    def test_type_text(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/type",
            json={"success": True, "message": "Typed text"},
        )
        result = json.loads(android_type("hello world"))
        assert result["success"] is True

    @responses.activate
    def test_type_clear_first(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/type",
            json={"success": True},
        )
        result = json.loads(android_type("new text", clear_first=True))
        assert result["success"] is True


class TestSwipe:
    @responses.activate
    def test_swipe(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/swipe",
            json={"success": True, "message": "Swiped up (medium)"},
        )
        result = json.loads(android_swipe("up"))
        assert result["success"] is True

    @responses.activate
    def test_swipe_long(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/swipe",
            json={"success": True},
        )
        result = json.loads(android_swipe("down", distance="long"))
        assert result["success"] is True


class TestOpenApp:
    @responses.activate
    def test_open_app(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/open_app",
            json={"success": True, "message": "Opening com.ubercab"},
        )
        result = json.loads(android_open_app("com.ubercab"))
        assert result["success"] is True


class TestPressKey:
    @responses.activate
    def test_press_key(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/press_key",
            json={"success": True, "message": "Pressed back"},
        )
        result = json.loads(android_press_key("back"))
        assert result["success"] is True


class TestScreenshot:
    @responses.activate
    def test_screenshot(self, bridge_url):
        import base64

        valid_png = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        responses.add(
            responses.GET,
            f"{bridge_url}/screenshot",
            json={"image": valid_png, "width": 1080, "height": 1920},
        )
        result = android_screenshot()
        assert "Screenshot captured" in result
        assert "1080x1920" in result


class TestScroll:
    @responses.activate
    def test_scroll(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/scroll",
            json={"success": True},
        )
        result = json.loads(android_scroll("down"))
        assert result["success"] is True

    @responses.activate
    def test_scroll_with_node(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/scroll",
            json={"success": True},
        )
        result = json.loads(android_scroll("up", node_id="scroll_view_1"))
        assert result["success"] is True


class TestWait:
    @responses.activate
    def test_wait_found(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/wait",
            json={"success": True, "message": "Element found"},
        )
        result = json.loads(android_wait(text="Loading complete"))
        assert result["success"] is True

    @responses.activate
    def test_wait_timeout(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/wait",
            json={"success": False, "message": "Timeout"},
        )
        result = json.loads(android_wait(text="Never appears", timeout_ms=1000))
        assert result["success"] is False


class TestGetApps:
    @responses.activate
    def test_get_apps(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/apps",
            json={
                "apps": [{"packageName": "com.ubercab", "label": "Uber"}],
                "count": 1,
            },
        )
        result = json.loads(android_get_apps())
        assert result["count"] == 1


class TestCurrentApp:
    @responses.activate
    def test_current_app(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/current_app",
            json={"package": "com.ubercab", "className": "MainActivity"},
        )
        result = json.loads(android_current_app())
        assert result["package"] == "com.ubercab"


class TestSetup:
    @responses.activate
    def test_setup_saves_config(self, monkeypatch):
        """android_setup saves pairing code and sets env vars."""
        from tools.android_tool import _get_public_ip

        monkeypatch.setattr("tools.android_tool._get_public_ip", lambda: "1.2.3.4")
        result = json.loads(android_setup("ABC123"))
        assert os.environ.get("ANDROID_BRIDGE_TOKEN") == "ABC123"
        assert "localhost" in os.environ.get("ANDROID_BRIDGE_URL", "")


class TestClipboardRead:
    @responses.activate
    def test_clipboard_read(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/clipboard",
            json={"success": True, "message": "Clipboard read", "data": "Hello world"},
        )
        result = json.loads(android_clipboard_read())
        assert result["success"] is True
        assert result["data"] == "Hello world"

    @responses.activate
    def test_clipboard_read_empty(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/clipboard",
            json={"success": True, "message": "Clipboard is empty", "data": ""},
        )
        result = json.loads(android_clipboard_read())
        assert result["success"] is True
        assert result["data"] == ""

    @responses.activate
    def test_clipboard_read_failure(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/clipboard",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_clipboard_read())
        assert "error" in result


class TestClipboardWrite:
    @responses.activate
    def test_clipboard_write(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/clipboard",
            json={"success": True, "message": "Copied to clipboard", "data": "Hello"},
        )
        result = json.loads(android_clipboard_write("Hello"))
        assert result["success"] is True

    @responses.activate
    def test_clipboard_write_failure(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/clipboard",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_clipboard_write("test"))
        assert "error" in result


class TestNotifications:
    @responses.activate
    def test_notifications(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/notifications",
            json={
                "notifications": [
                    {
                        "packageName": "com.whatsapp",
                        "title": "John",
                        "text": "Hey!",
                        "timestamp": 1700000000000,
                    }
                ],
                "count": 1,
                "listenerActive": True,
            },
        )
        result = json.loads(android_notifications())
        assert result["count"] == 1
        assert result["notifications"][0]["packageName"] == "com.whatsapp"
        assert result["listenerActive"] is True

    @responses.activate
    def test_notifications_with_since(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/notifications",
            json={"notifications": [], "count": 0, "listenerActive": True},
        )
        result = json.loads(android_notifications(since=1700000000000))
        assert result["count"] == 0

    @responses.activate
    def test_notifications_listener_inactive(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/notifications",
            json={"notifications": [], "count": 0, "listenerActive": False},
        )
        result = json.loads(android_notifications())
        assert result["listenerActive"] is False

    @responses.activate
    def test_notifications_failure(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/notifications",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_notifications())
        assert "error" in result


class TestLongPress:
    @responses.activate
    def test_long_press_by_coordinates(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/long_press",
            json={"success": True, "message": "Long pressed (100, 200) 500ms"},
        )
        result = json.loads(android_long_press(x=100, y=200))
        assert result["success"] is True

    @responses.activate
    def test_long_press_by_node(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/long_press",
            json={"success": True, "message": "Long pressed node n1"},
        )
        result = json.loads(android_long_press(node_id="n1"))
        assert result["success"] is True

    @responses.activate
    def test_long_press_custom_duration(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/long_press",
            json={"success": True},
        )
        result = json.loads(android_long_press(x=100, y=200, duration=1000))
        assert result["success"] is True

    def test_long_press_no_args(self):
        result = json.loads(android_long_press())
        assert "error" in result


class TestDrag:
    @responses.activate
    def test_drag(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/drag",
            json={"success": True, "message": "Dragged (100,200) to (300,400)"},
        )
        result = json.loads(android_drag(100, 200, 300, 400))
        assert result["success"] is True

    @responses.activate
    def test_drag_with_duration(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/drag",
            json={"success": True},
        )
        result = json.loads(android_drag(0, 0, 100, 100, duration=800))
        assert result["success"] is True

    @responses.activate
    def test_drag_failure(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/drag",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_drag(0, 0, 100, 100))
        assert "error" in result


class TestDescribeNode:
    @responses.activate
    def test_describe_node(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/describe_node",
            json={
                "success": True,
                "data": {
                    "nodeId": "n1",
                    "className": "android.widget.EditText",
                    "text": "Hello",
                    "clickable": True,
                    "editable": True,
                    "childCount": 0,
                },
            },
        )
        result = json.loads(android_describe_node("n1"))
        assert result["success"] is True
        assert result["data"]["editable"] is True

    @responses.activate
    def test_describe_node_not_found(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/describe_node",
            json={"success": False, "message": "Node not found: bad_id"},
        )
        result = json.loads(android_describe_node("bad_id"))
        assert result["success"] is False

    @responses.activate
    def test_describe_node_failure(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/describe_node",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_describe_node("n1"))
        assert "error" in result


class TestScreenHash:
    @responses.activate
    def test_screen_hash(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/screen_hash",
            json={"success": True, "data": {"hash": "abc123", "nodeCount": 42}},
        )
        result = json.loads(android_screen_hash())
        assert result["success"] is True
        assert result["data"]["hash"] == "abc123"

    @responses.activate
    def test_screen_hash_failure(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/screen_hash",
            body=ConnectionError("refused"),
        )
        result = json.loads(android_screen_hash())
        assert "error" in result


class TestMacro:
    @responses.activate
    def test_macro_open_and_wait(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/open_app",
            json={"success": True, "message": "Opening com.ubercab"},
        )
        responses.add(
            responses.POST,
            f"{bridge_url}/wait",
            json={"success": True, "message": "Element found"},
        )
        result = json.loads(
            android_macro(
                steps=[
                    {"tool": "android_open_app", "args": {"package": "com.ubercab"}},
                    {"tool": "android_wait", "args": {"text": "Where to?"}},
                ],
                name="open_uber",
            )
        )
        assert result["success"] is True
        assert result["completed"] == 2

    @responses.activate
    def test_macro_stops_on_failure(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/tap_text",
            json={"success": False, "message": "Not found"},
        )
        result = json.loads(
            android_macro(
                steps=[
                    {"tool": "android_tap_text", "args": {"text": "nonexistent"}},
                ]
            )
        )
        assert "error" in result
        assert result["completed"] == 0

    def test_macro_unknown_tool(self):
        result = json.loads(
            android_macro(
                steps=[
                    {"tool": "android_nonexistent", "args": {}},
                ]
            )
        )
        assert "error" in result


class TestLocation:
    @responses.activate
    def test_location(self, bridge_url):
        responses.add(
            responses.GET,
            f"{bridge_url}/location",
            json={
                "success": True,
                "data": {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 10.0},
            },
        )
        result = json.loads(android_location())
        assert result["success"] is True
        assert result["data"]["latitude"] == 37.7749

    @responses.activate
    def test_location_failure(self, bridge_url):
        responses.add(
            responses.GET, f"{bridge_url}/location", body=ConnectionError("refused")
        )
        result = json.loads(android_location())
        assert "error" in result


class TestSendSms:
    @responses.activate
    def test_send_sms(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/send_sms",
            json={"success": True, "message": "SMS sent to +1234567890"},
        )
        result = json.loads(android_send_sms("+1234567890", "Hello!"))
        assert result["success"] is True

    @responses.activate
    def test_send_sms_failure(self, bridge_url):
        responses.add(
            responses.POST, f"{bridge_url}/send_sms", body=ConnectionError("refused")
        )
        result = json.loads(android_send_sms("+1234567890", "test"))
        assert "error" in result


class TestCall:
    @responses.activate
    def test_call(self, bridge_url):
        responses.add(
            responses.POST,
            f"{bridge_url}/call",
            json={"success": True, "message": "Calling +1234567890"},
        )
        result = json.loads(android_call("+1234567890"))
        assert result["success"] is True

    @responses.activate
    def test_call_failure(self, bridge_url):
        responses.add(
            responses.POST, f"{bridge_url}/call", body=ConnectionError("refused")
        )
        result = json.loads(android_call("+1234567890"))
        assert "error" in result
