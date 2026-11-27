package com.bugra.altyazi.phone.gta

import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import com.bugra.altyazi.phone.CevirixEngine
import com.bugra.altyazi.phone.Prefs
import com.ninotranslator.core.reading.live.LiveBox
import com.ninotranslator.core.reading.live.LiveClock
import com.ninotranslator.core.translation.TargetLanguage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

/**
 * GTA 6 oyun içi telefon mesajları ve harita/görev kartı (Nino'nun okuma kuralları, AGPL-3.0).
 * Akış açıkken [offer] ile kareler gelir; çeviriler TV'ye `screen` örtüsü olarak gider.
 */
object GtaBridge {
    private val clock = LiveClock { SystemClock.elapsedRealtime() }
    @Volatile private var reader: GtaReader? = null
    private var scope: CoroutineScope? = null
    private var channel: ScreenChannel? = null
    private var ocr: MlKitTextReader? = null
    @Volatile var gtaSeen = false
        private set

    private var buf: IntArray? = null
    private var lastOffer = 0L

    @Synchronized
    fun start(context: Context) {
        if (reader != null || !Prefs.gtaExtras || !com.bugra.altyazi.phone.GameProfile.current.gtaPhone) return
        val sc = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val ml = MlKitTextReader()
        val ch = ScreenChannel(sc, clock, object : ScreenOutput {
            override fun screen(items: List<Map<String, Any?>>, durationMs: Int) = CevirixEngine.sendScreen(items, durationMs)
            override fun screenClear() = CevirixEngine.sendScreenClear()
        })
        reader = try {
            GtaReader(
                scope = sc,
                clock = clock,
                reader = SharedReader(ml),
                channel = ch,
                pool = null,
                target = TargetLanguage.TR,
                filesDir = context.filesDir,
                active = { Prefs.gtaExtras },
                poolFirst = { gtaSeen },
                blocked = { false },
                game = { if (gtaSeen) "gta-6" else null },
                sharePool = { false },
                deviceTranslate = { en -> CevirixEngine.translateLineFast(en) { better -> reader?.upgrade(en, better) } },
                onGta6Seen = { gtaSeen = true },
                onRulesChanged = {},
            )
        } catch (e: Throwable) {
            null
        }
        scope = sc
        channel = ch
        ocr = ml
    }

    @Synchronized
    fun stop() {
        runCatching { reader?.stop() }
        reader = null
        channel?.close()
        channel = null
        runCatching { ocr?.close() }
        ocr = null
        scope?.cancel()
        scope = null
        com.bugra.altyazi.phone.AppState.gtaStatus.value = ""
        buf = null
    }

    /** Akıştan bir kare (tam kare). Çağıran iş parçacığında kısa iş yapar, okuma arka planda sürer. */
    fun offer(bmp: Bitmap) {
        val r = reader ?: return
        val now = SystemClock.elapsedRealtime()
        if (now - lastOffer < GtaReader.LOCATE_MS) return
        lastOffer = now
        try {
            val w = bmp.width
            val h = bmp.height
            val b = buf?.takeIf { it.size == w * h } ?: IntArray(w * h).also { buf = it }
            bmp.getPixels(b, 0, w, 0, 0, w, h)
            r.offer(VideoFrame(b, w, h))
            val st = when {
                !Prefs.gtaExtras -> ""
                r.phoneVisible -> "Oyundaki telefon görüldü · ${r.panelCount} mesaj"
                r.mapState.mapOpen(clock.nowMs()) -> "Harita açık"
                else -> "Oyundaki telefon aranıyor"
            }
            if (com.bugra.altyazi.phone.AppState.gtaStatus.value != st) com.bugra.altyazi.phone.AppState.gtaStatus.value = st
        } catch (e: Throwable) {
        }
    }

    /** Altyazı satırı oyunun telefonundan / arayüzünden mi (atılsın mı)? [box] kareye göre 0–1. */
    fun dropLine(text: String, box: LiveBox?): Boolean =
        try { reader?.dropLine?.invoke(text, box) ?: false } catch (e: Throwable) { false }

    /** Kutu oyundaki telefonun içinde mi (GTA 6)? */
    fun insidePhone(box: LiveBox?): Boolean =
        try { box != null && (reader?.rules?.insidePhone(box, clock.nowMs()) ?: false) } catch (e: Throwable) { false }

    /** Harita açık: altyazı okunmasın. */
    fun subtitlesSuppressed(): Boolean = try { reader?.subtitlesSuppressed() ?: false } catch (e: Throwable) { false }
}
