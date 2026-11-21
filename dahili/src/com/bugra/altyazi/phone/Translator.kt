package com.bugra.altyazi.phone

import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Çeviri yöneticisi. Üç parça:
 * - cached(): daha önce çevrilmiş satır (anında)
 * - offline(): sokak sözlüğü + telefon içi ML Kit çevirisi (~0,1 sn)
 * - gemini(): Gemini ile GTA sokak dili (0,5-1,5 sn)
 */
class Translator {

    private val cache = object : LinkedHashMap<String, String>(256, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, String>?): Boolean = size > 400
    }
    private val history = ArrayDeque<Pair<String, String>>()

    @Volatile private var failStreak = 0
    @Volatile private var pausedUntil = 0L
    @Volatile private var lastNoticeAt = 0L

    var onNotice: ((String) -> Unit)? = null

    fun cached(en: String): String? {
        val key = TextTools.normalize(en)
        return synchronized(cache) { cache[key] }
    }

    val geminiAvailable: Boolean
        get() = Prefs.geminiEnabled && Prefs.geminiKey.isNotBlank() && SystemClock.elapsedRealtime() >= pausedUntil

    /**
     * Çevrimdışı hızlı çeviri + sokak dili katmanı.
     * Sözlükteki kalıplar paket olmasa bile anında döner; diğerleri ML Kit ile çevrilip samimileştirilir.
     */
    suspend fun offline(en: String): String? {
        OfflineSlang.translateFromPhrasesOnly(en)?.let { return it }
        if (OfflineTranslator.state.value != OfflineTranslator.ModelState.READY) {
            OfflineTranslator.download()
            return null
        }
        return OfflineSlang.translate(en) { text ->
            OfflineTranslator.translate(text)?.takeIf { it.isNotBlank() }
        }?.takeIf { it.isNotBlank() }
    }

    /**
     * Gemini çevirisi. null: kullanılamadı/hata (yedek kullanılmalı).
     * Boş metin: Gemini bunun diyalog olmadığına karar verdi.
     */
    suspend fun gemini(en: String): String? {
        if (!geminiAvailable) return null
        val ctx = synchronized(history) { history.toList() }
        return try {
            val tr = withContext(Dispatchers.IO) {
                GeminiClient.translate(Prefs.geminiKey, Prefs.geminiModel, en, ctx)
            }
            failStreak = 0
            if (tr.isNotBlank()) remember(en, tr)
            tr
        } catch (e: Exception) {
            failStreak++
            handleError(e)
            null
        }
    }

    fun remember(en: String, tr: String) {
        val key = TextTools.normalize(en)
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
