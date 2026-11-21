package com.bugra.altyazi.phone

import android.graphics.Bitmap
import android.media.Image
import android.os.SystemClock
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Ekran karelerinden sadece altyazı bandını keser, değişim varsa yazıyı okur (OCR).
 * - Aynı altyazıyı iki kez görmeden göndermez (titreme ve yarım yazıyı önler).
 * - Altyazı kaybolunca TV'den silinmesi için haber verir.
 */
class FrameAnalyzer(
    private val onText: (String) -> Unit,
    private val onCleared: () -> Unit,
    private val onNotice: (String) -> Unit
) {
    companion object {
        private const val FRAME_INTERVAL_MS = 200L
        private const val PREVIEW_INTERVAL_MS = 1200L
        private const val SIG_W = 96
        private const val SIG_H = 12
    }

    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    private val ocrExecutor = Executors.newSingleThreadExecutor()
    private val busy = AtomicBoolean(false)

    @Volatile private var closed = false
    @Volatile private var candidate = ""
    private var shown = ""
    private var emptyStreak = 0

    private var lastFrameAt = 0L
    private var lastOcrAt = 0L
    private var lastPreviewAt = 0L
    private var lastSignature: IntArray? = null
    private var portraitNoticeAt = 0L
    private var blackSince = 0L
    private var blackNoticeAt = 0L
    private var frameBitmap: Bitmap? = null

    /** Görüntüyü her durumda kapatır. Yakalama thread'inde çağrılır. */
    fun onImage(image: Image) {
        try {
            process(image)
        } catch (e: Exception) {
            // tek bir bozuk kare akışı durdurmasın
        } finally {
            try { image.close() } catch (e: Exception) { }
        }
    }

    fun close() {
        closed = true
        try { recognizer.close() } catch (e: Exception) { }
        try { ocrExecutor.shutdown() } catch (e: Exception) { }
    }

    private fun process(image: Image) {
        if (closed) return
        val now = SystemClock.uptimeMillis()
        if (now - lastFrameAt < FRAME_INTERVAL_MS) return
        lastFrameAt = now

        val w = image.width
        val h = image.height
        if (h > w) {
            if (now - portraitNoticeAt > 6000) {
                portraitNoticeAt = now
                onNotice("PS Remote Play'i açıp telefonu yatay tutun")
            }
            return
        }

        val plane = image.planes[0]
        val rowStride = plane.rowStride
        val pixelStride = plane.pixelStride
        if (pixelStride <= 0) return
        val paddedW = rowStride / pixelStride

        val top = (h * Prefs.roiTop / 100).coerceIn(0, h - 8)
        val bottom = (h * Prefs.roiBottom / 100).coerceIn(top + 8, h)

        val buffer = plane.buffer.duplicate()
        var rows = bottom - top
        while (rows > 8 && top.toLong() * rowStride + rows.toLong() * rowStride > buffer.capacity()) rows--
        if (rows <= 8) return

        buffer.position(top * rowStride)
        buffer.limit(top * rowStride + rows * rowStride)

        val full = obtainBitmap(paddedW, rows)
        full.copyPixelsFromBuffer(buffer)

        val left = (w * 0.04f).toInt()
        val right = max(left + 16, (w * 0.96f).toInt()).coerceAtMost(w)
        val crop = Bitmap.createBitmap(full, left, 0, right - left, rows)

        // Değişim imzası (küçültülmüş parlaklık haritası)
        val small = Bitmap.createScaledBitmap(crop, SIG_W, SIG_H, true)
        val px = IntArray(SIG_W * SIG_H)
        small.getPixels(px, 0, SIG_W, 0, 0, SIG_W, SIG_H)
        small.recycle()
        var maxLum = 0
        val sig = IntArray(px.size)
        for (i in px.indices) {
            val c = px[i]
            val lum = (((c shr 16) and 0xFF) * 3 + ((c shr 8) and 0xFF) * 6 + (c and 0xFF)) / 10
            sig[i] = lum
            if (lum > maxLum) maxLum = lum
        }

        checkBlack(now, maxLum)
        maybePreview(now, crop)

        val prev = lastSignature
        var changed = prev == null
        if (prev != null) {
            var diff = 0
            for (i in sig.indices) if (abs(sig[i] - prev[i]) > 20) diff++
            changed = diff >= 3
        }
        lastSignature = sig

        val needOcr = changed || candidate.isNotEmpty() || (now - lastOcrAt > 2500)
        if (!needOcr || !busy.compareAndSet(false, true)) return
        lastOcrAt = now

        try {
            recognizer.process(InputImage.fromBitmap(crop, 0))
                .addOnSuccessListener(ocrExecutor) { result -> if (!closed) handleText(result) }
                .addOnCompleteListener(ocrExecutor) { busy.set(false) }
        } catch (e: Exception) {
            busy.set(false)
        }
    }

    private fun obtainBitmap(width: Int, height: Int): Bitmap {
        val b = frameBitmap
        if (b != null && !b.isRecycled && b.width == width && b.height == height) return b
        val nb = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        frameBitmap = nb
        return nb
    }

    private fun maybePreview(now: Long, crop: Bitmap) {
        if (now - lastPreviewAt < PREVIEW_INTERVAL_MS) return
        lastPreviewAt = now
        try {
            val scale = min(1f, 720f / crop.width)
            val pw = max(1, (crop.width * scale).toInt())
            val ph = max(1, (crop.height * scale).toInt())
            AppState.preview.value = Bitmap.createScaledBitmap(crop, pw, ph, true)
        } catch (e: Exception) { }
    }

    private fun checkBlack(now: Long, maxLum: Int) {
        if (maxLum > 6) {
            blackSince = 0
            return
        }
        if (blackSince == 0L) blackSince = now
        if (now - blackSince > 8000 && now - blackNoticeAt > 15000) {
            blackNoticeAt = now
            onNotice("Görüntü tamamen siyah: uygulama ekran yakalamayı engelliyor olabilir")
        }
    }

    private fun handleText(result: Text) {
        val lines = result.textBlocks
            .flatMap { it.lines }
            .sortedBy { it.boundingBox?.top ?: 0 }
            .map { it.text.trim() }
            .filter { TextTools.isDialogLine(it) }
        val joined = TextTools.clean(lines.joinToString(" "))

        if (joined.length < 3) {
            candidate = ""
            if (shown.isNotEmpty()) {
                emptyStreak++
                if (emptyStreak >= 2) {
                    shown = ""
                    emptyStreak = 0
                    onCleared()
                }
            }
            return
        }
        emptyStreak = 0

        val n = TextTools.normalize(joined)
        if (n.length < 3) return
        if (shown.isNotEmpty() && TextTools.similar(n, shown)) {
            candidate = ""
            return
        }
        val cand = candidate
        if (cand.isNotEmpty() && TextTools.similar(n, TextTools.normalize(cand))) {
            shown = n
            candidate = ""
            onText(joined)
        } else {
            candidate = joined
        }
    }
}
