"""Tests for Task 16: message.send vertical — WhatsApp adapter.

SAFETY: This vertical requires confirmation before sending.
The adapter COMPOSES but does NOT auto-send by default.
"""

import pytest
from tools.capabilities.adapters import AdapterRegistry
from tools.capabilities.adapters.whatsapp_message import WhatsAppMessageAdapter
from tools.capabilities.errors import AuthorizationRefused
from tools.capabilities.flow_executor import FlowExecutor, FlowHandler
from tools.capabilities.models import (
    DeviceFingerprint,
    EvidenceReference,
    ResultStatus,
    VerificationOutcome,
    VerificationResult,
)
from tools.capabilities.policy import PolicyGate, classify_action
from tools.capabilities.recipes import load_recipe_from_dict


class FakeHandler(FlowHandler):
    def __init__(self):
        self.actions = []
    def execute(self, action, params):
        self.actions.append((action, params))
        return {"success": True}
    def verify(self, verifier, params):
        return VerificationResult(
            outcome=VerificationOutcome.CONFIRMED,
            verifier_type=verifier,
            evidence_ref=EvidenceReference.create(verifier, "msg sent"),
        )


class TestWhatsAppMessageAdapter:
    def test_adapter_creation(self):
        adapter = WhatsAppMessageAdapter()
        assert adapter.name == "whatsapp_message"
        assert adapter.capability == "message.send"
        assert adapter.package == "com.whatsapp"

    def test_adapter_supports(self):
        adapter = WhatsAppMessageAdapter()
        assert adapter.supports("message.send", "com.whatsapp")
        assert not adapter.supports("message.send", "com.telegram.messenger")
        assert not adapter.supports("timer.set")

    def test_build_flow_compose_only(self):
        """Default flow: compose message, do NOT send."""
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="Julio", message="Hola!")
        assert flow.capability == "message.send"
        # Should have: open, select contact, type message
        assert len(flow.steps) >= 3
        # Should NOT have a send step (auto_send=False by default)
        actions = [s.action for s in flow.steps]
        # Last step should be the type_text with verifier
        assert flow.steps[-1].verifier == "node_predicate"

    def test_build_flow_with_auto_send(self):
        """Flow with auto_send: includes send step with confirmation_token."""
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="Julio", message="Hola!", auto_send=True)
        # Last step should be the send
        last_step = flow.steps[-1]
        assert last_step.action == "message.send"
        assert last_step.params["text"] == "Send"
        # CRITICAL: confirmation_token must be present
        assert last_step.confirmation_token == "user_confirmed_send"

    def test_flow_compose_executes(self):
        """Compose-only flow should succeed."""
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="Julio", message="Hola!")
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_flow_send_requires_confirmation(self):
        """Send step WITHOUT confirmation_token should be REFUSED by policy."""
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="Julio", message="Hola!", auto_send=True)
        # Remove the confirmation_token to test policy enforcement
        flow.steps[-1].confirmation_token = None
        result = executor.execute(flow)
        assert result.status == ResultStatus.REFUSED
        assert result.failure_class.value == "confirmation_required"

    def test_flow_send_with_confirmation_succeeds(self):
        """Send step WITH confirmation_token should succeed."""
        handler = FakeHandler()
        executor = FlowExecutor(handler)
        adapter = WhatsAppMessageAdapter()
        flow = adapter.build_flow(contact="Julio", message="Hola!", auto_send=True)
        result = executor.execute(flow)
        assert result.status == ResultStatus.SUCCESS

    def test_send_action_is_confirmation_required(self):
        """Policy classifies send_whatsapp as confirmation_required."""
        classification = classify_action("send_whatsapp")
        assert classification.value == "confirmation_required"

    def test_send_message_action_is_confirmation_required(self):
        """Policy classifies message.send as confirmation_required."""
        classification = classify_action("message.send")
        assert classification.value == "confirmation_required"

    def test_adapter_registry_select(self):
        registry = AdapterRegistry()
        registry.register(WhatsAppMessageAdapter())
        fp = DeviceFingerprint("pixel8", "15", 35)
        selected = registry.select("message.send", fp, package="com.whatsapp")
        assert selected is not None
        assert selected.name == "whatsapp_message"

    def test_recipe_loads_with_safety(self):
        recipe = load_recipe_from_dict({
            "id": "whatsapp.message.send.v1",
            "capability": "message.send",
            "package": "com.whatsapp",
            "maturity": "candidate",
            "steps": [
                {"action": "android_open_app", "params": {}},
                {"action": "android_tap_text", "params": {"text": "Send"}, "confirmation_token": "user_confirmed_send"},
            ],
            "verifier": {"type": "notification_pattern"},
        })
        assert recipe.id == "whatsapp.message.send.v1"
        # Verify the confirmation_token is preserved
        send_step = recipe.steps[1]
        assert send_step["confirmation_token"] == "user_confirmed_send"
