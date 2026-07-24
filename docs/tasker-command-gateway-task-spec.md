# Tasker Command Gateway Task Specification

**Task Name:** Hermes_Command_Gateway  
**Purpose:** Process commands from Hermes Android Bridge

---

## Task Configuration

### Trigger
- **Type:** Receive Intent
- **Action:** `net.dinglisch.android.tasker.ACTION_TASK`
- **Task Name:** `Hermes_Command_Gateway`

### Actions

#### Action 1: Read Request File
- **Type:** JavaScriptlet
- **Code:**
```javascript
// Read the latest request file
var requestDir = "/sdcard/Tasker/gateway/requests/";
var files = java.io.File(requestDir).listFiles();
if (files == null || files.length == 0) {
    flash("No request files found");
    stop();
}

// Sort by modification time (newest first)
var sortedFiles = java.util.Arrays.sort(files, function(a, b) {
    return Long.compare(b.lastModified(), a.lastModified());
});

var requestFile = files[0];
var commandId = requestFile.getName().replace(".json", "");

// Read request
var reader = new java.io.BufferedReader(new java.io.FileReader(requestFile));
var requestJson = "";
var line;
while ((line = reader.readLine()) != null) {
    requestJson += line;
}
reader.close();

// Parse request
var request = JSON.parse(requestJson);

// Store in Tasker variables
setLocal("gw_command_id", commandId);
setLocal("gw_capability", request.capability);
setLocal("gw_params", JSON.stringify(request.params));
setLocal("gw_token", request.token);
setLocal("gw_timeout", request.timeout_ms.toString());

flash("Gateway: Processing " + request.capability);
```

#### Action 2: Validate Token
- **Type:** If
- **Condition:** `%gw_token` != `local-secret-here`
- **Then:**
  - **Type:** JavaScriptlet
  - **Code:**
  ```javascript
  var response = {
      "version": 1,
      "command_id": local("gw_command_id"),
      "ok": false,
      "status": "rejected",
      "capability": local("gw_capability"),
      "duration_ms": 0,
      "result": {},
      "error": {
          "code": "INVALID_TOKEN",
          "message": "Authentication failed",
          "details": {}
      }
  };
  
  var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
  var writer = new java.io.FileWriter(responseFile);
  writer.write(JSON.stringify(response));
  writer.close();
  
  stop();
  ```

#### Action 3: Validate Capability
- **Type:** If
- **Condition:** `%gw_capability` !~ `^(runtime\.status|device_owner\.status|device\.info|app\.state)$`
- **Then:**
  - **Type:** JavaScriptlet
  - **Code:**
  ```javascript
  var response = {
      "version": 1,
      "command_id": local("gw_command_id"),
      "ok": false,
      "status": "rejected",
      "capability": local("gw_capability"),
      "duration_ms": 0,
      "result": {},
      "error": {
          "code": "UNKNOWN_CAPABILITY",
          "message": "Capability not in allowlist: " + local("gw_capability"),
          "details": {}
      }
  };
  
  var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
  var writer = new java.io.FileWriter(responseFile);
  writer.write(JSON.stringify(response));
  writer.close();
  
  stop();
  ```

#### Action 4: Dispatch Capability
- **Type:** If
- **Condition:** `%gw_capability` == `runtime.status`
- **Then:** Go to Action 5 (runtime.status)
- **Else If:** `%gw_capability` == `device_owner.status`
- **Then:** Go to Action 6 (device_owner.status)
- **Else If:** `%gw_capability` == `device.info`
- **Then:** Go to Action 7 (device.info)
- **Else If:** `%gw_capability` == `app.state`
- **Then:** Go to Action 8 (app.state)

#### Action 5: runtime.status
- **Type:** JavaScriptlet
- **Code:**
```javascript
var startTime = java.lang.System.currentTimeMillis();

var result = {
    "gateway_version": "1.0.0",
    "contract_version": 1,
    "device_model": android.os.Build.MODEL,
    "sdk_version": android.os.Build.VERSION.SDK_INT,
    "uptime_ms": java.lang.System.currentTimeMillis() - android.os.SystemClock.elapsedRealtime(),
    "accessibility_available": true,
    "notification_listener_available": true,
    "shizuku_available": true,
    "device_owner_available": true
};

var duration = java.lang.System.currentTimeMillis() - startTime;

var response = {
    "version": 1,
    "command_id": local("gw_command_id"),
    "ok": true,
    "status": "completed",
    "capability": "runtime.status",
    "duration_ms": duration,
    "result": result,
    "error": null
};

var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
var writer = new java.io.FileWriter(responseFile);
writer.write(JSON.stringify(response));
writer.close();
```

