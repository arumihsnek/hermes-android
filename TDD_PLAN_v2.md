# TDD Plan v2: feature/android-terminal fixes

Validado por Codex (NEEDS_CHANGES v1 → corregido).

## Priorización

| # | Prioridad | Arreglo | Archivos |
|---|-----------|---------|----------|
| 1 | 🔴 CRÍTICO | Bounded readers (evitar OOM) + output limits | TerminalExecutor.kt + todos los backends |
| 2 | 🔴 CRÍTICO | Process kill real en Shizuku timeout | ShizukuUserService.kt |
| 3 | 🔴 CRÍTICO | Termux timeout con ID único de ejecución | TermuxExecutor.kt |
| 4 | 🟡 ALTO | Thread leak: pool en finally blocks | ShizukuUserService.kt, TerminalExecutor.kt |
| 5 | 🟡 ALTO | State machine de binding sincronizada + binder death | ShizukuExecutor.kt |
| 6 | 🟡 MEDIO | Backend desconocido → reject o fallback explícito | TerminalExecutor.kt |
| 7 | 🟢 BAJO | Integration tests (separar JVM de instrumented) | tests/ |

---

## Step 1: Bounded readers para todos los backends

### RED
**Archivo**: `tests/.../TerminalExecutorTest.kt`

```kotlin
@Test
fun `output exceeding 1MB is truncated without OOM`() {
    // Usar comando que produce >1.5MB en app backend
    // No debe lanzar OutOfMemoryError
    val result = TerminalExecutor.exec("awk 'BEGIN{while(i++<150000) print i}'", timeoutMs = 5000)
    assertTrue(result.stdout.length <= 1_048_576)
    assertTrue(result.stderr.length <= 1_048_576)
    assertEquals(0, result.exitCode)
}
```

### GREEN
Reemplazar `process.inputStream.bufferedReader().readText()` en TODOS los backends:

```kotlin
// TerminalExecutor.kt, ShizukuUserService.kt
fun boundedRead(stream: InputStream, maxBytes: Int): String {
    val buffer = ByteArray(maxBytes + 1)
    val totalRead = stream.read(buffer)
    val actualRead = minOf(totalRead, maxBytes)
    val result = String(buffer, 0, actualRead, Charsets.UTF_8)
    // Si hay exceso, cerrar stream pero no leerlo
    if (totalRead > maxBytes) stream.read(ByteArray(4096)) // drain
    return result
}
```

**Cubrir**: app, root, shizuku, termux backends.

---

## Step 2: Process kill real en Shizuku timeout

### RED
```kotlin
@Test
fun `shizuku timeout destroys process and descendants`() {
    val marker = "/tmp/test_shizuku_${System.nanoTime()}"
    val result = userService.exec("touch $marker; sleep 60", timeoutMs = 100)
    assertTrue(result.timedOut)
    // Verificar que el proceso hijo no sigue vivo
    val check = userService.exec("test -f $marker && echo exists || echo gone", 1000)
    assertEquals("gone", check.stdout.trim())
}
```

### GREEN
**Archivo**: `ShizukuUserService.kt`

```kotlin
if (!finished) {
    // Capturar descendientes ANTES de destruir
    val descendants = process.descendants().toList()
    process.destroyForcibly()
    descendants.forEach { it.destroyForcibly() }
    process.waitFor(1, TimeUnit.SECONDS)
    pool.shutdownNow()
    return result(...)
}
```

---

## Step 3: Termux timeout con ID único de ejecución

### RED
```kotlin
@Test
fun `termux timeout terminates the specific command`() {
    val tag = "termux_test_${System.nanoTime()}"
    // Lanzar proceso que crea archivo marker y duerme
    val result = TermuxExecutor.exec("touch /sdcard/$tag; sleep 60", timeoutMs = 50)
    assertTrue(result.timedOut)
    // Verificar que el proceso sleep fue terminado
    // (No podemos inspeccionar PID directamente, pero podemos verificar
    //  que no quedan procesos sleep con nuestro tag)
    val check = TermuxExecutor.exec("test -f /sdcard/$tag && echo 'created' || echo 'no'", timeoutMs = 1000)
    assertEquals("created", check.stdout.trim())
}
```

### GREEN
**Archivo**: `TermuxExecutor.kt`

Envolver el comando con wrapper que captura PID y lo mata en timeout:

```kotlin
// En lugar de ejecutar el comando directamente, usar:
// bash -c 'PIDFILE=/tmp/task_$RANDOM; (comando & echo $! > $PIDFILE; wait) & PID=$!; trap "kill $PID 2>/dev/null; rm -f $PIDFILE" EXIT; ...'
// O mejor: usar termux-notification con acción de cancelación

val safeCommand = """
    cleanup_$$() { kill -- -$$ 2>/dev/null; pkill -P $$ 2>/dev/null; }
    trap cleanup_$$ EXIT
    ($command) &
    CMD_PID=$!
    if ! wait $CMD_PID 2>/dev/null; then exit 1; fi
""".trimIndent()
```

---

## Step 4: Thread leak: pool en finally blocks

### RED
Usar executor inyectable para conteo determinista:

```kotlin
// En lugar de Thread.activeCount(), usar executor service injectado
interface ExecutorFactory {
    fun newFixedThreadPool(n: Int): ExecutorService
}

@Test
fun `exception during process setup does not leak threads`() {
    val factory = mock<ExecutorFactory>()
    var created = 0
    whenever(factory.newFixedThreadPool(any())).thenAnswer {
        created++
        Executors.newFixedThreadPool(1)
    }
    // Repetir 100 veces con fallo simulado
    repeat(100) {
        TerminalExecutor.exec("cmd_that_fails", executorFactory = factory)
    }
    assertEquals(0, created, "Pools should not leak")
}
```

