package com.bugra.altyazi.phone

import android.graphics.Bitmap
import android.os.SystemClock
import com.bugra.altyazi.phone.gta.GtaBridge
import com.bugra.altyazi.phone.gta.MlKitTextReader
import com.ninotranslator.core.reading.live.LiveBox
import com.ninotranslator.core.reading.live.LiveLine
import com.ninotranslator.core.reading.live.LumaPlane
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.min

/**
 * Menü, görev, yardım kutusu gibi ekrandaki yazıları okur; Türkçesini yazının yanında balonla gösterir.
 * Altyazı şeridi, oyunun sabit arayüz köşeleri (mini harita, mermi, para) ve oyun içi telefon atlanır.
 * Bir yazı iki taramada üst üste görülünce çevrilir (kamera dönerken titremesin).
 */
object ScreenTextReader {
    private const val SCAN_MS = 1300L
    private const val MAX_BLOCKS = 14
    private const val REFRESH_MS = 50_000L
    private const val SOURCE = "menu"

    private var scope: CoroutineScope? = null
    private var ocr: MlKitTextReader? = null
    @Volatile private var busy = false
    private var lastScan = 0L
    private var pixels: IntArray? = null

    private data class Block(val key: String, val en: String, val box: LiveBox, val lineH: Double)

    /** GTA V: telefon sağ altta dikey durur (iFruit / Badger / Facade). Bu sütundaki yazılar ayrı panelde çevrilir. */
    private val GTA5_PHONE = floatArrayOf(0.66f, 0.30f, 0.93f, 0.985f)
    private var phoneBlocks: List<Block> = emptyList()
    private var phoneSeenKey = ""
    private var phoneSeenCount = 0
    private var phoneMissing = 0

    private val seenCount = HashMap<String, Int>()
    private val shown = LinkedHashMap<String, Block>()
    private val missing = HashMap<String, Int>()
    private val cache = ConcurrentHashMap<String, String>()
    private val pending = ConcurrentHashMap.newKeySet<String>()
    private val slots = Semaphore(2)
    private var lastSig = ""
    @Volatile private var lastLineCount = 0
    private var lastSentAt = 0L

    @Synchronized
    fun start() {
        if (scope != null) return
        scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        ocr = MlKitTextReader()
    }

    @Synchronized
    fun stop() {
        scope?.cancel()
        scope = null
        runCatching { ocr?.close() }
        ocr = null
        busy = false
        synchronized(shown) {
            shown.clear()
            seenCount.clear()
            missing.clear()
        }
        lastSig = ""
        pixels = null
        AppState.menuStatus.value = ""
        CevirixEngine.setScreen(SOURCE, emptyList())
    }

    /** Akıştan tam kare (kısa iş; okuma arka planda). */
    fun offer(bmp: Bitmap) {
        if (!Prefs.menuBalloons) {
            if (shown.isNotEmpty()) { synchronized(shown) { shown.clear(); seenCount.clear() }; publish(force = true) }
            return
        }
        val sc = scope ?: return
        val reader = ocr ?: return
        val now = SystemClock.elapsedRealtime()
        val interval = if (phoneBlocks.isNotEmpty() || phoneSeenCount > 0) 800L else SCAN_MS
        if (busy || now - lastScan < interval) return
        lastScan = now
        val plane = try { lumaScaled(bmp) } catch (e: Throwable) { null } ?: return
        busy = true
        sc.launch {
            try {
                val lines = withTimeoutOrNull(4000) { reader.read(plane) } ?: return@launch
                process(lines)
            } catch (e: Throwable) {
            } finally {
                busy = false
            }
        }
    }

    /** Kareyi en çok 1280 genişlikte gri düzleme çevirir (çift boyut). */
    private fun lumaScaled(bmp: Bitmap): LumaPlane? {
        val sw = bmp.width
        val sh = bmp.height
        if (sw < 64 || sh < 64) return null
        val px = pixels?.takeIf { it.size == sw * sh } ?: IntArray(sw * sh).also { pixels = it }
        bmp.getPixels(px, 0, sw, 0, 0, sw, sh)
        val w = min(1280, sw) and 1.inv()
        val h = (w.toLong() * sh / sw).toInt() and 1.inv()
        val data = ByteArray(w * h)
        for (y in 0 until h) {
            val sy = (y.toLong() * sh / h).toInt()
            val row = sy * sw
            val dst = y * w
            for (x in 0 until w) {
                val p = px[row + (x.toLong() * sw / w).toInt()]
                data[dst + x] = ((((p shr 16) and 0xFF) * 299 + ((p shr 8) and 0xFF) * 587 + (p and 0xFF) * 114) / 1000).toByte()
            }
        }
        return LumaPlane(data, w, h, w)
    }

