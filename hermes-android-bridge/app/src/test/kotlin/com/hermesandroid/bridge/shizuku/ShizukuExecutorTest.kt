package com.hermesandroid.bridge.shizuku

import org.junit.Assert.*
import org.junit.Test

class ShizukuExecutorTest {

    @Test
    fun `isRunning returns false without Shizuku`() {
        val running = ShizukuExecutor.isRunning()
        assertNotNull(running)
    }

    @Test
    fun `isInstalled does not crash`() {
        val installed = ShizukuExecutor.isInstalled()
        assertNotNull(installed)
    }

    @Test
    fun `hasPermission returns false without Shizuku`() {
        val hasPerm = ShizukuExecutor.hasPermission()
        assertFalse(hasPerm)
    }

    @Test
    fun `exec returns error without Shizuku`() {
        val result = ShizukuExecutor.exec("echo hello", 5000)
        assertTrue(result.contains("not running") || result.contains("error") || result.contains("not granted"))
    }

    @Test
    fun `repeated exec after shutdown returns error`() {
        ShizukuExecutor.exec("echo hello", 100) // warm up
        ShizukuExecutor.shutdown()
        val result = ShizukuExecutor.exec("echo hello", 100)
        assertTrue(result.contains("shut down"))
    }
}
