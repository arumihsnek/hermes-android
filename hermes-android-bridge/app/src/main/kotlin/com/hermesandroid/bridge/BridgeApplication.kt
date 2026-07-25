package com.hermesandroid.bridge

import android.app.Application
import com.hermesandroid.bridge.auth.PairingManager
import com.hermesandroid.bridge.client.RelayClient
import com.hermesandroid.bridge.model.DeviceCapabilities
import com.hermesandroid.bridge.power.WakeLockManager
import com.hermesandroid.bridge.server.BridgeServer
import com.hermesandroid.bridge.executor.TerminalExecutor

class BridgeApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        PairingManager.init(applicationContext)
        DeviceCapabilities.init(applicationContext)
        WakeLockManager.init(applicationContext)
        TerminalExecutor.init(applicationContext)
        com.hermesandroid.bridge.tasker.TaskerGatewayClient.init(applicationContext)

        // HTTP server is debug-only; production uses intent-driven relay
        if (BuildConfig.DEBUG) {
            BridgeServer.start(port = 8765)
        }

        // Relay is on-demand via Intent. Do NOT auto-connect here.
        RelayClient.init(applicationContext)
    }
}
