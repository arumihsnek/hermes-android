# TDD Plan: feature/android-terminal fixes

Basado en el Codex review NEEDS_CHANGES y análisis de código.

## Priorización

| # | Prioridad | Arreglo | Archivos | Riesgo si no se hace |
|---|-----------|---------|----------|---------------------|
| 1 | 🔴 CRÍTICO | Process destroy en timeout | TermuxExecutor.kt, ShizukuUserService.kt | Procesos huérfanos consumen recursos |
| 2 | 🔴 CRÍTICO | Thread leak en setup failure | TerminalExecutor.kt, ShizukuUserService.kt | Threads colgados en cada error |
| 3 | 🟡 ALTO | Input/output bounds | TerminalExecutor.kt, BridgeRouter.kt | Memory exhaustion |
| 4 | 🟡 ALTO | AIDL concurrency safety | ShizukuExecutor.kt | Race conditions |
| 5 | 🟢 MEDIO | Tests de integración | tests/ | Sin red de seguridad |

---

## Step 1: Process destroy en timeout (TermuxExecutor.kt)

### RED
**Archivo**: `tests/hermes-android-bridge/src/test/kotlin/com/hermesandroid/bridge/executor/TermuxExecutorTest.kt`

```kotlin
@Test
fun `timeout kills running process`() {
    // Arrange: lanzar comando que no termina (sleep 60)
    // Act: timeoutMs = 100ms
    val result = TermuxExecutor.exec("sleep 60", timeoutMs = 100)
    // Assert: exitCode = -1, timedOut = true, proceso no running
    assertFalse(isProcessRunning("sleep"))
}
```

### GREEN
**Archivo**: `TermuxExecutor.kt` — método `exec()`

Antes del `latch.await()`, guardar referencia al proceso (si el broadcast expone PID). Si timeout, ejecutar `Process.destroyForcibly()` en el proceso remoto via Termux API.

**Alternativa**: Si Termux no expone PID, enviar `kill` via segundo comando de cleanup.

```kotlin
if (!completed) {
    // Intentar cleanup del proceso remoto
    runCatching {
        val cleanup = Intent(ACTION_RUN_COMMAND).apply {
            component = ComponentName(TERMUX_PACKAGE, RUN_COMMAND_SERVICE)
            putExtra(EXTRA_PATH, BASH)
            putExtra(EXTRA_ARGUMENTS, arrayOf("-c", "pkill -f 'sleep 60' 2>/dev/null; true"))
        }
        appContext.startForegroundService(cleanup)
    }
}
```

---

## Step 2: Process destroy en timeout (ShizukuUserService.kt)

### RED
**Archivo**: `tests/.../ShizukuUserServiceTest.kt`

```kotlin
@Test
fun `shizuku timeout destroys process`() {
    val result = userService.exec("sleep 60", timeoutMs = 100)
    assertTrue(result.timedOut)
    assertFalse(isProcessRunning("sleep"))
}
```

### GREEN
**Archivo**: `ShizukuUserService.kt`

```kotlin
if (!finished) {
    process.destroyForcibly() // YA existe
    // Añadir: kill process group
    process.descendants().forEach { it.destroyForcibly() }
    process.waitFor(1, TimeUnit.SECONDS)
    pool.shutdownNow()
    return result(...)
}
```

---

## Step 3: Thread leak en setup failure (ShizukuUserService.kt)

### RED
```kotlin
@Test
fun `exception during process setup does not leak threads`() {
    val before = Thread.activeCount()
    repeat(100) {
        userService.exec("invalid_cmd_that_crashes || true", timeoutMs = 500)
    }
    val after = Thread.activeCount()
    assertTrue(after - before < 50) // Debe haber cleanup
}
```

### GREEN
**Archivo**: `ShizukuUserService.kt` — mover `pool.shutdownNow()` a bloque `finally`

```kotlin
override fun exec(command: String, timeoutMs: Long): String {
    val pool = Executors.newFixedThreadPool(2)
    return try {
        // ... proceso y futures ...
    } catch (e: Exception) {
        result(...)
    } finally {
        pool.shutdownNow()
    }
}
```

---

## Step 4: Thread leak en setup failure (TerminalExecutor.kt)

### RED
```kotlin
@Test
fun `process setup failure does not leak threads in app backend`() {
    val before = Thread.activeCount()
    repeat(100) {
        TerminalExecutor.exec("invalid_cmd", backend = "app")
    }
    val after = Thread.activeCount()
    assertTrue(after - before < 50)
}
```

### GREEN
**Archivo**: `TerminalExecutor.kt` — método `runProcess()`

Mover `pool.shutdownNow()` a bloque `finally`:

