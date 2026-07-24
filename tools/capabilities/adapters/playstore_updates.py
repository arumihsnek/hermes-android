"""Adapter: updates.pause on Google Play Store."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class PlayStoreUpdatesAdapter(Adapter):
    """Pause app updates on Google Play Store.

    Flow:
      1. open_app → com.android.vending
      2. tap profile icon / Settings
      3. tap Network preferences → Auto-update apps
      4. select "Don't auto-update apps"
      5. Verify via node_predicate (selected state)
    """

    def __init__(self):
        super().__init__(
            name="playstore_updates",
            capability="updates.pause",
            package="com.android.vending",
            min_sdk=21,
            recipe_id="playstore.updates.pause.v1",
        )

    def build_flow(self) -> FlowDefinition:
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "com.android.vending"},
                verifier="screen_transition",
                verifier_params={"expected_package": "com.android.vending"},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Settings", "exact": False},
                fallback=FlowStep(
                    action="android_tap_res_id",
                    params={"resId": "com.android.vending:id/settings_button"},
                ),
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Network preferences", "exact": False},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Auto-update apps", "exact": False},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Don't auto-update apps", "exact": False},
                fallback=FlowStep(
                    action="android_tap_text",
                    params={"text": "Don't auto-update", "exact": False},
                ),
                verifier="node_predicate",
                verifier_params={"text": "Don't auto-update apps"},
            ),
        ]

        return FlowDefinition(
            capability="updates.pause",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=20000,
        )
