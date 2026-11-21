package com.bugra.altyazi.phone

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import android.util.TypedValue
import android.view.Gravity
import android.view.PixelCopy
import android.view.SurfaceView
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import kotlin.math.max
import kotlin.math.min

/**
 * Dahili Remote Play: PS5 görüntüsünün gösterildiği yüzeyden altyazı şeridini
 * düzenli aralıklarla kopyalar (PixelCopy) ve Çevirix motoruna verir.
 * Oyun sırasında ekranın üstünde küçük bir canlı teşhis satırı gösterir.
 */
class StreamCapture(private val activity: Activity, private val surfaceView: SurfaceView) {

    companion object {
        private const val INTERVAL_MS = 200L
    }

    private val tickThread = HandlerThread("cevirix-tick").apply { start() }
    private val tickHandler = Handler(tickThread.looper)
    private val copyThread = HandlerThread("cevirix-pixelcopy").apply { start() }
    private val copyHandler = Handler(copyThread.looper)
    private val ui = Handler(Looper.getMainLooper())

    private var ocr: SubtitleOcr? = null
    @Volatile private var running = false
    @Volatile private var inFlight = false
    @Volatile private var inFlightSince = 0L
    private var acquired = false
    @Volatile private var copyOk = 0L
    @Volatile private var copyFail = 0L
    @Volatile private var lastErr = 0
    private var hud: TextView? = null

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            capture()
            tickHandler.postDelayed(this, INTERVAL_MS)
        }
    }

    private val hudUpdater = object : Runnable {
        override fun run() {
            if (!running) return
            renderHud()
            ui.postDelayed(this, 500)
        }
    }

    fun start() {
        Prefs.init(activity)
        if (!Prefs.streamTranslate || Build.VERSION.SDK_INT < 24) return

        // Eski ekran okuma modu açık kaldıysa kapat: iki mod aynı anda çalışmasın
        if (CaptureService.instance != null) {
            try {
                activity.startService(Intent(activity, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
            } catch (e: Exception) { }
        }

        CevirixEngine.acquire(activity, "Dahili Remote Play")
        acquired = true
        ocr = SubtitleOcr(
            source = "Dahili Remote Play",
            onText = { CevirixEngine.onSubtitleText(it) },
            onCleared = { CevirixEngine.sendClear() },
            onNotice = { CevirixEngine.notice(it) }
        )
        running = true
        AppState.update {
            it.copy(frames = 0, ocrRuns = 0, copyOk = 0, copyFail = 0, copyErr = 0, rawText = "", source = "Dahili Remote Play")
        }
        addHud()
        tickHandler.postDelayed(tick, 1500)
        ui.post(hudUpdater)
    }

    fun stop() {
        running = false
        tickHandler.removeCallbacksAndMessages(null)
        copyHandler.removeCallbacksAndMessages(null)
        ui.removeCallbacksAndMessages(null)
        ocr?.close()
        ocr = null
        if (acquired) {
            acquired = false
            CevirixEngine.release()
        }
        try { tickThread.quitSafely() } catch (e: Exception) { }
        try { copyThread.quitSafely() } catch (e: Exception) { }
    }

    private fun capture() {
        if (inFlight) {
            if (SystemClock.uptimeMillis() - inFlightSince < 2000) return
            // yanıt gelmedi: hata say ve devam et
            inFlight = false
            copyFail++
            lastErr = -2
            publishCopyStats()
        }
        val w = surfaceView.width
        val h = surfaceView.height
        if (w < 32 || h < 32) return
        if (!surfaceView.holder.surface.isValid) return

        // Tüm kareyi sabit boyutlu bir resme kopyala (video çözünürlüğünden bağımsız),
        // altyazı şeridini sonra kes. srcRect video tamponu koordinatı istediği için kullanılmıyor.
        val fw = min(1920, max(640, w))
        val fh = max(360, (fw.toLong() * h / w).toInt())
        val full = obtainFull(fw, fh)

        try {
            inFlight = true
            inFlightSince = SystemClock.uptimeMillis()
            PixelCopy.request(surfaceView, full, { result ->
                if (result == PixelCopy.SUCCESS) {
                    val crop = cropSubtitle(full)
                    onCopied(result, crop)
                } else {
                    onCopied(result, null)
                }
            }, copyHandler)
        } catch (e: Exception) {
            inFlight = false
            copyFail++
            lastErr = -1
            publishCopyStats()
        } catch (e: OutOfMemoryError) {
            inFlight = false
        }
    }

    private var fullBmp: Bitmap? = null

    private fun obtainFull(w: Int, h: Int): Bitmap {
        val b = fullBmp
        if (b != null && !b.isRecycled && b.width == w && b.height == h) return b
        val nb = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        fullBmp = nb
        return nb
    }

    private fun cropSubtitle(full: Bitmap): Bitmap? = try {
        val w = full.width
        val h = full.height
        val top = (h * Prefs.roiTop / 100).coerceIn(0, h - 8)
        val bottom = (h * Prefs.roiBottom / 100).coerceIn(top + 8, h)
        val left = (w * Roi.LEFT).toInt()
        val right = max(left + 16, (w * Roi.RIGHT).toInt()).coerceAtMost(w)
        Bitmap.createBitmap(full, left, top, right - left, bottom - top)
    } catch (e: Throwable) {
        null
    }

    private fun onCopied(result: Int, bmp: Bitmap?) {
        inFlight = false
        if (result == PixelCopy.SUCCESS && bmp != null) {
            copyOk++
            if (running) ocr?.submit(bmp)
        } else {
            copyFail++
            lastErr = result
        }
        if ((copyOk + copyFail) % 5 == 0L) publishCopyStats()
    }

    private fun publishCopyStats() {
        val ok = copyOk
        val fail = copyFail
        val err = lastErr
        AppState.update { it.copy(copyOk = ok, copyFail = fail, copyErr = err) }
    }

    // ---------------------------------------------------------------- canlı teşhis satırı

    private fun addHud() {
        ui.post {
            try {
                val tv = TextView(activity).apply {
                    setTextColor(Color.WHITE)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
                    setBackgroundColor(Color.argb(150, 0, 0, 0))
                    setPadding(16, 6, 16, 6)
                    maxLines = 3
                    isClickable = false
                    isFocusable = false
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }
                activity.addContentView(
                    tv,
                    FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                        Gravity.TOP or Gravity.CENTER_HORIZONTAL
                    )
                )
                hud = tv
            } catch (e: Exception) { }
        }
    }

    private fun renderHud() {
        val tv = hud ?: return
        val s = AppState.status.value
        val tvState = if (s.tvClients > 0) "TV ✓" else "TV ✗"
        val errText = if (s.copyFail > 0) " hata ${s.copyFail} (kod ${s.copyErr})" else ""
        val raw = s.rawText.take(60)
        val tr = s.lastTr.take(70)
        tv.text = "Çevirix · $tvState · kopya ${s.copyOk}$errText · okuma ${s.ocrRuns}\n" +
            "EN: ${raw.ifBlank { "—" }}\nTR: ${tr.ifBlank { "—" }}"
    }
}
