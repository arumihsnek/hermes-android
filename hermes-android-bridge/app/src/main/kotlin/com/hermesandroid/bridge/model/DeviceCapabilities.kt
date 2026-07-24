package com.hermesandroid.bridge.model

import android.content.Context
import android.content.pm.PackageManager

object DeviceCapabilities {

    var hasTelephony: Boolean = false
        private set

    var packageManager: PackageManager? = null
        private set

    fun init(context: Context) {
        hasTelephony = context.packageManager.hasSystemFeature(PackageManager.FEATURE_TELEPHONY)
        packageManager = context.packageManager
    }
}
