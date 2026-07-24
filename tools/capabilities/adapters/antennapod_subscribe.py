"""Adapter: podcast.subscribe on AntennaPod."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class AntennaPodSubscribeAdapter(Adapter):
    """Subscribe to a podcast on AntennaPod.

    Flow:
      1. open_app → de.danoeh.antennapod
      2. tap Add Podcast / Search
      3. type podcast name
      4. select from results
      5. tap Subscribe button
      6. Verify via node_predicate (subscribed state)
    """

    def __init__(self):
        super().__init__(
            name="antennapod_subscribe",
            capability="podcast.subscribe",
            package="de.danoeh.antennapod",
            min_sdk=21,
            recipe_id="antennapod.podcast.subscribe.v1",
        )

    def build_flow(self, podcast_name: str = "") -> FlowDefinition:
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "de.danoeh.antennapod"},
                verifier="screen_transition",
                verifier_params={"expected_package": "de.danoeh.antennapod"},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Add Podcast", "exact": False},
                fallback=FlowStep(
                    action="android_tap_text",
                    params={"text": "Search", "exact": False},
                ),
            ),
        ]

        if podcast_name:
            steps.extend([
                FlowStep(
                    action="android_type_text",
                    params={"text": podcast_name},
                ),
                FlowStep(
                    action="android_press_key",
                    params={"key": "ENTER"},
                ),
                FlowStep(
                    action="android_tap_text",
                    params={"text": podcast_name, "exact": False},
                    retries=1,
                ),
            ])

        steps.append(FlowStep(
            action="android_tap_text",
            params={"text": "Subscribe", "exact": False},
            fallback=FlowStep(
                action="android_tap_text",
                params={"text": "Add", "exact": False},
            ),
            verifier="node_predicate",
            verifier_params={"text": "Subscribed"},
        ))

        return FlowDefinition(
            capability="podcast.subscribe",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=30000,
        )
