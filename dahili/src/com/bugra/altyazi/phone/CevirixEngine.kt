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

    fun onSubtitleText(en: String) {
        val seq = reqSeq.incrementAndGet()
        val t0 = SystemClock.elapsedRealtime()
        scope.launch {
            val res = runCatching { translator.translate(en) }.getOrNull() ?: return@launch
            if (res.tr.isBlank()) return@launch
            synchronized(emitLock) {
                if (seq <= lastEmitted) return@launch
                lastEmitted = seq
            }
            server?.sendSubtitle(res.tr, en, seq)
            if (Prefs.dubbing) speaker?.speak(res.tr)
            val ms = SystemClock.elapsedRealtime() - t0
            AppState.update {
                it.copy(lastEn = en, lastTr = res.tr, latencyMs = ms, engine = res.engine, lineCount = it.lineCount + 1)
            }
        }
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