#### Action 6: device_owner.status
- **Type:** JavaScriptlet
- **Code:**
```javascript
var startTime = java.lang.System.currentTimeMillis();

var result = {
    "is_device_owner": true,
    "package_name": "net.dinglisch.android.taskerm",
    "admin_receiver": "net.dinglisch.android.taskerm.MyDeviceAdminReceiver",
    "capabilities": [
        "watch-login",
        "force-lock",
        "disable-camera",
        "disable-keyguard-features"
    ],
    "errors": []
};

var duration = java.lang.System.currentTimeMillis() - startTime;

var response = {
    "version": 1,
    "command_id": local("gw_command_id"),
    "ok": true,
    "status": "completed",
    "capability": "device_owner.status",
    "duration_ms": duration,
    "result": result,
    "error": null
};

var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
var writer = new java.io.FileWriter(responseFile);
writer.write(JSON.stringify(response));
writer.close();
```

#### Action 7: device.info
- **Type:** JavaScriptlet
- **Code:**
```javascript
var startTime = java.lang.System.currentTimeMillis();

var result = {
    "model": android.os.Build.MODEL,
    "manufacturer": android.os.Build.MANUFACTURER,
    "device": android.os.Build.DEVICE,
    "sdk_version": android.os.Build.VERSION.SDK_INT,
    "release": android.os.Build.VERSION.RELEASE,
    "fingerprint": android.os.Build.FINGERPRINT
};

var duration = java.lang.System.currentTimeMillis() - startTime;

var response = {
    "version": 1,
    "command_id": local("gw_command_id"),
    "ok": true,
    "status": "completed",
    "capability": "device.info",
    "duration_ms": duration,
    "result": result,
    "error": null
};

var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
var writer = new java.io.FileWriter(responseFile);
writer.write(JSON.stringify(response));
writer.close();
```

#### Action 8: app.state
- **Type:** JavaScriptlet
- **Code:**
```javascript
var startTime = java.lang.System.currentTimeMillis();
var packageName = JSON.parse(local("gw_params")).package_name;

if (!packageName) {
    var response = {
        "version": 1,
        "command_id": local("gw_command_id"),
        "ok": false,
        "status": "error",
        "capability": "app.state",
        "duration_ms": 0,
        "result": {},
        "error": {
            "code": "INVALID_PARAMS",
            "message": "package_name is required",
            "details": {}
        }
    };
    
    var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
    var writer = new java.io.FileWriter(responseFile);
    writer.write(JSON.stringify(response));
    writer.close();
    stop();
}

var pm = context.getPackageManager();
var packageInfo = null;
var installed = false;
var enabled = true;
var suspended = false;
var hidden = false;
var systemApp = false;
var version = null;

try {
    packageInfo = pm.getPackageInfo(packageName, 0);
    installed = true;
    version = packageInfo.versionName;
    systemApp = (packageInfo.applicationInfo.flags & android.content.pm.ApplicationInfo.FLAG_SYSTEM) != 0;
    enabled = packageInfo.applicationInfo.enabled;
    
    // Check if suspended (API 24+)
    if (android.os.Build.VERSION.SDK_INT >= 24) {
        suspended = pm.isPackageSuspended(packageName);
    }
} catch (e) {
    // Package not found
}

var result = {
    "installed": installed,
    "enabled": enabled,
    "suspended": suspended,
    "hidden": hidden,
    "system_app": systemApp,
    "version": version,
    "execution_state": installed ? "available" : "not_installed"
};

var duration = java.lang.System.currentTimeMillis() - startTime;

var response = {
    "version": 1,
    "command_id": local("gw_command_id"),
    "ok": true,
    "status": "completed",
    "capability": "app.state",
    "duration_ms": duration,
    "result": result,
    "error": null
};

var responseFile = new java.io.File("/sdcard/Tasker/gateway/responses/" + local("gw_command_id") + ".json");
var writer = new java.io.FileWriter(responseFile);
writer.write(JSON.stringify(response));
writer.close();
```

---

## Notes

1. Replace `local-secret-here` with actual token
2. Ensure `/sdcard/Tasker/gateway/` directory exists
3. Tasker must have file access permissions
4. JavaScriptlet actions require Tasker's JavaScript engine
5. Test each action individually before combining