    // ---------------------------------------------------------------- süzme ve gruplama

    private fun inZone(b: LiveBox, z: FloatArray): Boolean {
        val cx = (b.left + b.right) / 2
        val cy = (b.top + b.bottom) / 2
        return cx >= z[0] && cx <= z[2] && cy >= z[1] && cy <= z[3]
    }

    private fun keep(l: LiveLine): Boolean {
        val b = l.box ?: return false
        val t = l.text.trim()
        if (t.count { it.isLetter() } < 3) return false
        val cy = (b.top + b.bottom) / 2
        val cx = (b.left + b.right) / 2
        // Altyazı şeridi (altyazıyı zaten çeviriyoruz)
        if (cy >= Prefs.roiTop / 100.0 - 0.01 && cy <= Prefs.roiBottom / 100.0 + 0.01 && cx in 0.12..0.88) return false
        val profile = GameProfile.current
        if (profile == GameProfile.GTA5 && inPhoneZone(b)) return false
        if (profile.hudZones.any { inZone(b, it) }) return false
        if (!TextTools.isDialogLine(t) || TextTools.isNoiseLine(t)) return false
        if (GtaBridge.insidePhone(b)) return false
        return true
    }

    private fun inPhoneZone(b: LiveBox): Boolean {
        val z = GTA5_PHONE
        val cx = (b.left + b.right) / 2
        val cy = (b.top + b.bottom) / 2
        return cx >= z[0] && cx <= z[2] && cy >= z[1] && cy <= z[3] && b.right <= 0.95
    }

    /** GTA V telefonu açıkken altyazı okuması telefon sütununu atlasın. */
    fun phoneHidesSubtitle(b: LiveBox?): Boolean {
        if (b == null || phoneBlocks.isEmpty() || GameProfile.current != GameProfile.GTA5) return false
        val left = phoneBlocks.minOf { it.box.left } - 0.02
        return (b.left + b.right) / 2 >= left
    }

    /** GTA V telefon satırları: yalnız telefon sütunu, sabit arayüz köşeleri dikkate alınmaz. */
    private fun keepPhone(l: LiveLine): Boolean {
        val b = l.box ?: return false
        val t = l.text.trim()
        if (!inPhoneZone(b)) return false
        if (t.count { it.isLetter() } < 2) return false
        if (b.right - b.left > 0.25) return false // telefon ekranından geniş olamaz
        return TextTools.isDialogLine(t) && !TextTools.isNoiseLine(t)
    }

    private fun normKey(s: String) = s.lowercase().filter { it.isLetterOrDigit() || it == ' ' }.replace(Regex("\\s+"), " ").trim()

    private fun group(lines: List<LiveLine>, filter: (LiveLine) -> Boolean = ::keep, limit: Int = MAX_BLOCKS, byArea: Boolean = true): List<Block> {
        val kept = lines.filter { filter(it) }.sortedBy { it.box!!.top }
        val out = ArrayList<Block>()
        var curText = StringBuilder()
        var cur: LiveBox? = null
        var hSum = 0.0
        var n = 0
        fun flush() {
            val c = cur ?: return
            val en = TextTools.clean(curText.toString())
            val key = normKey(en)
            if (key.length >= 3) out += Block(key, en, c, hSum / n)
            curText = StringBuilder(); cur = null; hSum = 0.0; n = 0
        }
        for (l in kept) {
            val b = l.box!!
            val h = b.bottom - b.top
            val c = cur
            if (c != null) {
                val lineH = hSum / n
                val gap = b.top - c.bottom
                val overlap = min(c.right, b.right) - max(c.left, b.left)
                val minW = min(c.right - c.left, b.right - b.left)
                val sameColumn = overlap > minW * 0.3 && kotlin.math.abs(b.left - c.left) < 0.06
                // Paragraf: alt alta, aynı sütunda, satır boyları yakın, önceki satır cümle bitirmemiş ya da açıklama kutusu
                if (gap < lineH * 0.9 && sameColumn && kotlin.math.abs(h - lineH) < lineH * 0.45) {
                    curText.append(' ').append(l.text.trim())
                    cur = LiveBox(min(c.left, b.left), c.top, max(c.right, b.right), b.bottom)
                    hSum += h; n++
                    continue
                }
                flush()
            }
            curText.append(l.text.trim()); cur = b; hSum = h; n = 1
        }
        flush()
        return if (byArea) out.sortedByDescending { (it.box.right - it.box.left) * (it.box.bottom - it.box.top) }.take(limit)
        else out.take(limit)
    }

