#!/bin/bash
# tasker-send-adapter.sh — Send adapter source + envelope to Tasker via am broadcast
#
# Usage:
#   ./tasker-send-adapter.sh <adapter_source_file> <envelope_json> [bridge_url] [bridge_token]
#
# This script:
# 1. Reads the adapter source code from a file
# 2. Base64-encodes and writes to device
# 3. Sends am broadcast with par1 (source) and par2 (envelope)

set -euo pipefail

ADAPTER_FILE="${1:?Usage: $0 <adapter_source> <envelope_json> [bridge_url] [bridge_token]}"
ENVELOPE="${2:?Missing envelope JSON}"
BRIDGE_URL="${3:-http://100.64.0.1:8765}"
BRIDGE_TOKEN="${4:-REDACTED_BRIDGE_TOKEN_ROTATED}"

# Bridge shell helper
bridge_shell() {
    curl -s --max-time 15 "${BRIDGE_URL}/shell" -X POST \
        -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"command\": \"$1\", \"timeoutMs\": 12000}"
}

# Base64 encode source
B64_SRC=$(base64 -w0 "$ADAPTER_FILE")
B64_ENV=$(echo -n "$ENVELOPE" | base64 -w0)

# Write to device
bridge_shell "echo \"${B64_SRC}\" | base64 -d > /sdcard/Tasker/gateway/sources/par1.txt"
bridge_shell "echo \"${B64_ENV}\" | base64 -d > /sdcard/Tasker/gateway/sources/par2.txt"

# Send broadcast
bridge_shell 'am broadcast -a com.hermes.tasker.HERMES_JAVA_RUNNER --es par1 "$(cat /sdcard/Tasker/gateway/sources/par1.txt)" --es par2 "$(cat /sdcard/Tasker/gateway/sources/par2.txt)" 2>&1'
