"""Adapter: place.save on OsmAnd."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class OsmAndPlaceAdapter(Adapter):
    """Save a favorite location on OsmAnd.

    Flow:
      1. open_app → net.osmand.plus
      2. search or navigate to location
      3. long-press or tap to get POI details
      4. tap Save / Add to Favorites
      5. Verify via favorite_saved verifier
    """

    def __init__(self):
        super().__init__(
            name="osmand_place",
            capability="place.save",
            package="net.osmand.plus",
            min_sdk=21,
            recipe_id="osmand.place.save.v1",
        )

    def build_flow(self, place_name: str = "", latitude: float = 0.0, longitude: float = 0.0) -> FlowDefinition:
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "net.osmand.plus"},
                verifier="screen_transition",
                verifier_params={"expected_package": "net.osmand.plus"},
            ),
        ]

        if place_name:
            steps.extend([
                FlowStep(
                    action="android_tap_text",
                    params={"text": "Search", "exact": False},
                    fallback=FlowStep(
                        action="android_tap_res_id",
                        params={"resId": "net.osmand.plus:id/search_button"},
                    ),
                ),
                FlowStep(
                    action="android_type_text",
                    params={"text": place_name},
                ),
                FlowStep(
                    action="android_press_key",
                    params={"key": "ENTER"},
                ),
                FlowStep(
                    action="android_tap_text",
                    params={"text": place_name, "exact": False},
                    retries=1,
                ),
            ])

        steps.append(FlowStep(
            action="android_tap_text",
            params={"text": "Add to Favorites", "exact": False},
            fallback=FlowStep(
                action="android_tap_text",
                params={"text": "Save", "exact": False},
            ),
            verifier="favorite_saved",
            verifier_params={"place_name": place_name},
        ))

        return FlowDefinition(
            capability="place.save",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=30000,
        )
