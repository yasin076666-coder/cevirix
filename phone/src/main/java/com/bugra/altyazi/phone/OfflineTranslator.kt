package com.bugra.altyazi.phone

import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.common.model.RemoteModelManager
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.TranslateRemoteModel
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/** Google ML Kit ile internetsiz İngilizce → Türkçe çeviri (yedek motor). */
object OfflineTranslator {

    enum class ModelState { UNKNOWN, MISSING, DOWNLOADING, READY, FAILED }

    val state = MutableStateFlow(ModelState.UNKNOWN)

    private val client by lazy {
        Translation.getClient(
            TranslatorOptions.Builder()
                .setSourceLanguage(TranslateLanguage.ENGLISH)
                .setTargetLanguage(TranslateLanguage.TURKISH)
                .build()
        )
    }

    fun checkDownloaded() {
        try {
            val model = TranslateRemoteModel.Builder(TranslateLanguage.TURKISH).build()
            RemoteModelManager.getInstance().isModelDownloaded(model)
                .addOnSuccessListener { ok ->
                    if (state.value != ModelState.DOWNLOADING) {
                        state.value = if (ok == true) ModelState.READY else ModelState.MISSING
                    }
                }
                .addOnFailureListener { state.value = ModelState.MISSING }
        } catch (e: Exception) {
            state.value = ModelState.MISSING
        }
    }

    fun download() {
        if (state.value == ModelState.DOWNLOADING || state.value == ModelState.READY) return
        state.value = ModelState.DOWNLOADING
        try {
            client.downloadModelIfNeeded(DownloadConditions.Builder().build())
                .addOnSuccessListener { state.value = ModelState.READY }
                .addOnFailureListener { state.value = ModelState.FAILED }
        } catch (e: Exception) {
            state.value = ModelState.FAILED
        }
    }

    suspend fun translate(text: String): String? = suspendCancellableCoroutine { cont ->
        try {
            client.translate(text)
                .addOnSuccessListener { if (cont.isActive) cont.resume(it) }
                .addOnFailureListener { if (cont.isActive) cont.resume(null) }
        } catch (e: Exception) {
            if (cont.isActive) cont.resume(null)
        }
    }
}
