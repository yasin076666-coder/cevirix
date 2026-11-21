package com.bugra.altyazi.phone

import android.graphics.Bitmap
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
 * Altyazı şeridi görüntülerini (Bitmap) alır, değişim varsa yazıyı okur.
 * Hem dahili Remote Play (PixelCopy) hem ekran okuma (MediaProjection) bunu kullanır.
 */
class SubtitleOcr(
    private val onText: (String) -> Unit,
    private val onCleared: () -> Unit,
    private val onNotice: (String) -> Unit
) {
    companion object {
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

    private var lastOcrAt = 0L
    private var lastPreviewAt = 0L
    @Volatile private var lastTextPreviewAt = 0L
    private var lastSignature: IntArray? = null
    private var blackSince = 0L
    private var blackNoticeAt = 0L
    private var frameCount = 0L
    private var ocrCount = 0L

    fun close() {
        closed = true
        try { recognizer.close() } catch (e: Exception) { }
        try { ocrExecutor.shutdown() } catch (e: Exception) { }
    }

    /** Altyazı şeridini işler. Çağıran thread'de imza hesaplanır, OCR arka planda yapılır. */
    fun submit(crop: Bitmap) {
        if (closed) return
        try {
            process(crop)
        } catch (e: Exception) {
            // tek bir bozuk kare akışı durdurmasın
        }
    }

    private fun process(crop: Bitmap) {
        val now = SystemClock.uptimeMillis()
        frameCount++
        if (frameCount % 5 == 0L) {
            val fc = frameCount
            AppState.update { it.copy(frames = fc) }
        }

        val small = Bitmap.createScaledBitmap(crop, SIG_W, SIG_H, true)
        val px = IntArray(SIG_W * SIG_H)
        small.getPixels(px, 0, SIG_W, 0, 0, SIG_W, SIG_H)
        if (small != crop) small.recycle()
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
        if (prev != null && prev.size == sig.size) {
            var diff = 0
            for (i in sig.indices) if (abs(sig[i] - prev[i]) > 20) diff++
            changed = diff >= 3
        }
        lastSignature = sig

        val needOcr = changed || candidate.isNotEmpty() || (now - lastOcrAt > 2500)
        if (!needOcr || !busy.compareAndSet(false, true)) return
        lastOcrAt = now

        // Küçük yazılar için büyüterek oku
        val ocrBitmap = try {
            if (crop.width < 1800) Bitmap.createScaledBitmap(crop, crop.width * 2, crop.height * 2, true) else crop
        } catch (e: OutOfMemoryError) {
            crop
        }

        try {
            recognizer.process(InputImage.fromBitmap(ocrBitmap, 0))
                .addOnSuccessListener(ocrExecutor) { result -> if (!closed) handleText(result, crop) }
                .addOnCompleteListener(ocrExecutor) { busy.set(false) }
        } catch (e: Exception) {
            busy.set(false)
        }
    }

    private fun setPreview(crop: Bitmap) {
        try {
            val scale = min(1f, 720f / crop.width)
            val pw = max(1, (crop.width * scale).toInt())
            val ph = max(1, (crop.height * scale).toInt())
            AppState.preview.value = Bitmap.createScaledBitmap(crop, pw, ph, true)
        } catch (e: Exception) { }
    }

    private fun maybePreview(now: Long, crop: Bitmap) {
        if (now - lastPreviewAt < PREVIEW_INTERVAL_MS) return
        if (now - lastTextPreviewAt < 6000) return
        lastPreviewAt = now
        setPreview(crop)
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

    private fun handleText(result: Text, crop: Bitmap) {
        ocrCount++
        val raw = result.text.replace('\n', ' ').trim()
        val oc = ocrCount
        AppState.update { it.copy(ocrRuns = oc, rawText = if (raw.isBlank()) it.rawText else raw.take(160)) }
        if (raw.isNotBlank()) {
            lastTextPreviewAt = SystemClock.uptimeMillis()
            setPreview(crop)
        }

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
