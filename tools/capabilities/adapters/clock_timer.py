"""Adapter: timer.set on Android Clock app."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep
from ..models import DeviceFingerprint


@dataclass
class ClockTimerAdapter(Adapter):
    """Set a timer on the Android Clock app.

    Flow:
      1. open_app → com.google.android.deskclock
      2. tap_text "Timer" (switch to Timer tab)
      3. Set duration via tap_text on number buttons
      4. tap_text "Start" to begin timer
      5. Verify via timer_exists verifier
    """

    def __init__(self):
        super().__init__(
            name="clock_timer",
            capability="timer.set",
            package="com.google.android.deskclock",
            min_sdk=21,
            recipe_id="clock.timer.set.v1",
        )

    def build_flow(
        self,
        duration_seconds: int = 60,
        label: str = "",
    ) -> FlowDefinition:
        """Build a flow to set a timer."""
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60

        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "com.google.android.deskclock"},
                verifier="screen_transition",
                verifier_params={"expected_package": "com.google.android.deskclock"},
            ),
            FlowStep(
                action="android_tap_text",
                params={"text": "Timer", "exact": False},
                retries=1,
            ),
        ]

        # Set minutes if > 0
        if minutes > 0:
            for digit in str(minutes):
                steps.append(FlowStep(
                    action="android_tap_text",
                    params={"text": digit, "exact": True},
                ))

        # Set seconds if > 0 and timer has seconds field
        if seconds > 0 and minutes == 0:
            for digit in str(seconds):
                steps.append(FlowStep(
                    action="android_tap_text",
                    params={"text": digit, "exact": True},
                ))

        # Start the timer
        steps.append(FlowStep(
            action="android_tap_text",
            params={"text": "Start", "exact": True},
            verifier="timer_exists",
            verifier_params={"duration_seconds": duration_seconds},
        ))

        return FlowDefinition(
            capability="timer.set",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=15000,
        )
