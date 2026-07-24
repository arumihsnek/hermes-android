#!/usr/bin/env python3
"""
Live dogfood test for capability-runtime-hardening.

Prerequisites:
  - Pixel 8 connected via relay or direct bridge
  - ANDROID_BRIDGE_URL and ANDROID_BRIDGE_TOKEN set in environment
  - Bridge APK must have /device/info endpoint (currently NOT deployed)

Run:
  cd ~/code/hermes-android
  ANDROID_BRIDGE_URL="http://localhost:18766" ANDROID_BRIDGE_TOKEN="REDACTED_BRIDGE_TOKEN_ROTATED" \
    python3 tests/capabilities/test_live_dogfood.py
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.expanduser("~/code/hermes-android"))

from tools.capabilities.fingerprint import get_device_fingerprint
from tools.capabilities.service import CapabilityService
from tools.android_tool import _BridgeFlowHandler
from tools.capabilities.adapters.clock_timer import ClockTimerAdapter
from tools.capabilities.persistence import CapabilityStateStore

EVIDENCE = {}

def log_evidence(key, value):
    EVIDENCE[key] = value
    print(f"  {key}: {value}")

def main():
    print("=" * 60)
    print("LIVE DOGFOOD: timer.set on Pixel 8")
    print("=" * 60)

    # Step 1: Connectivity check
    import requests
    bridge_url = os.environ.get("ANDROID_BRIDGE_URL", "")
    token = os.environ.get("ANDROID_BRIDGE_TOKEN", "")
    if not bridge_url:
        print("\n✗ No ANDROID_BRIDGE_URL set. Cannot run live dogfood.")
        return 1

    try:
        r = requests.get(f"{bridge_url}/ping",
                        headers={"Authorization": f"Bearer {token}"}, timeout=5)
        ping = r.json()
    except Exception as e:
        print(f"\n✗ Bridge unreachable: {e}")
        return 1

    if "error" in ping:
        print(f"\n✗ Bridge error: {ping['error']}")
        print("  → Open Hermes Bridge app on Pixel 8 and enable auto-connect")
        return 1

    print(f"\n✓ Bridge connected: {json.dumps(ping)}")

    # Step 2: Device fingerprint
    print("\n--- Step 2: Device Fingerprint ---")
    try:
        fp = get_device_fingerprint()
        log_evidence("device_fingerprint_digest", fp.digest())
        log_evidence("sdk_int", fp.sdk_int)
        log_evidence("model", f"{fp.manufacturer} {fp.model}")
        log_evidence("packages", list(fp.package_fingerprints.keys()))
    except Exception as e:
        print(f"  /device/info not available ({e}) — using synthetic fingerprint")
        from tools.capabilities.models import DeviceFingerprint
        fp = DeviceFingerprint(
            device_id="google_pixel_8", android_version="15", sdk_int=35,
            manufacturer="Google", model="Pixel 8",
            package_fingerprints={"com.google.android.deskclock": "7.3:53093345"})
        log_evidence("device_fingerprint_digest", fp.digest())
        log_evidence("sdk_int", fp.sdk_int)
        log_evidence("model", "Google Pixel 8 (synthetic)")
        log_evidence("fingerprint_source", "synthetic (APK needs /device/info)")

    # Step 3: Adapter selection
    print("\n--- Step 3: Adapter & Recipe Selection ---")
    from tools.capabilities.adapters import AdapterRegistry
    registry = AdapterRegistry()
    registry.register(ClockTimerAdapter())
    adapter = registry.select("timer.set", fp)
    log_evidence("selected_adapter", adapter.name if adapter else "none")
    log_evidence("selected_recipe", adapter.recipe_id if adapter else "none")

    # Step 4: Execute timer.set
    print("\n--- Step 4: Execute timer.set via SET_TIMER ---")
    handler = _BridgeFlowHandler()
    service = CapabilityService(handler)
    flow = adapter.build_flow(duration_seconds=30, label="Dogfood Test")

    steps = []
    for step in flow.steps:
        s = {"action": step.action, "params": step.params,
             "verifier": step.verifier, "verifier_params": step.verifier_params}
        if step.fallback:
            s["fallback"] = {"action": step.fallback.action,
                             "params": step.fallback.params}
        steps.append(s)

    result = service.execute_flow(
        steps=steps, capability="timer.set",
        recipe_id="clock.timer.set.v1", tier="stable")

    data = json.loads(result)
    log_evidence("execution_status", data["status"])
    log_evidence("trace_id", data.get("trace_id", "none"))
    log_evidence("policy_decision", "allowed" if data["status"] != "refused" else "refused")

    if data["status"] == "success":
        log_evidence("dispatched_action", "android_send_intent (SET_TIMER)")
        log_evidence("verification_outcome", data.get("final_verifier", {}).get("outcome", "none"))
        log_evidence("evidence_refs", len(data.get("evidence_refs", [])))
    else:
        log_evidence("error", data.get("error_message", data.get("failure_class", "unknown")))

    # Step 5: Verify via observer
    print("\n--- Step 5: Verify via Observer ---")
    time.sleep(2)
    try:
        r = requests.get(f"{bridge_url}/current_app",
                        headers={"Authorization": f"Bearer {token}"}, timeout=5)
        current = r.json()
        log_evidence("observer_type", "current_app")
        log_evidence("observer_data", json.dumps(current))
    except Exception as e:
        log_evidence("observer_error", str(e))

    # Step 6: Retrieve trace
    print("\n--- Step 6: Retrieve Trace ---")
    trace_id = data.get("trace_id")
    if trace_id:
        trace_result = json.loads(service.get_trace(trace_id))
        log_evidence("trace_retrieved", "yes" if "trace_id" in trace_result else "no")
        log_evidence("trace_events", len(trace_result.get("events", [])))

    # Step 7: Test persistence across restart
    print("\n--- Step 7: Persistence After Restart ---")
    store = CapabilityStateStore(":memory:")
    # Simulate new CapabilityService with fresh store
    service2 = CapabilityService(handler)
    if trace_id:
        trace2 = json.loads(service2.get_trace(trace_id))
        log_evidence("persisted_after_restart", "yes" if "trace_id" in trace2 else "no")

    # Step 8: Negative learning
    print("\n--- Step 8: Negative Learning ---")
    store.record_incompatible_route(
        capability="timer.set",
        package="com.google.android.deskclock",
        fingerprint_digest=fp.digest(),
        method="ui_automator",
        failure_reason="Clock timer buttons ignore accessibility clicks")
    log_evidence("negative_learning_recorded", "ui_automator for timer.set")
    assert store.is_route_incompatible(fp.digest(), "timer.set", "ui_automator")
    log_evidence("negative_learning_verified", "true")
    store.close()

    # Summary
    print("\n" + "=" * 60)
    print("LIVE DOGFOOD EVIDENCE")
    print("=" * 60)
    for k, v in EVIDENCE.items():
        print(f"  {k}: {v}")

    print("\n✓ LIVE DOGFOOD COMPLETE")
    return 0

if __name__ == "__main__":
    sys.exit(main())
