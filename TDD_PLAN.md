# TDD Plan: On-Demand Intent-Driven Hermes Bridge

## Fase 1 — RelayIntentReceiver (BroadcastReceiver)
### RED
- [ ] Comprobar que el receiver responde a `com.hermesandroid.bridge.START`
- [ ] Comprobar que extrae `server` extra del intent
- [ ] Comprobar que `STOP` para el servicio
- [ ] Comprobar que `STATUS` emite broadcast de respuesta

### GREEN
- [ ] Crear `RelayIntentReceiver.kt`
- [ ] Implementar `onReceive()` con dispatch por action
- [ ] Registrar en AndroidManifest.xml

## Fase 2 — RelayService (Foreground Service)
### RED
- [ ] Comprobar que arranca foreground con notificación
- [ ] Comprobar que conecta al relay server
- [ ] Comprobar idle timeout 5min → stop
- [ ] Comprobar que dispacha comandos a ActionExecutor

### GREEN
- [ ] Crear `RelayService.kt`
- [ ] Canal de notificación "bridge-relay"
- [ ] Timer idle
- [ ] Integrar RelayClient

## Fase 3 — RelayClient sin token + dispatch
### RED
- [ ] Comprobar que conecta sin token
- [ ] Comprobar que recibe JSON y dispacha a ActionExecutor
- [ ] Comprobar que envía resultado de vuelta

### GREEN
- [ ] Modificar `RelayClient.kt` — quitar token
- [ ] Añadir dispatch: cmd→ActionExecutor
- [ ] Añadir envío de resultados

## Fase 4 — HTTP server debug-only
### RED
- [ ] Comprobar que server NO arranca por defecto
- [ ] Comprobar que arranca con flag DEBUG

### GREEN
- [ ] Modificar `BridgeServer.kt`
- [ ] Añadir pref/flag enableHttpServer

## Fase 5 — MainActivity simplificada
### RED
- [ ] Comprobar que startup no requiere HTTP
- [ ] Comprobar que botones START/STOP funcionan

### GREEN
- [ ] Modificar `MainActivity.kt`

## Fase 6 — AndroidManifest final
### RED
- [ ] Comprobar receiver registrado
- [ ] Comprobar service registrado

### GREEN
- [ ] Modificar `AndroidManifest.xml`
