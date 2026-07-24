"""Adapter: route.start on Waze."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class WazeRouteAdapter(Adapter):
    """Start navigation on Waze.

    Flow:
      1. open_app → com.waze
      2. tap Search
      3. type destination
      4. select result
      5. tap Go / Navigate
      6. Verify via route_active verifier
    """

    def __init__(self):
        super().__init__(
            name="waze_route",
            capability="route.start",
            package="com.waze",
            min_sdk=21,
            recipe_id="waze.route.start.v1",
        )

    def build_flow(self, destination: str = "") -> FlowDefinition:
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "com.waze"},
                verifier="screen_transition",
                verifier_params={"expected_package": "com.waze"},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Search", "exact": False},
                fallback=FlowStep(
                    action="android_tap_res_id",
                    params={"resId": "com.waze:id/search_button"},
                ),
            ),
        ]

        if destination:
            steps.extend([
                FlowStep(
                    action="android_type_text",
                    params={"text": destination},
                ),
                FlowStep(
                    action="android_tap_text",
                    params={"text": destination, "exact": False},
                    retries=1,
                ),
            ])

        steps.append(FlowStep(
            action="android_tap_text",
            params={"text": "Go", "exact": False},
            fallback=FlowStep(
                action="android_tap_text",
                params={"text": "Navigate", "exact": False},
            ),
            verifier="route_active",
            verifier_params={"destination": destination},
        ))

        return FlowDefinition(
            capability="route.start",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=30000,
        )