```kotlin
private fun runProcess(cmd: Array<String>, timeoutMs: Long, backend: String): ShellResult {
    val process = try { ProcessBuilder(*cmd).redirectErrorStream(false).start() } catch (e: Exception) { ... }
    val pool = Executors.newFixedThreadPool(2)
    return try {
        // futures y waitFor
    } catch (e: Exception) {
        ShellResult(...)
    } finally {
        pool.shutdownNow()
        if (::process.isInitialized && process.isAlive()) process.destroyForcibly()
    }
}
```

---

## Step 5: Input/output bounds (TerminalExecutor.kt + BridgeRouter.kt)

### RED
```kotlin
@Test
fun `commands longer than 4KB are rejected`() {
    val longCmd = "a".repeat(5000)
    val result = TerminalExecutor.exec(longCmd, backend = "app")
    assertEquals(-1, result.exitCode)
    assertTrue(result.stderr.contains("too long"))
}

@Test
fun `output longer than 1MB is truncated`() {
    val result = TerminalExecutor.exec("dd if=/dev/zero bs=1024 count=2048 2>/dev/null | base64", backend = "app")
    assertTrue(result.stdout.length <= 1_048_576)
}
```

### GREEN
**Archivos**: `TerminalExecutor.kt` + `BridgeRouter.kt`

```kotlin
// TerminalExecutor.kt
private const val MAX_COMMAND_LENGTH = 4096
private const val MAX_OUTPUT_SIZE = 1_048_576 // 1MB

fun exec(command: String, timeoutMs: Long = 10_000, backend: String = "auto"): ShellResult {
    if (command.length > MAX_COMMAND_LENGTH) {
        return ShellResult("", "Command too long (max $MAX_COMMAND_LENGTH chars)", -1, backend = "app")
    }
    // ... ejecutar y truncar output ...
}

// BridgeRouter.kt - añadir validación en endpoint /shell
post("/shell") {
    val req = call.receive<ShellRequest>()
    if (req.command.length > MAX_COMMAND_LENGTH) {
        call.respond(mapOf("success" to false, "error" to "Command too long"))
        return@post
    }
    // ...
}
```

---

## Step 6: AIDL concurrency safety (ShizukuExecutor.kt)

### RED
```kotlin
@Test
fun `concurrent shizuku execs do not race`() {
    val futures = (1..10).map { i ->
        thread { userService.exec("echo $i", 5000) }
    }
    val results = futures.map { it.join() }
    // Ningún resultado debe estar vacío o tener error de concurrencia
    results.forEach { assertTrue(it.exitCode == 0) }
}
```

### GREEN
**Archivo**: `ShizukuExecutor.kt`

- Eliminar `@Synchronized` del `ensureBound()` (el binding es lazy)
- En `exec()`, si el AIDL es single-thread, usar `runBlocking(Dispatchers.IO)` o cola de ejecución
- O añadir synchronized solo en `exec()` para serializar requests:

```kotlin
@Synchronized
fun exec(command: String, timeoutMs: Long): String {
    // ... llamada AIDL ...
}
```

---

## Step 7: Tests de integración

Crear suite de tests que cubra:

1. **Timeout cleanup** - comando que no termina, timeout, verificar que no queda running
2. **Concurrent exec** - 10 requests paralelos, todos deben completar
3. **Binder death** - matar servicio Shizuku, verificar que exec retorna error en vez de crashear
4. **Invalid backend** - backend desconocido debe fallar graciosamente
5. **Large output** - comando que produce >1MB output

```kotlin
@Test
fun `binder death returns error instead of crashing`() {
    // Simular muerte de binder
    userService.destroy()
    val result = userService.exec("echo ok", 1000)
    assertNotNull(result.stderr)
    assertTrue(result.exitCode == -1)
}

@Test
fun `unknown backend falls back to app`() {
    val result = TerminalExecutor.exec("echo ok", backend = "nonexistent")
    assertNotNull(result.stdout)
    assertEquals("ok", result.stdout.trim())
}
```

---

## Resumen de archivos a modificar

| Archivo | Steps |
|---------|-------|
| `TermuxExecutor.kt` | 1 |
| `ShizukuUserService.kt` | 2, 3 |
| `TerminalExecutor.kt` | 4, 5 |
| `ShizukuExecutor.kt` | 6 |
| `BridgeRouter.kt` | 5 |
| `tests/.../TermuxExecutorTest.kt` | 1, 7 |
| `tests/.../ShizukuUserServiceTest.kt` | 2, 3, 6, 7 |
| `tests/.../TerminalExecutorTest.kt` | 4, 5, 7 |

## Orden de ejecución

1. Step 1 (Termux timeout kill)
2. Step 2 (Shizuku timeout kill)
3. Step 3 (Shizuku thread leak)
4. Step 4 (Terminal thread leak)
5. Step 5 (I/O bounds)
6. Step 6 (AIDL concurrency)
7. Step 7 (Integration tests)
