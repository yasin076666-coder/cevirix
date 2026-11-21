package com.bugra.altyazi.phone

import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Çeviri yöneticisi: önce önbellek, sonra Gemini (sokak dili), sorun olursa
 * otomatik olarak çevrimdışı ML Kit çevirisine geçer.
 */
class Translator {

    data class Result(val tr: String, val engine: String)

    private val cache = object : LinkedHashMap<String, String>(256, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, String>?): Boolean = size > 400
    }
    private val history = ArrayDeque<Pair<String, String>>()

    @Volatile private var failStreak = 0
    @Volatile private var pausedUntil = 0L
    @Volatile private var lastNoticeAt = 0L

    var onNotice: ((String) -> Unit)? = null

    suspend fun translate(en: String): Result? {
        val key = TextTools.normalize(en)
        synchronized(cache) { cache[key] }?.let { return Result(it, "Önbellek") }

        val geminiReady = Prefs.geminiEnabled && Prefs.geminiKey.isNotBlank() &&
            SystemClock.elapsedRealtime() >= pausedUntil

        if (geminiReady) {
            val ctx = synchronized(history) { history.toList() }
            try {
                val tr = withContext(Dispatchers.IO) {
                    GeminiClient.translate(Prefs.geminiKey, Prefs.geminiModel, en, ctx)
                }
                failStreak = 0
                if (tr.isBlank()) return null // Gemini bunun diyalog olmadığına karar verdi
                remember(key, en, tr)
                return Result(tr, "Gemini")
            } catch (e: Exception) {
                failStreak++
                handleError(e)
            }
        }

        if (OfflineTranslator.state.value != OfflineTranslator.ModelState.READY) {
            OfflineTranslator.download()
            notice("Çevrimdışı Türkçe paketi indiriliyor…")
            return null
        }
        val tr = OfflineTranslator.translate(en) ?: return null
        if (tr.isBlank()) return null
        remember(key, en, tr)
        return Result(tr, "Çevrimdışı")
    }

    private fun remember(key: String, en: String, tr: String) {
        synchronized(cache) { cache[key] = tr }
        synchronized(history) {
            history.addLast(en to tr)
            while (history.size > 3) history.removeFirst()
        }
    }

    private fun handleError(e: Exception) {
        val now = SystemClock.elapsedRealtime()
        val msg = explain(e)
        when {
            e is GeminiClient.GeminiError && e.code == 429 -> pausedUntil = now + 60_000
            e is GeminiClient.GeminiError && isKeyProblem(e) -> pausedUntil = now + 30_000
            e is GeminiClient.GeminiError && e.code == 404 -> pausedUntil = now + 30_000
            failStreak >= 3 -> pausedUntil = now + 20_000
        }
        notice("$msg – çevrimdışı çeviri kullanılıyor")
    }

    private fun notice(msg: String) {
        val now = SystemClock.elapsedRealtime()
        if (now - lastNoticeAt < 3000) return
        lastNoticeAt = now
        onNotice?.invoke(msg)
    }

    companion object {
        private fun isKeyProblem(e: GeminiClient.GeminiError): Boolean =
            e.code == 401 || e.code == 403 || (e.message ?: "").contains("API key", ignoreCase = true)

        fun explain(e: Throwable): String = when {
            e is GeminiClient.GeminiError && e.code == 429 -> "Gemini kotası doldu"
            e is GeminiClient.GeminiError && isKeyProblem(e) -> "Gemini anahtarı geçersiz"
            e is GeminiClient.GeminiError && e.code == 404 -> "Model bulunamadı (${Prefs.geminiModel})"
            e is GeminiClient.GeminiError && e.code >= 500 -> "Gemini sunucusu yanıt vermedi"
            e is GeminiClient.GeminiError -> "Gemini hatası: ${e.message}"
            e is java.io.IOException -> "İnternet bağlantısı yok veya yavaş"
            else -> "Gemini hatası: ${e.message}"
        }
    }
}
