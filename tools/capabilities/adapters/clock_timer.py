"""Adapter: timer.set on Android Clock app.

Uses the standard android.provider.AlarmClock API:
  - android.intent.action.SET_TIMER with extras:
    - android.intent.extra.alarm.LENGTH (seconds)
    - android.intent.extra.alarm.MESSAGE (label)
    - android.intent.extra.alarm.SKIP_UI (bool)

Requires com.android.alarm.permission.SET_ALARM in bridge manifest.

Fallback: broadcast SET_TIMER (less reliable, Clock may ignore broadcasts).
Last resort: UI automation (tap Temporizador tab → enter digits → Start).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class ClockTimerAdapter(Adapter):
    """Set a timer on the Android Clock app via SET_TIMER intent.

    Primary: send_intent with SET_TIMER action (requires SET_ALARM permission).
    Fallback: broadcast SET_TIMER.
    UI fallback: open Clock → Timer tab → enter digits → Start.
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
        skip_ui: bool = True,
    ) -> FlowDefinition:
        """Build a flow to set a timer via intent.

        Args:
            duration_seconds: Timer duration in seconds (min 1)
            label: Optional label for the timer
            skip_ui: If True, timer starts silently in background
        """
        duration_seconds = max(1, duration_seconds)

        steps = [
            # Primary: send SET_TIMER intent via bridge /intent endpoint
            # Requires com.android.alarm.permission.SET_ALARM in bridge manifest
            FlowStep(
                action="android_send_intent",
                params={
                    "action": "android.intent.action.SET_TIMER",
                    "extras": {
                        "android.intent.extra.alarm.LENGTH": duration_seconds,
                        "android.intent.extra.alarm.MESSAGE": label or f"Timer {duration_seconds}s",
                        "android.intent.extra.alarm.SKIP_UI": skip_ui,
                    },
                },
                verifier="timer_exists",
                verifier_params={
                    "duration_seconds": duration_seconds,
                    "label": label,
                },
                fallback=FlowStep(
                    # Fallback: broadcast (less reliable, Clock may ignore)
                    action="android_broadcast",
                    params={
                        "action": "android.intent.action.SET_TIMER",
                        "extras": {
                            "android.intent.extra.alarm.LENGTH": duration_seconds,
                            "android.intent.extra.alarm.MESSAGE": label or f"Timer {duration_seconds}s",
                            "android.intent.extra.alarm.SKIP_UI": skip_ui,
                        },
                    },
                    verifier="timer_exists",
                    verifier_params={"duration_seconds": duration_seconds},
                ),
            ),
        ]

        return FlowDefinition(
            capability="timer.set",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=10000,
        )

    @staticmethod
    def intent_action() -> str:
        """Return the standard intent action for this capability."""
        return "android.intent.action.SET_TIMER"

    @staticmethod
    def intent_extras(duration_seconds: int, label: str = "", skip_ui: bool = True) -> dict:
        """Build the extras dict for the SET_TIMER intent."""
        return {
            "android.intent.extra.alarm.LENGTH": max(1, duration_seconds),
            "android.intent.extra.alarm.MESSAGE": label or f"Timer {duration_seconds}s",
            "android.intent.extra.alarm.SKIP_UI": skip_ui,
        }
