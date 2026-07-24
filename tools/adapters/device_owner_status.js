/*
 * Device Owner Status Adapter — Tasker Rhino JavaScriptlet
 * 
 * Executed inside Tasker's own process via eval(source).
 * Uses org.json.JSONObject (NOT JSON.stringify — unavailable in Rhino).
 * 
 * Input: tasker.getVariable("par2") → envelope JSON
 * Output: writes JSON to /sdcard/Tasker/gateway/responses/<command_id>.json
 */

var envText = tasker.getVariable("par2");
var env = new org.json.JSONObject(envText);
var token = env.optString("token", "");
var expected = tasker.getVariable("gw_secret");
var cmdId = env.optString("command_id", "unknown");
var capName = env.optString("capability", "unknown");
var params = env.optJSONObject("params");
if (params == null) params = new org.json.JSONObject();

var obj = new org.json.JSONObject();
obj.put("command_id", cmdId);
obj.put("executor", "tasker_process");
obj.put("process_pid", android.os.Process.myPid());
obj.put("process_uid", android.os.Process.myUid());
obj.put("timestamp_ms", java.lang.System.currentTimeMillis());

if (!token.equals(expected)) {
    obj.put("ok", false);
    obj.put("error_code", "invalid_token");
    obj.put("error_message", "Token rejected");
} else if (!capName.equals("device_owner.status")) {
    obj.put("ok", false);
    obj.put("error_code", "unknown_capability");
    obj.put("error_message", "Unknown: " + capName);
} else {
    var dpm = context.getSystemService("device_policy");
    var pkg = "net.dinglisch.android.taskerm";
    var receiver = pkg + ".MyDeviceAdminReceiver";
    var admin = new android.content.ComponentName(context, receiver);

    obj.put("ok", true);
    obj.put("device_owner", dpm.isDeviceOwnerApp(pkg));
    obj.put("admin_active", dpm.isAdminActive(admin));
    obj.put("admin_component", admin.flattenToString());
    obj.put("device_model", android.os.Build.MODEL);
    obj.put("android_version", java.lang.System.getProperty("os.version"));
    obj.put("sdk_version", "" + android.os.Build.VERSION.SDK_INT);
}

var r = obj.toString();
var f = new java.io.File(
    "/sdcard/Tasker/gateway/responses/" + cmdId + ".json"
);
var fw = new java.io.FileWriter(f);
fw.write(r);
fw.close();
r;
