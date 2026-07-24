# Tasker Java Runtime - Summary Table

**Date:** 2026-07-24  
**Device:** Pixel 8 (Shiba) - Android 15  
**Tasker:** 6.7.6-beta (versionCode=5452)

---

## Comportamiento Observado vs Esperado

| # | Comportamiento | Observado | Esperado | Diferencia | Impacto Arquitectónico | Recomendación |
|---|---------------|-----------|----------|------------|----------------------|---------------|
| 1 | Persistencia de Java | Cada ejecución aislada | Variables estáticas persisten | Estado perdido entre ejecuciones | No se puede mantener estado Java | Usar variables Tasker |
| 2 | eval() | Solo en JavaScriptlet | Disponible en Java | No disponible en Java | Debe usar JavaScriptlet para eval | Usar JavaScriptlet para JS |
| 3 | source() | No estándar | Carga archivos externos | No disponible | No se pueden cargar archivos externos | Pre-configurar tareas |
| 4 | JSONObject | Disponible | Disponible | Ninguna | Manipulación JSON funciona | Usar para manejo de datos |
| 5 | HashMap | Disponible | Disponible | Ninguna | Colecciones funcionan | Usar para estructuras de datos |
| 6 | ArrayList | Disponible | Disponible | Ninguna | Listas funcionan | Usar para colecciones |
| 7 | APIs Android | Disponible | Disponible | Ninguna | Framework accesible | Usar para interacción con dispositivo |
| 8 | Acceso Shell | Disponible | Disponible | Ninguna | Comandos shell funcionan | Usar para comandos del sistema |
| 9 | Acceso Archivos | Disponible (más de lo esperado) | Restringido | Más acceso del esperado | Puede leer/escribir archivos | Usar para persistencia |
| 10 | Red | Disponible (más de lo esperado) | Restringido | Más acceso del esperado | Puede acceder a red | Usar para peticiones HTTP |
| 11 | Reflexión | Disponible | Restringido | Ninguna | Puede usar reflexión | Usar para código dinámico |
| 12 | Hilos | RxJava solamente | Java estándar | Modelo diferente | Debe usar patrones RxJava | Usar RxJava para async |
| 13 | Estado compartido | Vía archivos/variables | Vía Java | Mecanismo diferente | No se puede compartir estado Java | Usar variables Tasker |
| 14 | Rendimiento | Rápido (<100ms) | Lento | Mejor de lo esperado | Ejecución rápida | Adecuado para automatización |
| 15 | Seguridad | Disponible (más de lo esperado) | Restringido | Más acceso del esperado | Puede acceder a recursos del sistema | Usar con precaución |
| 16 | Tamaño script | ~10KB práctico | Ilimitado | Límite práctico | No se pueden scripts grandes | Dividir en tareas pequeñas |
| 17 | Variables Tasker | Persisten | Persisten | Ninguna | Estado persistente disponible | Mecanismo principal de estado |
| 18 | Concurrencia | RxJava | Hilos estándar | Modelo diferente | Operaciones asíncronas requieren RxJava | Usar patrones RxJava |
| 19 | Comunicación | Intents | Directo | Mecanismo diferente | Comunicación vía intents | Diseñar arquitectura basada en intents |
| 20 | Persistencia | Archivos en /sdcard/Tasker/ | Base de datos | Mecanismo diferente | Almacenamiento en archivos | Usar archivos para persistencia |

---

## Resumen de Hallazgos Críticos

### ✅ Lo que SÍ funciona:
1. **JSONObject** - Manipulación de JSON completa
2. **HashMap/ArrayList** - Colecciones Java estándar
3. **APIs Android** - Framework accesible (Context, Connectivity, etc.)
4. **Acceso Shell** - Comandos del sistema ejecutables
5. **Acceso a Archivos** - Lectura/escritura en /sdcard/
6. **Reflexión** - Acceso a clases vía Class.forName()
7. **RxJava** - Concurrencia asíncrona disponible
8. **Variables Tasker** - Estado persistente entre ejecuciones
9. **Intents** - Comunicación entre tareas y con Hermes
10. **Rendimiento** - Ejecución rápida (<100ms)

### ❌ Lo que NO funciona:
1. **Persistencia Java** - Cada ejecución crea nuevo contexto
2. **eval()** - Solo disponible en JavaScriptlet, no en Java Function
3. **source()** - No es una acción estándar de Tasker
4. **Hilos estándar** - Debe usar RxJava en su lugar
5. **Estado Java** - No se puede mantener entre ejecuciones
6. **Código dinámico** - No se puede cargar código externo
7. **Scripts grandes** - Límite práctico de ~10KB
8. **Compilación** - No hay javac/java en el dispositivo

### ⚠️ Limitaciones Importantes:
1. **Aislamiento** - Cada ejecución es independiente
2. **RxJava** - Modelo de concurrencia diferente al estándar
3. **Intents** - Comunicación vía intents, no directa
4. **Archivos** - Persistencia en archivos, no en memoria
5. **Permisos** - Requiere permisos de usuario para servicios

---

## Recomendación Arquitectónica

### Opción A: Tasker como runtime permanente ❌
**No recomendado** - Falta persistencia de estado, soporte limitado para código complejo.

### Opción B: Tasker únicamente como laboratorio ❌
**No recomendado** - Tasker tiene capacidades útiles que deben aprovecharse.

### Opción C: Tasker como backend especializado ✅ **RECOMENDADO**
**Recomendado** - Tasker excela en automatización del dispositivo. Usar para:
- Servicio de accesibilidad
- Gestión de notificaciones
- Control de apps
- Modificación de configuración del sistema

### Opción D: Tasker solo como herramienta de transición ⚠️
**Parcialmente recomendado** - Tasker tiene capacidades que no se pueden replicar fácilmente en Kotlin.

---

## Arquitectura Recomendada

```
┌─────────────────────────────────────────────────────────────┐
│                    Hermes Agent                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Business Logic & State Management                  │    │
│  │  - Lógica de negocio                                │    │
│  │  - Estado persistente                               │    │
│  │  - Toma de decisiones                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│                    Intent System                             │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Tasker Backend (Especializado)                     │    │
│  │  - Automatización del dispositivo                   │    │
│  │  - Acceso a APIs de Android                         │    │
│  │  - Control de UI                                    │    │
│  │  - Gestión de notificaciones                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│                    Device Actions                            │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Pixel 8 (Shiba)                                    │    │
│  │  - Servicios de accesibilidad                       │    │
│  │  - Configuración del sistema                        │    │
│  │  - Aplicaciones                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Patrón de Comunicación:
```
Hermes → Intent → Tasker → Acción del Dispositivo
Evento del Dispositivo → Tasker → Intent → Hermes
```

### Gestión de Estado:
```
Hermes: Lógica de negocio, estado, persistencia
Tasker: Acciones de automatización sin estado
Comunicación: Extras de intent, variables Tasker
```

---

## Conclusión

Tasker es un motor de automatización del dispositivo poderoso con capacidades
y limitaciones específicas. La evidencia experimental respalda usar Tasker
como backend especializado para capacidades específicas del dispositivo,
mientras se mantiene la lógica de negocio y la gestión de estado en Hermes.

**Veredicto Final:** Tasker es adecuado para su propósito (automatización)
pero NO como un runtime Java de propósito general.
