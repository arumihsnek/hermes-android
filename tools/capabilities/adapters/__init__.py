"""Adapters — app-specific capability execution adapters with fingerprint matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import DeviceFingerprint


@dataclass
class Adapter:
    """An adapter for executing a capability on a specific app."""
    name: str
    capability: str
    package: str
    min_sdk: int = 21
    recipe_id: str = ""
    required_packages: list[str] = field(default_factory=list)
    priority: int = 0  # lower = preferred

    def supports(self, capability: str, package: Optional[str] = None) -> bool:
        """Check if this adapter supports the given capability and package."""
        if self.capability != capability:
            return False
        if package and self.package != "com.any" and self.package != package:
            return False
        return True

    def matches_fingerprint(self, fingerprint: DeviceFingerprint) -> bool:
        """Check if the device fingerprint meets this adapter's requirements."""
        if fingerprint.sdk_int < self.min_sdk:
            return False
        for req_pkg in self.required_packages:
            if req_pkg not in fingerprint.package_fingerprints:
                return False
        return True


class AdapterRegistry:
    """Registry for selecting adapters by capability and fingerprint."""

    def __init__(self):
        self._adapters: list[Adapter] = []

    def register(self, adapter: Adapter) -> None:
        self._adapters.append(adapter)

    def select(
        self,
        capability: str,
        fingerprint: DeviceFingerprint,
        package: Optional[str] = None,
    ) -> Optional[Adapter]:
        """Select the best adapter for a capability on this device.

        Prefers exact package match, then highest priority.
        """
        candidates = []
        for adapter in self._adapters:
            if not adapter.supports(capability, package):
                continue
            if not adapter.matches_fingerprint(fingerprint):
                continue
            candidates.append(adapter)

        if not candidates:
            return None

        # Sort by: exact package match first, then by priority
        def sort_key(a: Adapter) -> tuple:
            exact_match = 0 if (package and a.package == package) else 1
            return (exact_match, a.priority)

        candidates.sort(key=sort_key)
        return candidates[0]

    def find_all(self, capability: str) -> list[Adapter]:
        """Find all adapters for a capability."""
        return [a for a in self._adapters if a.capability == capability]

    def count(self) -> int:
        return len(self._adapters)
