#!/usr/bin/env python3
"""
Hermes Android Bridge - Tasker Gateway Integration
Client for testing the full flow.
"""

import json
import uuid
import time
import subprocess
from typing import Dict, Any, Optional

# Configuration
BRIDGE_URL = "http://100.64.0.1:8765"
BRIDGE_TOKEN = "REDACTED_BRIDGE_TOKEN_ROTATED"
GATEWAY_DIR = "/sdcard/Tasker/gateway"
REQUESTS_DIR = f"{GATEWAY_DIR}/requests"
RESPONSES_DIR = f"{GATEWAY_DIR}/responses"
TASKER_RECEIVER = "net.dinglisch.android.taskerm/.ReceiverStaticRunTasks"
TASK_NAME = "Hermes_Command_Gateway"
LOCAL_SECRET = "REDACTED_GW_TOKEN_ROTATED"


class HermesBridge:
    """Hermes Android Bridge client."""
    
    def __init__(
        self,
        bridge_url: str = BRIDGE_URL,
        bridge_token: str = BRIDGE_TOKEN,
        gateway_token: str = LOCAL_SECRET
    ):
        self.bridge_url = bridge_url
        self.bridge_token = bridge_token
        self.gateway_token = gateway_token
    
    def _shell(self, cmd: str, timeout: int = 10) -> Dict[str, Any]:
        """Execute shell command via Bridge."""
        payload = json.dumps({"command": cmd, "timeoutMs": timeout * 1000})
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{self.bridge_url}/shell",
             "-H", f"Authorization: Bearer {self.bridge_token}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return json.loads(result.stdout)
    
    def _write_file(self, remote_path: str, content: str) -> bool:
        """Write file to device via Bridge."""
        local_path = f"/tmp/hermes_{remote_path.split('/')[-1]}"
        with open(local_path, 'w') as f:
            f.write(content)
        
        result = subprocess.run(
            ["adb", "-s", "100.64.0.1:5555", "push", local_path, remote_path],
            capture_output=True, text=True
        )
        return result.returncode == 0
    
    def _read_file(self, remote_path: str) -> Optional[str]:
        """Read file from device via Bridge."""
        result = self._shell(f"cat {remote_path}")
        return result.get('stdout', None)
    
    def _delete_file(self, remote_path: str) -> bool:
        """Delete file from device via Bridge."""
        result = self._shell(f"rm -f {remote_path}")
        return result.get('exitCode', 1) == 0
    
    def _send_broadcast(self, task_name: str) -> bool:
        """Send broadcast to Tasker."""
        cmd = (
            f'am broadcast -a net.dinglisch.android.tasker.ACTION_TASK '
            f'--es task_name "{task_name}" '
            f'-n {TASKER_RECEIVER}'
        )
        result = self._shell(cmd)
        return 'result=0' in result.get('stdout', '')
    
    def execute_gateway_command(
        self,
        capability: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 10000
    ) -> Dict[str, Any]:
        """
        Execute a command via Tasker Gateway.
        
        Args:
            capability: Capability name
            params: Capability parameters
            timeout_ms: Maximum execution time
            
        Returns:
            Response dict
        """
        command_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Build request
        request = {
            "version": 1,
            "command_id": command_id,
            "capability": capability,
            "params": params or {},
            "timeout_ms": timeout_ms,
            "token": self.gateway_token
        }
        
        # Write request file
        request_path = f"{REQUESTS_DIR}/{command_id}.json"
        if not self._write_file(request_path, json.dumps(request)):
            return self._error_response(command_id, capability, "Failed to write request")
        
        # Send broadcast to trigger Tasker
        if not self._send_broadcast(TASK_NAME):
            self._delete_file(request_path)
            return self._error_response(command_id, capability, "Failed to send broadcast")
        
        # Wait for response
        response_path = f"{RESPONSES_DIR}/{command_id}.json"
        response = None
        
        while (time.time() - start_time) * 1000 < timeout_ms:
            time.sleep(0.1)  # Poll every 100ms
            
            response_content = self._read_file(response_path)
            if response_content:
                try:
                    response = json.loads(response_content)
                    break
                except json.JSONDecodeError:
                    continue
        
        # Cleanup
        self._delete_file(request_path)
        self._delete_file(response_path)
        
        if response is None:
            return self._timeout_response(command_id, capability, timeout_ms)
        
        return response
    
    def _error_response(
        self,
        command_id: str,
        capability: str,
        message: str
    ) -> Dict[str, Any]:
        """Build error response."""
        return {
            "version": 1,
            "command_id": command_id,
            "ok": False,
            "status": "error",
            "capability": capability,
            "duration_ms": 0,
            "result": {},
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
                "details": {}
            }
        }
    
    def _timeout_response(
        self,
        command_id: str,
        capability: str,
        timeout_ms: int
    ) -> Dict[str, Any]:
        """Build timeout response."""
        return {
            "version": 1,
            "command_id": command_id,
            "ok": False,
            "status": "timeout",
            "capability": capability,
            "duration_ms": timeout_ms,
            "result": {},
            "error": {
                "code": "TIMEOUT",
                "message": f"Execution exceeded {timeout_ms}ms",
                "details": {}
            }
        }


def main():
    """Test the Bridge integration."""
    bridge = HermesBridge()
    
    print("Hermes Android Bridge - Tasker Gateway Integration Test")
    print("=" * 60)
    print()
    
    # Test 1: runtime.status
    print("Test 1: runtime.status")
    result = bridge.execute_gateway_command("runtime.status")
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Gateway Version: {result['result'].get('gateway_version')}")
    print()
    
    # Test 2: device_owner.status
    print("Test 2: device_owner.status")
    result = bridge.execute_gateway_command("device_owner.status")
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Is Device Owner: {result['result'].get('is_device_owner')}")
    print()
    
    # Test 3: device.info
    print("Test 3: device.info")
    result = bridge.execute_gateway_command("device.info")
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Model: {result['result'].get('model')}")
    print()
    
    # Test 4: app.state (Tasker)
    print("Test 4: app.state (Tasker)")
    result = bridge.execute_gateway_command(
        "app.state",
        {"package_name": "net.dinglisch.android.taskerm"}
    )
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Installed: {result['result'].get('installed')}")
    print()
    
    # Test 5: app.state (Bridge)
    print("Test 5: app.state (Bridge)")
    result = bridge.execute_gateway_command(
        "app.state",
        {"package_name": "com.hermesandroid.bridge"}
    )
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Installed: {result['result'].get('installed')}")
    print()
    
    # Test 6: app.state (non-existent)
    print("Test 6: app.state (non-existent)")
    result = bridge.execute_gateway_command(
        "app.state",
        {"package_name": "com.nonexistent.app"}
    )
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Duration: {result.get('duration_ms')}ms")
    if result.get('ok'):
        print(f"  Installed: {result['result'].get('installed')}")
    print()
    
    # Test 7: Unknown capability
    print("Test 7: Unknown capability")
    result = bridge.execute_gateway_command("unknown.capability")
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Error Code: {result.get('error', {}).get('code')}")
    print()
    
    # Test 8: Invalid token
    print("Test 8: Invalid token")
    bridge_invalid = HermesBridge(gateway_token="invalid-token")
    result = bridge_invalid.execute_gateway_command("runtime.status")
    print(f"  OK: {result.get('ok')}")
    print(f"  Status: {result.get('status')}")
    print()
    
    print("All tests completed.")


if __name__ == "__main__":
    main()
