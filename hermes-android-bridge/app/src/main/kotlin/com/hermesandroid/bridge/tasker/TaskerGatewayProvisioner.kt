package com.hermesandroid.bridge.tasker

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.util.Log
import com.google.gson.Gson
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout

/** Intent flag for API 34+ implicit broadcast export. */
private const val FLAG_RECEIVER_EXPORTED = 0x01000000

/**
 * Handles provisioning of the HMAC secret between Bridge and Tasker.
 *
 * Flow:
 * 1. Bridge generates secret + challenge (via TaskerGatewayConfig.startProvisioning)
 * 2. Bridge sends provisioning broadcast with secret + challenge
 * 3. Tasker stores secret, computes challenge_hmac, sends response broadcast
 * 4. Bridge verifies challenge_hmac via TaskerGatewayConfig.completeProvisioning
 *
 * Security:
 * - Provisioning window is temporal (5 minutes)
 * - One-shot: already-paired state blocks silent reprovisioning
 * - Challenge proves Tasker stores the correct secret
 * - secret_b64 is NEVER logged
 * - Requires explicit local action to trigger
 */
object TaskerGatewayProvisioner {

    private const val TAG = "TaskerGatewayProvisioner"
    private const val PROVISION_TIMEOUT_MS = 10_000L

    private var receiverRegistered = false
    private var pendingDeferred: CompletableDeferred<TaskerGatewayConfig.ProvisionResponse>? = null

    /**
     * Start provisioning: send secret + challenge to Tasker, await response.
     *
     * Must be called explicitly by local action (not automatic).
     * Returns null if already paired or provisioning fails.
     */
    suspend fun provision(context: Context): ProvisionResult {
        // 1. Generate provisioning request
        val request = TaskerGatewayConfig.startProvisioning(context)
            ?: return ProvisionResult(
                success = false,
                error = "Already provisioned or provisioning not possible"
            )

        // 2. Store challenge for later verification
        val prefs = context.getSharedPreferences("tasker_gateway_encrypted", Context.MODE_PRIVATE)
        prefs.edit().putString("pending_challenge", request.challenge).commit()

        // 3. Register response receiver
        val deferred = CompletableDeferred<TaskerGatewayConfig.ProvisionResponse>()
        pendingDeferred = deferred

        if (!receiverRegistered) {
            val filter = IntentFilter(TaskerGatewayConfig.ACTION_PROVISION_RESPONSE)
            context.registerReceiver(
                ProvisionResponseReceiver(),
                filter,
                Context.RECEIVER_NOT_EXPORTED
            )
            receiverRegistered = true
        }

        // 4. Send provisioning broadcast
        val gson = Gson()
        val provisionJson = gson.toJson(request)

        val intent = Intent(TaskerGatewayConfig.ACTION_PROVISION).apply {
            setPackage(TaskerGatewayConfig.taskerPackage)
            putExtra(TaskerGatewayConfig.EXTRA_PROVISION_JSON, provisionJson)
            addFlags(FLAG_RECEIVER_EXPORTED)
        }

        context.sendBroadcast(intent)
        Log.d(TAG, "Provisioning broadcast sent for pairing_id=${request.pairingId}")

        // 5. Await response with timeout
        return try {
            val response = withTimeout(PROVISION_TIMEOUT_MS) {
                deferred.await()
            }

            // 6. Verify challenge_hmac
            val verified = TaskerGatewayConfig.completeProvisioning(context, response)

            if (verified) {
                Log.d(TAG, "Provisioning complete and verified for pairing_id=${request.pairingId}")
                ProvisionResult(
                    success = true,
                    pairingId = request.pairingId,
                    verified = true
                )
            } else {
                Log.w(TAG, "Provisioning response received but verification failed")
                ProvisionResult(
                    success = false,
                    error = "Challenge HMAC verification failed — Tasker may have wrong secret"
                )
            }
        } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
            Log.e(TAG, "Provisioning timed out after ${PROVISION_TIMEOUT_MS}ms")
            ProvisionResult(
                success = false,
                error = "Tasker did not respond within ${PROVISION_TIMEOUT_MS}ms"
            )
        } catch (e: Exception) {
            Log.e(TAG, "Provisioning failed: ${e.message}", e)
            ProvisionResult(
                success = false,
                error = "Provisioning error: ${e.message}"
            )
        } finally {
            pendingDeferred = null
        }
    }

    /**
     * Rotate the secret and re-provision.
     */
    suspend fun rotateAndReprovision(context: Context): ProvisionResult {
        TaskerGatewayConfig.rotateSecret(context)
        return provision(context)
    }

    data class ProvisionResult(
        val success: Boolean,
        val pairingId: String? = null,
        val verified: Boolean = false,
        val error: String? = null
    )

    /**
     * Receiver for provisioning responses from Tasker.
     */
    class ProvisionResponseReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != TaskerGatewayConfig.ACTION_PROVISION_RESPONSE) {
                Log.w(TAG, "Unexpected action: ${intent.action}")
                return
            }

            val provisionJson = intent.getStringExtra(TaskerGatewayConfig.EXTRA_PROVISION_JSON)
            if (provisionJson == null) {
                Log.w(TAG, "No provision JSON in intent")
                return
            }

            try {
                val gson = Gson()
                val response = gson.fromJson(provisionJson, TaskerGatewayConfig.ProvisionResponse::class.java)
                pendingDeferred?.complete(response)
                Log.d(TAG, "Provisioning response received for pairing_id=${response.pairingId}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to parse provisioning response: ${e.message}", e)
                pendingDeferred?.completeExceptionally(e)
            }
        }
    }
}
