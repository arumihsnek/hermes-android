// IUserService.aidl
package com.hermesandroid.bridge.shizuku;

interface IUserService {
    // Reserved transaction id Shizuku uses to tear the user service down.
    void destroy() = 16777114;

    // Execute `sh -c command` inside the Shizuku-spawned process (UID 2000 / shell).
    // Returns a JSON string: {"stdout":..,"stderr":..,"exitCode":..,"timedOut":..}.
    String exec(String command, long timeoutMs) = 1;
}