    // ---------------------------------------------------------------- izleme, çeviri, yayın

    private fun process(lines: List<LiveLine>) {
        lastLineCount = lines.size
        val blocks = group(lines)
        val now = blocks.associateBy { it.key }
        synchronized(shown) {
            // Görülme sayıları
            val nextSeen = HashMap<String, Int>()
            for (k in now.keys) nextSeen[k] = (seenCount[k] ?: 0) + 1
            seenCount.clear(); seenCount.putAll(nextSeen)
            // Gösterilenleri güncelle / kaldır
            val it = shown.entries.iterator()
            while (it.hasNext()) {
                val e = it.next()
                val fresh = now[e.key]
                if (fresh != null) { e.setValue(fresh); missing.remove(e.key) }
                else {
                    val m = (missing[e.key] ?: 0) + 1
                    if (m >= 2) { it.remove(); missing.remove(e.key) } else missing[e.key] = m
                }
            }
            // İki taramadır görünenleri ekle
            for (b in blocks) if ((seenCount[b.key] ?: 0) >= 2 && b.key !in shown) shown[b.key] = b
        }
        if (GameProfile.current == GameProfile.GTA5) trackPhone(lines) else if (phoneBlocks.isNotEmpty()) phoneBlocks = emptyList()
        for (b in synchronized(shown) { shown.values.toList() }) ensureTranslated(b)
        for (b in phoneBlocks) ensureTranslated(b)
        publish()
    }

    /** GTA V telefonu: en az iki satır/mesaj görünce açık sayılır, iki tarama üst üste aynıysa gösterilir. */
    private fun trackPhone(lines: List<LiveLine>) {
        val blocks = group(lines, ::keepPhone, limit = 10, byArea = false)
        val lineCount = lines.count { keepPhone(it) }
        if (blocks.isEmpty() || lineCount < 2) {
            phoneMissing++
            if (phoneMissing >= 2) { phoneBlocks = emptyList(); phoneSeenKey = ""; phoneSeenCount = 0 }
            return
        }
        phoneMissing = 0
        val key = blocks.joinToString("|") { it.key }
        if (key == phoneSeenKey) phoneSeenCount++ else { phoneSeenKey = key; phoneSeenCount = 1 }
        // İçerik değişince (yeni mesaj) eski panel kalır, yenisi iki taramada oturur
        if (phoneSeenCount >= 2 || lineCount >= 3) phoneBlocks = blocks
    }

    /** Telefonun soluna ayrı panel: başlık + her mesaj ayrı balon. */
    private fun phonePanelItems(): List<Map<String, Any?>> {
        val blocks = phoneBlocks
        if (blocks.isEmpty()) return emptyList()
        val msgs = blocks.mapNotNull { b -> cache[b.key]?.takeIf { it.isNotBlank() }?.let { b to it } }
        if (msgs.isEmpty()) return emptyList()
        val phoneLeft = blocks.minOf { it.box.left }
        val phoneTop = blocks.minOf { it.box.top }
        val w = 0.27
        val right = (phoneLeft - 0.012).coerceAtLeast(w + 0.01)
        val left = right - w
        val line = 0.026
        val charW = 0.219 * line
        val perLine = max(8, ((w - 0.014) / charW).toInt())
        val items = ArrayList<Map<String, Any?>>()
        var top = (phoneTop - 0.05).coerceIn(0.03, 0.6)
        val headH = line * 1.35 + 0.008
        items += mapOf(
            "text" to "Telefon",
            "box" to mapOf("left" to left, "top" to top, "right" to right, "bottom" to top + headH),
            "line" to line, "fill" to "#FF3D9A", "ink" to "#FFFFFF", "alpha" to 0.95,
        )
        top += headH + 0.006
        for ((_, tr) in msgs) {
            val lines = ceil(tr.length / perLine.toDouble()).toInt().coerceIn(1, 6)
            val h = lines * line * 1.25 + 0.012
            if (top + h > 0.985) break
            items += mapOf(
                "text" to tr,
                "box" to mapOf("left" to left, "top" to top, "right" to right, "bottom" to top + h),
                "line" to line, "fill" to "#15233F", "ink" to "#FFFFFF", "alpha" to 0.94, "side" to true,
            )
            top += h + 0.006
        }
        return items
    }

