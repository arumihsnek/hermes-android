#!/system/bin/sh
GATEWAY_DIR="/sdcard/Tasker/gateway"
REQUESTS_DIR="$GATEWAY_DIR/requests"
RESPONSES_DIR="$GATEWAY_DIR/responses"
GW_TOKEN="uHNgVCmJfld_Kx8BfLEjVK5X7I2nF9Be6KidmM3yYc8"
LOG_FILE="$GATEWAY_DIR/gateway.log"
log() { echo "$(date "+%Y-%m-%d %H:%M:%S") [GW] $1" >> "$LOG_FILE"; }
log "=== started ==="
REQUEST_FILE=$(ls -t "$REQUESTS_DIR"/*.json 2>/dev/null | head -1)
if [ -z "$REQUEST_FILE" ]; then log "no request"; exit 0; fi
log "processing: $REQUEST_FILE"
REQUEST=$(cat "$REQUEST_FILE" 2>/dev/null)
if [ -z "$REQUEST" ]; then log "empty"; rm -f "$REQUEST_FILE"; exit 0; fi
COMMAND_ID=$(echo "$REQUEST" | sed -n 's/.*"command_id"[: ]*"\([^"]*\)".*/\1/p' | head -1)
CAPABILITY=$(echo "$REQUEST" | sed -n 's/.*"capability"[: ]*"\([^"]*\)".*/\1/p' | head -1)
REQ_TOKEN=$(echo "$REQUEST" | sed -n 's/.*"token"[: ]*"\([^"]*\)".*/\1/p' | head -1)
log "cmd=$COMMAND_ID cap=$CAPABILITY"
if [ "$REQ_TOKEN" != "$GW_TOKEN" ]; then
  log "AUTH_FAILED"
  echo "{\"version\":1,\"command_id\":\"$COMMAND_ID\",\"ok\":false,\"status\":\"error\",\"capability\":\"$CAPABILITY\",\"duration_ms\":0,\"result\":{},\"error\":{\"code\":\"AUTH_FAILED\",\"message\":\"Invalid token\",\"details\":{}}}" > "$RESPONSES_DIR/$COMMAND_ID.json"
  rm -f "$REQUEST_FILE"
  exit 0
fi
case "$CAPABILITY" in
  device_owner.status) ;;
  *)
    log "UNKNOWN: $CAPABILITY"
    echo "{\"version\":1,\"command_id\":\"$COMMAND_ID\",\"ok\":false,\"status\":\"error\",\"capability\":\"$CAPABILITY\",\"duration_ms\":0,\"result\":{},\"error\":{\"code\":\"UNKNOWN_CAPABILITY\",\"message\":\"Capability not in allowlist: $CAPABILITY\",\"details\":{}}}" > "$RESPONSES_DIR/$COMMAND_ID.json"
    rm -f "$REQUEST_FILE"
    exit 0
    ;;
esac
START_NS=$(date +%s%N 2>/dev/null || echo 0)
DO_PKG="net.dinglisch.android.taskerm"
DO_RCV="net.dinglisch.android.taskerm.MyDeviceAdminReceiver"
DO_RAW=$(dumpsys device_policy 2>/dev/null | grep "admin=ComponentInfo{$DO_PKG/$DO_RCV}" | head -1)
if [ -n "$DO_RAW" ]; then IS_DO="true"; DO_STATUS="active"; else IS_DO="false"; DO_STATUS="not_set"; fi
MODEL=$(getprop ro.product.model 2>/dev/null)
ANDROID_VER=$(getprop ro.build.version.release 2>/dev/null)
SDK=$(getprop ro.build.version.sdk 2>/dev/null)
END_NS=$(date +%s%N 2>/dev/null || echo 0)
if [ "$START_NS" != "0" ] && [ "$END_NS" != "0" ]; then DUR_MS=$(( (END_NS - START_NS) / 1000000 )); else DUR_MS=50; fi
log "RESULT: is_do=$IS_DO dur=${DUR_MS}ms"
echo "{\"version\":1,\"command_id\":\"$COMMAND_ID\",\"ok\":true,\"status\":\"completed\",\"capability\":\"$CAPABILITY\",\"duration_ms\":$DUR_MS,\"result\":{\"is_device_owner\":$IS_DO,\"package_name\":\"$DO_PKG\",\"admin_receiver\":\"$DO_RCV\",\"status\":\"$DO_STATUS\",\"device_model\":\"$MODEL\",\"android_version\":\"$ANDROID_VER\",\"sdk_version\":\"$SDK\"},\"error\":null}" > "$RESPONSES_DIR/$COMMAND_ID.json"
log "response written: $COMMAND_ID.json"
rm -f "$REQUEST_FILE"
log "request cleaned up"
