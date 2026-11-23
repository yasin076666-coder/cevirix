// Çevirix uyarlaması: Nino'nun SideReaders / MlKitTextReader / FrameSource parçaları (AGPL-3.0).
package com.bugra.altyazi.phone.gta

import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.ninotranslator.core.reading.live.FrameTrace
import com.ninotranslator.core.reading.live.LiveBox
import com.ninotranslator.core.reading.live.LiveClock
import com.ninotranslator.core.reading.live.LiveLine
import com.ninotranslator.core.reading.live.LiveRegion
import com.ninotranslator.core.reading.live.LumaPlane
import com.ninotranslator.core.reading.live.RgbImage
import com.ninotranslator.core.reading.live.ScreenRefresh
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Bir oyun karesi: Çevirix'in yakaladığı görüntünün pikselleri (ARGB). Yalnız [GtaReader.offer] çağrısı içinde
 * kullanılır; kopyalar ([copyRegion], [rgbSmall]) kalıcıdır.
 */
class VideoFrame(val pixels: IntArray, val width: Int, val height: Int) {

    /** Telefon bulma için küçük renkli görüntü (240x135, en yakın örnek). */
    fun rgbSmall(outW: Int = RgbImage.PHONE_W, outH: Int = RgbImage.PHONE_H): RgbImage {
        val out = RgbImage(outW, outH)
        for (oy in 0 until outH) {
            val y = ((oy + 0.5) * height / outH).toInt().coerceIn(0, height - 1)
            val row = y * width
            for (ox in 0 until outW) {
                val x = ((ox + 0.5) * width / outW).toInt().coerceIn(0, width - 1)
                out.pixels[oy * outW + ox] = pixels[row + x] and 0xFFFFFF
            }
        }
        return out
    }

    /** Karenin bir bölgesini gri düzlem olarak kopyalar (kutu kareye göre); çok küçükse null. Boyutlar çifttir. */
    fun copyRegion(r: LiveRegion): LumaPlane? {
        val rect = FrameTrace.crop(r.clamped(), width, height) ?: return null
        val w = rect.width and 1.inv()
        val h = rect.height and 1.inv()
        if (w < 16 || h < 16) return null
        val data = ByteArray(w * h)
        for (y in 0 until h) {
            val src = (rect.top + y) * width + rect.left
            val dst = y * w
            for (x in 0 until w) {
                val p = pixels[src + x]
                val l = (((p shr 16) and 0xFF) * 299 + ((p shr 8) and 0xFF) * 587 + (p and 0xFF) * 114) / 1000
                data[dst + x] = l.toByte()
            }
        }
        return LumaPlane(data, w, h, w)
    }
}

/** Yazı tanıma: gri kırpmadan satırlar (kutular kırpmaya göre, 0–1). */
fun interface TextReader {
    suspend fun read(image: LumaPlane): List<LiveLine>
}

/** ML Kit Latin modeli; girdi gri düzlem (renk düzlemleri 128). */
class MlKitTextReader : TextReader, AutoCloseable {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    override suspend fun read(image: LumaPlane): List<LiveLine> {
        val w = image.width
        val h = image.height
        if (w < 16 || h < 16 || w % 2 != 0 || h % 2 != 0) return emptyList()
        val size = w * h + w * h / 2
        val buf = ByteArray(size)
        for (y in 0 until h) System.arraycopy(image.data, y * image.rowStride, buf, y * w, w)
        java.util.Arrays.fill(buf, w * h, size, 128.toByte())
        val input = InputImage.fromByteArray(buf, w, h, 0, InputImage.IMAGE_FORMAT_NV21)
        val result = suspendCancellableCoroutine<com.google.mlkit.vision.text.Text> { cont ->
            recognizer.process(input)
                .addOnSuccessListener { cont.resume(it) }
                .addOnFailureListener { cont.resumeWithException(it) }
        }
        val out = ArrayList<LiveLine>()
        for (block in result.textBlocks) for (line in block.lines) {
            val text = line.text.trim()
            if (text.isEmpty()) continue
            val b = line.boundingBox
            val box = b?.let { LiveBox(it.left.toDouble() / w, it.top.toDouble() / h, it.right.toDouble() / w, it.bottom.toDouble() / h) }
            out += LiveLine(text, box)
        }
        return out.sortedBy { it.box?.top ?: Double.MAX_VALUE }
    }

    override fun close() = recognizer.close()
}

/** Tek okuyucu, sıralı kullanım (altyazıyı bekletmez). */
class SharedReader(private val reader: TextReader, private val timeoutMs: Long = 5_000) {
    private val lock = Mutex()

    suspend fun read(p: LumaPlane): List<LiveLine>? = lock.withLock {
        try {
            withTimeoutOrNull(timeoutMs) { reader.read(p) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            null
        }
    }
}

/** TV'ye ekran örtüsü gönderen taraf (Çevirix TV + Nino TV). */
interface ScreenOutput {
    fun screen(items: List<Map<String, Any?>>, durationMs: Int)
    fun screenClear()
}

/**
 * TV'deki `screen` kanalı: oyun içi telefon/harita katmanı. Katman 120 sn sürelidir; değişmese de 60 sn'de bir
 * yenilenir.
 */
class ScreenChannel(
    private val scope: CoroutineScope,
    private val clock: LiveClock,
    private val out: ScreenOutput,
) {
    private val refresh = ScreenRefresh()
    private var refresher: Job? = null

    @Synchronized fun setOverlay(items: List<Map<String, Any?>>) {
        run(refresh.set(items, clock.nowMs()))
    }

    @Synchronized fun tick() {
        run(refresh.tick(clock.nowMs()))
    }

    private fun run(a: ScreenRefresh.Action) {
        when (a) {
            ScreenRefresh.Action.None -> Unit
            ScreenRefresh.Action.Clear -> {
                runCatching { out.screenClear() }
                refresher?.cancel()
                refresher = null
            }
            is ScreenRefresh.Action.Send -> {
                runCatching { out.screen(a.items, a.durationMs) }
                if (refresher == null) refresher = scope.launch {
                    while (true) {
                        delay(1_000)
                        tick()
                    }
                }
            }
        }
    }

    fun close() {
        refresher?.cancel()
        refresher = null
    }
}
