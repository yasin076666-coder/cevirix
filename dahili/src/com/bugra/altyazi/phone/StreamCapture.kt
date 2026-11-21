package com.bugra.altyazi.phone

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.view.PixelCopy
import android.view.SurfaceView
import kotlin.math.max
import kotlin.math.min

/**
 * Dahili Remote Play: PS5 görüntüsünün gösterildiği yüzeyden altyazı şeridini
 * düzenli aralıklarla kopyalar (PixelCopy) ve Çevirix motoruna verir.
 * Ekran paylaşım izni gerekmez, başka uygulamanın engellemesi söz konusu değildir.
 */
class StreamCapture(private val activity: Activity, private val surfaceView: SurfaceView) {

    companion object {
        private const val INTERVAL_MS = 220L
        private const val MAX_WIDTH = 1800f
    }

    private val thread = HandlerThread("cevirix-pixelcopy").apply { start() }
    private val handler = Handler(thread.looper)
    private var ocr: SubtitleOcr? = null
    @Volatile private var running = false
    @Volatile private var inFlight = false
    @Volatile private var inFlightSince = 0L
    private var acquired = false

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            capture()
            handler.postDelayed(this, INTERVAL_MS)
        }
    }

    fun start() {
        Prefs.init(activity)
        if (!Prefs.streamTranslate || Build.VERSION.SDK_INT < 24) return
        CevirixEngine.acquire(activity, "Dahili Remote Play")
        acquired = true
        ocr = SubtitleOcr(
            onText = { CevirixEngine.onSubtitleText(it) },
            onCleared = { CevirixEngine.sendClear() },
            onNotice = { CevirixEngine.notice(it) }
        )
        running = true
        handler.postDelayed(tick, 1500)
    }

    fun stop() {
        running = false
        handler.removeCallbacksAndMessages(null)
        ocr?.close()
        ocr = null
        if (acquired) {
            acquired = false
            CevirixEngine.release()
        }
        try { thread.quitSafely() } catch (e: Exception) { }
    }

    private fun capture() {
        if (inFlight) {
            // Kopyalama yanıtı gelmediyse 2 sn sonra kilidi aç
            if (android.os.SystemClock.uptimeMillis() - inFlightSince < 2000) return
            inFlight = false
        }
        val w = surfaceView.width
        val h = surfaceView.height
        if (w < 32 || h < 32) return
        if (!surfaceView.holder.surface.isValid) return

        val top = (h * Prefs.roiTop / 100).coerceIn(0, h - 8)
        val bottom = (h * Prefs.roiBottom / 100).coerceIn(top + 8, h)
        val left = (w * 0.04f).toInt()
        val right = max(left + 16, (w * 0.96f).toInt()).coerceAtMost(w)
        val srcW = right - left
        val srcH = bottom - top
        val scale = min(1f, MAX_WIDTH / srcW)
        val dw = max(16, (srcW * scale).toInt())
        val dh = max(8, (srcH * scale).toInt())

        try {
            inFlight = true
            inFlightSince = android.os.SystemClock.uptimeMillis()
            if (Build.VERSION.SDK_INT >= 26) {
                val bmp = Bitmap.createBitmap(dw, dh, Bitmap.Config.ARGB_8888)
                PixelCopy.request(surfaceView, Rect(left, top, right, bottom), bmp, { result ->
                    inFlight = false
                    if (result == PixelCopy.SUCCESS && running) ocr?.submit(bmp)
                }, handler)
            } else {
                val full = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
                PixelCopy.request(surfaceView, full, { result ->
                    inFlight = false
                    if (result == PixelCopy.SUCCESS && running) {
                        val crop = Bitmap.createBitmap(full, left, top, srcW, srcH)
                        val scaled = if (scale < 1f) Bitmap.createScaledBitmap(crop, dw, dh, true) else crop
                        ocr?.submit(scaled)
                    }
                }, handler)
            }
        } catch (e: Exception) {
            inFlight = false
        } catch (e: OutOfMemoryError) {
            inFlight = false
        }
    }
}
