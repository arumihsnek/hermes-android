"""
Device fingerprint — fetches real device identity from the bridge
and constructs a validated DeviceFingerprint.

This module replaces the old stub `_get_device_fingerprint()` which
returned sdk_int=0 and device_id="unknown".
"""
from __future__ import annotations

import os
from typing import Any, Optional

from .models import DeviceFingerprint


def _get_bridge_json(endpoint: str, params: Optional[dict] = None) -> dict:
    """Fetch JSON from the bridge HTTP API.

    Uses the same bridge URL/token resolution as android_tool.py.
    Raises ConnectionError if bridge is unreachable.
    Raises ValueError if response is not valid JSON.
    """
    import requests

    bridge_url = os.environ.get("ANDROID_BRIDGE_URL", "http://localhost:18766")
    token = os.environ.get("ANDROID_BRIDGE_TOKEN", "")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{bridge_url}{endpoint}"
    resp = requests.get(url, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json()


def get_device_fingerprint(
    packages: Optional[list[str]] = None,
) -> DeviceFingerprint:
    """Get a real device fingerprint from the bridge.

    Args:
        packages: Optional list of package names to include fingerprints for.
                  If None, the bridge returns all known packages.
                  Pass a specific list to avoid enumeration cost.

    Returns:
        DeviceFingerprint with real sdk_int, device_id, and package fingerprints.

    Raises:
        ConnectionError: If the bridge is unreachable.
        ValueError: If the response is missing required fields or has sdk_int=0.
    """
    params: dict[str, Any] = {}
    if packages:
        params["packages"] = ",".join(packages)

    data = _get_bridge_json("/device/info", params)

    return DeviceFingerprint.from_bridge_response(data)
