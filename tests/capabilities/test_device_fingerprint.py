"""
Block 1: Real device fingerprint tests.

Tests that the device fingerprint is obtained from the bridge /device/info
endpoint and parsed correctly. No silent fallback to sdk_int=0.
"""
import hashlib
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Bridge response schema fixtures ────────────────────────────────────────

SAMPLE_DEVICE_INFO = {
    "device_id": "pixel8_shiba",
    "android_version": "15",
    "sdk_int": 35,
    "manufacturer": "Google",
    "model": "Pixel 8",
    "packages": {
        "com.google.android.deskclock": {
            "versionName": "7.3.646893345",
            "versionCode": 53093345,
            "lastUpdateTime": 1720000000000,
        },
        "de.danoeh.antennapod": {
            "versionName": "3.4.0",
            "versionCode": 174,
            "lastUpdateTime": 1719000000000,
        },
    },
}


def _expected_digest(data: dict) -> str:
    """Compute expected digest matching the model logic."""
    raw = f"{data['device_id']}:{data['android_version']}:{data['sdk_int']}"
    for pkg in sorted(data.get("packages", {})):
        pkg_data = data["packages"][pkg]
        vname = pkg_data.get("versionName", "")
        vcode = pkg_data.get("versionCode", 0)
        raw += f":{pkg}={vname}:{vcode}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Schema validation ──────────────────────────────────────────────────────

class TestDeviceInfoSchema:
    """Verify the bridge /device/info response has the required schema."""

    def test_has_required_top_level_fields(self):
        data = SAMPLE_DEVICE_INFO
        assert "device_id" in data
        assert "android_version" in data
        assert "sdk_int" in data
        assert isinstance(data["sdk_int"], int)
        assert data["sdk_int"] > 0, "sdk_int must be a real positive integer"

    def test_has_manufacturer_and_model(self):
        data = SAMPLE_DEVICE_INFO
        assert "manufacturer" in data
        assert "model" in data
        assert isinstance(data["manufacturer"], str)
        assert isinstance(data["model"], str)
        assert len(data["manufacturer"]) > 0
        assert len(data["model"]) > 0

    def test_packages_is_dict(self):
        data = SAMPLE_DEVICE_INFO
        assert "packages" in data
        assert isinstance(data["packages"], dict)

    def test_package_entry_has_required_fields(self):
        data = SAMPLE_DEVICE_INFO
        for pkg_name, pkg_data in data["packages"].items():
            assert "versionName" in pkg_data, f"{pkg_name} missing versionName"
            assert "versionCode" in pkg_data, f"{pkg_name} missing versionCode"
            assert isinstance(pkg_data["versionCode"], int)
            assert pkg_data["versionCode"] > 0

    def test_no_fallback_sdk_zero(self):
        """sdk_int=0 is never a valid response from a real device."""
        data = SAMPLE_DEVICE_INFO
        assert data["sdk_int"] != 0
        assert data["device_id"] != "unknown"
        assert data["android_version"] != "unknown"


# ── Python parsing ─────────────────────────────────────────────────────────

class TestDeviceFingerprintParsing:
    """Test that the bridge response is parsed into a DeviceFingerprint."""

    def test_parse_from_bridge_response(self):
        from tools.capabilities.models import DeviceFingerprint

        data = SAMPLE_DEVICE_INFO
        fp = DeviceFingerprint.from_bridge_response(data)
        assert fp.device_id == "pixel8_shiba"
        assert fp.android_version == "15"
        assert fp.sdk_int == 35
        assert fp.manufacturer == "Google"
        assert fp.model == "Pixel 8"
        assert "com.google.android.deskclock" in fp.package_fingerprints

    def test_parse_package_fingerprints_format(self):
        from tools.capabilities.models import DeviceFingerprint

        data = SAMPLE_DEVICE_INFO
        fp = DeviceFingerprint.from_bridge_response(data)
        pkg_fp = fp.package_fingerprints["com.google.android.deskclock"]
        # Format should encode version name and code
        assert "7.3" in pkg_fp or "53093345" in pkg_fp

    def test_parse_missing_packages_is_empty_dict(self):
        from tools.capabilities.models import DeviceFingerprint

        data = {
            "device_id": "test",
            "android_version": "14",
            "sdk_int": 34,
            "manufacturer": "Test",
            "model": "Device",
        }
        fp = DeviceFingerprint.from_bridge_response(data)
        assert fp.package_fingerprints == {}


# ── Digest stability ───────────────────────────────────────────────────────

