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
        // Terminal backends (app/root always; shizuku/termux when available on device)
        TerminalExecutor.init(applicationContext)
        BridgeServer.start(port = 8765)

        // Initialize relay client and auto-connect if previously configured
        RelayClient.init(applicationContext)
        RelayClient.autoConnect()
    }
}
