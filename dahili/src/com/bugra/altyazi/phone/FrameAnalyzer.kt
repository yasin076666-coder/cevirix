package com.bugra.altyazi.phone

import android.graphics.Bitmap
import android.media.Image
import android.os.SystemClock
import kotlin.math.max

/** Ekran okuma modu: MediaProjection karelerinden altyazı şeridini keser ve SubtitleOcr'a verir. */
class FrameAnalyzer(
    onText: (String) -> Unit,
    onCleared: () -> Unit,
    private val onNotice: (String) -> Unit
) {
    companion object {
        private const val FRAME_INTERVAL_MS = 200L
    }

    private val ocr = SubtitleOcr("Ekran okuma", onText, onCleared, onNotice)
    @Volatile private var closed = false
    private var lastFrameAt = 0L
    private var portraitNoticeAt = 0L
    private var frameBitmap: Bitmap? = null

    fun onImage(image: Image) {
        try {
            process(image)
        } catch (e: Exception) {
        } finally {
            try { image.close() } catch (e: Exception) { }
        }
    }

    fun close() {
        closed = true
        ocr.close()
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
        val left = (w * Roi.LEFT).toInt()
        val right = max(left + 16, (w * Roi.RIGHT).toInt()).coerceAtMost(w)
        val crop = Bitmap.createBitmap(full, left, 0, right - left, rows)
        ocr.submit(crop)
    }

    private fun obtainBitmap(width: Int, height: Int): Bitmap {
        val b = frameBitmap
        if (b != null && !b.isRecycled && b.width == width && b.height == height) return b
        val nb = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        frameBitmap = nb
        return nb
    }
}
