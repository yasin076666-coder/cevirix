package com.bugra.altyazi.phone

import android.content.Context
import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.atomic.AtomicLong

/**
 * Çeviri hattının tek merkezi: TV bağlantı sunucusu, çeviri ve seslendirme.
 * Dahili Remote Play ve ekran okuma modu aynı motoru paylaşır (aynı anda biri açık olsa da çakışmaz).
 */
object CevirixEngine {

    private var users = 0
    private var server: SubtitleServer? = null
    private var speaker: Speaker? = null
    private val translator = Translator().apply { onNotice = { notice(it) } }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val reqSeq = AtomicLong(0)
    private val emitLock = Any()
    private var lastEmitted = 0L

    val isRunning: Boolean
        get() = synchronized(this) { users > 0 }

    @Synchronized
    fun acquire(context: Context, source: String) {
        Prefs.init(context)
        users++
        if (users == 1) {
            val app = context.applicationContext
            server = SubtitleServer(app).apply {
                onClientsChanged = { n -> AppState.update { it.copy(tvClients = n) } }
                onNotice = { msg -> notice(msg) }
                start()
            }
            speaker = Speaker(app).apply { onNotice = { msg -> notice(msg) } }
            if (!Prefs.geminiEnabled || Prefs.geminiKey.isBlank()) OfflineTranslator.download()
        }
        AppState.update {
            it.copy(running = true, phoneIp = NetUtil.localIp(), message = "Çalışıyor ($source)")
        }
    }

    @Synchronized
    fun release() {
        if (users == 0) return
        users--
        if (users == 0) {
            server?.stop()
            speaker?.shutdown()
            server = null
            speaker = null
            AppState.update { it.copy(running = false, tvClients = 0, message = "Durduruldu") }
        }
    }

    fun notice(msg: String) {
        AppState.update { it.copy(message = msg) }
    }

    private var lastFinal = true

    /**
     * Yeni altyazı: önbellekte varsa anında; yoksa (açıksa) önce hızlı çevrimdışı çeviri gösterilir,
     * Gemini'nin sokak dili çevirisi gelince aynı satırın yerine geçer.
     */
    fun onSubtitleText(en: String) {
        val seq = reqSeq.incrementAndGet()
        val t0 = SystemClock.elapsedRealtime()
        scope.launch {
            translator.cached(en)?.let {
                emit(seq, en, it, "Önbellek", final = true, t0 = t0)
                return@launch
            }
            val useGemini = translator.geminiAvailable
            val fastJob = if (!useGemini || Prefs.instantTranslate) {
                launch {
                    val fast = runCatching { translator.offline(en) }.getOrNull()
                    if (fast != null) emit(seq, en, fast, "Hızlı", final = !useGemini, t0 = t0)
                }
            } else null

            if (useGemini) {
                val g = runCatching { translator.gemini(en) }.getOrNull()
                when {
                    g == null -> {
                        // Gemini kullanılamadı: hızlı çeviri yoksa şimdi yap
                        if (fastJob == null) {
                            val fast = runCatching { translator.offline(en) }.getOrNull()
                            if (fast != null) emit(seq, en, fast, "Çevrimdışı", final = true, t0 = t0)
                        } else {
                            fastJob.join()
                            finalizeFast(seq)
                        }
                    }
                    g.isBlank() -> {
                        // Diyalog değil: hızlı çeviri ekrana çıktıysa kaldır
                        fastJob?.cancel()
                        clearIfCurrent(seq)
                    }
                    else -> emit(seq, en, g, "Gemini", final = true, t0 = t0)
                }
            }
        }
    }

    private fun emit(seq: Long, en: String, tr: String, engine: String, final: Boolean, t0: Long) {
        synchronized(emitLock) {
            if (seq < lastEmitted) return // daha yeni bir satır gösteriliyor
            if (seq == lastEmitted && lastFinal) return // kesin çeviri zaten gösterildi
            lastEmitted = seq
            lastFinal = final
        }
        server?.sendSubtitle(tr, en, seq)
        if (final && Prefs.dubbing) speaker?.speak(tr)
        val ms = SystemClock.elapsedRealtime() - t0
        AppState.update {
            it.copy(lastEn = en, lastTr = tr, latencyMs = ms, engine = engine, lineCount = it.lineCount + 1)
        }
    }

    /** Gemini başarısız olduysa hızlı çeviriyi kesin say (seslendirme için). */
    private fun finalizeFast(seq: Long) {
        val speak: Boolean
        synchronized(emitLock) {
            speak = seq == lastEmitted && !lastFinal
            if (speak) lastFinal = true
        }
        if (speak && Prefs.dubbing) speaker?.speak(AppState.status.value.lastTr)
    }

    private fun clearIfCurrent(seq: Long) {
        val clear: Boolean
        synchronized(emitLock) { clear = seq == lastEmitted }
        if (clear) server?.sendClear()
    }

    fun sendClear() {
        server?.sendClear()
    }

    fun sendTest(): Boolean {
        val s = server ?: return false
        val tr = "Vice City'ye hoş geldin kanka! Her şey tıkırında."
        val en = "Welcome to Vice City, bro! Everything's running smooth."
        s.sendSubtitle(tr, en, reqSeq.incrementAndGet())
        if (Prefs.dubbing) speaker?.speak(tr)
        AppState.update { it.copy(lastEn = en, lastTr = tr, engine = "Test") }
        return true
    }

    fun pushStyle(): Boolean {
        val s = server ?: return false
        s.sendStyle(preview = true)
        return true
    }
}
