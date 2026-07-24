"""Adapter: media.play on AntennaPod."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class AntennaPodMediaAdapter(Adapter):
    """Play media on AntennaPod.

    Flow:
      1. open_app → de.danoeh.antennapod
      2. tap search icon
      3. type query
      4. select result
      5. tap play
      6. Verify via media_state verifier
    """

    def __init__(self):
        super().__init__(
            name="antennapod_media",
            capability="media.play",
            package="de.danoeh.antennapod",
            min_sdk=21,
            recipe_id="antennapod.media.play.v1",
        )

    def build_flow(self, query: str = "") -> FlowDefinition:
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "de.danoeh.antennapod"},
                verifier="screen_transition",
                verifier_params={"expected_package": "de.danoeh.antennapod"},
            ),
        ]

        if query:
            steps.extend([
                FlowStep(
                    action="android_tap_text",
                    params={"text": "Search", "exact": False},
                    fallback=FlowStep(
                        action="android_tap_res_id",
                        params={"resId": "de.danoeh.antennapod:id/search"},
                    ),
                ),
                FlowStep(
                    action="android_type_text",
                    params={"text": query},
                ),
                FlowStep(
                    action="android_press_key",
                    params={"key": "ENTER"},
                ),
                FlowStep(
                    action="android_tap_text",
                    params={"text": query, "exact": False},
                    retries=1,
                ),
            ])

        steps.append(FlowStep(
            action="android_tap_text",
            params={"text": "Play", "exact": False},
            fallback=FlowStep(
                action="android_tap_res_id",
                params={"resId": "de.danoeh.antennapod:id/butPlay"},
            ),
            verifier="media_state",
            verifier_params={"expected_title": query},
        ))

        return FlowDefinition(
            capability="media.play",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=30000,
        )
