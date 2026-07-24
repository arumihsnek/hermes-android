#!/usr/bin/env python3
"""
Tasker Command Gateway Client
Sends commands to Tasker via file-based communication.
"""

import json
import uuid
import time
import os
import subprocess
from typing import Dict, Any, Optional

BRIDGE = "http://100.64.0.1:8765"
TOKEN = "REDACTED_BRIDGE_TOKEN_ROTATED"
GATEWAY_DIR = "/sdcard/Tasker/gateway"
REQUESTS_DIR = f"{GATEWAY_DIR}/requests"
RESPONSES_DIR = f"{GATEWAY_DIR}/responses"


class TaskerGatewayClient:
    """Client for Tasker Command Gateway."""
    
    def __init__(self, bridge_url: str = BRIDGE, token: str = TOKEN):
        self.bridge_url = bridge_url
        self.token = token
    
    def _shell(self, cmd: str, timeout: int = 10) -> Dict[str, Any]:
        """Execute shell command via Bridge."""
        payload = json.dumps({"command": cmd, "timeoutMs": timeout * 1000})
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{self.bridge_url}/shell",
             "-H", f"Authorization: Bearer {self.token}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 5
        )
        return json.loads(result.stdout)
    
    def _write_file(self, remote_path: str, content: str) -> bool:
        """Write file to device via Bridge."""
        # Write locally first
        local_path = f"/tmp/gateway_{os.path.basename(remote_path)}"
        with open(local_path, 'w') as f:
            f.write(content)
        
        # Push via ADB
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
            f'-n net.dinglisch.android.taskerm/.ReceiverStaticRunTasks'
        )
        result = self._shell(cmd)
        return 'result=0' in result.get('stdout', '')
    
    def execute(
        self,
        capability: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 10000,
        token: str = TOKEN
    ) -> Dict[str, Any]:
        """
        Execute a capability on Tasker.
        
        Args:
            capability: Capability name (e.g., "runtime.status")
            params: Capability parameters
            timeout_ms: Maximum execution time
            token: Authentication token
            
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
            "token": token
        }
        
        # Write request file
        request_path = f"{REQUESTS_DIR}/{command_id}.json"
        if not self._write_file(request_path, json.dumps(request)):
            return self._error_response(command_id, capability, "Failed to write request")
        
        # Send broadcast to trigger Tasker
        if not self._send_broadcast("Hermes_Command_Gateway"):
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
    """Test the gateway client."""
    client = TaskerGatewayClient()
    
    print("Testing Tasker Command Gateway Client...")
    print()
    
    # Test 1: runtime.status
    print("Test 1: runtime.status")
    result = client.execute("runtime.status")
    print(f"  Result: {json.dumps(result, indent=2)}")
    print()
    
    # Test 2: device_owner.status
    print("Test 2: device_owner.status")
    result = client.execute("device_owner.status")
    print(f"  Result: {json.dumps(result, indent=2)}")
    print()
    
    # Test 3: device.info
    print("Test 3: device.info")
    result = client.execute("device.info")
    print(f"  Result: {json.dumps(result, indent=2)}")
    print()
    
    # Test 4: app.state
    print("Test 4: app.state (Tasker)")
    result = client.execute("app.state", {"package_name": "net.dinglisch.android.taskerm"})
    print(f"  Result: {json.dumps(result, indent=2)}")
    print()
    
    print("All tests completed.")


if __name__ == "__main__":
    main()
