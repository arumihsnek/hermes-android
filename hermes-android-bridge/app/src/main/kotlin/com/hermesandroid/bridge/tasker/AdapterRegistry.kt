package com.hermesandroid.bridge.tasker

/**
 * Static registry of allowed adapters.
 *
 * Only adapters registered here can be executed.
 * NO dynamic code loading, NO eval, NO file paths.
 * The request can ONLY select an adapter_id from this allowlist.
 */
object AdapterRegistry {

    data class AdapterEntry(
        val adapterId: String,
        val capability: String,
        val version: Int,
        val riskLevel: String,
        val timeoutMs: Long,
        val idempotent: Boolean,
        val paramSchema: Map<String, String> = emptyMap(),
        val implementationHash: String = ""
    )

    private val adapters = mutableMapOf<String, AdapterEntry>()

    init {
        // The sole capability for v1 — device_owner.status
        register(
            AdapterEntry(
                adapterId = "device_owner.status.v1",
                capability = "device_owner.status",
                version = 1,
                riskLevel = "LOW",
                timeoutMs = 5_000,
                idempotent = true,
                paramSchema = emptyMap(),
                implementationHash = "v1-initial"
            )
        )
    }

    fun register(entry: AdapterEntry) {
        adapters[entry.adapterId] = entry
    }

    fun lookup(adapterId: String): AdapterEntry? = adapters[adapterId]

    fun isAllowed(adapterId: String): Boolean = adapters.containsKey(adapterId)

    fun allowedIds(): Set<String> = adapters.keys.toSet()

    /**
     * Validate request adapter_id against the registry.
     * Returns null if valid, error code string if not.
     */
    fun validateAdapter(adapterId: String): String? {
        if (!isAllowed(adapterId)) return "UNKNOWN_ADAPTER"
        val entry = lookup(adapterId)!!
        if (entry.riskLevel !in listOf("LOW", "MEDIUM")) return "HIGH_RISK_ADAPTER"
        return null
    }
}
