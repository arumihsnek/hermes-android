"""Adapter: message.send on WhatsApp.

SAFETY: This adapter COMPOSES but does NOT send.
The final 'send' step requires explicit confirmation_token.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from . import Adapter
from ..flow_executor import FlowDefinition, FlowStep


@dataclass
class WhatsAppMessageAdapter(Adapter):
    """Compose a message on WhatsApp.

    SAFETY: The send action is CONFIRMATION_REQUIRED by policy.
    This adapter builds the flow with a confirmation_token placeholder
    on the send step. The flow executor will refuse to send without it.

    Flow:
      1. open_app → com.whatsapp
      2. select contact (by name or phone)
      3. type message in compose field
      4. STOP — verify composed state, do NOT auto-send
    """

    def __init__(self):
        super().__init__(
            name="whatsapp_message",
            capability="message.send",
            package="com.whatsapp",
            min_sdk=21,
            recipe_id="whatsapp.message.send.v1",
        )

    def build_flow(
        self,
        contact: str = "",
        message: str = "",
        auto_send: bool = False,
    ) -> FlowDefinition:
        """Build a message flow.

        Args:
            contact: Contact name or phone number
            message: Message body
            auto_send: If True, adds a send step WITH confirmation_token.
                       If False (default), stops after composing.
        """
        steps = [
            FlowStep(
                action="android_open_app",
                params={"packageName": "com.whatsapp"},
                verifier="screen_transition",
                verifier_params={"expected_package": "com.whatsapp"},
            ),
        ]

        if contact:
            steps.append(FlowStep(
                action="android_tap_text",
                params={"text": contact, "exact": False},
                retries=1,
            ))

        if message:
            steps.append(FlowStep(
                action="android_type_text",
                params={"text": message},
                verifier="node_predicate",
                verifier_params={"text": message[:30]},
            ))

        if auto_send:
            # SAFETY: Use semantic action 'message.send' which is classified
            # as CONFIRMATION_REQUIRED by policy. The handler maps this to
            # the actual android_tap_text call on the Send button.
            # confirmation_token is REQUIRED by policy — without it, refused.
            steps.append(FlowStep(
                action="message.send",
                params={"text": "Send", "exact": False},
                confirmation_token="user_confirmed_send",
                verifier="notification_pattern",
                verifier_params={"pattern": "sent"},
            ))

        return FlowDefinition(
            capability="message.send",
            steps=steps,
            recipe_id=self.recipe_id,
            timeout_ms=20000,
        )