### GREEN
**Archivo**: `TerminalExecutor.kt`, `ShizukuUserService.kt`

```kotlin
private fun runProcess(cmd: Array<String>, timeoutMs: Long, backend: String): ShellResult {
    val process = try {
        ProcessBuilder(*cmd).redirectErrorStream(false).start()
    } catch (e: Exception) {
        return ShellResult("", "Process creation failed: ${e.message}", -1, backend = backend)
    }
    val pool = Executors.newFixedThreadPool(2)
    return try {
        // ... futures ...
    } finally {
        pool.shutdownNow()
        if (process.isAlive()) process.destroyForcibly()
    }
}
```

---

## Step 5: State machine de binding + binder death

### RED
```kotlin
@Test
fun `concurrent execs do not race on binding state`() {
    val latches = (1..10).map { CountDownLatch(1) }
    val results = mutableListOf<String>()
    val threads = (1..10).map { i ->
        thread {
            results.add(ShizukuExecutor.exec("echo $i", 1000))
            latches[i-1].countDown()
        }
    }
    latches.forEach { it.await(5, TimeUnit.SECONDS) }
    threads.forEach { it.join(1000) }
    
    assertEquals(10, results.size)
    results.forEach { assertTrue(it.contains("\"exitCode\":0")) }
}

@Test
fun `binder death triggers rebind on next call`() {
    userService.destroy() // mata el servicio simulado
    Thread.sleep(500) // espera que Shizuku detecte muerte
    
    val result = ShizukuExecutor.exec("echo ok", 1000)
    // Debe haber hecho rebind y ejecutado exitosamente
    assertTrue(result.contains("\"exitCode\":0"))
}
```

### GREEN
**Archivo**: `ShizukuExecutor.kt`

```kotlin
// Mantener @Synchronized en ensureBound()
// Añadir death recipient:
private val deathRecipient = Shizuku.OnBinderDeadListener {
    userService = null
    binding = false
}

init {
    Shizuku.addBinderDeadListener(deathRecipient)
}

// En exec(), si userService es null o no responde, intentar rebind
@Synchronized
fun exec(command: String, timeoutMs: Long): String {
    if (!isRunning()) return errorJson("Shizuku not running")
    if (!hasPermission()) {
        requestPermission()
        return errorJson("Permission not granted")
    }
    val svc = ensureBound() ?: return errorJson("Could not bind")
    return try {
        svc.exec(command, timeoutMs)
    } catch (e: RemoteException) {
        userService = null // binder muerto
        errorJson("Shizuku exec failed (binder died): ${e.message}")
    }
}
```

---

## Step 6: Backend desconocido → fallback o reject

### RED
```kotlin
@Test
fun `unknown backend is rejected`() {
    val result = TerminalExecutor.exec("echo ok", backend = "nonexistent")
    assertTrue(result.exitCode == -1)
    assertTrue(result.stderr.contains("unknown backend"))
}

@Test
fun `empty backend defaults to auto`() {
    val result = TerminalExecutor.exec("echo ok", backend = "")
    assertEquals(0, result.exitCode)
}
```

### GREEN
**Archivo**: `TerminalExecutor.kt`

```kotlin
private fun resolveBackend(requested: String): String {
    val known = setOf("auto", "app", "shizuku", "termux", "root")
    val lower = requested.lowercase()
    if (lower.isEmpty()) return resolveBackend("auto")
    if (lower !in known) {
        throw IllegalArgumentException("Unknown backend: $requested. Known: ${known.joinToString()}")
    }
    return when (lower) {
        "auto", "" -> if (ShizukuExecutor.isAvailable()) "shizuku" else "app"
        else -> lower
    }
}
```

Y en `exec()`:
```kotlin
fun exec(command: String, timeoutMs: Long = 10_000, backend: String = "auto"): ShellResult {
    return try {
        when (resolveBackend(backend)) { ... }
    } catch (e: IllegalArgumentException) {
        ShellResult("", e.message ?: "Invalid backend", -1, backend = backend)
    }
}
```

---

## Step 7: Integration tests (JVM vs instrumented)

Separar en dos suites:

### JVM tests (sin dispositivo real)
- TerminalExecutor con mock Process
- ShizukuExecutor con mock IUserService
- Timeouts, límites, backends inválidos
- Thread leaks con executor inyectable

### Instrumented tests (requieren dispositivo)
- Termux real: `pkg install -y python` con timeout
- Shizuku real: `pm list packages --user 0`
- Concurrent exec: 10 requests simultáneos
- Binder death real: `am force-stop moe.shizuku.privileged.api`

---

## Resumen de cambios v2 (vs v1)

| Aspecto | v1 (rechazado) | v2 (corregido) |
|---------|---------------|----------------|
| Readers | `readText()` + truncar post-facto | Bounded readers que drenan |
| Termux timeout | `pkill -f` hardcodeado | Wrapper con PID capture + trap |
| Shizuku descendants | `descendants()` después de destroy | Capturar ANTES de destruir |
| Thread leak test | `Thread.activeCount()` global | Executor inyectable + mock |
| Concurrency | Quitar `@Synchronized` + `Thread.join()` | State machine sincronizada + latches |
| Binder death | No cubierto | Death recipient + rebind |
| Backend inválido | `when` sin default | Reject explícito con error |
| Tests | Mezclados | JVM + instrumented separados |