class TestDigestStability:
    """Test that digest is deterministic for the same input."""

    def test_digest_deterministic(self):
        from tools.capabilities.models import DeviceFingerprint

        fp1 = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        fp2 = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        assert fp1.digest() == fp2.digest()

    def test_digest_format(self):
        from tools.capabilities.models import DeviceFingerprint

        fp = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        d = fp.digest()
        assert len(d) == 16
        assert all(c in "0123456789abcdef" for c in d)

    def test_digest_changes_on_version_change(self):
        from tools.capabilities.models import DeviceFingerprint

        data1 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2["packages"]["com.google.android.deskclock"]["versionCode"] = 999999999

        fp1 = DeviceFingerprint.from_bridge_response(data1)
        fp2 = DeviceFingerprint.from_bridge_response(data2)
        assert fp1.digest() != fp2.digest(), "Digest must change when app version changes"

    def test_digest_changes_on_sdk_change(self):
        from tools.capabilities.models import DeviceFingerprint

        data1 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2["sdk_int"] = 34

        fp1 = DeviceFingerprint.from_bridge_response(data1)
        fp2 = DeviceFingerprint.from_bridge_response(data2)
        assert fp1.digest() != fp2.digest()

    def test_digest_changes_on_device_id_change(self):
        from tools.capabilities.models import DeviceFingerprint

        data1 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        data2["device_id"] = "different_device"

        fp1 = DeviceFingerprint.from_bridge_response(data1)
        fp2 = DeviceFingerprint.from_bridge_response(data2)
        assert fp1.digest() != fp2.digest()

    def test_package_fingerprints_sorted_in_digest(self):
        """Digest must be independent of dict iteration order."""
        from tools.capabilities.models import DeviceFingerprint

        data1 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        # Swap package order in dict (Python 3.7+ preserves insertion order)
        data2 = json.loads(json.dumps(SAMPLE_DEVICE_INFO))
        pkgs = list(data2["packages"].keys())
        data2["packages"] = {k: data2["packages"][k] for k in reversed(pkgs)}

        fp1 = DeviceFingerprint.from_bridge_response(data1)
        fp2 = DeviceFingerprint.from_bridge_response(data2)
        assert fp1.digest() == fp2.digest()


# ── Adapter selection with real SDK ────────────────────────────────────────

class TestAdapterSelectionWithRealSDK:
    """Test that adapter selection works with a real fingerprint (not sdk_int=0)."""

    def test_clock_timer_adapter_selects_with_sdk_35(self):
        from tools.capabilities.adapters import AdapterRegistry
        from tools.capabilities.adapters.clock_timer import ClockTimerAdapter
        from tools.capabilities.models import DeviceFingerprint

        registry = AdapterRegistry()
        registry.register(ClockTimerAdapter())

        fp = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        adapter = registry.select("timer.set", fp)
        assert adapter is not None
        assert adapter.name == "clock_timer"
        assert adapter.min_sdk <= fp.sdk_int

    def test_adapter_rejects_insufficient_sdk(self):
        from tools.capabilities.adapters import Adapter
        from tools.capabilities.adapters import AdapterRegistry
        from tools.capabilities.models import DeviceFingerprint

        class HighSdkAdapter(Adapter):
            def __init__(self):
                super().__init__(
                    name="high_sdk",
                    capability="test.cap",
                    package="com.test",
                    min_sdk=99,
                )

        registry = AdapterRegistry()
        registry.register(HighSdkAdapter())

        fp = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        adapter = registry.select("test.cap", fp)
        assert adapter is None, "Should reject adapter requiring SDK 99 on SDK 35"

    def test_adapter_checks_required_packages(self):
        from tools.capabilities.adapters import Adapter
        from tools.capabilities.adapters import AdapterRegistry
        from tools.capabilities.models import DeviceFingerprint

        class NeedsPackageAdapter(Adapter):
            def __init__(self):
                super().__init__(
                    name="needs_pkg",
                    capability="test.cap",
                    package="com.test",
                    min_sdk=21,
                    required_packages=["com.nonexistent.package"],
                )

        registry = AdapterRegistry()
        registry.register(NeedsPackageAdapter())

        fp = DeviceFingerprint.from_bridge_response(SAMPLE_DEVICE_INFO)
        adapter = registry.select("test.cap", fp)
        assert adapter is None, "Should reject adapter requiring nonexistent package"


# ── Error handling ─────────────────────────────────────────────────────────

class TestFingerprintErrorHandling:
    """Test error handling when bridge is unavailable."""

    def test_bridge_unavailable_raises_error(self):
        """_get_device_fingerprint should raise, not silently fallback to sdk_int=0."""
        from tools.capabilities.fingerprint import get_device_fingerprint

        with patch("tools.capabilities.fingerprint._get_bridge_json") as mock_get:
            mock_get.side_effect = ConnectionError("Bridge unreachable")
            with pytest.raises(ConnectionError):
                get_device_fingerprint()

    def test_invalid_json_raises_error(self):
        from tools.capabilities.fingerprint import get_device_fingerprint

        with patch("tools.capabilities.fingerprint._get_bridge_json") as mock_get:
            mock_get.return_value = {"invalid": "schema"}
            with pytest.raises(ValueError, match="Missing required field"):
                get_device_fingerprint()

    def test_sdk_zero_raises_error(self):
        """Even if bridge returns sdk_int=0, we should reject it."""
        from tools.capabilities.fingerprint import get_device_fingerprint

        with patch("tools.capabilities.fingerprint._get_bridge_json") as mock_get:
            mock_get.return_value = {
                "device_id": "test",
                "android_version": "unknown",
                "sdk_int": 0,
            }
            with pytest.raises(ValueError, match="sdk_int"):
                get_device_fingerprint()

    def test_request_specific_packages(self):
        """Can request fingerprints for specific packages to avoid enumeration."""
        from tools.capabilities.fingerprint import get_device_fingerprint

        with patch("tools.capabilities.fingerprint._get_bridge_json") as mock_get:
            mock_get.return_value = SAMPLE_DEVICE_INFO
            fp = get_device_fingerprint(
                packages=["com.google.android.deskclock"]
            )
            assert fp is not None
            assert "com.google.android.deskclock" in fp.package_fingerprints