    private fun ensureTranslated(b: Block) {
        if (cache.containsKey(b.key) || !pending.add(b.key)) return
        OfflineSlang.translateFromPhrasesOnly(b.en)?.let { cache[b.key] = it; pending.remove(b.key); return }
        val sc = scope ?: run { pending.remove(b.key); return }
        sc.launch {
            try {
                // Önce internetsiz çeviri anında, Gemini'ninki gelince değiştirilir
                val tr = slots.withPermit {
                    CevirixEngine.translateLineFast(b.en) { better ->
                        cache[b.key] = better.trim()
                        publish()
                    }
                }
                cache[b.key] = tr?.trim().orEmpty()
                publish()
            } finally {
                pending.remove(b.key)
            }
        }
    }

    @Synchronized
    private fun publish(force: Boolean = false) {
        val blocks = synchronized(shown) { shown.values.sortedBy { it.box.top } }
        val items = ArrayList<Map<String, Any?>>()
        val placed = ArrayList<DoubleArray>()
        for (b in blocks) {
            val tr = cache[b.key] ?: continue
            if (tr.isBlank() || normKey(tr) == b.key) continue // çevrilecek bir şey yok (ad, sayı)
            val box = balloonBox(b, tr, placed) ?: continue
            placed += box
            items += mapOf(
                "text" to tr,
                "box" to mapOf("left" to box[0], "top" to box[1], "right" to box[2], "bottom" to box[3]),
                "line" to b.lineH.coerceIn(0.018, 0.05),
                "fill" to "#0D1830",
                "ink" to "#FFFFFF",
                "alpha" to 0.92,
            )
        }
        items += phonePanelItems()
        val sig = items.joinToString("|") { "${it["text"]}@${(it["box"] as Map<*, *>).values.joinToString(",") { v -> "%.3f".format(v as Double) }}" }
        val nowMs = SystemClock.elapsedRealtime()
        if (!force && sig == lastSig && nowMs - lastSentAt < REFRESH_MS) return
        lastSig = sig
        lastSentAt = nowMs
        val st = "Ekran yazıları: $lastLineCount satır görüldü, ${items.size} balon"
        if (AppState.menuStatus.value != st) AppState.menuStatus.value = st
        CevirixEngine.setScreen(SOURCE, items)
    }

    /** Balon: yazının sağına, sığmazsa soluna, o da olmazsa altına; öncekilerle çakışırsa aşağı kaydır. */
    private fun balloonBox(b: Block, tr: String, placed: List<DoubleArray>): DoubleArray? {
        val line = b.lineH.coerceIn(0.018, 0.05)
        val origW = b.box.right - b.box.left
        val w = origW.coerceIn(0.14, 0.34)
        val charW = 0.219 * line
        val perLine = max(6, ((w - 0.012) / charW).toInt())
        val lines = ceil(tr.length / perLine.toDouble()).toInt().coerceIn(1, 8)
        val h = lines * line * 1.25 + 0.012
        val gap = 0.008
        var left: Double
        var top = b.box.top
        when {
            b.box.right + gap + w <= 0.99 -> left = b.box.right + gap
            b.box.left - gap - w >= 0.01 -> left = b.box.left - gap - w
            else -> { left = b.box.left.coerceIn(0.01, 0.99 - w); top = b.box.bottom + 0.005 }
        }
        for (p in placed) {
            val xOverlap = min(p[2], left + w) - max(p[0], left)
            val yOverlap = min(p[3], top + h) - max(p[1], top)
            if (xOverlap > 0 && yOverlap > 0) top = p[3] + 0.004
        }
        if (top + h > 0.995) top = 0.995 - h
        if (top < 0.005) return null
        return doubleArrayOf(left, top, left + w, top + h)
    }
}
