package com.hermesandroid.bridge.tasker

import android.util.Base64
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * HMAC-SHA256 authentication for Tasker Gateway.
 *
 * Secret is provisioned on-device via [TaskerGatewayConfig].
 * Never stored in Git, logs, or Tasker exports.
 *
 * Canonical JSON: sorted keys, no whitespace, UTF-8 encoding.
 * The Kotlin canonical form MUST produce identical bytes to the Python
 * reference implementation in tools/verify/tasker_gateway_contract.py.
 */
object TaskerGatewayAuthenticator {

    private var secret: ByteArray? = null
    private val gson: Gson = GsonBuilder().disableHtmlEscaping().create()

    /**
     * Configure with Base64-encoded secret.
     */
    fun configure(base64Secret: String) {
        secret = Base64.decode(base64Secret, Base64.NO_WRAP)
    }

    /**
     * Configure with raw byte array (for testing).
     */
    fun configureRaw(rawSecret: ByteArray) {
        secret = rawSecret.clone()
    }

    /**
     * Produce canonical JSON bytes from a Kotlin object.
     * - Sorted keys (lexicographic)
     * - No whitespace
     * - UTF-8 encoding
     * - No HTML escaping
     */
    fun canonicalJson(obj: Any): ByteArray {
        val element = JsonParser.parseString(gson.toJson(obj))
        val sorted = sortJsonKeys(element)
        return sorted.toString().toByteArray(Charsets.UTF_8)
    }

    /**
     * Recursively sort all JSON object keys.
     */
    private fun sortJsonKeys(element: JsonElement): JsonElement {
        return when (element) {
            is JsonObject -> {
                val sorted = JsonObject()
                element.entrySet().sortedBy { it.key }.forEach { (k, v) ->
                    sorted.add(k, sortJsonKeys(v))
                }
                sorted
            }
            is JsonArray -> {
                val sorted = JsonArray()
                element.forEach { sorted.add(sortJsonKeys(it)) }
                sorted
            }
            else -> element
        }
    }

    /**
     * SHA-256 hash as lowercase hex string.
     */
    fun sha256(data: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return digest.digest(data).joinToString("") { "%02x".format(it) }
    }

    /**
     * HMAC-SHA256 sign, returned as Base64 (no wrapping).
     */
    fun sign(data: ByteArray): String {
        val key = secret ?: throw IllegalStateException("Secret not configured")
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return Base64.encodeToString(mac.doFinal(data), Base64.NO_WRAP)
    }

    /**
     * Verify HMAC-SHA256 signature.
     * Uses constant-time comparison to prevent timing attacks.
     */
    fun verify(data: ByteArray, signature: String): Boolean {
        val expected = sign(data)
        return constantTimeEquals(expected, signature)
    }

    /**
     * Constant-time string comparison.
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        return result == 0
    }
}
